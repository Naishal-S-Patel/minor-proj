"""
End-to-end AudioService.transcribe() test with a fake Whisper model.

Real (synthetic) two-speaker audio goes through the actual diarization and
naming code; only Whisper itself and audio decoding are faked.
"""

from unittest.mock import patch

import numpy as np
import pytest

from app.core.config import settings
from app.services.audio_service import AudioService
from app.services.diarization import SAMPLE_RATE
from tests.test_diarization import VOICE_A, VOICE_B, _voice


def _words(text: str, start: float, end: float) -> list[dict]:
    tokens = text.split()
    step = (end - start) / len(tokens)
    return [
        {"word": f" {tok}", "start": start + i * step, "end": start + (i + 0.9) * step}
        for i, tok in enumerate(tokens)
    ]


SCRIPT = [
    # (speaker, start, end, text)
    ("A", 0.0, 3.0, "Hi everyone, I'm Ramesha. Naishal, can you give the update?"),
    ("B", 3.0, 6.0, "Sure. The API is ready for review."),
    ("A", 6.0, 9.0, "Great, thanks. Let's freeze merges on Friday."),
    ("B", 9.0, 12.0, "I will deploy the build by Friday evening."),
]


class FakeWhisper:
    is_multilingual = True

    def __init__(self, segments: list[dict]) -> None:
        self._segments = segments
        self.calls: list[dict] = []

    def transcribe(self, samples, **opts):
        self.calls.append(opts)
        return {"language": opts.get("language") or "en", "segments": self._segments}


def _audio() -> np.ndarray:
    parts = [_voice(VOICE_A if who == "A" else VOICE_B, end - start, seed=i) for i, (who, start, end, _) in enumerate(SCRIPT)]
    parts.append(np.zeros(SAMPLE_RATE, dtype=np.float32))  # 1 s of silence at the end
    return np.concatenate(parts)


def _segments() -> list[dict]:
    segs = [
        {"start": s, "end": e, "text": t, "words": _words(t, s, e), "no_speech_prob": 0.02, "avg_logprob": -0.2}
        for _, s, e, t in SCRIPT
    ]
    # Whisper's classic silence hallucination — must be dropped.
    segs.append({"start": 12.0, "end": 13.0, "text": "Thanks for watching!", "no_speech_prob": 0.7, "avg_logprob": -1.2})
    return segs


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(settings, "diarization_backend", "mfcc")
    svc = AudioService()
    monkeypatch.setattr(svc, "_segment_to_samples", lambda _seg: _audio())
    return svc


def _run(service, fake, **kwargs):
    with patch("app.services.audio_service.AudioSegment"), patch.object(service, "_get_model", return_value=fake):
        return service.transcribe(b"fake", "standup.wav", **kwargs)


def test_zoom_tags_names_and_hallucination_filter(service):
    live: list[list[str]] = []
    fake = FakeWhisper(_segments())
    transcript, lang = _run(
        service, fake, language="en", platform="Zoom", on_segment=lambda line, lines: live.append(list(lines))
    )
    lines = transcript.splitlines()

    assert lang == "en"
    assert lines == [
        "[00:00] [USR-101 (Ramesha)]: Hi everyone, I'm Ramesha. Naishal, can you give the update?",
        "[00:03] [USR-102 (Naishal)]: Sure. The API is ready for review.",
        "[00:06] [USR-101 (Ramesha)]: Great, thanks. Let's freeze merges on Friday.",
        "[00:09] [USR-102 (Naishal)]: I will deploy the build by Friday evening.",
    ]
    assert live and live[-1] == lines  # streamed to the UI
    assert fake.calls[0]["language"] == "en"
    assert fake.calls[0]["word_timestamps"] is True


def test_google_meet_roster_sets_speaker_count_and_names(service):
    fake = FakeWhisper(_segments())
    transcript, _ = _run(service, fake, language="en", platform="Google Meet", participants="Ramesha, Naishal")
    assert [l.split("]: ")[0] for l in transcript.splitlines()] == [
        "[00:00] [P01 (Ramesha)",
        "[00:03] [P02 (Naishal)",
        "[00:06] [P01 (Ramesha)",
        "[00:09] [P02 (Naishal)",
    ]
    # Participant names are given to Whisper so it spells them correctly.
    assert "Ramesha, Naishal" in fake.calls[0]["initial_prompt"]


def test_hinglish_mode_romanises_devanagari_output(service):
    segs = [
        {"start": 0.0, "end": 3.0, "text": "मैं कल तक कर दूंगा", "words": _words("मैं कल तक कर दूंगा", 0.0, 3.0)},
    ]
    transcript, lang = _run(service, FakeWhisper(segs), language="hinglish")
    assert lang == "hi"
    assert transcript == "[00:00] [Speaker 1]: main kal tak kar doonga"
