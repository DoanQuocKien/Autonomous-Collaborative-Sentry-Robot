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


DEADBAND = 0.02  # |wheel value| below this (before the cap) means "stop": PD noise around zero must not creep


def check_drive(max_speed, min_pwm, k=1.0):
    """Raise ValueError unless 0 <= min_pwm < max_speed <= 1 and k is finite and positive (a typo must not drive)."""
    for name, x in (("max_speed", max_speed), ("min_pwm", min_pwm), ("k", k)):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise ValueError("%s must be a finite number, got %r" % (name, x))
    if not 0.0 <= min_pwm < max_speed <= 1.0:
        raise ValueError("need 0 <= min_pwm < max_speed <= 1, got min_pwm=%r max_speed=%r" % (min_pwm, max_speed))
    if k <= 0:
        raise ValueError("k must be positive, got %r" % (k,))


def to_pwm(x, max_speed, min_pwm=0.0, deadband=DEADBAND):
    """Wheel value in [-1, 1] -> motor value, compensating the dead zone instead of zeroing below it.

    0 stays 0 (and |x| < deadband becomes 0); any other x maps to sign(x) * (min_pwm + (max_speed - min_pwm) * |x|).
    Wheel speed is roughly proportional to (motor value - min_pwm), so this keeps the turn ratio that mix() kept:
    the evasion command (v=-1, w=0.8) stays a reverse arc with both wheels turning, even under a low speed cap,
    where zeroing every value below min_pwm used to stop the inner wheel. min_pwm is a property of the real wheel.
    """
    if abs(x) < deadband:
        return 0.0
    mag = min_pwm + (max_speed - min_pwm) * min(abs(x), 1.0)
    return mag if x > 0 else -mag
