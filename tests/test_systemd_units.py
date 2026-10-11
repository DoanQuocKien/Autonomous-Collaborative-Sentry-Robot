"""The robot's boot units must apply the documented safety rule, not a test convenience."""
import re
import shlex
from pathlib import Path

from jetson.estop import ARM_BUTTONS, ARM_HOLD_S, DEADMAN_BUTTON

UNITS = Path(__file__).resolve().parent.parent / "jetson" / "systemd"


def _estop_args():
    line = next(l for l in (UNITS / "sentry-estop.service").read_text().splitlines() if l.startswith("ExecStart="))
    cmd = re.search(r"exec (/usr/bin/python3 \S*estop\.py[^>']*)", line).group(1)
    return shlex.split(cmd)[2:]


def _option(args, name):
    """Values after `name` up to the next option, or None when the option is absent."""
    if name not in args:
        return None
    rest = args[args.index(name) + 1:]
    return rest[:next((i for i, a in enumerate(rest) if a.startswith("--")), len(rest))]


def test_estop_unit_arms_with_start_held_1_5s():
    args = _estop_args()
    buttons = _option(args, "--arm-buttons")
    assert buttons is None or tuple(int(b) for b in buttons) == ARM_BUTTONS == (11,)
    hold = _option(args, "--arm-hold")
    assert hold is None or float(hold[0]) == ARM_HOLD_S == 1.5
    deadman = _option(args, "--deadman")
    assert deadman is None or int(deadman[0]) == DEADMAN_BUTTON
    assert "--no-motor-cut" not in args


def test_control_unit_never_disables_the_estop():
    unit = (UNITS / "sentry-control.service").read_text()
    assert "--no-estop" not in unit
