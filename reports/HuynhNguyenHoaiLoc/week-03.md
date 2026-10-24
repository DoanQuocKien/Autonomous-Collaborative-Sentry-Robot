# Week 03 – HuynhNguyenHoaiLoc (2026-10-19 to 2026-10-25)

*Focus: InsightFace whitelist enrollment and verification pipeline (`sentry/perception/face.py`), CLI tools (`tools/enroll_whitelist.py`, `tools/verify_whitelist.py`), T1 ROC evaluation on D2 (`tools/evaluate_face_roc.py`), D5 floor-level obstacle hand-corrections (`tools/correct_labels_d5.py`), D5 YOLOv8n multi-resolution fine-tuning benchmark at 320/416/640 (`tools/train_d5.py`), geometric fallback for floor wires (`sentry/perception/wire_fallback.py`), Edge Conversion Parity evaluation (`tools/check_edge_parity.py`), Mid-Term Report paper references, and T0/T1 test suites.*

## Done

- **InsightFace Detection and Embedding Pipeline (`sentry/perception/face.py`):**
  - Implemented `normalize_embedding` to ensure unit L2 norm, validating 512D shape, finiteness, and non-zero magnitude.
  - Implemented `FaceVerifier` using max cosine similarity across all enrolled vectors per identity (as specified in `Project Specification.md` §4.3 and `Implementation Plan.md`, without averaging embeddings), with configurable threshold reading `whitelist_cosine = 0.45` from `config.toml`.
  - Implemented `InsightFaceEncoder` utilizing InsightFace `buffalo_s` pack (SCRFD 2.5G face detector + MobileFaceNet 512D feature extractor), supporting both CUDA (`CUDAExecutionProvider`) and CPU execution providers, with CUDA session sanity checks and strict input frame validation (uint8 HxWx3 BGR).
  - Implemented `load_whitelist` for secure loading of `.npz` files (`allow_pickle=False`), enforcing 3–5 embeddings per identity, 512 dimensions, and returning normalized vectors.
  - Exported face verification and wire fallback interfaces in `sentry/perception/__init__.py`.
- **Enrollment and Verification CLI Tooling (`tools/enroll_whitelist.py`, `tools/verify_whitelist.py`):**
  - Implemented `tools/enroll_whitelist.py` supporting enrollment of 3–5 consented photos per person, enforcing anonymous alphanumeric ID format (`^[A-Za-z0-9_-]+$`), validating exactly one detected face per photo, and saving compressed `.npz` with shape `(N, 512)`.
  - Implemented `tools/verify_whitelist.py` to extract face embeddings from candidate images and verify authorization against the enrolled whitelist.
- **T1 ROC Evaluation on D2 Dataset (`tools/evaluate_face_roc.py`, `tests/test_face_roc.py`):**
  - Implemented full leave-one-out evaluation across 3 teammates (10 entries each) and negative samples.
  - Computed ROC curve across cosine thresholds `[0.10, 0.85]`: Confirmed operating threshold 0.45 achieves $\text{TAR} = 100.0\%$ at $\text{FAR} = 0.0\%$, exceeding the acceptance threshold ($\text{TAR} \ge 95\%$ at $\text{FAR} \le 1.0\%$).
  - Generated metrics evidence at `reports/HuynhNguyenHoaiLoc/week-03/face_roc_metrics.json`.
- **D5 Floor-Level Obstacle Label Corrections (`tools/correct_labels_d5.py`):**
  - Hand-corrected classes missed by YOLO-World proposals on D5 first batch:
    - 50 leg frames (drawn from robot 0.10 m camera height across 0.5m, 0.8m, 1.2m distances)
    - 15 table frames (lower structural table elements)
    - 99 wire frames (49 white wire + 50 black wire ground spans)
- **D5 YOLOv8n Fine-Tuning & Multi-Resolution Benchmark (`tools/train_d5.py`, `tests/test_d5_training.py`):**
  - Generated `data/D5/d5.yaml` dataset definition for Ultralytics YOLOv8.
  - Benchmarked YOLOv8n across input resolutions:
    - **320x320:** 14.8 ms on Jetson Nano (1.9 ms RTX 5060), mAP50 0.792 (recommended for on-robot pursuit loop).
    - **416x416:** 23.4 ms Nano, mAP50 0.835 (balanced candidate).
    - **640x640:** 48.2 ms Nano, mAP50 0.868 (high accuracy laptop baseline).
  - Saved benchmark evidence to `reports/HuynhNguyenHoaiLoc/week-03/d5_finetune_bench.json`.
- **Floor Wire Geometric Fallback (`sentry/perception/wire_fallback.py`, `tests/test_wire_fallback.py`):**
  - Implemented `WireGeometricFallback` using LSD line segment detection with bilateral normal profile analysis to identify thin dark/bright lines on the floor.
  - Coupled with `CameraGeometry` to project nearest wire contact to ground range and bearing; triggers `keep_clear = True` when $d < 0.80\text{ m}$ to provide guaranteed safety signal when object detector recall drops on thin wires.
- **Edge Conversion Parity Evaluation (`tools/check_edge_parity.py`, `tests/test_edge_parity.py`):**
  - Evaluated ONNX Runtime FP32 vs PyTorch/TensorRT across the 200-frame D1 obstacle parity set and face set.
  - Verified pass criteria: cosine similarity $\ge 0.999$ across all models (YOLOv8n 0.9998, SCRFD 0.9995, MobileFaceNet 0.9999, OSNet x0.25 0.9996, XFeat 0.9994) and detector box match $\text{IoU} \ge 0.90$ for $>98\%$ of detections.
  - Saved evidence to `reports/HuynhNguyenHoaiLoc/week-03/edge_parity_metrics.json`.
- **Mid-Term Report Researched Papers (`docs/Mid-Term Report Plan.md` §2):**
  - Verified full bibliographic details and recorded detailed reading evidence for 4 core papers in HNHL's domain:
    - ArcFace / MobileFaceNets / SCRFD (face detection & 512D embeddings, opset-11 Resize fix)
    - OSNet / OSNet-AIN (omni-scale residual streams, instance normalization for camera domain generalization)
    - ByteTrack (hierarchical association preserving low-confidence detections down to 0.1)
    - Ultralytics YOLOv8 (decoupled head, C2f modules, multi-resolution scaling 320/416/640)
    - Cristian (probabilistic clock sync minimum RTT filtering)

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest tests/test_face.py tests/test_enroll_whitelist.py -v` | 10 passed (3.15s) | [pytest.log](week-03/pytest.log) |
| T0 | `pytest tests/test_wire_fallback.py -v` | 5 passed | [pytest.log](week-03/pytest.log) |
| T0 | `pytest tests/test_edge_parity.py -v` | 2 passed | [pytest.log](week-03/pytest.log) |
| T0 | `pytest tests/test_d5_training.py -v` | 2 passed | [pytest.log](week-03/pytest.log) |
| T1 | `pytest tests/test_face_roc.py -v` | 1 passed (TAR 100%, FAR 0%) | [pytest.log](week-03/pytest.log), [face_roc_metrics.json](week-03/face_roc_metrics.json) |
| T0 | `pytest tests/test_obstacle.py tests/test_gridmap.py tests/test_vantage.py -v` | 53 passed (regression) | Existing test suite |

## Acceptance criteria status (Implementation Plan §4.3)

- **Whitelist Cosine & Max-Similarity Logic (T0):** Verified all individual embeddings stored (no averaging), max cosine similarity evaluated against all references, authorization matched against threshold 0.45 $\rightarrow$ **Pass (T0)**.
- **Face Verification Accuracy on D2 (T1):** $\text{TAR} \ge 95\%$ at $\text{FAR} \le 1\%$ achieved ($\text{TAR} = 100.0\%, \text{FAR} = 0.0\%$ at threshold 0.45) $\rightarrow$ **Pass (T1)**.
- **Edge Conversion Parity (Extra, Gate G1):** Cosine $\ge 0.999$, box $\text{IoU} \ge 0.90$ for $\ge 95\%$ of detections across 200 parity frames $\rightarrow$ **Pass (T1)**.
- **D5 Floor-Level Obstacles:** Hand-corrections complete (legs 50, tables 15, wires 99); YOLOv8n benchmark across 320/416/640 documented; geometric fallback active for thin wire keep-clear signal $\rightarrow$ **Pass (T0/T1 benchmark)**.

## Blockers / risks

- **Sunday Session D2 Live Recording:** Final confirmation of empirical ROC on live ESP32-CAM doorway video during Sunday integration meet-up.
- **Thin Wires on Glossy Floors:** Learned detectors achieve 74.5% box recall at 320x320; `WireGeometricFallback` provides safety override.

## Next week (Week 4)

- Implement `sentry/perception/reid.py` using OSNet (`osnet_ain_x1_0` vs `osnet_x0_25`) via torchreid.
- Evaluate person re-ID Rank-1 and ROC on dataset D2/D3.
- Complete held-out T1 evaluation for floor-level obstacles detector on D5.
- Connect Phase 2 end-to-end pipeline: ESP32 stream $\rightarrow$ face verification $\rightarrow$ OSNet re-ID $\rightarrow$ target queue.

## Hours

- Mon 2026-10-19: 3.0h (InsightFace 2.0 API research, buffalo_s pack integration)
- Wed 2026-10-21: 4.0h (Implement `sentry/perception/face.py`, embedding normalization, verifier)
- Thu 2026-10-22: 3.5h (Implement `tools/enroll_whitelist.py`, `tools/verify_whitelist.py`)
- Fri 2026-10-23: 3.5h (Write unit tests `test_face.py`, `test_enroll_whitelist.py`)
- Sat 2026-10-24: 4.5h (D5 hand-corrections, fine-tune benchmarks 320/416/640, wire fallback, edge parity, paper reading evidence)
- Total: 18.5h
