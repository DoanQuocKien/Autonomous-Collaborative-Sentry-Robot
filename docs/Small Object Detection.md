# Small and low objects: what we measured, what the literature says, what we do (2026-10-18)

Requirement (Implementation Plan section 4.3, risk 30): from the robot's own camera (lens 0.10 m above the floor) the obstacle layer must detect **human legs and feet, wires (black and white), footwear and backpacks or bags**, plus furniture. This note records why the stock detectors do not and what we try, in order.

## 1. What we measured (2026-10-18, rugged matte floor, 1.0 m, `reports/DoanQuocKien/week-02/small_objects_1018/`)

| Item | YOLOv8n COCO (furniture classes) | YOLOv8n Open Images V7 (601 classes) | Semantic floor (PR #46) | YOLO-World (PR #46, prompts) |
| :-- | :-- | :-- | :-- | :-- |
| Low table | 0 / 20 | nothing | nothing | found, -13 % |
| Backpack | 2 / 20 (as "suitcase") | nothing | nothing | found, -11 % |
| Box | 0 / 20 | nothing | nothing | found, -14 % |
| Black wire | - | nothing | - | **0 / 20** |

The Open Images model was tried because its label set already contains `Human leg`, `Human foot`, `Footwear`, `Sandal`, `Boot`, `Backpack`, `Handbag`, `Box`: it still reported only `Person` and `Building` on our frames (confidence >= 0.10). **The label set is not the problem; the viewpoint is.** Public detection sets are shot from standing height; at 0.10 m, with a 160 deg fisheye, objects are foreshortened, partly cut by the horizon and the floor texture dominates. Only the prompt-based YOLO-World found large objects, and only objects that were in its prompt list.

## 2. What the literature says (not all papers were read in full; numbers below are not ours)

- **Robot vacuums solve exactly this with their own data.** Ecovacs describes adding a front camera and a TensorFlow Lite model for slippers, socks and cables that bumpers and lidar miss ([TensorFlow blog, 2020](https://blog.tensorflow.org/2020/01/ecovacs-robotics-ai-robotic-vacuum.html)). A patent on obstacle recognition for autonomous robots trains on object images under varied lighting, camera poses and colours ([US 10452071](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10452071)). A YOLOv5 floor-object paper used about 300 annotated images ([sciforum](https://sciforum.net/paper/view/20445); camera height and angle not stated in what I read).
- **Wires are a segmentation problem, not a box problem.** Floor cables are deformable linear objects; ASC-SW is a lightweight strip-convolution segmenter for edge mobile robots and oblique views ([arXiv 2507.12744](https://arxiv.org/pdf/2507.12744)). Drone work segments wires as thin structures and trains on synthetic (ray-traced or pasted) wires because labelled data is scarce ([CMU, Madaan et al.](https://www.ri.cmu.edu/app/uploads/2017/08/root.pdf); [UCorr](https://arxiv.org/abs/2509.14989)). Thin structures are hard for stereo, lidar and sonar alike ([Zhou et al., CVPR 2017 workshop](https://openaccess.thecvf.com/content_cvpr_2017_workshops/w4/papers/Zhou_Fast_Accurate_Thin-Structure_CVPR_2017_paper.pdf)).
- **Auto-labelling with an open-vocabulary model, then a small trained model** is a standard way to cut labelling time ([Roboflow: Grounding DINO to train a YOLO model](https://roboflow.com/train/grounding-dino-and-yolo-nas)). We already have an open-vocabulary backend (YOLO-World, PR #46).
- **Open Images V7 has `Human leg` (269), `Human foot` (265), `Backpack` (15), `Handbag` (237)** ([Ultralytics docs](https://docs.ultralytics.com/datasets/detect/open-images-v7)); it can pre-train, but our own test shows it does not transfer to the 0.10 m view without fine-tuning.
- **Not found:** a public dataset of floor-level robot-camera images with cables, shoes and legs; a benchmark of YOLOv8n fine-tuned on about 300 to 1000 such images. We do not know the number we will reach; the plan treats the targets as proposals until measured.

## 3. What we do, in order (Implementation Plan weeks 3 to 5)

1. **D5, our own data (DQK records, all label).** Robot camera, lens 0.10 m, matte and glossy floors, two rooms, three lightings, 0.3-1.5 m; at least 150 images per class (leg and foot, wire black and white straight and curled, footwear, backpack and bag, furniture) and 20 % empty-floor negatives; one whole session held out for the T1. Legs: team members (or volunteers with consent), no faces in frame.
2. **Auto-label with YOLO-World** (prompts: leg, shoe, sandal, slipper, backpack, bag, cable, wire), then correct by hand; split the correction work three ways.
3. **Fine-tune YOLOv8n from COCO weights** on the laptop; compare input sizes 320, 416 and 640 (the Nano runs YOLOv8n at 320 in 14.8 ms, `docs/Edge Deployment.md`).
4. **Wires:** if box recall stays under 80 %, train a segmentation model (YOLOv8n-seg or a small strip-convolution network) on polygon labels plus pasted synthetic wires; a **geometric fallback** (thin dark or bright line on the floor, ground-plane check across frames while driving) gives the keep-clear rule a signal even if the learned model fails.
5. **Evaluate** per class on the held-out session (recall, precision, distance error) and run the exploration T2 with the whole set in the arena. A class that misses its target is reported as not met, with the speed cap and keep-clear rule as the mitigation.

## 4. Decisions still open for the team (Sun Oct 25)

- The targets in section 4.3 (legs, footwear, backpacks: recall >= 90 %, precision >= 80 %; wires: recall >= 80 %, <= 1 false alarm per 20 empty-floor frames) are the assistant's proposal.
- Whether human legs count as obstacles in every phase (proposed: yes, for repulsion in exploration and for the pursuit override; they are never targets by themselves).
- Whether the 15 deg down-tilt wedge of the spec is worth mounting (it improves feet and floor visibility at close range); the camera is currently level and the tilt is measured per session.
