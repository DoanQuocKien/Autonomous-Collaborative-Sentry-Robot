# Entrance recognition bake-off, D1 doorway sets (2026-10-12)

`python -m tools.bench_entrance` (PR: w02-preflight-bench). Two doors recorded by the robot camera (640x480 fisheye, no undistortion): the cafe glass door (1,419 frames) and the classroom white door (1,593 frames), every 4th frame, positives = door in view (1-4 m, 0 / +-30 deg), negatives = door out of view. The reference position (2 m, 0 deg) is left out of the evaluation. Raw numbers: `entrance_bench_robot_ref.json`, `entrance_bench_phone_ref.json`.

**Per-door threshold = 95th percentile of that door's negatives (optimistic); the "transfer" rows take the threshold from the OTHER door.**

## Reference = the robot's own frame at the reference position
| method | cafe AUC / TPR@5%FPR | classroom AUC / TPR@5%FPR | transfer cafe->class (TPR / FPR) | transfer class->cafe (TPR / FPR) | ms/frame (GPU) |
| :-- | :-- | :-- | :-- | :-- | :-- |
| ORB (2000, CLAHE, ratio 0.75, RANSAC) | 0.913 / 0.67 | 0.917 / 0.65 | 0.65 / 0.05 | 0.67 / 0.05 | 70-75 (CPU) |
| **XFeat** (top_k 2048, mutual NN, RANSAC) | **0.991 / 0.96** | **1.000 / 1.00** | **1.00 / 0.00** (27 inliers) | 1.00 / 0.17 (21 inliers) | about 20 + RANSAC |
| DINOv2-S (cls + GeM patch tokens, cosine) | 0.947 / 0.58 | 1.000 / 1.00 | 0.67 / 0.00 | 1.00 / 0.16 | 8 |
| DINOv2-B | 0.979 / 0.82 | 1.000 / 1.00 | 0.90 / 0.00 | 1.00 / 0.64 | 16 |
| XFeat + DINOv2-B (z-scored sum) | 0.992 / 0.97 | 1.000 / 1.00 | | | |

## Reference = the phone photo of the door (resized to 640x480)
| method | cafe AUC / TPR@5%FPR | classroom AUC / TPR@5%FPR | transfer cafe->class (TPR / FPR) | transfer class->cafe (TPR / FPR) |
| :-- | :-- | :-- | :-- | :-- |
| ORB | 0.607 / 0.00 | 0.686 / 0.11 | 0.02 / 0.00 | 0.01 / 0.07 |
| XFeat | 0.873 / 0.55 | 0.982 / 0.91 | 0.99 / 0.30 | 0.38 / 0.00 |
| **DINOv2-B** | **1.000 / 1.00** | **1.000 / 1.00** | 1.00 / 0.41 | 0.66 / 0.00 |
| XFeat + DINOv2-B | 0.973 / 0.84 | 0.999 / 0.99 | | |

## Linear probe on frozen DINOv2 features (trained on one door, tested on the other; no reference photo)
| features | train cafe -> test classroom (AUC) | train classroom -> test cafe (AUC) |
| :-- | :-- | :-- |
| DINOv2-S | 0.995 | 0.931 |
| DINOv2-B | 1.000 | 0.951 |

## Reading
- ORB (the plan's method) separates the frames poorly with a robot reference (AUC 0.91, TPR 0.65 at 5 % FPR) and not at all with a phone photo (AUC 0.61-0.69).
- **XFeat with a robot-eye reference** is far better (AUC 0.99-1.00); a threshold of about 27 inliers taken from the harder (cafe) door gives TPR 1.00 / FPR 0.00 on the classroom door. It also yields the matched points, so the bearing comes from the homography as in the plan. Weakest position: cafe 3 m, -30 deg (median 29 inliers against a negatives p95 of 27).
- **DINOv2-B with a phone reference** ranks perfectly (AUC 1.00 on both doors), i.e. a plain phone photo is enough, but the cosine threshold differs per door (0.49-0.52 here), so it has to be set per door from a short sweep of the room (negatives).
- Fine-tuning DINOv2 is not justified yet: with two doors there is nothing to validate it on beyond leave-one-door-out, and the frozen features plus a linear head already reach 0.93-1.00 AUC across doors. Revisit with a third door.

## Caveats (read before quoting these numbers)
- Two doors, one room each, one session each: lighting, time of day and people walking are not tested; one entrance door per room is assumed (DQK, 2026-10-12), so a second door in the same room is out of scope; frames within a position are near-duplicates (positions, not frames, are the independent units: 6-11 positive positions per door).
- The robot reference comes from the same session (a left-out position, same lighting); a reference taken on another day would be the honest test.
- Negatives are other views of the same room (the door out of view).
- Latencies were measured on the RTX 4050 (batched for DINOv2) while another job was running; XFeat on CPU only, same caveat: about 350-400 ms matching + 180 ms RANSAC per frame at top_k 1024-2048, so use it on demand, not per frame, on KR's CPU-only laptop (not re-measured on an idle machine).
- XFeat weights are from the authors' repository (Apache-2.0), DINOv2 from torch hub (facebookresearch/dinov2, Apache-2.0 code; check the weights' license before the final submission).

## Through the module (`sentry/perception/entrance.py`, `python -m tools.enroll_entrance`, added later on 2026-10-12)
The bake-off thresholds were the 95th percentile of each door's own test negatives (optimistic). The module calibrates from a sweep of negatives and is tested on the other positions, with the reference position left out:
| door | policy | negative positions used to calibrate | TPR (n) | FPR (n) |
| :-- | :-- | :-- | :-- | :-- |
| classroom | XFeat (`auto`), door box given | first 2 | **1.00** (210) | **0.00** (52) |
| cafe glass | XFeat | 2 / 4 / 6 | 0.87 / 0.87 / 0.72 (114) | 0.055 / 0.081 / 0.00 (110 / 74 / 38) |
| cafe glass | DINOv2 (robot + phone references) | 2 / 4 / 6 | 1.00 / 1.00 / 0.37 | 0.18 / 0.27 / 0.00 |
| cafe glass | XFeat and DINOv2 | 2 / 4 / 6 | 0.87 / 0.87 / 0.31 | 0.055 / 0.081 / 0.00 |
| cafe glass | XFeat or DINOv2 | 2 | 1.00 | 0.18 |

- The classroom door meets the plan thresholds (TPR >= 90 %, FPR <= 5 %); the **cafe glass door does not** (0.87 / 0.06-0.08 with XFeat), and the DINOv2 threshold is brittle: a few more negative positions swing it between TPR 1.00 / FPR 0.27 and TPR 0.37 / FPR 0.00. XFeat is the primary method; DINOv2 stays optional.
- Bearing with the door box (classroom): the door centre projects to within about 6 deg of the expected value at 1.5-3 m (reference door centre -1.6 deg; straight-on positions -1.3 / -5.1 / -7.1 deg at 1 / 1.5 / 3 m); at 1 m and +-30 deg it is unreliable (below the 1.5 m entrance range). There is no ground truth for the robot heading, so this is indicative only.
- Time per frame through the module: about 230-300 ms for XFeat on the RTX 4050 including image decoding and RANSAC, 40-47 ms with DINOv2.
