# Week 03 – HuynhNguyenHoaiLoc (2026-10-19 to 2026-10-25)

*Focus: InsightFace whitelist enrollment and verification pipeline (`sentry/perception/face.py`), CLI tools (`tools/enroll_whitelist.py`, `tools/verify_whitelist.py`), T0 unit tests (`tests/test_face.py`, `tests/test_enroll_whitelist.py`), package exports, and Mid-Term Report paper references.*

## Done

- **InsightFace Detection and Embedding Pipeline (`sentry/perception/face.py`):**
  - Implemented `normalize_embedding` to ensure unit L2 norm, validating 512D shape, finiteness, and non-zero magnitude.
  - Implemented `FaceVerifier` using max cosine similarity across all enrolled vectors per identity (as specified in `Project Specification.md` §4.3 and `Implementation Plan.md`, without averaging embeddings), with configurable threshold reading `whitelist_cosine = 0.45` from `config.toml`.
  - Implemented `InsightFaceEncoder` utilizing InsightFace `buffalo_s` pack (SCRFD 2.5G face detector + MobileFaceNet 512D feature extractor), supporting both CUDA (`CUDAExecutionProvider`) and CPU execution providers, with CUDA session sanity checks and strict input frame validation (uint8 HxWx3 BGR).
  - Implemented `load_whitelist` for secure loading of `.npz` files (`allow_pickle=False`), enforcing 3–5 embeddings per identity, 512 dimensions, and returning normalized vectors.
  - Exported face verification interfaces in `sentry/perception/__init__.py`.
- **Enrollment and Verification CLI Tooling (`tools/enroll_whitelist.py`, `tools/verify_whitelist.py`):**
  - Implemented `tools/enroll_whitelist.py` supporting enrollment of 3–5 consented photos per person, enforcing anonymous alphanumeric ID format (`^[A-Za-z0-9_-]+$`), validating exactly one detected face per photo, and saving compressed `.npz` with shape `(N, 512)`.
  - Implemented `tools/verify_whitelist.py` to extract face embeddings from candidate images and verify authorization against the enrolled whitelist.
- **T0 Unit Tests (`tests/test_face.py`, `tests/test_enroll_whitelist.py`):**
  - Added 10 comprehensive unit tests covering embedding normalization, known face authorization, unknown face rejection, zero/corrupt vector rejection, mock backend extraction, input frame validation, preservation of individual embeddings without averaging, photo count bounds (3–5), save-load-verify round trip, and corrupt whitelist rejection.
- **Mid-Term Report Contributions (`docs/Mid-Term Report Plan.md` §2):**
  - Confirmed paper references for perception components: ArcFace/MobileFaceNets/SCRFD (face biometrics), OSNet/OSNet-AIN (re-ID), ByteTrack (tracking), and YOLOv8.

## Tests run

| Tier | Command | Result | Evidence |
| :-- | :-- | :-- | :-- |
| T0 | `pytest tests/test_face.py tests/test_enroll_whitelist.py -v` | 10 passed (4.67s) | [pytest.log](week-03/pytest.log) |
| T0 | `pytest tests/test_obstacle.py tests/test_gridmap.py tests/test_vantage.py -v` | 53 passed (regression) | Existing test suite |

## Acceptance criteria status (Implementation Plan §4.3)

- **Whitelist Cosine & Max-Similarity Logic (T0):** Verified all individual embeddings stored (no averaging), max cosine similarity evaluated against all references, authorization matched against threshold 0.45 $\rightarrow$ **Pass (T0)**.
- **Face Verification Accuracy (T1):** Target TAR $\ge 95\%$ at FAR $\le 1\%$ on dataset D2 (leave-one-out evaluation across 3 team members $\times$ 10 entries) $\rightarrow$ **Pending Sunday D2 session**.
- **Floor-Level Obstacles (D5):** DQK committed first batch (397 frames, PR #59); auto-labeling and manual box refinement in progress with team.

## Blockers / risks

- **Dataset D2 Collection:** Pending Sunday meet-up session to record ESP32-CAM doorway entries for all 3 members to compute the empirical ROC curve and verify threshold 0.45.
- **Edge Deployment Parity:** Parity checks between ONNX Runtime FP32 and TensorRT FP16 on Jetson Nano will be reviewed alongside PR conversion tooling.

## Next week (Week 4)

- Implement `sentry/perception/reid.py` using OSNet (`osnet_ain_x1_0` vs `osnet_x0_25`) via torchreid.
- Evaluate person re-ID Rank-1 and ROC on dataset D2/D3.
- Complete held-out T1 evaluation for floor-level obstacles detector on D5.
- Connect Phase 2 end-to-end pipeline: ESP32 stream $\rightarrow$ face verification $\rightarrow$ OSNet re-ID $\rightarrow$ target queue.

## Hours

- Mon 2026-10-19: 3.0h (InsightFace 2.0 API research, buffalo_s pack integration)
- Wed 2026-10-21: 4.0h (Implement `sentry/perception/face.py`, embedding normalization, verifier)
- Thu 2026-10-22: 3.5h (Implement `tools/enroll_whitelist.py`, `tools/verify_whitelist.py`)
- Fri 2026-10-23: 3.5h (Write unit tests `test_face.py`, `test_enroll_whitelist.py`, verify edge cases)
- Sat 2026-10-24: 2.0h (Integration verification, PR report, documentation)
- Total: 16.0h
