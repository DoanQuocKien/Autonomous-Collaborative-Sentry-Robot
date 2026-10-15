"""Steady speed and start-up lag from the marker range over time (used by tools/speed_trial.py).

Model of one drive from rest: x(t) = S * ((t - t0) - tau * (1 - exp(-(t - t0) / tau))) for t > t0, i.e. the speed is S * (1 - exp(-(t - t0) / tau)); range d(t) = d0 - x(t) + noise.
The fit needs a dense range series (the marker found 15+ times a second); on the rugged floor (2026-10-15) it was found only 2-6 times a second while moving, so tools/speed_trial.py also
reports the net displacement over the wheel seconds, which does not need continuous tracking.
"""
import numpy as np
from scipy.optimize import least_squares


def model(p, t):
    d0, S, tau, t0 = p
    u = np.clip(t - t0, 0, None)
    return d0 - S * (u - tau * (1 - np.exp(-u / max(tau, 1e-3))))


def fit_start(t, d, t_stop=None):
    """Fit one drive from rest. t, d: arrays (s, m). t_stop: samples after it are dropped. -> dict(S, tau, t0, d0, rms, n) or None (fewer than 12 samples)."""
    t, d = np.asarray(t, float), np.asarray(d, float)
    if t_stop is not None:
        m = t <= t_stop
        t, d = t[m], d[m]
    if len(t) < 12:
        return None
    best = None
    for tau0 in (0.2, 0.6, 1.2):
        for t00 in np.linspace(t.min(), t.min() + 0.7 * (t.max() - t.min()), 5):
            p0 = [d[:5].mean(), 0.2, tau0, t00]
            r = least_squares(lambda p: model(p, t) - d, p0, bounds=([0, 0.02, 0.02, t.min() - 0.5], [10, 1.5, 3.0, t.max()]))
            if best is None or r.cost < best.cost:
                best = r
    d0, S, tau, t0 = best.x
    return dict(S=float(S), tau=float(tau), t0=float(t0), d0=float(d0), rms=float(np.sqrt(2 * best.cost / len(t))), n=len(t))


def window_speeds(t, d, win=1.0, step=0.5):
    """Speed from the range slope in sliding windows (m/s, positive = approaching): array of (window centre, speed)."""
    t, d = np.asarray(t, float), np.asarray(d, float)
    out = []
    for t0 in np.arange(t.min(), t.max() - win, step):
        m = (t >= t0) & (t < t0 + win)
        if m.sum() >= 8:
            out.append((t0 + win / 2, -np.polyfit(t[m], d[m], 1)[0]))
    return np.array(out)
