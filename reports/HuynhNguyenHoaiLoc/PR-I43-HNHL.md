# Improve glossy-floor chair contacts and add small-obstacle proposal backends

Refs #43. Base `b7d19be`; branch `HuynhNguyenHoaiLoc/w02-issue43-obstacles`; reviewer DQK.

## Problem and change

The existing glossy-floor path detects chairs but rejects every distance on the 15 October clips. The COCO furniture detector also misses low objects. Add optional semantic-floor evidence and image-edge contact refinement, plus an offline prompt-bound YOLO-World detector with overlapping floor crops and merged NMS. Keep uncertain/cut contacts unresolved, keep semantics separate from COCO IDs, and never infer map FREE from floor segmentation alone.

Both backends are opt-in through single-image/replay flags. Downloads happen only in a separate, pinned preparation command; inference reads local assets. Add a box-matched benchmark with missing-ID/frame coverage, stable detections, hashes, timing and memory. Private data/annotations/weights stay gitignored; reports contain metrics only.

## Validation — 2026-10-17

- CPU/transport regression: **360 passed**, 2 data-dependent skips, 2 GPU tests deselected.
- Real-model GPU tests: **2 passed**; CUDA FP32 with inference network requests blocked. Environment check: ALL GOOD.
- 86 public chair frames: valid distance **0/9 → 8/9 placements**, remaining placement border-truncated. Held-out chairs_c: 3/3 have estimates, median/p90 **5.37%/17.11%**; 24/28 frames valid for the weakest ID. All measured chair IDs p90 **20.91%**, still above 20%.
- 259 private mixed-object frames: all80 baseline detects 7/15 IDs at least once, 2/15 in ≥50% frames. Hybrid detects **12/15**, **10/15** stable; distance **10/15** at least once, **6/15** stable. Manual image-box annotations need DQK review; class-agnostic IoU matching, no tape used for association.
- Hybrid matched-subset median/p90 distance error **11.27%/27.80%**; still outside 10%/20%. RTX5060 semantic/hybrid image throughput **11.45 / 7.80 FPS**, below 20 FPS. These results do not replace RTX4050, map or HIL acceptance.

[Full report and reproduction commands](ISSUE-43-HNHL.md), [evidence](week-02/issue-43/).

## Remaining work

Charger, stand and phone remain undetected. Some detected objects still have no stable distance. Need reviewed dense labels, false-positive evaluation, matte/rugged control images, pose checks and runtime optimization. Do **not** close #43 or enable the new paths on the robot based on these experiments. No motor commands or GitHub comments. Commit/push of this branch was requested by HNHL after reviewing the local results.
