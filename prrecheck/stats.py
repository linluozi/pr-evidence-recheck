"""Deterministic statistics used by pr-evidence-recheck.

Deliberately dependency-free and seed-reproducible: every number the tool
reports can be recomputed from the raw per-call samples stored in the
certificate.
"""

from __future__ import annotations

from typing import Sequence


def percentile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (the "inclusive" / numpy default)."""
    if not xs:
        raise ValueError("percentile of empty sample")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be in [0, 100]")
    s = sorted(float(x) for x in xs)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * (q / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def median(xs: Sequence[float]) -> float:
    return percentile(xs, 50.0)


def p25(xs: Sequence[float]) -> float:
    return percentile(xs, 25.0)


def p75(xs: Sequence[float]) -> float:
    return percentile(xs, 75.0)


def mean(xs: Sequence[float]) -> float:
    if not xs:
        raise ValueError("mean of empty sample")
    return sum(float(x) for x in xs) / len(xs)


def stdev(xs: Sequence[float]) -> float:
    """Sample standard deviation (n-1 denominator)."""
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    var = sum((float(x) - m) ** 2 for x in xs) / (len(xs) - 1)
    return var**0.5


def rsd(xs: Sequence[float]) -> float:
    """Relative standard deviation; 0.0 when the mean is 0."""
    m = mean(xs)
    if m == 0:
        return 0.0
    return stdev(xs) / m


def speedup(base: Sequence[float], cand: Sequence[float]) -> float:
    """Ratio of medians, base / candidate. >1.0 means candidate is faster."""
    return median(base) / median(cand)


def bootstrap_ci(
    base: Sequence[float],
    cand: Sequence[float],
    *,
    iterations: int = 2000,
    seed: int = 20261116,
    confidence: float = 95.0,
):
    """Percentile bootstrap CI for median(base) / median(cand).

    Uses a local ``random.Random(seed)`` so the interval is reproducible from
    the raw samples alone. Returns ``(low, high)``.
    """
    import random

    if not base or not cand:
        raise ValueError("bootstrap_ci needs non-empty samples")
    if iterations < 100:
        raise ValueError("iterations must be >= 100")
    rng = random.Random(seed)
    bs = [float(x) for x in base]
    cs = [float(x) for x in cand]
    nb, nc = len(bs), len(cs)
    ratios = []
    for _ in range(iterations):
        rb = sorted(bs[rng.randrange(nb)] for _ in range(nb))
        rc = sorted(cs[rng.randrange(nc)] for _ in range(nc))
        mb = rb[nb // 2] if nb % 2 else (rb[nb // 2 - 1] + rb[nb // 2]) / 2.0
        mc = rc[nc // 2] if nc % 2 else (rc[nc // 2 - 1] + rc[nc // 2]) / 2.0
        ratios.append(mb / mc)
    alpha = (100.0 - confidence) / 2.0
    return percentile(ratios, alpha), percentile(ratios, 100.0 - alpha)


def summarize(base: Sequence[float], cand: Sequence[float], *, ci_iterations: int = 2000, seed: int = 20261116):
    """All reported statistics for one (baseline, candidate) pair."""
    lo, hi = bootstrap_ci(base, cand, iterations=ci_iterations, seed=seed)
    return {
        "n": [len(base), len(cand)],
        "baseline_median_ns": median(base),
        "candidate_median_ns": median(cand),
        "baseline_p25_ns": p25(base),
        "baseline_p75_ns": p75(base),
        "candidate_p25_ns": p25(cand),
        "candidate_p75_ns": p75(cand),
        "baseline_rsd": rsd(base),
        "candidate_rsd": rsd(cand),
        "speedup": speedup(base, cand),
        "speedup_ci95": [lo, hi],
    }
