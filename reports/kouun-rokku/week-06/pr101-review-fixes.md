# PR #101 re-review fixes — 2026-11-14

Base: PR head `969a5e0b61a804784344741f868c57fb2ecbd508`, integrated with main
`4f80eacb6f0e23c519ca24f293e572974168c9da`. This is CPU/simulation validation;
no hardware or GPU inference was run.

- HOLD release checks the last consumed observation before processing a new
  sample after a control-loop stall. Detector TARGET_LOST / PURSUE mode also
  releases StateMachine HOLD, including custom gap timeouts.
- Both observation entry points feed the controller once per measurement
  timestamp. Duplicate, out-of-order, stale and wrong-target observations do
  not advance the detector. Future samples cannot command motion before their
  timestamp. Identity handoff still resets caches and controller history.
- NaN and either infinity in either motor-command axis return (0, 0) before
  clamping. Existing finite legality and handoff regressions are retained.
- The consolidated report keeps obstacle distance pending (8/9 IDs, p90
  20.91% above 20%, fewer than 20 IDs/independent conditions). Appearance
  vectors stay on the laptop; JetBot receives v/w. F18 and DQK's floor-range
  limitations now cite primary evidence. Video p95 and single-run ArUco rows
  no longer imply acceptance. Owner chapters remain drafts for final editing.

## Validation

- Targeted runner/controllers/hold/state-machine/queue: **71 passed**.
- Full CPU/replay: **754 passed, 5 skipped, 4 deselected in 46.47s**:
  [pytest log](pr101-review-pytest.log).
- `python -m tools.replay_phase3 --out /tmp/pr101-phase3-replay.json`: PASS,
  HOLD at 6.32 s, resume at 8.26 s, zero HOLD translation, two completed
  targets, zero illegal commands (same scripted metrics as the existing
  [simulation summary](phase3_replay_summary.json)).
- [Page audit](pr101-page-audit.json): 9/9 chapters and 6/6 image assets.
  Word-derived page estimate only; actual rendered layout is unverified.
- `git diff --check`: PASS.

Linux, Python 3.14.4, pytest 9.1.1. The suite needs localhost sockets. Existing
Windows beep tests use a test-only shim; no application beep code was changed.
Run from repository root with its environment activated:

```bash
python - <<'PYTEST'
import sys
import types
import pytest
sys.modules['winsound'] = types.SimpleNamespace(Beep=lambda *args: None)
raise SystemExit(pytest.main(['-m', 'not gpu and not hil', '-q']))
PYTEST
```

The original workspace's uncommitted Week 7 packaging/data changes were not
included. This work does not claim a clean-checkout test of the future
`midterm` tag or resolve publication/history cleanup.
