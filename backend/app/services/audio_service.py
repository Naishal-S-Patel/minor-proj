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
    """

    def __init__(self, platform: str | None = None, threshold: float = 0.22) -> None:
        self.platform = (platform or "").lower()
        self.threshold = threshold
        self.centroids: list[np.ndarray] = []
        self.last_speaker_idx: int = 0
        self.last_end_sec: float = 0.0

    def extract_voice_feature(self, samples: np.ndarray, sr: int = 16000) -> np.ndarray | None:
        """
        Extracts a calibrated acoustic voice feature vector from audio samples.
        Features include:
        1. Fundamental Pitch (F0) via normalized autocorrelation (60Hz - 450Hz).
        2. Spectral Centroid (mean frequency distribution).
        3. Low (<500Hz), Mid (500-2000Hz), and High (>=2000Hz) spectral energy ratios.
        """
        if len(samples) < int(sr * 0.15):  # Ignore bursts under 150ms
            return None

        # Remove DC offset
        samples = samples - np.mean(samples)
        norm = np.sum(samples ** 2)
        if norm < 1e-4:
            return None

        # Take up to 1.5s representative slice
        chunk = samples[:min(len(samples), int(sr * 1.5))]

        # 1. Pitch / F0 via autocorrelation
        min_lag = int(sr / 450)
        max_lag = int(sr / 60)
        autocorr = np.correlate(chunk, chunk, mode="full")[len(chunk) - 1 :]
        lags = autocorr[min_lag : min(max_lag, len(autocorr))]
        f0 = 0.0
        if len(lags) > 0 and np.max(lags) > 0.15 * np.sum(chunk ** 2):
            best_lag = min_lag + int(np.argmax(lags))
            f0 = sr / best_lag

        # 2. Spectral features via FFT
        fft_vals = np.abs(np.fft.rfft(chunk))
        freqs = np.fft.rfftfreq(len(chunk), 1.0 / sr)
        tot_energy = float(np.sum(fft_vals)) + 1e-8
        centroid = float(np.sum(freqs * fft_vals)) / tot_energy

        # 3. Low, Mid, High energy ratios
        e_low = float(np.sum(fft_vals[freqs < 500])) / tot_energy
        e_mid = float(np.sum(fft_vals[(freqs >= 500) & (freqs < 2000)])) / tot_energy
        e_high = float(np.sum(fft_vals[freqs >= 2000])) / tot_energy

        return np.array([f0, centroid, e_low, e_mid, e_high], dtype=np.float32)

    def compute_voice_distance(self, f1: np.ndarray, f2: np.ndarray) -> float:
        """
        Computes the acoustic distance between two voice embeddings.
        Returns a value in [0.0, 1.0]. Lower values indicate the same human speaker.
        """
        f0_1, c1, e1_low, e1_mid, e1_high = f1
        f0_2, c2, e2_low, e2_mid, e2_high = f2

        diff_f0 = abs(f0_1 - f0_2) / max(f0_1, f0_2, 100.0) if (f0_1 > 50 and f0_2 > 50) else 0.12
        diff_c = abs(c1 - c2) / max(c1, c2, 500.0)
        diff_e = (abs(e1_low - e2_low) + abs(e1_mid - e2_mid) + abs(e1_high - e2_high)) / 2.0

        return float(0.45 * diff_f0 + 0.35 * diff_c + 0.20 * diff_e)

    def identify_speaker(
        self, samples: np.ndarray, start_sec: float = 0.0, end_sec: float = 0.0, sr: int = 16000
    ) -> str:
        """
        Matches speech samples to an existing speaker cluster, or spawns a new speaker.
        Returns the appropriate speaker tag label (e.g. 'USR-101' for Zoom, 'P01' for Meet).
        """
        feat = self.extract_voice_feature(samples, sr)
        if feat is None:
            idx = self.last_speaker_idx if self.centroids else 0
            if not self.centroids:
                self.centroids.append(np.array([150.0, 1200.0, 0.3, 0.5, 0.2], dtype=np.float32))
            return self.get_speaker_label(idx)

        if not self.centroids:
            self.centroids.append(feat)
            self.last_speaker_idx = 0
            self.last_end_sec = end_sec
            return self.get_speaker_label(0)

        # Compute voice distances to each existing speaker centroid
        distances = []
        for i, c in enumerate(self.centroids):
            dist = self.compute_voice_distance(feat, c)
            # Conversational continuity prior: if same speaker spoke within 0.8s, slight bias
            if i == self.last_speaker_idx and (start_sec - self.last_end_sec) < 0.8:
                dist -= 0.06
            distances.append(dist)

        best_idx = int(np.argmin(distances))
        best_dist = distances[best_idx]

        # Distance threshold for distinguishing distinct speakers
        if best_dist < self.threshold:
            # Same speaker voice: update running centroid
            self.centroids[best_idx] = 0.8 * self.centroids[best_idx] + 0.2 * feat
            speaker_idx = best_idx
        else:
            # Distinct new voice detected!
            self.centroids.append(feat)
            speaker_idx = len(self.centroids) - 1

        self.last_speaker_idx = speaker_idx
        self.last_end_sec = end_sec
        return self.get_speaker_label(speaker_idx)

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
        if language and language.lower() not in ("auto", "none", ""):
            whisper_lang = language.lower()

        detected_language = whisper_lang
        lines: list[str] = []
        diarizer = AcousticVoiceDiarizer(platform=detected_platform)

        # If audio is longer than 20 seconds, process in progressive 15-20s chunks
        CHUNK_MS = 20000
        if duration_ms > CHUNK_MS:
            num_chunks = int(np.ceil(duration_ms / CHUNK_MS))
            last_text = ""

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
                        language=whisper_lang,
                        word_timestamps=False,
                        verbose=False,
                    )
                except Exception as exc:
                    logger.warning("Chunk %d transcription error: %s", i, exc)
                    continue

                if not detected_language and result.get("language"):
                    detected_language = result["language"]

                chunk_segments = result.get("segments", [])
                start_sec = int(start_ms / 1000)
                end_sec = int(end_ms / 1000)

                if chunk_segments and len(chunk_segments) > 1:
                    # Fine-grained multi-speaker distinction inside chunk
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
                        speaker_tag = diarizer.identify_speaker(slice_samples, s_abs, e_abs)
                        
                        mins, secs = divmod(int(s_abs), 60)
                        time_stamp = f"{mins:02d}:{secs:02d}"
                        formatted_line = f"[{time_stamp}] [{speaker_tag}]: {txt}"
                        lines.append(formatted_line)
                        if on_segment:
                            try:
                                on_segment(formatted_line, lines)
                            except Exception as cb_exc:
                                logger.warning("on_segment callback error: %s", cb_exc)
                else:
                    text = result.get("text", "").strip()
                    if text and text != last_text:
                        last_text = text
                        speaker_tag = diarizer.identify_speaker(chunk_samples, start_sec, end_sec)
                        mins, secs = divmod(start_sec, 60)
                        time_stamp = f"{mins:02d}:{secs:02d}"

                        formatted_line = f"[{time_stamp}] [{speaker_tag}]: {text}"
                        lines.append(formatted_line)

                        if on_segment:
                            try:
                                on_segment(formatted_line, lines)
                            except Exception as cb_exc:
                                logger.warning("on_segment callback error: %s", cb_exc)

            full_transcript = "\n".join(lines)
            if full_transcript.strip():
                return full_transcript, detected_language

        # Full audio fallback if short or chunking had no speech
        samples = self._segment_to_samples(audio_segment)
        result = model.transcribe(
            samples,
            language=whisper_lang,
            word_timestamps=False,
            verbose=False,
        )

        if not detected_language and result.get("language"):
            detected_language = result["language"]

        segments = result.get("segments", [])
        full_transcript = self._format_with_speaker_turns(
            segments, result.get("text", ""), samples=samples, platform=detected_platform
        )

        if on_segment:
            for l in full_transcript.split("\n"):
                if l.strip():
                    try:
                        on_segment(l.strip(), [l.strip()])
                    except Exception:
                        pass

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
        voice clustering to distinguish speaker voices.
        """
        if not segments:
            return full_text.strip()

        diarizer = AcousticVoiceDiarizer(platform=platform)
        lines: list[str] = []

        for seg in segments:
            start = seg.get("start", 0.0)
            end = seg.get("end", start)
            text = seg.get("text", "").strip()
            if not text:
                continue

            # Extract voice segment samples to identify speaker
            if samples is not None and len(samples) > 0:
                s_idx = max(0, int(start * 16000))
                e_idx = min(len(samples), int(end * 16000))
                seg_samples = samples[s_idx:e_idx] if e_idx > s_idx else samples
                speaker_tag = diarizer.identify_speaker(seg_samples, start, end)
            else:
                speaker_tag = diarizer.get_speaker_label(0)

            mins, secs = divmod(int(start), 60)
            time_stamp = f"{mins:02d}:{secs:02d}"
            lines.append(f"[{time_stamp}] [{speaker_tag}]: {text}")

        return "\n".join(lines)
