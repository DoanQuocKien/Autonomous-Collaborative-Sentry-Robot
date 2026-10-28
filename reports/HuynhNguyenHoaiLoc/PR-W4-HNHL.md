# W4: OSNet re-ID, real D2 pilot and D5 development release

## Problem and resulting behavior

Provide HNHL's Week 4 person re-ID pipeline and integrate it with KR's newly merged Phase 2 queue. Local YOLO person crops feed either re-ID-trained OSNet-AIN x1.0 or OSNet x0.25, using one validated loader/preprocessor and model/hash provenance. Missing real models/crops fail before queue/state mutation; synthetic appearance requires an explicit mock. The simulation CLI now requires `--simulated` and labels its JSON as simulation, with `t1_accepted=false`. Fix the missing `Optional` import in the merged replay tool.

Integrate main **6367935** (PRs #75–#87) into this existing PR. Unpack the newly shared D2 cafe archive locally and add an entry-held-out pilot plus aggregate F13 face ROC. Keep the independent calibration/test evaluator strict: no renamed sessions or frame leakage. No raw biometric data, vectors, weights or engines are added by this PR.

Retain corrected-label D5 training at 320/416/640, class/checkpoint freeze, ONNX opset11 export and 90-image conversion parity. DQK's 28 October fallback allows whole distance/position groups within the one glossy session: the existing 307/90 split already holds out complete distance groups (empty controls use the final contiguous block). Publish its rules/hash; do not retrain unchanged data or describe the reused dev-val as an untouched independent test. The live obstacle default remains unchanged; `deployment_ready=false`.

## Validation — updated 2026-10-29

- CPU regression: **546 passed**, 2 D1 data skips, 3 GPU tests deselected.
- GPU regression: **3 passed**, including both real OSNet checkpoints, offline CUDA inference and the Phase 2 adapter/queue handoff. Check same-batch vector agreement and cross-batch cosine ≥0.999.
- Real D2: **125 walker-face frames, 21 entries, 3 identities**, first entry per member reserved as gallery. YOLO yields **23 unambiguous person crops**; 99 absent and 3 ambiguous. Two gallery entries and nine query entries lack body crops: both OSNet models run but retrieval is **unscorable**, with no model winner or fabricated rank-1.
- Face pilot on DQK-supplied buffalo_s vectors: leave-one-member-out, first-entry enrollment, 194 genuine / 125 impostor queries. At the unchanged 0.45 threshold: **TAR 82.99%, FAR 46.40%**. Automatic walker/entry labels require review; same-session correlated queries, not T1 acceptance. F13 is explicitly labelled as a pilot.
- D5 retained evidence (28 October): all-size mAP50 0.759/0.753/0.810; wire recall **0 at the validation operating point**. The 640 development candidate's PyTorch/ONNX parity has equal box counts on **90/90 frames**, 294 boxes, matched fraction 1.0 at IoU≥0.9. This is laptop conversion parity, not TensorRT.
- Updated CLI help, explicit simulation CLI, Python AST including common/jetson Python 3.6, and whitespace checks pass.

[Report](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/HuynhNguyenHoaiLoc/w04-reid-obstacles/reports/HuynhNguyenHoaiLoc/week-04.md), [API/reproduction](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/HuynhNguyenHoaiLoc/w04-reid-obstacles/reports/HuynhNguyenHoaiLoc/W4-USAGE.md), [evidence](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/tree/HuynhNguyenHoaiLoc/w04-reid-obstacles/reports/HuynhNguyenHoaiLoc/week-04).

## Remaining acceptance

D2 is now available and evaluated as a pilot; D3/cross-camera queries, reviewed full-body gallery data and ≥5 re-ID gallery identities are still missing. No calibrated model winner. Wire misses its target; no independent D5 session/matte generalisation, contact-distance acceptance or hardware T2 is claimed. DQK's stock TensorRT parity (#79) is measured, but literal same-count remains **205/208**, with no team exception granted here; it does not certify the custom D5 model, OSNet-AIN or glossy ground-distance parity. Outline/page budget/owners are agreed per #86. No motor commands or hardware run in this update.

Keep PR #74 open for review (DQK/KR); no merge to main in this task. Earlier approval covered the previous head and should be revisited for the integrated code.
