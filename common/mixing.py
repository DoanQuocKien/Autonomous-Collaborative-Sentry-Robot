"""(v, w) -> (left, right) wheel values. Python 3.6-compatible, stdlib-only.

Convention (docs/JetBot Notes.md): v forward, positive w turns LEFT, all in [-1, 1].
"""
import math


def mix(v, w, k=1.0):
    """left = v - k*w, right = v + k*w; if a wheel exceeds 1, rescale BOTH (never clip).

    Rescaling keeps the turn ratio, e.g. evasion (v=-1, w=0.8) stays a reverse arc.
    Non-finite input -> (0, 0).
    """
    if not (math.isfinite(v) and math.isfinite(w)):
        return 0.0, 0.0
    left, right = v - k * w, v + k * w
    m = max(abs(left), abs(right))
    if m > 1.0:
        left, right = left / m, right / m
    return left, right


def deadzone(x, min_pwm):
    """Motors do not turn below min_pwm: send 0 instead of a value that only whines.

    min_pwm is a property of the real wheel, so apply it to the FINAL value (after any speed cap).
    """
    return 0.0 if abs(x) < min_pwm else x
