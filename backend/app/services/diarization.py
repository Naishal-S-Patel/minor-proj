"""
Speaker diarization — "who spoke when".

Two interchangeable voice back-ends:

  * MFCC + Delta-BIC (default, numpy only, always available)
      1. MFCC front-end (25 ms frames / 10 ms hop, 40 mel bands, c1..c19),
         computed only on speech frames (adaptive energy gate).
      2. Each segment is summarised by Gaussian sufficient statistics (frame
         count, sum, sum of outer products) — enough to compute covariances,
         likelihoods and BIC scores without keeping the frames around.
      3. Agglomerative clustering with the classic Delta-BIC merge criterion
         (Chen & Gopalakrishnan, 1998): two clusters merge when one
         full-covariance Gaussian describes them better (in BIC terms) than
         two. Stops when every remaining merge would raise BIC, or when the
         expected number of speakers (e.g. from the roster) is reached.
      4. Re-assignment passes move each segment to the Gaussian that explains
         it best, fixing greedy-merge mistakes; clusters with < 1.5 s of
         speech are folded into their nearest neighbour.

  * ECAPA-TDNN neural speaker embeddings (optional, used automatically when
    `speechbrain` is installed — torch is already present via Whisper).
    Cosine-distance average-linkage clustering on the embeddings. This is
    markedly better at separating voices that sound alike (e.g. two adult
    male speakers at ~120 Hz), which is where MFCC statistics struggle.

Speaker indices are always relabelled by first appearance, so index 0 is the
first person who speaks — this keeps Zoom (USR-101, ...) and Google Meet
(P01, ...) tags stable and predictable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_LEN = 400          # 25 ms
FRAME_HOP = 160          # 10 ms
N_FFT = 512
N_MELS = 40
N_CEPS = 19              # c1..c19 (c0 / loudness dropped)
MIN_SPEECH_FRAMES = 30   # 0.3 s of speech needed to describe a voice


# --------------------------------------------------------------------------- #
# MFCC front-end
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def _mel_filterbank() -> np.ndarray:
    """(N_MELS, N_FFT//2+1) triangular mel filterbank, 60 Hz - 7.6 kHz."""

    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel_to_hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)

    mels = np.linspace(hz_to_mel(60.0), hz_to_mel(7600.0), N_MELS + 2)
    bins = np.floor((N_FFT + 1) * mel_to_hz(mels) / SAMPLE_RATE).astype(int)
    fb = np.zeros((N_MELS, N_FFT // 2 + 1), dtype=np.float32)
    for m in range(1, N_MELS + 1):
        left, centre, right = bins[m - 1], bins[m], bins[m + 1]
        centre = max(centre, left + 1)
        right = max(right, centre + 1)
        fb[m - 1, left:centre] = (np.arange(left, centre) - left) / (centre - left)
        fb[m - 1, centre:right] = (right - np.arange(centre, right)) / (right - centre)
    return fb


@lru_cache(maxsize=1)
def _dct_matrix() -> np.ndarray:
    """Orthonormal DCT-II rows 1..N_CEPS (c0 dropped)."""
    n = np.arange(N_MELS)
    k = np.arange(1, N_CEPS + 1)[:, None]
    return (np.sqrt(2.0 / N_MELS) * np.cos(np.pi * k * (2 * n + 1) / (2 * N_MELS))).astype(np.float32)


def speech_mfcc(samples: np.ndarray) -> np.ndarray:
    """
    MFCC vectors (n_speech_frames, N_CEPS) for the speech-like frames of a
    16 kHz mono float signal. Silence / background frames are dropped by an
    adaptive energy gate (within 30 dB of the loudest frame and above the
    30th percentile).
    """
    if samples is None or len(samples) < FRAME_LEN * 2:
        return np.empty((0, N_CEPS), dtype=np.float32)

    x = samples.astype(np.float32)
    x = x - float(np.mean(x))
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])  # pre-emphasis
    frames = np.lib.stride_tricks.sliding_window_view(x, FRAME_LEN)[::FRAME_HOP]
    frames = frames * np.hamming(FRAME_LEN).astype(np.float32)

    log_energy = np.log(np.sum(frames ** 2, axis=1) + 1e-10)
    gate = max(float(np.percentile(log_energy, 30)), float(log_energy.max()) - 6.9)
    speech = frames[log_energy > gate]
    if len(speech) == 0:
        return np.empty((0, N_CEPS), dtype=np.float32)

    power = np.abs(np.fft.rfft(speech, N_FFT, axis=1)) ** 2
    log_mel = np.log(power @ _mel_filterbank().T + 1e-10)
    return (log_mel @ _dct_matrix().T).astype(np.float32)


# --------------------------------------------------------------------------- #
# Gaussian sufficient statistics + BIC
# --------------------------------------------------------------------------- #


@dataclass
class GaussStats:
    n: float = 0.0
    s1: np.ndarray = field(default_factory=lambda: np.zeros(N_CEPS, dtype=np.float64))
    s2: np.ndarray = field(default_factory=lambda: np.zeros((N_CEPS, N_CEPS), dtype=np.float64))

    @classmethod
    def from_samples(cls, samples: np.ndarray) -> "GaussStats | None":
        feats = speech_mfcc(samples)
        if len(feats) < MIN_SPEECH_FRAMES:
            return None
        f = feats.astype(np.float64)
        return cls(n=float(len(f)), s1=f.sum(axis=0), s2=f.T @ f)

    def __add__(self, other: "GaussStats") -> "GaussStats":
        return GaussStats(self.n + other.n, self.s1 + other.s1, self.s2 + other.s2)

    @property
    def mean(self) -> np.ndarray:
        return self.s1 / max(self.n, 1.0)

    def cov(self, reg: float) -> np.ndarray:
        mu = self.mean
        return self.s2 / max(self.n, 1.0) - np.outer(mu, mu) + reg * np.eye(N_CEPS)


def _logdet(c: np.ndarray) -> float:
    sign, val = np.linalg.slogdet(c)
    return float(val) if sign > 0 else 1e6


def _sum_stats(items: list[GaussStats]) -> GaussStats:
    total = items[0]
    for it in items[1:]:
        total = total + it
    return total


class _BICScorer:
    def __init__(self, penalty: float, reg: float) -> None:
        d = N_CEPS
        self.n_params = d + d * (d + 1) / 2
        self.penalty = penalty
        self.reg = reg

    def logdet(self, st: GaussStats) -> float:
        return _logdet(st.cov(self.reg))

    def delta_bic(self, a: GaussStats, b: GaussStats, ld_a: float, ld_b: float) -> float:
        """> 0 means 'two different voices', < 0 means 'same voice'."""
        ab = a + b
        gain = 0.5 * (ab.n * self.logdet(ab) - a.n * ld_a - b.n * ld_b)
        return gain - self.penalty * 0.5 * self.n_params * np.log(ab.n)

    @staticmethod
    def avg_loglik(seg: GaussStats, cov_inv: np.ndarray, mean: np.ndarray, ld: float) -> float:
        """Average per-frame Gaussian log-likelihood of a segment (constants dropped)."""
        mu_s = seg.mean
        scatter = seg.s2 / max(seg.n, 1.0) - np.outer(mu_s, mu_s)
        diff = mu_s - mean
        return -0.5 * (ld + float(np.sum(cov_inv * scatter)) + float(diff @ cov_inv @ diff))


def _kmeans(points: np.ndarray, weights: np.ndarray, k: int, iters: int = 15) -> np.ndarray:
    """Weighted k-means; only used to bound clustering cost on very long audio."""
    rng = np.random.default_rng(0)
    idx = rng.choice(len(points), size=k, replace=False, p=weights / weights.sum())
    centres = points[idx].copy()
    labels = np.zeros(len(points), dtype=int)
    for _ in range(iters):
        dist = ((points[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        labels = dist.argmin(axis=1)
        for c in range(k):
            mask = labels == c
            if mask.any():
                centres[c] = np.average(points[mask], axis=0, weights=weights[mask])
    return labels


def cluster_bic(
    stats: list[GaussStats | None],
    num_speakers: int | None = None,
    max_speakers: int = 8,
    penalty: float = 2.5,
    max_initial_clusters: int = 300,
) -> list[int]:
    """
    Clusters segments into speakers with MFCC Gaussians + Delta-BIC.
    `stats[i]` is None for segments too short / silent to characterise; those
    inherit a neighbour's label. Returns one speaker index per segment.
    """
    valid = [i for i, s in enumerate(stats) if s is not None and s.n >= MIN_SPEECH_FRAMES]
    if not valid:
        return [0] * len(stats)
    seg_stats = [stats[i] for i in valid]

    pooled = _sum_stats(seg_stats)
    reg = 1e-3 * float(np.trace(pooled.cov(0.0))) / N_CEPS + 1e-6
    scorer = _BICScorer(penalty=penalty, reg=reg)

    if len(seg_stats) > max_initial_clusters:
        means = np.stack([s.mean for s in seg_stats])
        weights = np.array([s.n for s in seg_stats], dtype=np.float64)
        pre = _kmeans(means, weights, max_initial_clusters)
        members = [list(np.where(pre == c)[0]) for c in range(max_initial_clusters)]
        members = [m for m in members if m]
    else:
        members = [[i] for i in range(len(seg_stats))]

    clusters = [_sum_stats([seg_stats[j] for j in m]) for m in members]
    logdets = [scorer.logdet(c) for c in clusters]

    k = len(clusters)
    D = np.full((k, k), np.inf)
    for i in range(k):
        for j in range(i + 1, k):
            D[i, j] = scorer.delta_bic(clusters[i], clusters[j], logdets[i], logdets[j])

    alive = list(range(k))
    target = min(num_speakers, k) if num_speakers else None

    while len(alive) > 1:
        sub = D[np.ix_(alive, alive)]
        ai, aj = divmod(int(np.argmin(sub)), len(alive))
        if target is not None:
            if len(alive) <= target:
                break
        elif sub[ai, aj] > 0 and len(alive) <= max_speakers:
            break
        i, j = sorted((alive[ai], alive[aj]))
        clusters[i] = clusters[i] + clusters[j]
        logdets[i] = scorer.logdet(clusters[i])
        members[i] = members[i] + members[j]
        alive.remove(j)
        D[j, :] = np.inf
        D[:, j] = np.inf
        for o in alive:
            if o != i:
                a, b = (i, o) if i < o else (o, i)
                D[a, b] = scorer.delta_bic(clusters[a], clusters[b], logdets[a], logdets[b])

    labels = np.zeros(len(seg_stats), dtype=int)
    for new_id, cid in enumerate(alive):
        labels[members[cid]] = new_id

    labels = _reassign(seg_stats, labels, scorer)
    if target is None:
        labels = _absorb_tiny_clusters(seg_stats, labels, scorer)
    return _expand_and_relabel(labels.tolist(), valid, len(stats))


def _cluster_models(seg_stats, labels, scorer: _BICScorer):
    models = {}
    for c in np.unique(labels):
        st = _sum_stats([s for s, l in zip(seg_stats, labels) if l == c])
        cov = st.cov(scorer.reg)
        models[int(c)] = (st, np.linalg.inv(cov), st.mean, _logdet(cov))
    return models


def _reassign(seg_stats, labels, scorer: _BICScorer, iters: int = 3) -> np.ndarray:
    labels = labels.copy()
    if len(np.unique(labels)) < 2:
        return labels
    for _ in range(iters):
        models = _cluster_models(seg_stats, labels, scorer)
        changed = 0
        for idx, seg in enumerate(seg_stats):
            scores = {c: scorer.avg_loglik(seg, inv, mu, ld) for c, (_, inv, mu, ld) in models.items()}
            best = max(scores, key=scores.get)
            if best != labels[idx] and np.sum(labels == labels[idx]) > 1:
                labels[idx] = best
                changed += 1
        if changed == 0:
            break
    return labels


def _absorb_tiny_clusters(
    seg_stats, labels, scorer: _BICScorer, min_frames: int = 150, min_share: float = 0.03
) -> np.ndarray:
    """
    Merge clusters holding < max(1.5 s, 3 % of all speech) into the closest
    other cluster — such clusters are far more often noise, laughter or a
    cough than a genuine extra participant.
    """
    labels = labels.copy()
    min_frames = max(min_frames, min_share * sum(s.n for s in seg_stats))
    while len(np.unique(labels)) > 1:
        sizes = {int(c): sum(s.n for s, l in zip(seg_stats, labels) if l == c) for c in np.unique(labels)}
        tiny = [c for c, n in sizes.items() if n < min_frames]
        if not tiny:
            break
        c = min(tiny, key=lambda t: sizes[t])
        models = _cluster_models(seg_stats, labels, scorer)
        st_c = models[c][0]
        others = {o: scorer.avg_loglik(st_c, inv, mu, ld) for o, (_, inv, mu, ld) in models.items() if o != c}
        labels[labels == c] = max(others, key=others.get)
    return labels


# --------------------------------------------------------------------------- #
# Neural embeddings (optional) + cosine clustering
# --------------------------------------------------------------------------- #


class EcapaEmbedder:
    """
    Wraps SpeechBrain's pretrained ECAPA-TDNN (VoxCeleb) speaker encoder.
    Only constructed if `speechbrain` is importable; the model (~80 MB) is
    downloaded once on first use into `savedir`.
    """

    _lock = threading.Lock()
    _instance: "EcapaEmbedder | None" = None
    _failed = False

    def __init__(self, savedir: str) -> None:
        import torch  # noqa: F401  (torch ships with openai-whisper)

        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError:  # speechbrain < 1.0
            from speechbrain.pretrained import EncoderClassifier  # type: ignore

        kwargs = {"source": "speechbrain/spkrec-ecapa-voxceleb", "savedir": savedir}
        try:
            # Windows cannot create symlinks without developer mode — copy instead.
            from speechbrain.utils.fetching import LocalStrategy

            kwargs["local_strategy"] = LocalStrategy.COPY
        except Exception:  # noqa: BLE001
            pass
        self._model = EncoderClassifier.from_hparams(**kwargs, run_opts={"device": "cpu"})

    @classmethod
    def get(cls, savedir: str) -> "EcapaEmbedder | None":
        if cls._failed:
            return None
        with cls._lock:
            if cls._instance is None:
                try:
                    cls._instance = cls(savedir)
                    logger.info("ECAPA speaker embedder loaded (neural diarization enabled)")
                except Exception as exc:  # noqa: BLE001
                    cls._failed = True
                    logger.info("ECAPA embedder unavailable (%s); using MFCC/BIC diarization", exc)
                    return None
        return cls._instance

    def embed(self, samples: np.ndarray) -> np.ndarray | None:
        """L2-normalised embedding, averaged over <=3 s windows for long segments."""
        import torch

        if samples is None or len(samples) < int(0.8 * SAMPLE_RATE):
            return None
        win = 3 * SAMPLE_RATE
        chunks = [samples[i : i + win] for i in range(0, len(samples), win)]
        chunks = [c for c in chunks if len(c) >= int(0.8 * SAMPLE_RATE)] or [samples]
        vecs = []
        with torch.no_grad():
            for c in chunks:
                wav = torch.from_numpy(np.ascontiguousarray(c, dtype=np.float32)).unsqueeze(0)
                emb = self._model.encode_batch(wav).squeeze().cpu().numpy()
                vecs.append(emb / (np.linalg.norm(emb) + 1e-9))
        v = np.mean(vecs, axis=0)
        return v / (np.linalg.norm(v) + 1e-9)


def cluster_embeddings(
    embeddings: list[np.ndarray | None],
    weights: list[float],
    num_speakers: int | None = None,
    max_speakers: int = 8,
    threshold: float = 0.70,
) -> list[int]:
    """
    Average-linkage agglomerative clustering on cosine distance. Merging stops
    at `threshold` (or when `num_speakers` clusters remain, if known).
    """
    valid = [i for i, e in enumerate(embeddings) if e is not None]
    if not valid:
        return [0] * len(embeddings)
    X = np.stack([embeddings[i] for i in valid])
    w = np.array([max(weights[i], 1e-3) for i in valid])
    n = len(X)

    D = 1.0 - X @ X.T
    np.fill_diagonal(D, np.inf)
    sizes = w.copy()
    members = [[i] for i in range(n)]
    alive = list(range(n))
    target = min(num_speakers, n) if num_speakers else None

    while len(alive) > 1:
        sub = D[np.ix_(alive, alive)]
        ai, aj = divmod(int(np.argmin(sub)), len(alive))
        if target is not None:
            if len(alive) <= target:
                break
        elif sub[ai, aj] > threshold and len(alive) <= max_speakers:
            break
        i, j = sorted((alive[ai], alive[aj]))
        # Lance-Williams update for (weighted) average linkage.
        for o in alive:
            if o in (i, j):
                continue
            D[i, o] = D[o, i] = (sizes[i] * D[i, o] + sizes[j] * D[j, o]) / (sizes[i] + sizes[j])
        sizes[i] += sizes[j]
        members[i] += members[j]
        alive.remove(j)
        D[j, :] = np.inf
        D[:, j] = np.inf

    labels = [0] * n
    for new_id, cid in enumerate(alive):
        for m in members[cid]:
            labels[m] = new_id
    return _expand_and_relabel(labels, valid, len(embeddings))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _expand_and_relabel(labels: list[int], valid: list[int], n_total: int) -> list[int]:
    """Expand labels of characterised segments to all segments, then number by first appearance."""
    full = [-1] * n_total
    for pos, seg_idx in enumerate(valid):
        full[seg_idx] = int(labels[pos])
    last = -1
    for i in range(n_total):
        if full[i] == -1:
            full[i] = last
        else:
            last = full[i]
    first = full[valid[0]]
    full = [first if v == -1 else v for v in full]

    mapping: dict[int, int] = {}
    out = []
    for v in full:
        if v not in mapping:
            mapping[v] = len(mapping)
        out.append(mapping[v])
    return out
