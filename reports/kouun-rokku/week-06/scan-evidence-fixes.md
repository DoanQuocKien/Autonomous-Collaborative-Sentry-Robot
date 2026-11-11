# Scan video guards and chair-check output preservation — 2026-11-11

Base: main `a200ae3` (PR #106 merged). This branch includes PR #104 head `7f1d18d` and PR #105 head `9d8a5a5`, followed by the review fixes below, so the combined PR can be reviewed independently.

## Changes

- `tools/scan_boards.py` requires a complete sample of fresh video frames before any spin. Receive timestamps use the laptop's monotonic clock; frames older than 0.5 s are discarded, and stale video also aborts before/during the pulse. Valid images with no markers may still use the calibrated prior. On failure/interruption the sender closes with an immediate stop, the receiver closes, and partial run evidence records the error.
- Only the calibrated `--spin-s 0.2` is supported. Other durations are rejected before robot setup, preventing the 0.2 s angle prior from being applied to a different duration. New calibration is required to support another duration.
- The chair-check script requires an explicit new `--out`, validates all three image sets before loading the model, rejects missing/corrupt images, and creates the output exclusively. A file created while inference is running is also protected. The historical committed JSON is unchanged.
- Tests cover missing/stale/partial video, processing that makes a frame stale, video loss after a pulse, receiver exceptions, interruption, calibrated fallback with marker-free images, dry scan, bad pulse duration, missing/corrupt chair inputs, existing outputs, successful numeric output, and a competing output created during inference.

## Validation

Environment: Linux, repo-local Python 3.14 interpreter from the original workspace, isolated checkout `/tmp/sentry-fix107`.

- Targeted: `python -m pytest -q tests/test_scan_boards.py tests/test_chair_1109_check.py` — **22 passed in 1.55 s**.
- Full CPU/replay selection: `pytest -m 'not gpu and not hil' -q` — **684 passed, 5 skipped, 4 deselected in 48.83 s**. Loopback socket tests ran outside the restricted network sandbox. Existing Windows motor-tool tests require `winsound.Beep`; on Linux the test launcher supplied only that name as a no-op module. The launcher was temporary and is not included in the PR. Equivalent invocation:

```python
import sys
import types
import pytest
if sys.platform != "win32":
    sys.modules["winsound"] = types.SimpleNamespace(Beep=lambda *args: None)
raise SystemExit(pytest.main(["-m", "not gpu and not hil", "-q"]))
```

- `git diff --check` — passed.
- No robot, motor or GPU inference was executed; no experiment numbers were regenerated. These checks establish software behavior, not physical scan accuracy or T1/T2 acceptance.
