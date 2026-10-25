# Week 03 – HuynhNguyenHoaiLoc (2026-10-19 to 2026-10-25)

**Phạm vi:** InsightFace whitelist enrollment/verification; D2 ROC evaluation harness; D5 floor-obstacle labels and real YOLOv8n fine-tuning at 320/416/640; wire geometric fallback diagnosis and segmentation-label pilot; edge conversion parity harness; literature notes. **All D5 metrics below are internal development results, not independent T1 acceptance results.**

## Done

### 1. InsightFace whitelist verification (T0)

- `sentry/perception/face.py`: 512D finite, nonzero, L2-normalized embeddings; `FaceVerifier` compares each query with **all** per-person enrolled vectors using **maximum** cosine similarity (does not average vectors); threshold `whitelist_cosine = 0.45` from configuration.
- `InsightFaceEncoder` integrates `buffalo_s` (SCRFD detector and 512D embedding extraction), with CPU/CUDA provider options and input validation.
- `load_whitelist` reads compressed `.npz` with `allow_pickle=False`, validates 3–5 embeddings per identity.
- `tools/enroll_whitelist.py` and `tools/verify_whitelist.py` provide enrollment and verification; use consented photos and anonymized IDs. Unit tests cover these interfaces.
- `tools/evaluate_face_roc.py` implements leave-one-out / threshold metrics and was tested with **simulated vectors (T0 only)**. **Real D2 T1 ROC, TAR/FAR at threshold 0.45 are not yet verified.**

### 2. D5 labels and dataset preparation

- D5 first batch: **397 real images** captured from one glossy-floor room/session. Target-class label presence after manual editing: `leg` **50/50**; `footwear` **49/49**; `backpack` **49/49**; `bag` **50/50**; `table` **15/15**; `wire_black` **50/50**, `wire_white` **49/49**. These are **coverage counts**, not a claim that every bounding box/background label has been exhaustively audited.
- Visual QA sampled representative frames; checked normalized coordinates and exact duplicate label lines. Background classes and difficult instances may still need review.
- `tools/prepare_d5_yolo_dev.py` produced Ultralytics dataset `data/D5_yolo_dev/`: **307 train / 90 internal dev-val**, 8 classes, no **exact duplicate image files** between splits. **Both splits are from the same session/room; near-duplicate appearance and optimistic validation remain possible.** The earlier 317/80 split specification is superseded by this actual dataset.
- `data/D5_yolo_dev/data.yaml` is the **actual training YAML**. `data/D5/d5.yaml` and `tools/train_d5.py` must be checked/fixed for consistency with the exported layout before claiming that legacy harness is independently reproducible.

### 3. Actual YOLOv8n fine-tuning and validation (RTX 5060, internal dev-val)

Ran Ultralytics 8.4.172, Python 3.12.15, PyTorch 2.9.1+cu128, GPU RTX 5060 Laptop (~8 GiB). For each setting: pretrained `yolov8n.pt`, `epochs=30`, `batch=8`, `seed=42`, `workers=0`, `device=0`; model selection and validation on 90 dev-val images / **241 labeled instances**. Saved actual checkpoints under `runs/detect/runs/d5_dev/yolov8n_{320,416,640}/weights/best.pt` locally.

| img size | Precision (all) | Recall (all) | mAP50 | mAP50–95 | Wire Recall | Wire mAP50 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 320 | 0.730 | 0.693 | 0.739 | 0.574 | 0.050 | 0.1780 |
| 416 | 0.677 | 0.720 | **0.758** | **0.608** | **0.100** | 0.0458 |
| 640 | 0.588 | 0.803 | 0.750 | 0.606 | 0.050 | 0.0419 |

- 416 achieved highest aggregate mAP on this dev split but **was not validated as a safe/on-robot configuration**. The 640 setting did **not** resolve Wire. Wire had **20 labeled instances** at 1.00 m in dev-val; best reported class recall is only **10%**, below the **80% target**.
- Ultralytics validation reported per-image inference-only measurements of 0.6 ms (320), 1.6 ms (416), and 0.9 ms (640) in these runs; do **not** treat them as reliable speed ranking or Jetson Nano latency. **No measured Nano FPS/latency is available here.**
- These models were trained via actual `yolo detect train ... data=data/D5_yolo_dev/data.yaml ...` CLI commands. The legacy `tools/train_d5.py` was **not** the source of these results; do not cite its previous hardcoded benchmark.

### 4. Wire failure analysis on real D5 dev-val

- YOLOv8n-416 at low confidence `conf=0.05` produced **23 wire predictions over all 20/20 Wire-positive frames**. Diagnostic one-to-one GT box matches: **20/20 at IoU ≥ 0.25**, but **1/20 at IoU ≥ 0.50**; median best IoU **0.351**. At `conf=0.25`: 11/20 at IoU ≥ 0.25 and 1/20 at IoU ≥ 0.50. **These are diagnostic matches, not standard mAP/Recall.**
- On 70 no-GT-Wire dev-val controls, **5/70** images had a low-confidence Wire prediction at `conf=0.05`. The five inspected outputs showed false positives on floor grout/background lines (confidence roughly 0.05–0.15). Negative labels are based on the currently annotated dataset.
- `sentry/perception/wire_fallback.py` uses LSD line segments + contrast profile in a floor ROI; synthetic T0 tests passed (**5/5**). Real-data diagnostic: **20/20 Wire-positive images** had at least one candidate segment inside the broad GT box, but **70/70 no-GT-Wire controls** also had candidates. **Candidate overlap is not Wire recall, and any candidate is not by itself a final false alarm.** Visual review showed frequent detections of grout lines. **NO-GO for deploying the current heuristic as a standalone Wire alarm or blindly merging its candidates with YOLO.**

### 5. Segmentation feasibility pilot (annotation only)

- Selected **12 training images** (black/white wires × 0.30/0.50/0.70 m × 2 images), then manually traced nonempty binary wire masks: **12/12 coverage**.
- Contact-sheet inspection suggests masks mostly track cables, while some close-range coils/end connectors may have thick/overinclusive regions. **No segmentation model was trained; no segmentation accuracy or improvement over YOLO was measured.** Masks remain a small annotation feasibility pilot, not an independent evaluation.

### 6. Edge parity and research notes

- `tools/check_edge_parity.py` provides cosine/box-IoU evaluation helpers and a 200-frame D1 sampler plan; unit tests concern calculation/specification. **PyTorch/ONNX/TensorRT cross-runtime parity on real target engines is pending**, including Jetson Nano engine build. Do not report parity scores or acceptance PASS before measurement.
- Mid-term paper notes/reference scope covers ArcFace/MobileFaceNets/SCRFD, OSNet/OSNet-AIN, ByteTrack, YOLOv8, and Cristian clock synchronization. **OSNet re-ID and ByteTrack implementation are future-week tasks, not Week 3 achievements.**

## Tests and evidence

- Prior Week 3 test suite: **20/20 T0 unit tests passed** (`test_face`, `test_enroll_whitelist`, `test_face_roc`, `test_wire_fallback`, `test_edge_parity`, `test_d5_training`); the wire fallback subset was also rerun: **5/5 passed**. T0 success **does not** establish real D2 ROC, Jetson parity, or D5 T1.
- Previously reported perception regression suite: 53 tests passed; do not describe this as a fresh test after subsequent modifications without re-running.
- Actual Ultralytics validation logs and `best.pt` are currently **local**, under `runs/detect/runs/d5_dev/`. Diagnostic evidence is local under `data/D5_wire_val_audit.csv`, `data/D5_fallback_audit/`, `data/D5_wire_seg_masks_v1/`. Compact metric transcription: `reports/HuynhNguyenHoaiLoc/week-03/d5_finetune_results_real.json` (when added).

## Acceptance status and blockers

| Gate | Status | Evidence / blocker |
| --- | --- | --- |
| Face whitelist enrollment + max-cosine logic | **T0 PASS** | Simulated/unit tests, correct max-sim logic |
| Real D2 ROC/TAR/FAR | **PENDING T1** | Requires consented real D2 recordings |
| Edge ONNX/TensorRT parity | **PENDING T1** | Requires actual engines and recorded parity results |
| D5 training 320/416/640 | **COMPLETED, internal development** | Actual RTX 5060 training/val; 307/90 split |
| Wire recall ≥80% | **NOT MET** | Best reported Wire recall 10% |
| Geometric Wire fallback | **T0 PASS, real-data NO-GO standalone** | Grout-line ambiguity on 70/70 controls |
| Wire segmentation masks pilot | **12/12 masks** | Annotation pilot only, no model trained |
| Independent D5 session | **PENDING T1** | First batch limited to one room/session |

## Next phase / dependencies (not Week 3 completion)

- Acquire **independent D5 capture session(s)** and complete D2 face capture; freeze evaluation protocol before T1.
- Review wire-mask quality and decide whether to acquire a larger segmentation dataset; no claim of segmentation performance yet.
- Resolve `tools/train_d5.py`/YAML reproducibility before using it as an official training entrypoint; maintain exact commands/versions and preserve checkpoints outside Git until storage is agreed.
- OSNet and tracking belong to Week 4/5 milestones, **not** to this Week 3 delivery.

## Hours (current recorded timesheet; additional work should be reconciled before final submission)

- Mon 2026-10-19: 3.0h (InsightFace research, buffalo_s integration)
- Wed 2026-10-21: 4.0h (`face.py`, embedding normalization, verifier)
- Thu 2026-10-22: 3.5h (Enrollment and verification CLI)
- Fri 2026-10-23: 3.5h (Unit tests)
- Sat 2026-10-24: 3.5h (D5 tooling, wire fallback, ROC/parity harnesses, references)
- **Recorded total:** 17.5h. *This inherited timesheet does not yet include any additional unlogged 2026-10-25 work; verify with the author.*
