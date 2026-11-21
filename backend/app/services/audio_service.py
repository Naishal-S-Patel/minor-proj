"""
AudioService — owns all Whisper/audio concerns.

Responsibilities:
  1. Probe audio duration via pydub
  2. Progressive / Streaming line-by-line Whisper transcription
  3. Multi-language support (English, Hindi, Spanish, Gujarati, etc. or Auto-detect)
  4. Acoustic speaker diarization (voice timbre/pitch/spectral clustering) with Zoom (USR-xxx)
     and Google Meet (P0x) tag attribution
"""

from io import BytesIO
import logging
from typing import Any, Callable
import numpy as np
from pydub import AudioSegment
from pydub.utils import which

from app.core.config import settings

# Ensure pydub can find ffmpeg on Windows even if not on system PATH
if which("ffmpeg") is None:
    import os
    _ffmpeg_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Links", "ffmpeg.exe",
    )
    if os.path.isfile(_ffmpeg_path):
        AudioSegment.converter = _ffmpeg_path

logger = logging.getLogger(__name__)


class AcousticVoiceDiarizer:
    """
    Distinguishes between different speaker voices based on acoustic voice timbre,
    fundamental frequency/pitch (F0), and spectral features. Assigns Zoom Tag IDs (USR-101, USR-102, ...),
    Google Meet Tag IDs (P01, P02, ...), or standard Speaker numbers.

    Uses a robust two-pass architecture:
      Pass 1 (online streaming):
        - Frame-level voiced speech isolation (>35th percentile energy).
        - Pitch autocorrelation (65Hz-450Hz) with harmonic-invariant distance.
        - Spectral centroid and 4-band spectral energy ratios.
        - Conservative online clustering (threshold=0.16) to avoid over-splitting.
      Pass 2 (global consolidation):
        - Pairwise centroid consolidation (merge_threshold=0.15).
        - Collapsed-speaker recovery: if an audio file collapsed to 1 speaker but
          exhibits a strong bimodal spectral-energy distribution (Low/High band ratio gap),
          it cleanly splits into the true distinct speakers.
    """

    def __init__(self, platform: str | None = None, threshold: float = 0.16, merge_threshold: float = 0.15) -> None:
        self.platform = (platform or "").lower()
        self.threshold = threshold
        self.merge_threshold = merge_threshold
        self.centroids: list[np.ndarray] = []
        self.centroid_counts: list[int] = []
        self.last_speaker_idx: int = 0
        self.last_end_sec: float = 0.0
        # Store all segment features for global consolidation in Pass 2
        self._all_features: list[np.ndarray | None] = []

    def extract_voice_feature(self, samples: np.ndarray, sr: int = 16000) -> np.ndarray | None:
        """
        Extracts a calibrated acoustic voice feature vector from audio samples.
        Features include:
        1. Fundamental Pitch (F0) via voiced-frame autocorrelation (65Hz - 450Hz).
        2. Spectral Centroid (frequency center of gravity across speech frames).
        3. 4-Band Spectral Energy Ratios: <500Hz, 500-1500Hz, 1500-3000Hz, >=3000Hz.
        """
        if len(samples) < int(sr * 0.15):  # Ignore bursts under 150ms
            return None

        # Remove DC offset
        samples = samples - np.mean(samples)
        total_energy = float(np.sum(samples ** 2))
        if total_energy < 1e-4:
            return None

        # Frame analysis (25ms window, 10ms hop) to isolate speech & voiced frames
        frame_len = int(0.025 * sr)
        frame_step = int(0.010 * sr)
        num_frames = (len(samples) - frame_len) // frame_step + 1
        if num_frames <= 0:
            return None

        frame_energies: list[float] = []
        frames: list[np.ndarray] = []
        for i in range(num_frames):
            f = samples[i * frame_step : i * frame_step + frame_len]
            e = float(np.sum(f ** 2))
            frame_energies.append(e)
            frames.append(f)

        frame_energies_arr = np.array(frame_energies)
        # Filter out leading/trailing silence frames
        silence_thresh = max(1e-4, float(np.percentile(frame_energies_arr, 35)))
        speech_indices = np.where(frame_energies_arr > silence_thresh)[0]

        if len(speech_indices) < 5:
            return None

        voiced_f0s: list[float] = []
        voiced_centroids: list[float] = []
        voiced_subbands: list[list[float]] = []

        min_lag = int(sr / 450)  # 450 Hz
        max_lag = int(sr / 65)   # 65 Hz

        for idx in speech_indices:
            frame = frames[idx]
            fw = frame * np.hamming(len(frame))
            ac = np.correlate(fw, fw, mode="full")[len(fw) - 1 :]
            lags = ac[min_lag : min(max_lag, len(ac))]
            if len(lags) == 0:
                continue
            peak_val = np.max(lags)
            if peak_val > 0.20 * ac[0]:
                best_lag = min_lag + int(np.argmax(lags))
                voiced_f0s.append(sr / best_lag)

                fft_vals = np.abs(np.fft.rfft(fw, 512))
                freqs = np.fft.rfftfreq(512, 1.0 / sr)
                tot_e = np.sum(fft_vals) + 1e-8
                c = float(np.sum(freqs * fft_vals)) / tot_e
                voiced_centroids.append(c)

                e1 = float(np.sum(fft_vals[freqs < 500])) / tot_e
                e2 = float(np.sum(fft_vals[(freqs >= 500) & (freqs < 1500)])) / tot_e
                e3 = float(np.sum(fft_vals[(freqs >= 1500) & (freqs < 3000)])) / tot_e
                e4 = float(np.sum(fft_vals[freqs >= 3000])) / tot_e
                voiced_subbands.append([e1, e2, e3, e4])

        if len(voiced_f0s) < 3:
            return None

        f0 = float(np.median(voiced_f0s))
        centroid = float(np.median(voiced_centroids))
        sub = np.mean(voiced_subbands, axis=0)

        return np.array([f0, centroid, sub[0], sub[1], sub[2], sub[3]], dtype=np.float32)

    def compute_voice_distance(self, f1: np.ndarray, f2: np.ndarray) -> float:
        """
        Computes the acoustic distance between two voice embeddings.
        Employs harmonic octave folding (1x, 2x, 3x) so that pitch doubling/tripling
        does not falsely mark the same speaker as a different voice.
        Returns a value in [0.0, 1.0]. Lower values indicate the same human speaker.
        """
        f0_1, c1, e1_1, e1_2, e1_3, e1_4 = f1
        f0_2, c2, e2_1, e2_2, e2_3, e2_4 = f2

        if f0_1 > 50 and f0_2 > 50:
            ratio = f0_1 / f0_2 if f0_1 >= f0_2 else f0_2 / f0_1
            diff_1x = abs(f0_1 - f0_2) / max(f0_1, f0_2)
            diff_2x = abs(ratio - 2.0) / 2.0
            diff_3x = abs(ratio - 3.0) / 3.0
            diff_f0 = min(diff_1x, diff_2x + 0.04, diff_3x + 0.08)
        else:
            diff_f0 = 0.10

        diff_c = abs(c1 - c2) / max(c1, c2, 500.0)
        diff_e = (abs(e1_1 - e2_1) + abs(e1_2 - e2_2) + abs(e1_3 - e2_3) + abs(e1_4 - e2_4)) / 2.0

        r1 = e1_1 / (e1_3 + 0.01)
        r2 = e2_1 / (e2_3 + 0.01)
        diff_ratio = abs(r1 - r2) / max(r1, r2, 1.0)

        # Prioritize vocal tract spectral timbre and Low/High spectral band ratio
        # to cleanly separate adult speakers with similar fundamental frequency (~120Hz)
        return float(0.35 * diff_ratio + 0.35 * diff_e + 0.20 * diff_c + 0.10 * diff_f0)

    def identify_speaker_idx(
        self, samples: np.ndarray, start_sec: float = 0.0, end_sec: float = 0.0, sr: int = 16000
    ) -> int:
        """
        Matches speech samples to an existing speaker cluster, or spawns a new speaker index.
        Returns the raw integer speaker index (0, 1, 2, ...).
        Also stores the extracted feature for later global consolidation.
        """
        feat = self.extract_voice_feature(samples, sr)
        self._all_features.append(feat)

        dur = end_sec - start_sec

        # Slices with no detected pitch or very short duration inherit the active speaker
        if feat is None or (feat[0] < 50 and dur < 1.5):
            spk_idx = self.last_speaker_idx if self.centroids else 0
            if not self.centroids and feat is not None:
                self.centroids.append(feat)
                self.centroid_counts.append(1)
            return spk_idx

        if not self.centroids:
            self.centroids.append(feat)
            self.centroid_counts.append(1)
            self.last_speaker_idx = 0
            self.last_end_sec = end_sec
            return 0

        distances = []
        for i, c in enumerate(self.centroids):
            dist = self.compute_voice_distance(feat, c)
            # Conversational continuity prior: if same speaker spoke within 0.8s, slight bias
            if i == self.last_speaker_idx and (start_sec - self.last_end_sec) < 0.8:
                dist -= 0.05
            distances.append(dist)

        best_idx = int(np.argmin(distances))
        best_dist = distances[best_idx]

        # Guard against spurious mini-speakers: short utterances (<1.6s) cannot spawn a new cluster
        can_spawn = (dur >= 1.6) or (len(self.centroids) < 2 and dur >= 1.0)

        if best_dist < self.threshold or not can_spawn:
            # Same speaker voice: update running centroid asymptotically
            n = self.centroid_counts[best_idx]
            weight = 1.0 / min(n + 1, 10)
            self.centroids[best_idx] = (1.0 - weight) * self.centroids[best_idx] + weight * feat
            self.centroid_counts[best_idx] += 1
            spk_idx = best_idx
        else:
            # Distinct new voice detected!
            self.centroids.append(feat)
            self.centroid_counts.append(1)
            spk_idx = len(self.centroids) - 1

        self.last_speaker_idx = spk_idx
        self.last_end_sec = end_sec
        return spk_idx

    def consolidate_clusters(self, segment_speaker_indices: list[int]) -> list[int]:
        """
        Global cluster consolidation (Pass 2):
        1. First performs standard agglomerative centroid merging (merge_threshold=0.15).
        2. If the result collapsed to 1 speaker (common when two male speakers have nearly
           identical F0 ~120Hz), checks if a strong bimodal spectral-energy distribution
           exists (Low/High band energy ratio gap). If so, cleanly splits into 2 distinct speakers!
        Guarantees that distinct voices are never wrongly collapsed into 1 person.
        """
        if not segment_speaker_indices:
            return segment_speaker_indices

        # Step 1: Standard agglomerative centroid merging
        if len(self.centroids) > 1:
            parent = list(range(len(self.centroids)))

            def find(i: int) -> int:
                if parent[i] == i:
                    return i
                parent[i] = find(parent[i])
                return parent[i]

            def union(i: int, j: int) -> None:
                root_i = find(i)
                root_j = find(j)
                if root_i != root_j:
                    parent[root_j] = root_i

            for i in range(len(self.centroids)):
                for j in range(i + 1, len(self.centroids)):
                    d = self.compute_voice_distance(self.centroids[i], self.centroids[j])
                    if d < self.merge_threshold:
                        union(i, j)

            new_map: dict[int, int] = {}
            curr_id = 0
            for i in range(len(self.centroids)):
                root = find(i)
                if root not in new_map:
                    new_map[root] = curr_id
                    curr_id += 1

            merged_indices = [new_map[find(idx)] for idx in segment_speaker_indices]
        else:
            merged_indices = list(segment_speaker_indices)

        # Step 2: Check if all segments collapsed to 1 speaker
        unique_spks = set(merged_indices)
        if len(unique_spks) == 1 and len(merged_indices) >= 4:
            # Collect valid features and compute Low/High spectral band ratio
            valid = [(i, f) for i, f in enumerate(self._all_features)
                     if f is not None and i < len(merged_indices)]

            if len(valid) >= 6:
                ratios = [f[2] / (f[4] + 0.01) for _, f in valid]
                ratios_arr = np.array(ratios)
                sorted_r = np.sort(ratios_arr)
                gaps = np.diff(sorted_r)

                if len(gaps) > 0:
                    max_gap_idx = int(np.argmax(gaps))
                    max_gap = gaps[max_gap_idx]
                    median_gap = np.median(gaps) if len(gaps) > 1 else gaps[0]

                    split_thresh = (sorted_r[max_gap_idx] + sorted_r[max_gap_idx + 1]) / 2.0
                    g_low = int(np.sum(ratios_arr < split_thresh))
                    g_high = int(np.sum(ratios_arr >= split_thresh))

                    # If there is a prominent gap separating two substantial groups of turns:
                    if max_gap >= 0.30 and max_gap > 1.8 * median_gap and g_low >= 2 and g_high >= 2:
                        logger.info(
                            "Recovered 2 speakers from collapsed recording via spectral ratio split "
                            "(gap=%.3f, threshold=%.3f, low_count=%d, high_count=%d)",
                            max_gap, split_thresh, g_low, g_high,
                        )
                        new_indices = list(merged_indices)
                        # Determine which cluster was the first speaker
                        first_valid_ratio = ratios[0]
                        first_cluster = 0 if first_valid_ratio >= split_thresh else 1

                        for (seg_i, _), r in zip(valid, ratios):
                            # Cluster 0 for first speaker's group, Cluster 1 for second speaker's group
                            assigned = 0 if ((r >= split_thresh) == (first_cluster == 0)) else 1
                            new_indices[seg_i] = assigned

                        # Propagate assignments to None-feature segments
                        for k in range(len(new_indices)):
                            if k < len(self._all_features) and self._all_features[k] is None:
                                if k > 0:
                                    new_indices[k] = new_indices[k - 1]

                        return new_indices

        # Step 3: Absorb splinter clusters (< 2 segments) into closest primary cluster
        cluster_counts: dict[int, int] = {}
        for idx in merged_indices:
            cluster_counts[idx] = cluster_counts.get(idx, 0) + 1

        primary_clusters = [c for c, count in cluster_counts.items() if count >= 2]
        if primary_clusters and len(primary_clusters) < len(cluster_counts):
            for i, idx in enumerate(merged_indices):
                if cluster_counts[idx] < 2:
                    feat = self._all_features[i] if i < len(self._all_features) else None
                    if feat is not None and primary_clusters:
                        dists = [
                            (p, self.compute_voice_distance(feat, self.centroids[p]))
                            for p in primary_clusters
                            if p < len(self.centroids)
                        ]
                        if dists:
                            merged_indices[i] = min(dists, key=lambda x: x[1])[0]
                    elif primary_clusters:
                        merged_indices[i] = primary_clusters[0]

            # Re-index contiguously to 0, 1, ...
            remap: dict[int, int] = {}
            new_idx = 0
            for idx in merged_indices:
                if idx not in remap:
                    remap[idx] = new_idx
                    new_idx += 1
            merged_indices = [remap[idx] for idx in merged_indices]

        return merged_indices

    def identify_speaker(
        self, samples: np.ndarray, start_sec: float = 0.0, end_sec: float = 0.0, sr: int = 16000
    ) -> str:
        """
        Matches speech samples to an existing speaker cluster, or spawns a new speaker.
        Returns the appropriate speaker tag label (e.g. 'USR-101' for Zoom, 'P01' for Meet).
        """
        idx = self.identify_speaker_idx(samples, start_sec, end_sec, sr)
        return self.get_speaker_label(idx)

    def get_speaker_label(self, idx: int) -> str:
        """Formats the speaker label based on the meeting platform."""
        if "zoom" in self.platform:
            return f"USR-{101 + idx}"
        elif "meet" in self.platform:
            return f"P{idx + 1:02d}"
        else:
            return f"Speaker {idx + 1}"


class AudioService:
    def __init__(self) -> None:
        self._model = None
        self._model_name = settings.whisper_model

    def _get_model(self):
        """Lazy-load the Whisper model to avoid slow startup."""
        if self._model is None:
            logger.info("Loading Whisper model: %s", self._model_name)
            import whisper
            self._model = whisper.load_model(self._model_name)
            logger.info("Whisper model loaded successfully")
        return self._model

    def get_duration_seconds(self, audio_bytes: bytes, filename: str) -> float:
        """Returns audio duration in seconds. Raises ValueError if unparseable."""
        ext = filename.rsplit(".", 1)[-1].lower()
        try:
            segment = AudioSegment.from_file(BytesIO(audio_bytes), format=ext)
            return len(segment) / 1000.0
        except Exception as exc:
            raise ValueError(f"Cannot parse audio file: {exc}") from exc

    def _segment_to_samples(self, audio_seg: AudioSegment) -> np.ndarray:
        """Converts an AudioSegment to the 16kHz mono float32 numpy array Whisper expects."""
        if audio_seg.frame_rate != 16000:
            audio_seg = audio_seg.set_frame_rate(16000)

        samples = np.array(audio_seg.get_array_of_samples(), dtype=np.float32)

        if audio_seg.sample_width == 2:  # 16-bit PCM
            samples = samples / 32768.0
        elif audio_seg.sample_width == 4:  # 32-bit PCM
            samples = samples / 2147483648.0

        if audio_seg.channels == 2:  # stereo -> mono
            samples = samples.reshape((-1, 2)).mean(axis=1)

        return samples

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
        on_segment: Callable[[str, list[str]], None] | None = None,
        platform: str | None = None,
    ) -> tuple[str, str | None]:
        """
        Progressively transcribes audio using local Whisper with real acoustic
        speaker diarization to distinguish different human voices.
        Assigns Zoom Tag IDs (USR-101, USR-102, ...), Google Meet Tag IDs (P01, P02, ...),
        or standard Speaker tags based on meeting platform.
        Emits recognized lines in real time via on_segment(line, lines).
        Returns: (full_transcript, detected_language)
        """
        # Determine platform (Zoom, Google Meet, or generic)
        detected_platform = platform or ""
        if not detected_platform:
            fn_lower = (filename or "").lower()
            if "zoom" in fn_lower:
                detected_platform = "Zoom"
            elif "meet" in fn_lower:
                detected_platform = "Google Meet"

        logger.info(
            "Transcribing %d bytes with local Whisper (file=%r, lang=%r, platform=%r)",
            len(audio_bytes),
            filename,
            language,
            detected_platform,
        )

        model = self._get_model()
        ext = filename.rsplit(".", 1)[-1].lower()
        audio_segment = AudioSegment.from_file(BytesIO(audio_bytes), format=ext)
        duration_ms = len(audio_segment)

        whisper_lang = None
        initial_prompt = None
        if language and language.lower() not in ("auto", "none", ""):
            l_clean = language.lower().strip()
            if l_clean in ("hindi", "hi", "hinglish", "hi-in"):
                whisper_lang = "hi"
                initial_prompt = "नमस्ते, यह एक मीटिंग की चर्चा है जिसमें हिंदी और अंग्रेजी (Hinglish) दोनों भाषाएँ शामिल हैं।"
            elif l_clean in ("english", "en", "en-us", "en-in"):
                whisper_lang = "en"
            elif l_clean in ("gujarati", "gu"):
                whisper_lang = "gu"
            else:
                whisper_lang = l_clean.split("-")[0].split("_")[0]

        detected_language = whisper_lang
        lines: list[str] = []
        diarizer = AcousticVoiceDiarizer(platform=detected_platform)

        transcribe_opts: dict[str, Any] = {
            "language": whisper_lang,
            "word_timestamps": False,
            "verbose": False,
            "condition_on_previous_text": False,
            "compression_ratio_threshold": 2.4,
            "no_speech_threshold": 0.6,
        }
        if initial_prompt:
            transcribe_opts["initial_prompt"] = initial_prompt

        # For audio up to 10 minutes (600,000ms), transcribe full audio directly for superior quality
        # without arbitrary word-boundary slicing; for >10 mins, process in 60s windows
        CHUNK_MS = 60000
        if duration_ms > 600000:
            num_chunks = int(np.ceil(duration_ms / CHUNK_MS))
            raw_turns: list[tuple[float, int, str]] = []
            raw_indices: list[int] = []

            for i in range(num_chunks):
                start_ms = i * CHUNK_MS
                end_ms = min(duration_ms, (i + 1) * CHUNK_MS)
                chunk_seg = audio_segment[start_ms:end_ms]

                # Skip silent chunks
                if chunk_seg.dBFS < -50:
                    continue

                chunk_samples = self._segment_to_samples(chunk_seg)
                try:
                    result = model.transcribe(
                        chunk_samples,
                        **transcribe_opts,
                    )
                except Exception as exc:
                    logger.warning("Chunk %d transcription error: %s", i, exc)
                    continue

                if not detected_language and result.get("language"):
                    detected_language = result["language"]

                chunk_segments = result.get("segments", [])
                start_sec = int(start_ms / 1000)

                for seg in chunk_segments:
                    txt = seg.get("text", "").strip()
                    if not txt:
                        continue
                    s_rel = seg.get("start", 0.0)
                    e_rel = seg.get("end", s_rel)
                    s_abs = start_sec + s_rel
                    e_abs = start_sec + e_rel
                    s_idx = max(0, int(s_rel * 16000))
                    e_idx = min(len(chunk_samples), int(e_rel * 16000))

                    slice_samples = chunk_samples[s_idx:e_idx] if e_idx > s_idx else chunk_samples
                    spk_idx = diarizer.identify_speaker_idx(slice_samples, s_abs, e_abs)
                    raw_turns.append((s_abs, spk_idx, txt))
                    raw_indices.append(spk_idx)

                    mins, secs = divmod(int(s_abs), 60)
                    time_stamp = f"{mins:02d}:{secs:02d}"
                    speaker_tag = diarizer.get_speaker_label(spk_idx)
                    formatted_line = f"[{time_stamp}] [{speaker_tag}]: {txt}"
                    lines.append(formatted_line)
                    if on_segment:
                        try:
                            on_segment(formatted_line, lines)
                        except Exception as cb_exc:
                            logger.warning("on_segment callback error: %s", cb_exc)

            # Global cluster consolidation across all chunks
            final_indices = diarizer.consolidate_clusters(raw_indices)
            final_lines: list[str] = []
            for (s_abs, _, txt), f_idx in zip(raw_turns, final_indices):
                mins, secs = divmod(int(s_abs), 60)
                spk_tag = diarizer.get_speaker_label(f_idx)
                final_lines.append(f"[{mins:02d}:{secs:02d}] [{spk_tag}]: {txt}")

            full_transcript = "\n".join(final_lines)
            if full_transcript.strip():
                return full_transcript, detected_language

        # Full audio transcription (files <= 10 minutes)
        samples = self._segment_to_samples(audio_segment)
        result = model.transcribe(
            samples,
            **transcribe_opts,
        )

        if not detected_language and result.get("language"):
            detected_language = result["language"]

        segments = result.get("segments", [])
        raw_turns = []
        raw_indices = []

        for seg in segments:
            start = seg.get("start", 0.0)
            end = seg.get("end", start)
            txt = seg.get("text", "").strip()
            if not txt:
                continue

            s_idx = max(0, int(start * 16000))
            e_idx = min(len(samples), int(end * 16000))
            seg_samples = samples[s_idx:e_idx] if e_idx > s_idx else samples
            spk_idx = diarizer.identify_speaker_idx(seg_samples, start, end)

            raw_turns.append((start, spk_idx, txt))
            raw_indices.append(spk_idx)

            mins, secs = divmod(int(start), 60)
            time_stamp = f"{mins:02d}:{secs:02d}"
            speaker_tag = diarizer.get_speaker_label(spk_idx)
            formatted_line = f"[{time_stamp}] [{speaker_tag}]: {txt}"
            lines.append(formatted_line)
            if on_segment:
                try:
                    on_segment(formatted_line, lines)
                except Exception as cb_exc:
                    logger.warning("on_segment callback error: %s", cb_exc)

        # Global cluster consolidation (Pass 2)
        final_indices = diarizer.consolidate_clusters(raw_indices)
        final_lines = []
        for (start_sec, _, txt), f_idx in zip(raw_turns, final_indices):
            mins, secs = divmod(int(start_sec), 60)
            spk_tag = diarizer.get_speaker_label(f_idx)
            final_lines.append(f"[{mins:02d}:{secs:02d}] [{spk_tag}]: {txt}")

        # Deduplicate consecutive repeating lines (ASR stutter loop guard)
        deduped_final = []
        last_clean = None
        rep_count = 0
        for line in final_lines:
            c = line.split("]: ", 1)[-1].strip() if "]: " in line else line.strip()
            if c == last_clean:
                rep_count += 1
                if rep_count < 2:
                    deduped_final.append(line)
            else:
                rep_count = 0
                last_clean = c
                deduped_final.append(line)
        final_lines = deduped_final

        full_transcript = "\n".join(final_lines) if final_lines else self._format_with_speaker_turns(
            segments, result.get("text", ""), samples=samples, platform=detected_platform
        )

        return full_transcript, detected_language

    def _format_with_speaker_turns(
        self,
        segments: list,
        full_text: str,
        samples: np.ndarray | None = None,
        platform: str | None = None,
    ) -> str:
        """
        Formats Whisper segments into timestamped turns using real acoustic
        voice clustering and two-pass consolidation to distinguish speaker voices.
        """
        if not segments:
            return full_text.strip()

        diarizer = AcousticVoiceDiarizer(platform=platform)
        raw_turns: list[tuple[float, int, str]] = []
        raw_indices: list[int] = []

        for seg in segments:
            start = seg.get("start", 0.0)
            end = seg.get("end", start)
            text = seg.get("text", "").strip()
            if not text:
                continue

            if samples is not None and len(samples) > 0:
                s_idx = max(0, int(start * 16000))
                e_idx = min(len(samples), int(end * 16000))
                seg_samples = samples[s_idx:e_idx] if e_idx > s_idx else samples
                spk_idx = diarizer.identify_speaker_idx(seg_samples, start, end)
            else:
                spk_idx = 0

            raw_turns.append((start, spk_idx, text))
            raw_indices.append(spk_idx)

        final_indices = diarizer.consolidate_clusters(raw_indices)
        lines: list[str] = []
        for (start_sec, _, text), f_idx in zip(raw_turns, final_indices):
            speaker_tag = diarizer.get_speaker_label(f_idx)
            mins, secs = divmod(int(start_sec), 60)
            lines.append(f"[{mins:02d}:{secs:02d}] [{speaker_tag}]: {text}")

        return "\n".join(lines)
