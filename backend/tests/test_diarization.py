"""
Diarization tests on synthetic voices.

Each synthetic "speaker" utters random vowel sequences (like real speech,
a segment covers many sounds) with its own pitch range and vocal-tract
length (formant scaling) — the same cues MFCC/BIC clustering relies on in
real recordings — plus pitch jitter, syllable envelopes and noise.
"""

import numpy as np

from app.services.diarization import SAMPLE_RATE, GaussStats, cluster_bic, cluster_embeddings

# Peterson & Barney-style vowel formants (Hz) for an adult male vocal tract.
_VOWELS = [(730, 1090, 2440), (270, 2290, 3010), (300, 870, 2240), (530, 1840, 2480), (570, 840, 2410)]

VOICE_A = {"f0": 115.0, "tract": 1.00}
VOICE_B = {"f0": 210.0, "tract": 1.17}


def _syllable(f0: float, formants, seconds: float, rng) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    pitch = f0 * (1 + 0.04 * np.sin(2 * np.pi * rng.uniform(3, 6) * t))
    phase = 2 * np.pi * np.cumsum(pitch) / SAMPLE_RATE
    out = np.zeros_like(t)
    for h in range(1, int(4500 / f0)):
        freq = h * f0
        amp = sum(np.exp(-0.5 * ((freq - fc) / (60 + 0.08 * fc)) ** 2) for fc in formants) + 0.01
        out += amp * np.sin(h * phase)
    return out * np.hanning(len(t))


def _voice(voice: dict, seconds: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    parts, total = [], 0.0
    while total < seconds:
        dur = rng.uniform(0.15, 0.3)
        vowel = _VOWELS[rng.integers(len(_VOWELS))]
        f0 = voice["f0"] * rng.uniform(0.9, 1.1)
        parts.append(_syllable(f0, [f * voice["tract"] for f in vowel], dur, rng))
        total += dur
    out = np.concatenate(parts)[: int(seconds * SAMPLE_RATE)]
    out = out + 0.005 * rng.standard_normal(len(out))
    return (out / np.max(np.abs(out)) * 0.5).astype(np.float32)


def _segments(order: str, seconds: float = 3.0) -> list[GaussStats | None]:
    return [
        GaussStats.from_samples(_voice(VOICE_A if who == "A" else VOICE_B, seconds, seed=i))
        for i, who in enumerate(order)
    ]


def test_two_voices_are_separated_and_numbered_by_first_appearance():
    labels = cluster_bic(_segments("ABABAB"))
    assert labels == [0, 1, 0, 1, 0, 1]


def test_single_voice_stays_one_speaker():
    assert set(cluster_bic(_segments("AAAAAA"))) == {0}


def test_known_speaker_count_is_respected():
    labels = cluster_bic(_segments("ABBAAB"), num_speakers=2)
    assert labels == [0, 1, 1, 0, 0, 1]


def test_uncharacterisable_segments_inherit_neighbour():
    stats = _segments("AB")
    stats.insert(1, None)  # e.g. a 0.2 s "yes"
    assert cluster_bic(stats) == [0, 0, 1]


def test_cosine_clustering_on_embeddings():
    a, b = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    noisy = lambda v, s: (v + 0.05 * np.random.default_rng(s).standard_normal(3)) / np.linalg.norm(v)
    embs = [noisy(a, 0), noisy(b, 1), noisy(a, 2), None, noisy(b, 3)]
    assert cluster_embeddings(embs, [1.0] * 5) == [0, 1, 0, 0, 1]
