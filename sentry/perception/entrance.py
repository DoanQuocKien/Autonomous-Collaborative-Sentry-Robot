"""Entrance recognition: is THE door of this room in view, and where (bearing)?  Owner: KR (first version written by DQK, 2026-10-12).

Assumption (DQK, 2026-10-12): one entrance door per room, so the detector only has to say "the entrance is in view" (a room with several similar doors is out of scope).
Two methods, chosen by the D1 bake-off (reports/DoanQuocKien/week-02/d1/entrance_bench_2026-10-12.md; ORB was far weaker on both doors):

* XFeat (CVPR 2024, vendored in third_party/xfeat, CPU-capable): sparse local features + mutual nearest neighbour + RANSAC homography against a ROBOT-EYE reference frame.
  Inliers above a threshold (27 on D1) = door in view. The bearing is the projected centre of the door ROI given at enrolment, else the centroid of the inlier points
  (a ROI that is not covered by the matches would be extrapolated by the homography: a whole-frame ROI blew up at 1 m on D1).
* DINOv2 (torch hub, pinned commit): global descriptor (cls + GeM of the patch tokens), cosine similarity to the reference descriptors. A phone photo is enough as a
  reference here, but the threshold differs per room: `calibrate()` sets it from a sweep of the room without the door.

policy "auto": XFeat when robot-eye references are enrolled, else DINOv2; "and" / "or" combine both. Everything is injectable (matcher / describer) so the logic is tested without weights.
Frames are the RAW fisheye frames (640x480 BGR from the ZMQ stream), exactly as in the bench; the bearing is computed through the fisheye model of calib/camera.json.
Bearing convention: radians off the optical axis, positive = LEFT (the same sign as the robot's w).

    det = EntranceDetector(Camera.from_json("calib/camera.json"))
    det.enroll_robot([ref_frame], rois=[(x0, y0, x1, y1)])       # frames from the robot's own camera, hold-out position (e.g. 2 m, 0 deg)
    det.enroll_phone(cv2.imread("data/D1/class_door_iref.jpg"))   # optional, for the DINOv2 path
    det.calibrate(sweep_frames_without_the_door)
    result = det.detect(frame)       # EntranceResult(in_view, inliers, similarity, bearing_rad, quad)
    event = EntranceFilter().update(result)   # None | ("ENTRANCE_FOUND", bearing_rad) | ("ENTRANCE_LOST", None) for the state machine
"""
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
XFEAT_WEIGHTS = ROOT / "weights" / "xfeat.pt"             # python -m tools.fetch_models
DINO_REPO = "facebookresearch/dinov2:7764ea0f912e53c92e82eb78a2a1631e92725fc8"   # same pin as tools/fetch_models.py; python -m tools.fetch_models --dino b


@dataclass(frozen=True)
class EntranceConfig:
    xfeat_top_k: int = 2048
    min_inliers: int = 27            # D1 bake-off: the threshold taken from the harder (cafe) door gave TPR 1.00 / FPR 0.00 on the classroom door; calibrate() may raise it
    ransac_px: float = 5.0
    min_area_ratio: float = 0.05     # area of the inliers' hull in the frame / in the reference (scale squared): reject degenerate homographies
    max_area_ratio: float = 8.0
    dino_size: str = "b"             # "s" is 4x smaller (use it on a CPU-only laptop)
    dino_margin: float = 0.02        # added to the 99th percentile of the negatives' similarity
    policy: str = "auto"             # auto | xfeat | dino | and | or
    enter_frames: int = 3            # EntranceFilter: consecutive in-view frames for ENTRANCE_FOUND
    exit_frames: int = 5             # consecutive frames without it for ENTRANCE_LOST

    @classmethod
    def from_toml(cls, section):
        """config.toml [entrance] -> EntranceConfig (unknown keys are an error: a typo must not silently keep a default)."""
        return cls(**section)


@dataclass
class EntranceResult:
    in_view: bool
    inliers: int = 0                   # best XFeat RANSAC inliers over the references (0 without robot references)
    similarity: float = None           # best DINOv2 cosine similarity (None without references)
    bearing_rad: float = None          # of the door ROI centre, positive = left; None when no homography
    quad: list = None                  # polygon of the matched region in the frame: the projected door ROI when one was given, else the convex hull of the inliers

    def estimate_door_world_xy(self, robot_pose, distance_m: float | None = None):
        """Estimate 2D global coordinate (x, y) of the door when in view.
        Uses robot pose and bearing plus a measured range from the same pose
        origin. Bearing alone provides no world position: returns None without
        a range. Caller must account for the camera-to-pose offset first.
        """
        if not self.in_view or self.bearing_rad is None or distance_m is None:
            return None
        # Bearing convention in EntranceResult: positive = LEFT (+yaw)
        yaw = getattr(robot_pose, "yaw_rad", getattr(robot_pose, "theta", None))
        x = getattr(robot_pose, "x_m", getattr(robot_pose, "x", None))
        y = getattr(robot_pose, "y_m", getattr(robot_pose, "y", None))
        values = (x, y, yaw, self.bearing_rad, distance_m)
        if any(v is None or not math.isfinite(v) for v in values) or distance_m <= 0:
            raise ValueError("finite pose/bearing and positive measured door range required")
        theta = yaw + self.bearing_rad
        door_x = x + distance_m * math.cos(theta)
        door_y = y + distance_m * math.sin(theta)
        return (door_x, door_y)


class Camera:
    """Fisheye intrinsics (calib/camera.json, OpenCV equidistant model) -> bearing of a raw pixel."""

    def __init__(self, K, D=None):
        self.K = np.asarray(K, np.float64)
        self.D = np.zeros(4) if D is None else np.asarray(D, np.float64)

    @classmethod
    def from_json(cls, path):
        c = json.loads(Path(path).read_text())
        return cls(c["K"], c["D"])

    def bearing_rad(self, u, v):
        x = cv2.fisheye.undistortPoints(np.array([[[u, v]]], np.float64), self.K, self.D)[0, 0, 0]   # x / z of the undistorted ray
        return -math.atan(float(x))


# ---- backends (heavy: torch, weights). Tests inject fakes instead. ----------------------------------------------------------------------------------------------------

class XFeatMatcher:
    def __init__(self, weights=XFEAT_WEIGHTS, top_k=2048, device=None):
        from third_party.xfeat import XFeat
        if not Path(weights).exists():
            raise FileNotFoundError("%s missing: run python -m tools.fetch_models" % weights)
        self.xf, self.top_k = XFeat(weights, top_k=top_k, device=device), top_k

    def features(self, bgr):
        f = self.xf.detectAndCompute(self.xf.parse_input(bgr), top_k=self.top_k)[0]
        return {"kp": f["keypoints"].cpu().numpy(), "desc": f["descriptors"]}

    def match(self, ref, cur):
        """-> (points in the reference, points in the frame), mutual nearest neighbours."""
        if len(ref["kp"]) == 0 or len(cur["kp"]) == 0:
            return np.zeros((0, 2), np.float32), np.zeros((0, 2), np.float32)
        i0, i1 = self.xf.match(ref["desc"], cur["desc"], min_cossim=-1)
        return ref["kp"][i0.cpu().numpy()], cur["kp"][i1.cpu().numpy()]


class DinoDescriber:
    def __init__(self, size="b", device=None):
        import torch
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.half = self.dev == "cuda"
        m = torch.hub.load(DINO_REPO, "dinov2_vit%s14" % size, trust_repo=True, verbose=False).to(self.dev).eval()
        self.model = m.half() if self.half else m
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.dev).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.dev).view(1, 3, 1, 1)

    def describe(self, images):
        """list of BGR images -> (N, D) L2-normalised descriptors (cls token + GeM of the patch tokens), 448x336 input as in the bench."""
        torch = self.torch
        t = np.stack([cv2.resize(cv2.cvtColor(i, cv2.COLOR_BGR2RGB), (448, 336)) for i in images])
        x = (torch.from_numpy(t).to(self.dev).permute(0, 3, 1, 2).float() / 255 - self.mean) / self.std
        with torch.no_grad():
            o = self.model.forward_features(x.half() if self.half else x)
            cls, pat = o["x_norm_clstoken"].float(), o["x_norm_patchtokens"].float()
            gem = pat.clamp(min=1e-6).pow(3).mean(1).pow(1 / 3)
            return torch.nn.functional.normalize(torch.cat([cls, gem], 1), dim=1).cpu().numpy()


# ---- the detector -----------------------------------------------------------------------------------------------------------------------------------------------------

def _hull_area(points):
    return float(cv2.contourArea(cv2.convexHull(np.float32(points).reshape(-1, 1, 2))))


class EntranceDetector:
    def __init__(self, camera=None, config=None, matcher=None, describer=None):
        self.cam, self.cfg = camera, config or EntranceConfig()
        self._matcher, self._describer = matcher, describer
        self.robot_refs = []                 # dicts: image, door ROI quad, XFeat features
        self.phone_images = []               # photos that are not from the robot: only the DINOv2 path uses them
        self._descs = None                   # DINOv2 descriptors of every reference image, built on first use
        self.xfeat_thr, self.dino_thr = self.cfg.min_inliers, None

    # lazy backends
    @property
    def matcher(self):
        if self._matcher is None:
            self._matcher = XFeatMatcher(top_k=self.cfg.xfeat_top_k)
        return self._matcher

    @property
    def describer(self):
        if self._describer is None:
            self._describer = DinoDescriber(self.cfg.dino_size)
        return self._describer

    # enrolment
    def enroll_robot(self, frames, rois=None):
        """frames: reference frames from the robot's own camera (a position left out of any evaluation). rois: per frame (x0, y0, x1, y1) around the door, or None (bearing = centroid of the inliers)."""
        for i, f in enumerate(frames):
            roi = rois[i] if rois and rois[i] else None
            quad = None if roi is None else np.float32([[roi[0], roi[1]], [roi[2], roi[1]], [roi[2], roi[3]], [roi[0], roi[3]]])
            self.robot_refs.append({"image": f, "quad": quad, "feats": self.matcher.features(f), "roi": None if roi is None else list(roi)})
        self._descs = None

    def enroll_phone(self, images):
        """Photos of the door that are not from the robot (a phone): only the DINOv2 path can use them (XFeat on a phone photo: AUC 0.87-0.98 vs 0.99-1.00 on D1)."""
        self.phone_images += list(images if isinstance(images, (list, tuple)) else [images])
        self._descs = None

    def ref_descs(self):
        """DINOv2 descriptors of all reference images (the phone photos are resized to the robot frame size)."""
        if self._descs is None:
            imgs = [r["image"] for r in self.robot_refs] + [cv2.resize(i, (640, 480)) for i in self.phone_images]
            self._descs = self.describer.describe(imgs) if imgs else np.zeros((0, 0))
        return self._descs

    def calibrate(self, negatives):
        """negatives: frames of the room WITHOUT the door in view (a sweep). Sets the XFeat threshold (99th percentile of the negatives' inliers + 2, never below min_inliers)
        and the DINOv2 threshold (99th percentile of the similarities + dino_margin). -> (xfeat_thr, dino_thr)."""
        if self._uses_xfeat():
            ins = [self._xfeat(f)[0] for f in negatives]
            self.xfeat_thr = max(self.cfg.min_inliers, int(math.ceil(np.percentile(ins, 99))) + 2)
        if self._uses_dino():
            sims = [self._similarity(d) for d in self.describer.describe(list(negatives))]
            self.dino_thr = float(np.percentile(sims, 99)) + self.cfg.dino_margin
        return self.xfeat_thr, self.dino_thr

    # detection
    def _uses_xfeat(self):
        return bool(self.robot_refs) and self.cfg.policy in ("auto", "xfeat", "and", "or")

    def _uses_dino(self):
        have = bool(self.robot_refs or self.phone_images)
        return have and (self.cfg.policy in ("dino", "and", "or") or (self.cfg.policy == "auto" and not self.robot_refs))

    def _similarity(self, desc):
        return float((self.ref_descs() @ desc).max())

    def _xfeat(self, frame):
        """-> (inliers, (centre_uv, polygon) or None) of the best robot reference; None when the homography is degenerate (mirrored, or the matched area changed scale absurdly)."""
        cur, best = self.matcher.features(frame), (0, None)
        for ref in self.robot_refs:
            p0, p1 = self.matcher.match(ref["feats"], cur)
            if len(p0) < 8:
                continue
            H, mask = cv2.findHomography(np.float32(p0), np.float32(p1), cv2.RANSAC, self.cfg.ransac_px)
            if H is None or mask is None:
                continue
            n = int(mask.sum())
            if n <= best[0]:
                continue
            keep = mask.ravel().astype(bool)
            q0, q1 = np.float32(p0)[keep], np.float32(p1)[keep]
            ratio = _hull_area(q1) / max(_hull_area(q0), 1e-9)
            if np.linalg.det(H[:2, :2]) <= 0 or not self.cfg.min_area_ratio <= ratio <= self.cfg.max_area_ratio:
                best = (n, None) if best[1] is None else best
                continue
            if ref["quad"] is not None:
                poly = cv2.perspectiveTransform(ref["quad"].reshape(-1, 1, 2), H).reshape(-1, 2)
                centre = poly.mean(axis=0)
            else:
                poly, centre = cv2.convexHull(q1.reshape(-1, 1, 2)).reshape(-1, 2), q1.mean(axis=0)
            best = (n, (centre, poly))
        return best

    def __call__(self, frame_bgr, t=None):            # the plan's perception-module contract: __call__(frame_bgr, t) -> dataclass
        return self.detect(frame_bgr)

    def detect(self, frame):
        pol = self.cfg.policy
        use_x, use_d = self._uses_xfeat(), self._uses_dino()
        if not (use_x or use_d):
            raise RuntimeError("nothing enrolled for policy %r (enroll_robot / enroll_phone first)" % pol)
        inliers, found, sim = 0, None, None
        ok_x = ok_d = None
        if use_x:
            inliers, found = self._xfeat(frame)
            ok_x = inliers >= self.xfeat_thr and found is not None
        if use_d:
            if self.dino_thr is None:
                raise RuntimeError("DINOv2 threshold not set: call calibrate() with a sweep of the room without the door")
            sim = self._similarity(self.describer.describe([frame])[0])
            ok_d = sim >= self.dino_thr
        oks = [o for o in (ok_x, ok_d) if o is not None]
        in_view = all(oks) if pol == "and" else (any(oks) if pol == "or" else oks[0])
        bearing, quad_out = None, None
        if in_view and found is not None:
            centre, poly = found
            quad_out = [tuple(map(float, p)) for p in poly]
            bearing = self.cam.bearing_rad(centre[0], centre[1]) if self.cam else None
        return EntranceResult(bool(in_view), int(inliers), sim, bearing, quad_out)

    # persistence: reference images + thresholds in one folder (features are recomputed on load, so a weights update cannot leave stale data)
    def save(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        meta = {"config": asdict(self.cfg), "xfeat_thr": self.xfeat_thr, "dino_thr": self.dino_thr, "robot": [], "phone": []}
        for i, r in enumerate(self.robot_refs):
            cv2.imwrite(str(folder / ("robot_%02d.jpg" % i)), r["image"], [cv2.IMWRITE_JPEG_QUALITY, 95])
            meta["robot"].append({"file": "robot_%02d.jpg" % i, "roi": r["roi"]})
        for i, im in enumerate(self.phone_images):
            cv2.imwrite(str(folder / ("phone_%02d.jpg" % i)), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
            meta["phone"].append("phone_%02d.jpg" % i)
        (folder / "entrance.json").write_text(json.dumps(meta, indent=2))

    @classmethod
    def load(cls, folder, camera=None, matcher=None, describer=None):
        folder = Path(folder)
        meta = json.loads((folder / "entrance.json").read_text())
        det = cls(camera, EntranceConfig(**meta["config"]), matcher, describer)
        det.enroll_robot([cv2.imread(str(folder / r["file"])) for r in meta["robot"]], [tuple(r["roi"]) for r in meta["robot"]])
        if meta["phone"]:
            det.enroll_phone([cv2.imread(str(folder / f)) for f in meta["phone"]])
        det.xfeat_thr, det.dino_thr = meta["xfeat_thr"], meta["dino_thr"]
        return det


class EntranceFilter:
    """Debounce for the state machine: ENTRANCE_FOUND after `enter` consecutive in-view results (bearing = median of them), ENTRANCE_LOST after `exit` without."""

    def __init__(self, enter=3, exit=5):
        self.enter, self.exit, self.found = enter, exit, False
        self.hits, self.misses, self.bearings = 0, 0, deque(maxlen=enter)

    def update(self, result):
        if result.in_view:
            self.hits, self.misses = self.hits + 1, 0
            if result.bearing_rad is not None:
                self.bearings.append(result.bearing_rad)
            if not self.found and self.hits >= self.enter:
                self.found = True
                return "ENTRANCE_FOUND", (float(np.median(self.bearings)) if self.bearings else None)
        else:
            self.hits, self.misses = 0, self.misses + 1
            if self.found and self.misses >= self.exit:
                self.found = False
                self.bearings.clear()
                return "ENTRANCE_LOST", None
        return None


# Backward compatibility alias
EntranceMatcher = EntranceDetector

