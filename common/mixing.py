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


def apply_trim(left, right, trim):
    """Compensate a constant drift (the wheels are not identical: measured 2026-10-11, 0.19 rad/m to the right at full command): left *= 1 - trim, right *= 1 + trim.
    trim > 0 turns the robot left (it pulls to the right without trim). If a wheel would pass 1, both are rescaled (never clipped), so the speed cap still holds."""
    left, right = left * (1.0 - trim), right * (1.0 + trim)
    m = max(abs(left), abs(right))
    if m > 1.0:
        left, right = left / m, right / m
    return left, right


def check_drive(max_speed, min_pwm, k=1.0, trim=0.0):
    """Raise ValueError unless 0 <= min_pwm < max_speed <= 1, k is finite and positive and |trim| <= 0.2 (a typo must not drive)."""
    for name, x in (("max_speed", max_speed), ("min_pwm", min_pwm), ("k", k), ("trim", trim)):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise ValueError("%s must be a finite number, got %r" % (name, x))
    if not 0.0 <= min_pwm < max_speed <= 1.0:
        raise ValueError("need 0 <= min_pwm < max_speed <= 1, got min_pwm=%r max_speed=%r" % (min_pwm, max_speed))
    if k <= 0:
        raise ValueError("k must be positive, got %r" % (k,))
    if abs(trim) > 0.2:
        raise ValueError("trim must be within +-0.2, got %r" % (trim,))


def deadzone(x, min_pwm):
    """Motors do not turn below min_pwm: send 0 instead of a value that only whines (and veers: measured 2026-10-11, 0.09 veered left, 0.12 and above ran straight).

    min_pwm is a property of the real wheel, so apply it to the FINAL value (after any speed cap).
    """
    return 0.0 if abs(x) < min_pwm else x
