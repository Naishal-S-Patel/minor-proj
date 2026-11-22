"""
AudioService — owns all Whisper/audio concerns.

Pipeline for one recording:
  1. Decode -> 16 kHz mono float32, DC removal + 70 Hz high-pass (hum/rumble).
  2. Language: English, Hindi, Hinglish, any other Whisper language, or auto.
     Auto-detection averages Whisper's language probabilities over the three
     loudest 30 s windows and folds Urdu into Hindi (see language_support).
  3. Transcription in ~90 s chunks cut at the quietest moment near each
     boundary (no words sliced in half), with beam search, temperature
     fallback, a language/style + participant-name prompt, and hallucination
     filtering. Lines are streamed live after every chunk.
  4. Word timestamps split Whisper segments at long pauses, so a quick
     speaker hand-off inside one segment is not glued to one voice.
  5. Diarization (diarization.py): ECAPA neural embeddings when available,
     otherwise MFCC + BIC clustering. The roster size, when given, fixes the
     number of speakers.
  6. Names (speaker_identity.py): Zoom USR-101 / Meet P01 tags by first
     appearance, then names from introductions, greetings and the roster:
         [00:05] [USR-101 (Ramesha)]: ...
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import logging
import os
import threading
from typing import Callable

import numpy as np
from pydub import AudioSegment
from pydub.utils import which

from app.core.config import settings
from app.services import language_support as lang
from app.services.diarization import (
    SAMPLE_RATE,
    EcapaEmbedder,
    GaussStats,
    cluster_bic,
    cluster_embeddings,
)
from app.services.speaker_identity import (
    Participant,
    detect_platform,
    format_speaker_label,
    parse_participants,
    resolve_speaker_names,
)

# Ensure pydub can find ffmpeg on Windows even if not on system PATH
if which("ffmpeg") is None:
    _ffmpeg_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Links", "ffmpeg.exe",
    )
    if os.path.isfile(_ffmpeg_path):
        AudioSegment.converter = _ffmpeg_path

logger = logging.getLogger(__name__)

SINGLE_PASS_MAX_SEC = 300.0   # shorter recordings (up to 5 min) are transcribed in one pass
CHUNK_TARGET_SEC = 90.0
CHUNK_SEARCH_SEC = 10.0       # look +-10 s around the target for a quiet cut point
PAUSE_SPLIT_SEC = 0.8         # word gap that may hide a speaker change
MAX_PIECE_SEC = 12.0
TURN_MERGE_GAP_SEC = 1.5


@dataclass
class _Piece:
    """A stretch of speech attributed to exactly one speaker."""

    start: float
    end: float
    text: str
    stats: GaussStats | None = None
    embedding: np.ndarray | None = None


class AudioService:
    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._model_lock = threading.Lock()
        self._model_name = settings.whisper_model

    # ------------------------------------------------------------------ #
    # Model / audio helpers
    # ------------------------------------------------------------------ #

    def _get_model(self, name: str | None = None):
        """Lazy-load (and cache) a Whisper model to avoid slow startup."""
        name = name or self._model_name
        with self._model_lock:
            if name not in self._models:
                logger.info("Loading Whisper model: %s", name)
                import whisper

                self._models[name] = whisper.load_model(name)
                logger.info("Whisper model %s loaded", name)
            return self._models[name]

    def get_duration_seconds(self, audio_bytes: bytes, filename: str) -> float:
        """Returns audio duration in seconds. Raises ValueError if unparseable."""
        ext = filename.rsplit(".", 1)[-1].lower()
        try:
            segment = AudioSegment.from_file(BytesIO(audio_bytes), format=ext)
            return len(segment) / 1000.0
        except Exception as exc:
            raise ValueError(f"Cannot parse audio file: {exc}") from exc

    def _segment_to_samples(self, audio_seg: AudioSegment) -> np.ndarray:
        """Converts an AudioSegment to the 16 kHz mono float32 array Whisper expects."""
        audio_seg = audio_seg.set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2)
        return np.array(audio_seg.get_array_of_samples(), dtype=np.float32) / 32768.0

    @staticmethod
    def _preprocess(samples: np.ndarray) -> np.ndarray:
        """
        DC removal + low-frequency rumble/hum suppression: subtracting a ~16 ms
        moving average acts as a high-pass filter (vectorised, O(n)).
        """
        if len(samples) < 512:
            return samples.astype(np.float32)
        x = samples.astype(np.float64) - float(np.mean(samples))
        win = 257
        csum = np.cumsum(np.concatenate([np.zeros(win // 2 + 1), x, np.zeros(win // 2)]))
        moving_avg = (csum[win:] - csum[:-win]) / win
        y = x - moving_avg[: len(x)]
        peak = float(np.max(np.abs(y)))
        if peak > 1.0:
            y = y / peak * 0.95
        return y.astype(np.float32)

    @staticmethod
    def _plan_chunks(samples: np.ndarray) -> list[tuple[int, int]]:
        """Chunk boundaries placed at the quietest 100 ms near each ~90 s target."""
        total = len(samples)
        if total <= SINGLE_PASS_MAX_SEC * SAMPLE_RATE:
            return [(0, total)]
        hop = SAMPLE_RATE // 10
        n_blocks = total // hop
        energy = np.square(samples[: n_blocks * hop]).reshape(n_blocks, hop).mean(axis=1)

        bounds, start = [], 0
        while total - start > (CHUNK_TARGET_SEC + CHUNK_SEARCH_SEC) * SAMPLE_RATE:
            target = start + int(CHUNK_TARGET_SEC * SAMPLE_RATE)
            lo = max((target - int(CHUNK_SEARCH_SEC * SAMPLE_RATE)) // hop, start // hop + 1)
            hi = min((target + int(CHUNK_SEARCH_SEC * SAMPLE_RATE)) // hop, n_blocks - 1)
            cut = (lo + int(np.argmin(energy[lo:hi]))) * hop if hi > lo else target
            bounds.append((start, cut))
            start = cut
        bounds.append((start, total))
        return bounds

    def _language_probs(self, model, samples: np.ndarray) -> dict[str, float]:
        """Averages Whisper language probabilities over the 3 loudest 30 s windows."""
        if not getattr(model, "is_multilingual", True):
            return {"en": 1.0}
        import whisper

        win = 30 * SAMPLE_RATE
        starts = list(range(0, max(1, len(samples) - win // 2), win)) or [0]
        loudness = [float(np.mean(np.square(samples[s : s + win]))) for s in starts]
        chosen = [s for _, s in sorted(zip(loudness, starts), reverse=True)[:3]]

        totals: dict[str, float] = {}
        n_mels = getattr(getattr(model, "dims", None), "n_mels", 80)
        for s in chosen:
            audio = whisper.pad_or_trim(samples[s : s + win])
            mel = whisper.log_mel_spectrogram(audio, n_mels=n_mels).to(model.device)
            _, probs = model.detect_language(mel)
            for code, p in probs.items():
                totals[code] = totals.get(code, 0.0) + float(p) / len(chosen)
        return totals

    def _decode_options(self, whisper_lang: str | None, prompt: str | None) -> dict:
        try:
            import torch

            fp16 = bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            fp16 = False
        opts = {
            "language": whisper_lang,
            "task": "transcribe",
            "word_timestamps": True,
            "verbose": None,
            "temperature": (0.0, 0.2) if fp16 else 0.0,
            "condition_on_previous_text": False,  # stops runaway repetition loops
            "compression_ratio_threshold": 2.4,
            "logprob_threshold": -1.0,
            "no_speech_threshold": 0.6,
            "initial_prompt": prompt,
            "fp16": fp16,
            "hallucination_silence_threshold": 2.0,
        }
        if fp16 and settings.whisper_beam_size and settings.whisper_beam_size > 1:
            opts["beam_size"] = settings.whisper_beam_size
            opts["best_of"] = settings.whisper_beam_size
        return opts

    def _run_whisper(self, model, samples: np.ndarray, opts: dict) -> dict:
        try:
            return model.transcribe(samples, **opts)
        except TypeError:
            # Older openai-whisper without hallucination_silence_threshold
            opts = {k: v for k, v in opts.items() if k != "hallucination_silence_threshold"}
            return model.transcribe(samples, **opts)

    # ------------------------------------------------------------------ #
    # Segments -> single-speaker pieces
    # ------------------------------------------------------------------ #

    @staticmethod
    def _split_segment(seg: dict, offset: float) -> list[tuple[float, float, str]]:
        """Splits a Whisper segment at long pauses between words (possible speaker changes)."""
        words = [w for w in (seg.get("words") or []) if str(w.get("word", "")).strip()]
        s0 = float(seg.get("start", 0.0)) + offset
        e0 = float(seg.get("end", s0 - offset)) + offset
        if not words:
            return [(s0, e0, str(seg.get("text", "")).strip())]

        pieces: list[list[dict]] = [[words[0]]]
        for prev, w in zip(words, words[1:]):
            gap = float(w.get("start", 0.0)) - float(prev.get("end", 0.0))
            cur_len = float(prev.get("end", 0.0)) - float(pieces[-1][0].get("start", 0.0))
            sentence_end = str(prev.get("word", "")).rstrip().endswith((".", "?", "!", "।"))
            if gap >= PAUSE_SPLIT_SEC or (cur_len >= MAX_PIECE_SEC and (sentence_end or gap > 0.3)):
                pieces.append([w])
            else:
                pieces[-1].append(w)

        out = []
        for p in pieces:
            text = "".join(str(w.get("word", "")) for w in p).strip()
            if text:
                out.append((float(p[0]["start"]) + offset, float(p[-1]["end"]) + offset, text))
        return out

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
        on_segment: Callable[[str, list[str]], None] | None = None,
        platform: str | None = None,
        participants: str | list[Participant] | None = None,
    ) -> tuple[str, str | None]:
        """
        Transcribes + diarizes a recording.
        Emits lines live via on_segment(latest_line, all_lines_so_far).
        Returns (transcript, detected_language_code).
        """
        platform = detect_platform(platform, filename)
        roster = parse_participants(participants) if isinstance(participants, str) else list(participants or [])
        mode, whisper_lang = lang.normalize_language(language)

        model_name = self._model_name
        if mode in (lang.LANG_HI, lang.LANG_HINGLISH) and settings.whisper_hindi_model:
            model_name = settings.whisper_hindi_model
        if model_name.endswith(".en") and mode not in (lang.LANG_EN, lang.LANG_AUTO):
            logger.warning("Whisper model %s is English-only; it cannot transcribe %s", model_name, mode)

        logger.info(
            "Transcribing %d bytes (file=%r, language=%r, platform=%r, roster=%d)",
            len(audio_bytes), filename, language, platform, len(roster),
        )

        # Primary Priority: AWS Transcribe Cloud ASR (falls back to local Whisper if offline/fails)
        if settings.whisper_provider == "aws" or (settings.aws_s3_bucket and settings.aws_access_key_id):
            try:
                from app.services.aws_transcribe_service import AWSTranscribeService
                logger.info("Attempting primary transcription via AWS Transcribe (bucket=%s)...", settings.aws_s3_bucket)
                transcribe_svc = AWSTranscribeService()
                aws_text, aws_lang = transcribe_svc.transcribe(
                    audio_bytes=audio_bytes,
                    filename=filename,
                    language=language,
                    platform=platform,
                    participants=roster,
                )
                if aws_text and len(aws_text.strip()) > 10:
                    logger.info("AWS Transcribe succeeded (%d chars, lang=%s)", len(aws_text), aws_lang)
                    if on_segment:
                        for line in aws_text.split("\n"):
                            if line.strip():
                                on_segment(line, aws_text.split("\n"))
                    return aws_text, aws_lang
                logger.warning("AWS Transcribe returned empty text. Falling back to local Whisper.")
            except Exception as aws_exc:
                logger.warning(
                    "AWS Transcribe unavailable or failed (%s). Seamlessly falling back to local Whisper.",
                    aws_exc,
                )

        model = self._get_model(model_name)
        ext = filename.rsplit(".", 1)[-1].lower()
        samples = self._preprocess(
            self._segment_to_samples(AudioSegment.from_file(BytesIO(audio_bytes), format=ext))
        )

        if mode == lang.LANG_AUTO:
            try:
                mode, whisper_lang = lang.choose_auto_language(self._language_probs(model, samples))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Language detection failed (%s); letting Whisper decide", exc)
                mode, whisper_lang = lang.LANG_AUTO, None
            else:
                if mode in (lang.LANG_HI, lang.LANG_HINGLISH) and settings.whisper_hindi_model:
                    model = self._get_model(settings.whisper_hindi_model)
            logger.info("Auto language -> mode=%s whisper=%s", mode, whisper_lang)
        if model_name in ("tiny", "base") and mode in (lang.LANG_HI, lang.LANG_HINGLISH):
            logger.warning(
                "Whisper '%s' is weak on Hindi; set WHISPER_HINDI_MODEL=small or medium for much better accuracy",
                model_name,
            )

        embedder = self._get_embedder()
        num_speakers = len(roster) if roster else None
        names = [p.name for p in roster]
        pieces: list[_Piece] = []
        detected_whisper_lang = whisper_lang
        context = ""

        for c_start, c_end in self._plan_chunks(samples):
            chunk = samples[c_start:c_end]
            if len(chunk) < SAMPLE_RATE // 2 or float(np.sqrt(np.mean(np.square(chunk)))) < 1e-4:
                continue
            offset = c_start / SAMPLE_RATE
            opts = self._decode_options(whisper_lang, lang.initial_prompt(mode, names, context))
            try:
                result = self._run_whisper(model, chunk, opts)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chunk at %.0fs failed to transcribe: %s", offset, exc)
                continue
            detected_whisper_lang = detected_whisper_lang or result.get("language")

            chunk_text = []
            for seg in result.get("segments", []):
                text = str(seg.get("text", "")).strip()
                if lang.is_hallucination(text, seg):
                    continue
                for start, end, piece_text in self._split_segment(seg, offset):
                    if (language or "").strip().lower() in ("hinglish", "hi-latn"):
                        piece_text = lang.transliterate_devanagari(piece_text)
                    s_idx, e_idx = int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)
                    audio = samples[max(0, s_idx) : max(s_idx + 1, e_idx)]
                    piece = _Piece(start, end, piece_text, stats=GaussStats.from_samples(audio))
                    if embedder is not None:
                        try:
                            piece.embedding = embedder.embed(audio)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("Embedding failed for piece at %.1fs: %s", start, exc)
                    pieces.append(piece)
                    chunk_text.append(piece_text)
            context = " ".join(chunk_text)

            if on_segment and pieces:
                lines = self._render(pieces, self._diarize(pieces, embedder, num_speakers), roster, platform)
                try:
                    on_segment(lines[-1], lines)
                except Exception as cb_exc:  # noqa: BLE001
                    logger.warning("on_segment callback error: %s", cb_exc)

        if not pieces:
            return "", self._language_code(mode, detected_whisper_lang)

        labels = self._diarize(pieces, embedder, num_speakers)
        lines = self._render(pieces, labels, roster, platform)
        logger.info("Transcription done: %d lines, %d speakers", len(lines), len(set(labels)))
        return "\n".join(lines), self._language_code(mode, detected_whisper_lang)

    # ------------------------------------------------------------------ #
    # Diarization + rendering
    # ------------------------------------------------------------------ #

    @staticmethod
    def _language_code(mode: str, whisper_lang: str | None) -> str | None:
        if mode == lang.LANG_AUTO:
            if whisper_lang in ("ur", "hi"):
                return "hi"
            return whisper_lang
        return lang.stored_language_code(mode)

    @staticmethod
    def _get_embedder() -> EcapaEmbedder | None:
        backend = (settings.diarization_backend or "auto").lower()
        if backend == "mfcc":
            return None
        embedder = EcapaEmbedder.get(settings.speaker_model_dir)
        if embedder is None and backend == "ecapa":
            logger.warning("DIARIZATION_BACKEND=ecapa but speechbrain is unavailable; using MFCC/BIC")
        return embedder

    @staticmethod
    def _diarize(pieces: list[_Piece], embedder, num_speakers: int | None) -> list[int]:
        max_spk = settings.diarization_max_speakers
        if embedder is not None and any(p.embedding is not None for p in pieces):
            return cluster_embeddings(
                [p.embedding for p in pieces],
                [p.end - p.start for p in pieces],
                num_speakers=num_speakers,
                max_speakers=max_spk,
                threshold=settings.diarization_ecapa_threshold,
            )
        return cluster_bic(
            [p.stats for p in pieces],
            num_speakers=num_speakers,
            max_speakers=max_spk,
            penalty=settings.diarization_bic_penalty,
        )

    @staticmethod
    def _render(
        pieces: list[_Piece],
        labels: list[int],
        roster: list[Participant],
        platform: str | None,
    ) -> list[str]:
        # Merge consecutive pieces of the same speaker into turns.
        turns: list[list] = []  # [start, end, speaker, text]
        for p, spk in zip(pieces, labels):
            if turns and turns[-1][2] == spk and p.start - turns[-1][1] <= TURN_MERGE_GAP_SEC:
                turns[-1][1] = p.end
                turns[-1][3] = f"{turns[-1][3]} {p.text}".strip()
            else:
                turns.append([p.start, p.end, spk, p.text])

        names = resolve_speaker_names([(t[2], t[3]) for t in turns], roster, platform)
        lines = []
        for start, _, spk, text in turns:
            mins, secs = divmod(int(start), 60)
            label = format_speaker_label(platform, spk, names.get(spk))
            lines.append(f"[{mins:02d}:{secs:02d}] [{label}]: {text}")
        return lines
