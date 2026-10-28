# W4: OSNet re-ID pipeline, corrected D5 training and frozen ONNX candidate

## Behavior

Add a live/replay `PersonReID(frame_bgr,t) -> ReIDResult` pipeline: local YOLO person detection, bounded/validated crops, local re-ID-trained OSNet-AIN or OSNet x0.25 and normalized 512D vectors. Check backbone completeness, use restricted checkpoint deserialization, preserve model/hash provenance and abstain on invalid crops or tied gallery identities.

Add a session/entry-aware re-ID rank-1/CMC/ROC evaluator: calibrate threshold/model only on calibration, hold out test sessions, reject duplicate image bytes and entry leakage, report query-level false-match rates. Do not recommend an uncalibrated/reject-all model. No biometric images/vectors in this PR.

Re-run all three D5 input sizes after DQK's background-leg corrections (#66), freeze the best development checkpoint/class order/provenance, export fixed-shape ONNX opset11 and measure PyTorch/ONNX decoded parity. Add independent-session D5 audit/evaluation tooling. Keep default live obstacle model unchanged and candidate deployment_ready=false.

## Validation — 2026-10-28

- CPU regression: **476 passed**, 2 data skips, 3 GPU deselected; 18.94s, including CMC/reject-all tests.
- GPU regression: **3 passed**, 9.22s, including both real OSNet weights on CUDA with network requests blocked.
- D5 corrected-label retraining: 307 train / 90 dev-val, one session, 30 epochs ×320/416/640. Revalidation mAP50 **0.759 / 0.753 / 0.810**. Wire recall **0 at the validation operating point for all sizes**; no independent acceptance claim.
- ONNX real-image parity: **90/90 same box counts**, 294 reference boxes, every frame matched fraction1.0 at IoU≥0.9, minimum raw cosine0.9999999916. This is PyTorch CUDA FP32 vs ONNX Runtime CPU, **not TensorRT**.
- OSNet synthetic runtime: 512D, norm1, repeat consistency, CUDA FP32. No real D2/D3 accuracy or model-winner claim.

[Report](week-04.md), [reproduction/API](W4-USAGE.md), [evidence](week-04/).

## Pending acceptance

HNHL confirmed D2/D3 and an independent D5 session are unavailable. Real re-ID ROC/rank-1, model/threshold selection, glossy/matte held-out D5 metrics and distance acceptance, Nano FP16/engine parity and hardware exploration remain pending. Wire remains below target. Masks from W3 remain an annotation pilot, not a segmentation result. This PR completes the offline implementation/development experiments; it does not mark full W4 T1/T2 acceptance complete.

Per HNHL's request, DQK PRs #71/#72/#73 were reviewed/merged first (including MJPEG fixes in #73), and this branch starts at **39b4e4c**. Firmware build/flash and hardware measurements were not repeated locally. Reviewer: **DQK**. No merge to main requested for this PR; review first.
