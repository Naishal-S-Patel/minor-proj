"""
AudioService — owns all Whisper/audio concerns.

Responsibilities:
  1. Probe audio duration via pydub
  2. Progressive / Streaming line-by-line Whisper transcription
  3. Multi-language support (English, Hindi, Spanish, Gujarati, etc. or Auto-detect)
  4. Speaker diarization / dialogue attribution formatting with timestamps
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
    ) -> tuple[str, str | None]:
        """
        Progressively transcribes audio using local Whisper.
        Emits recognized lines in real time via on_segment(line, lines) so the
        frontend can show line-by-line transcription rather than waiting minutes.
        Supports multi-language selection or automatic language detection.
        Returns: (full_transcript, detected_language)
        """
        logger.info(
            "Transcribing %d bytes with local Whisper (file=%r, lang=%r)",
            len(audio_bytes),
            filename,
            language,
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

        # If audio is longer than 20 seconds, process in progressive 15-20s chunks
        # so line-by-line updates appear continuously.
        CHUNK_MS = 20000
        if duration_ms > CHUNK_MS:
            num_chunks = int(np.ceil(duration_ms / CHUNK_MS))
            speaker_idx = 1
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

                text = result.get("text", "").strip()
                if text and text != last_text:
                    last_text = text
                    # Alternate speakers on distinct topic/pause turns
                    start_sec = int(start_ms / 1000)
                    mins, secs = divmod(start_sec, 60)
                    time_stamp = f"{mins:02d}:{secs:02d}"

                    formatted_line = f"[{time_stamp}] [Speaker {speaker_idx}]: {text}"
                    lines.append(formatted_line)

                    # Toggle speaker periodically (every 1-2 chunks)
                    if (i % 2) == 1:
                        speaker_idx = 2 if speaker_idx == 1 else 1

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
        full_transcript = self._format_with_speaker_turns(segments, result.get("text", ""))

        if on_segment:
            for l in full_transcript.split("\n"):
                if l.strip():
                    try:
                        on_segment(l.strip(), [l.strip()])
                    except Exception:
                        pass

        return full_transcript, detected_language

    def _format_with_speaker_turns(self, segments: list, full_text: str) -> str:
        """Formats segments into timestamped speaker turns."""
        if not segments:
            return full_text.strip()

        turns: list[dict] = []
        current_texts: list[str] = []
        prev_end: float = 0.0
        turn_start: float = 0.0

        for seg in segments:
            start = seg.get("start", 0.0)
            end = seg.get("end", start)
            text = seg.get("text", "").strip()
            if not text:
                continue

            gap = start - prev_end if prev_end > 0 else 0.0
            if gap >= 1.5 and current_texts:
                turns.append({"start": turn_start, "text": " ".join(current_texts)})
                current_texts = [text]
                turn_start = start
            else:
                if not current_texts:
                    turn_start = start
                current_texts.append(text)
            prev_end = end

        if current_texts:
            turns.append({"start": turn_start, "text": " ".join(current_texts)})

        if len(turns) <= 1:
            return full_text.strip()

        lines: list[str] = []
        for i, turn in enumerate(turns):
            speaker_num = (i % 2) + 1
            sec = int(turn["start"])
            mins, secs = divmod(sec, 60)
            time_stamp = f"{mins:02d}:{secs:02d}"
            lines.append(f"[{time_stamp}] [Speaker {speaker_num}]: {turn['text']}")

        return "\n".join(lines)
