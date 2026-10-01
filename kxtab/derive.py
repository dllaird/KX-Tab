"""Derived values: midpoint, spread, power de-vig."""
from __future__ import annotations

import numpy as np


def mid(bid: float | None, ask: float | None, last: float | None = None) -> float | None:
    """Mid of a quoted book; else the quoted side; else the last trade. An empty book (no bid, $1 ask) is not a price."""
    if bid is not None and ask is not None and 0 < ask < 1:
        return round((bid + ask) / 2, 6)
    if ask is not None and 0 < ask < 1:
        return ask
    if bid is not None and bid > 0:
        return bid
    return last if last is not None and last > 0 else None


def spread(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or not 0 <= bid <= ask <= 1:
        return None
    return round(ask - bid, 6)


def devig_power(mids) -> np.ndarray:
    """q_i = mid_i ** k with k solved so the q's sum to 1."""
    p = np.clip(np.asarray(mids, float), 1e-9, 1 - 1e-9)
    if p.size <= 1:
        return np.ones(p.size)

    def excess(k: float) -> float:
        return float(np.sum(p ** k) - 1.0)

    lo, hi = 1.0, 1.0
    while excess(hi) > 0:
        hi *= 2
    while excess(lo) < 0:
        lo /= 2
    for _ in range(200):
        k = 0.5 * (lo + hi)
        lo, hi = (k, hi) if excess(k) > 0 else (lo, k)
        if hi - lo < 1e-12:
            break
    q = p ** (0.5 * (lo + hi))
    return q / q.sum()
