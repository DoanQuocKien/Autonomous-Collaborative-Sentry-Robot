# Week NN – <handle> (YYYY-MM-DD to YYYY-MM-DD)

## Done
- <work item> – PR #<n>

## Tests run
| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest -m "not gpu and not hil"` | 42 passed | week-NN/pytest.log |
| T1 | `pytest -m replay tests/test_<x>.py` | TPR 0.93 / FPR 0.03 (pass) | week-NN/<x>_metrics.json |
| T2 | <protocol name>, N trials | 4/5 pass | week-NN/<x>_trials.csv |

## Acceptance criteria status (Implementation Plan §4.3)
- <feature>: <metric> = <value> vs threshold <t> → pass / fail

## Blockers / risks
-

## Next week
-

## Hours
-
