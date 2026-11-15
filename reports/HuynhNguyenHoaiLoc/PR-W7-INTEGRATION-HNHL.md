# HNHL W7: synchronize Phase 2/3 target handoff and refresh midterm evidence

The shared StateMachine could advance targets on a search timeout while Phase3Runner's record queue remained on the previous person. The runner also had no PURSUE-to-SEARCH loss producer and did not install the active Phase 2 appearance record into the robot tracker.

- Follow `TargetQueue.sync_with` after machine events/ticks, replacing manual FIFO pops/completions. Optionally inject `target_tracker`; adopt the matching active record, enforce existing real-vector/model/hash checks and clear the reference when no target remains. Preserve shared-object use without enqueueing Phase 2 records twice.
- Emit TRACK_LOST once when PURSUE lacks a fresh observation beyond its configured timeout, stop on that tick and retain the same target for SEARCH. Accept fresh reacquisition; retain HOLD semantics. Coverage planning/reacquisition on the robot remains future work.
- Preserve explicit timestamp/enqueued_at=0 in dictionary/object records and save/load. **API note:** omitted timestamps now use None until push fills them from the enqueue clock. Serialized numeric zero is treated as a real timestamp. Remove Phase2Pipeline's post-push timestamp workaround.
- Refresh HNHL's current Chapter 5, Chapter 7 rows, code appendix and data checklist using merged #115/#108/#122/#123. Pin 15 numeric sources and current Markdown hashes; the checker recalculates door/GPU metrics and keeps historical snapshot/Word verification. Keep two D2 datasets, two GPUs, runtime/pilot/T1 scopes and manual-vantage versus automatic-map evidence separate.
- Record re-review/merge receipts: #108/#122/#123 merged after validation. #113 remains blocked by unchanged data deletions. These review records do not alter the editor's package or local datasets.

Validation on HNHL's Python3.12 environment:

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-integration-1115-final -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_nov15
.venv/Scripts/python.exe -m tools.check_midterm_hnhl
```

**881 passed,2 skipped,4 GPU deselected,60.06 s**, including shared handoff, target/model provenance, timeout FIFO progression and timestamp0 regressions. Skips need checkerboard/D1 classroom data. Midterm checker verifies 15 new pinned sources, 176 historical sources and 240 local links; frozen Word hash is unchanged. No new model benchmark or motor commands.

Refs #114 and #111; follows reviews of #115/#101/#119. #118's provisional0.45 / same-identity2-of-top-3 decision is unchanged. **Do not close #114:** full door T1, body visibility/cross-camera and combined-app robot evidence remain pending. Reviewers: DQK for record/provenance and KR for state/queue integration and editor handoff.
