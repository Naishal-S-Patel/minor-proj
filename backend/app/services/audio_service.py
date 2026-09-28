"""
AudioService — owns all Whisper/audio concerns.

Responsibilities:
  1. Probe audio duration via pydub (before sending to Whisper to enforce
     the duration cap without wasting compute on a 6-hour recording)
  2. Transcribe audio using local openai-whisper package
  3. Return raw transcript text

Does NOT:
  - Know about MongoDB or MeetingStatus (worker's job)
  - Do transcript cleaning (TranscriptService handles that)
  - Raise HTTPException (raises ValueError so callers decide how to handle)
"""

import logging
from io import BytesIO

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
            return len(segment) / 1000.0  # pydub gives milliseconds
        except Exception as exc:
            raise ValueError(f"Cannot parse audio file: {exc}") from exc

    def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        """
        Transcribes audio using local openai-whisper package.
        Converts audio to numpy array using pydub before passing to Whisper.
        """
        import numpy as np

        logger.info("Transcribing %d bytes with local Whisper (file=%r)", len(audio_bytes), filename)

        model = self._get_model()

        # Use pydub to load audio and convert to numpy array
        ext = filename.rsplit(".", 1)[-1].lower()
        audio_segment = AudioSegment.from_file(BytesIO(audio_bytes), format=ext)

        # Convert to numpy array (Whisper expects 16kHz mono float32)
        samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)

        # Normalize to [-1, 1] range if integer samples
        if audio_segment.sample_width == 2:  # 16-bit
            samples = samples / 32768.0
        elif audio_segment.sample_width == 4:  # 32-bit
            samples = samples / 2147483648.0

        # Resample to 16kHz if needed
        if audio_segment.frame_rate != 16000:
            from pydub.effects import speedup
            # Simple resampling: adjust speed factor
            speed_factor = audio_segment.frame_rate / 16000
            # Use pydub's built-in resampling
            audio_segment = audio_segment.set_frame_rate(16000)
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
            if audio_segment.sample_width == 2:
                samples = samples / 32768.0
            elif audio_segment.sample_width == 4:
                samples = samples / 2147483648.0

        # Ensure mono (combine channels if stereo)
        if audio_segment.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1)

        result = model.transcribe(samples)
        transcript = result["text"]

        logger.info("Whisper transcription complete, length=%d chars", len(transcript))
        return transcript
