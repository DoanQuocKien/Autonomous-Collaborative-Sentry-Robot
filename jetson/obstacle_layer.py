"""Stage A on-robot obstacle ground-distance, repulsion, and laptop fallback switch.

Python 3.6-compatible; uses only the Python standard library and numpy (no cv2,
no sentry.* imports). Designed for the Jetson Nano alongside TensorRT + yolo_post.
"""
import json
import math
import os

import numpy as np


DEFAULT_CLASS_IDS = (56, 57, 58, 59, 60, 62, 72, 28)  # chair, couch, plant, bed, table, tv, fridge, suitcase


def _is_finite_num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    return math.isfinite(float(x))


def _load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _validate_pose(pose, max_pose_rms_m):
    if not _is_finite_num(max_pose_rms_m) or float(max_pose_rms_m) <= 0.0:
        raise ValueError("positive finite pose RMS limit required")
    if "passed" in pose:
        if pose["passed"] is not True:
            raise ValueError("camera pose calibration must pass")
        return "explicit_pass"
    marks = pose.get("marks_m", [])
    rows = pose.get("rows_px", [])
    rms = pose.get("rms_m", math.inf)
    if (
        not pose.get("session")
        or pose.get("H_fixed_by_tape") is not True
        or len(marks) < 3
        or len(marks) != len(rows)
        or not all(_is_finite_num(v) for v in list(marks) + list(rows) + [rms])
        or not 0.0 <= float(rms) <= float(max_pose_rms_m)
        or any(float(v) <= 0.0 for v in marks)
    ):
        raise ValueError("session camera pose needs tape height and finite fit evidence")
    return "measured_session_without_pass_flag"


class EdgeCameraModel(object):
    """Pure-numpy equidistant fisheye undistortion and ground-plane projection.

    Matches `sentry.perception.camera.CameraGeometry` without importing OpenCV.
    """

    def __init__(self, camera, pose, max_range_m=5.0, max_pose_rms_m=0.03):
        self.K = np.asarray(camera["K"], dtype=np.float64)
        self.D = np.asarray(camera["D"], dtype=np.float64).reshape(-1)
        self.size = tuple(camera["image_size"])
        self.height_m = float(pose["H_cam_m"])
        self.pitch = math.radians(float(pose["pitch_down_deg"]))
        self.roll = math.radians(float(pose.get("camera_roll_deg", 0.0)))
        self.max_range_m = float(max_range_m)
        self.session = pose.get("session", pose.get("tag", "unspecified"))
        self.pose_status = _validate_pose(pose, max_pose_rms_m)

        if (
            self.K.shape != (3, 3)
            or self.D.size != 4
            or not np.isfinite(self.K).all()
            or not np.isfinite(self.D).all()
            or self.K[0, 0] <= 0.0
            or self.K[1, 1] <= 0.0
            or not np.allclose(self.K[2], [0.0, 0.0, 1.0])
            or self.K[0, 1] != 0.0
            or self.K[1, 0] != 0.0
        ):
            raise ValueError("invalid fisheye intrinsics (zero skew required)")
        if len(self.size) != 2 or any(type(n) is not int or n <= 0 for n in self.size):
            raise ValueError("invalid calibrated image size")
        if (
            not all(_is_finite_num(v) for v in (self.height_m, self.pitch, self.roll, self.max_range_m))
            or self.height_m <= 0.0
            or self.max_range_m <= 0.0
            or abs(self.pitch) >= math.pi / 2.0
        ):
            raise ValueError("invalid camera geometry")

        self._fx = float(self.K[0, 0])
        self._fy = float(self.K[1, 1])
        self._cx = float(self.K[0, 2])
        self._cy = float(self.K[1, 2])
        self._k1, self._k2, self._k3, self._k4 = [float(v) for v in self.D]

    @classmethod
    def from_files(cls, camera_path, pose_path, max_range_m=5.0, max_pose_rms_m=0.03):
        return cls(_load_json(camera_path), _load_json(pose_path), max_range_m, max_pose_rms_m)

    def set_pitch_deg(self, deg):
        if not _is_finite_num(deg) or abs(float(deg)) >= 90.0:
            raise ValueError("invalid pitch")
        self.pitch = math.radians(float(deg))

    def undistort_point(self, u, v, iters=12):
        """Raw fisheye pixel -> same-K rectified pixel via Newton-Raphson on equidistant model."""
        if not (_is_finite_num(u) and _is_finite_num(v)):
            raise ValueError("pixel coordinates must be finite")
        xd = (float(u) - self._cx) / self._fx
        yd = (float(v) - self._cy) / self._fy
        theta_d = math.hypot(xd, yd)
        if theta_d < 1e-12:
            return float(u), float(v)

        # Solve theta * (1 + k1*t^2 + k2*t^4 + k3*t^6 + k4*t^8) = theta_d
        theta_d_clipped = max(-math.pi / 2.0, min(math.pi / 2.0, theta_d))
        theta = theta_d_clipped
        k1, k2, k3, k4 = self._k1, self._k2, self._k3, self._k4
        for _ in range(iters):
            t2 = theta * theta
            t4 = t2 * t2
            t6 = t4 * t2
            t8 = t4 * t4
            f = theta * (1.0 + k1 * t2 + k2 * t4 + k3 * t6 + k4 * t8) - theta_d_clipped
            df = 1.0 + 3.0 * k1 * t2 + 5.0 * k2 * t4 + 7.0 * k3 * t6 + 9.0 * k4 * t8
            if abs(df) < 1e-12:
                break
            step = f / df
            theta -= step
            if abs(step) < 1e-12:
                break

        theta = max(-math.pi / 2.0 + 1e-9, min(math.pi / 2.0 - 1e-9, theta))
        scale = math.tan(theta) / theta_d
        xr = xd * scale
        yr = yd * scale
        return self._fx * xr + self._cx, self._fy * yr + self._cy

    def undistort_points(self, pts):
        arr = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        out = np.empty_like(arr)
        for i in range(arr.shape[0]):
            out[i, 0], out[i, 1] = self.undistort_point(float(arr[i, 0]), float(arr[i, 1]))
        return out

    def ground_point(self, u_rect, v_rect):
        """Intersect a same-K rectified pixel ray with the floor -> dict or None."""
        if not (_is_finite_num(u_rect) and _is_finite_num(v_rect)):
            return None
        w, h = self.size
        u = float(u_rect)
        v = float(v_rect)
        if not (0.0 <= u < w and 0.0 <= v < h):
            return None

        du, dv = u - self._cx, v - self._cy
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        right = (cr * du + sr * dv) / self._fx
        down = (-sr * du + cr * dv) / self._fy
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        forward = cp - sp * down
        vertical = sp + cp * down
        if vertical <= 0.0 or forward <= 0.0:
            return None
        scale = self.height_m / vertical
        fwd_m = scale * forward
        left_m = -scale * right
        dist_m = math.hypot(fwd_m, left_m)
        if dist_m > self.max_range_m:
            return None
        return {
            "forward_m": fwd_m,
            "left_m": left_m,
            "distance_m": dist_m,
            "bearing_rad": math.atan2(left_m, fwd_m),
        }

    def raw_pixel_to_ground(self, u_raw, v_raw):
        if not (_is_finite_num(u_raw) and _is_finite_num(v_raw)):
            return None
        ur, vr = self.undistort_point(u_raw, v_raw)
        return self.ground_point(ur, vr)


def _point_fields(pt):
    if isinstance(pt, dict):
        return float(pt["left_m"]), float(pt["distance_m"])
    if hasattr(pt, "left_m") and hasattr(pt, "distance_m"):
        return float(pt.left_m), float(pt.distance_m)
    if isinstance(pt, (tuple, list)) and len(pt) == 2:
        fwd, left = float(pt[0]), float(pt[1])
        return left, math.hypot(fwd, left)
    raise TypeError("unsupported ground point: %r" % (pt,))


def repulsive_w(points, threshold_m, gain=1.0, max_w=1.0, centre_turn=1):
    """Left obstacle -> negative w (right turn); right obstacle -> positive w."""
    if (
        not all(_is_finite_num(v) for v in (threshold_m, gain, max_w))
        or float(threshold_m) <= 0.0
        or float(gain) < 0.0
        or not 0.0 < float(max_w) <= 1.0
        or centre_turn not in (-1, 1)
    ):
        raise ValueError("invalid repulsion parameters")
    thr = float(threshold_m)
    g = float(gain)
    mw = float(max_w)
    total = 0.0
    for pt in points:
        left_m, dist_m = _point_fields(pt)
        if dist_m < thr:
            sign = -1 if left_m > 0.0 else (1 if left_m < 0.0 else centre_turn)
            total += sign * g * (1.0 - dist_m / thr)
    return float(np.clip(total, -mw, mw))


def _mix_legal(v, w, dead, k=1.0):
    if not (_is_finite_num(v) and _is_finite_num(w)):
        return False
    if v == 0.0 and w == 0.0:
        return True
    if abs(v) > 1.0 or abs(w) > 1.0:
        return False
    left = v - k * w
    right = v + k * w
    m = max(abs(left), abs(right))
    if m > 1.0:
        left, right = left / m, right / m
    return abs(left) >= dead - 1e-9 and abs(right) >= dead - 1e-9


def _normalize_detections(detections):
    """Accept yolo_post.decode tuple (boxes, scores, cls[, kpts]) or list of tuples/dicts."""
    if detections is None:
        return []
    if (
        isinstance(detections, tuple)
        and len(detections) in (3, 4)
        and hasattr(detections[0], "shape")
    ):
        boxes, scores, cls_ids = detections[0], detections[1], detections[2]
        out = []
        for i in range(len(boxes)):
            b = boxes[i]
            out.append({
                "class_id": int(cls_ids[i]),
                "confidence": float(scores[i]),
                "xyxy": (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                "flat_on_floor": False,
                "contact_uv": None,
            })
        return out

    out = []
    for det in detections:
        if isinstance(det, dict):
            out.append({
                "class_id": int(det["class_id"]),
                "confidence": float(det["confidence"]),
                "xyxy": tuple(float(x) for x in det["xyxy"]),
                "flat_on_floor": bool(det.get("flat_on_floor", False)),
                "contact_uv": det.get("contact_uv"),
            })
        elif hasattr(det, "class_id") and hasattr(det, "confidence") and hasattr(det, "xyxy"):
            out.append({
                "class_id": int(det.class_id),
                "confidence": float(det.confidence),
                "xyxy": tuple(float(x) for x in det.xyxy),
                "flat_on_floor": bool(getattr(det, "flat_on_floor", False)),
                "contact_uv": getattr(det, "contact_uv", None),
            })
        elif isinstance(det, (tuple, list)) and len(det) == 3:
            cid, conf, xyxy = det
            out.append({
                "class_id": int(cid),
                "confidence": float(conf),
                "xyxy": tuple(float(x) for x in xyxy),
                "flat_on_floor": False,
                "contact_uv": None,
            })
        else:
            raise TypeError("unsupported detection entry: %r" % (det,))
    return out


class EdgeObstacleLayer(object):
    """Python 3.6 ground-distance + angular repulsion + exploration safety controller."""

    def __init__(self, camera_model, settings=None):
        self.camera = camera_model
        s = dict(settings or {})
        self.class_ids = frozenset(s.get("class_ids", DEFAULT_CLASS_IDS))
        self.confidence = float(s.get("confidence", 0.25))
        self.border_margin_px = float(s.get("border_margin_px", 1.0))
        self.floor_type = str(s.get("floor_type", "unknown"))
        self.obstacle_explore_m = float(s.get("obstacle_explore_m", 0.6))
        self.obstacle_pursuit_m = float(s.get("obstacle_pursuit_m", 0.5))
        self.repulsion_gain = float(s.get("repulsion_gain", 1.0))
        self.repulsion_max_w = float(s.get("repulsion_max_w", 1.0))
        self.centre_turn = int(s.get("centre_turn", 1))
        self.stop_m = float(s.get("stop_m", 0.55))
        self.unresolved_bottom = float(s.get("unresolved_bottom", 0.55))
        self.v_forward = float(s.get("v_forward", 0.55))
        self.w_spin = float(s.get("w_spin", 0.45))
        self.clear_frames = int(s.get("clear_frames", 6))
        self.max_spin_s = float(s.get("max_spin_s", 8.0))
        self.min_pwm = float(s.get("min_pwm", 0.12))
        self.max_speed = float(s.get("max_speed", 0.3))

        if not _is_finite_num(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("invalid confidence threshold")
        if not _is_finite_num(self.border_margin_px) or self.border_margin_px < 1.0:
            raise ValueError("border_margin_px must be >= 1.0")
        if self.floor_type not in ("glossy", "matte", "unknown"):
            raise ValueError("invalid floor_type: %r" % (self.floor_type,))
        if not (0.0 <= self.min_pwm < self.max_speed <= 1.0):
            raise ValueError("need 0 <= min_pwm < max_speed <= 1")
        for mode in ("explore", "pursuit"):
            repulsive_w((), self._threshold_for(mode), self.repulsion_gain, self.repulsion_max_w, self.centre_turn)

        self._dead = self.min_pwm / self.max_speed
        self._w_forward_max = max(0.0, self.v_forward - self._dead - 0.01)
        self.state = "FORWARD"
        self.spin_dir = 0
        self.clear_count = 0
        self.spin_t = 0.0

    def reset(self):
        self.state = "FORWARD"
        self.spin_dir = 0
        self.clear_count = 0
        self.spin_t = 0.0

    def _threshold_for(self, mode):
        if mode == "explore":
            return self.obstacle_explore_m
        if mode == "pursuit":
            return self.obstacle_pursuit_m
        raise ValueError("mode must be 'explore' or 'pursuit', got %r" % (mode,))

    def process_detections(self, detections, t, mode="explore", rectified=False, floor_type=None):
        if not _is_finite_num(t):
            raise ValueError("finite timestamp required")
        thr_m = self._threshold_for(mode)
        ft = self.floor_type if floor_type is None else str(floor_type)
        if ft not in ("glossy", "matte", "unknown"):
            raise ValueError("invalid floor_type: %r" % (ft,))

        w_img, h_img = self.camera.size
        margin = self.border_margin_px
        items = _normalize_detections(detections)

        observations = []
        points = []
        best_block = None  # (rank, side)

        for det in items:
            if det["class_id"] not in self.class_ids:
                continue
            conf = det["confidence"]
            if not _is_finite_num(conf) or not 0.0 <= conf <= 1.0 or conf < self.confidence:
                continue
            box = det["xyxy"]
            point = None
            reason = None

            if (
                len(box) != 4
                or not all(_is_finite_num(x) for x in box)
                or not (0.0 <= box[0] < box[2] <= w_img and 0.0 <= box[1] < box[3] <= h_img)
            ):
                reason = "invalid_box"
            elif box[3] >= h_img - margin:
                reason = "bottom_truncated"
            elif box[0] <= margin or box[1] <= margin or box[2] >= w_img - margin:
                reason = "border_truncated"
            else:
                contact_uv = det["contact_uv"]
                if contact_uv is None and (ft == "matte" or det["flat_on_floor"]):
                    contact_uv = ((box[0] + box[2]) / 2.0, box[3])
                if contact_uv is None:
                    reason = "floor_type_unknown" if ft == "unknown" else "reflection_unresolved"
                else:
                    cu, cv = float(contact_uv[0]), float(contact_uv[1])
                    if not (_is_finite_num(cu) and _is_finite_num(cv)):
                        reason = "invalid_contact_pixel"
                    else:
                        if rectified:
                            point = self.camera.ground_point(cu, cv)
                        else:
                            point = self.camera.raw_pixel_to_ground(cu, cv)
                        if point is None:
                            reason = "no_ground_intersection_or_out_of_range"

            if point is not None:
                points.append(point)
                if point["distance_m"] < self.stop_m:
                    side = 1 if point["left_m"] > 0.0 else (-1 if point["left_m"] < 0.0 else 0)
                    if best_block is None or point["distance_m"] < best_block[0]:
                        best_block = (point["distance_m"], side)
            else:
                rejected_near = reason in ("bottom_truncated", "border_truncated")
                if len(box) == 4 and all(_is_finite_num(x) for x in box):
                    if rejected_near or box[3] >= self.unresolved_bottom * h_img:
                        side = 1 if (box[0] + box[2]) / 2.0 < w_img / 2.0 else -1
                        if best_block is None or 0.0 < best_block[0]:
                            best_block = (0.0, side)

            observations.append({
                "class_id": det["class_id"],
                "confidence": conf,
                "xyxy": box,
                "ground": point,
                "rejection": reason,
            })

        rep_w = repulsive_w(points, thr_m, self.repulsion_gain, self.repulsion_max_w, self.centre_turn)
        nearest_m = min((p["distance_m"] for p in points), default=None)
        unresolved = sum(1 for o in observations if o["ground"] is None)

        return {
            "t": float(t),
            "obstacles": observations,
            "ground_points": points,
            "repulsive_w": rep_w,
            "nearest_m": nearest_m,
            "unresolved": unresolved,
            "blocked": best_block is not None,
            "block_side": best_block[1] if best_block is not None else 0,
            "floor_type": ft,
        }

    def step(self, detections, t, dt, mode="explore", rectified=False, floor_type=None):
        """Process frame detections and compute a dead-zone-legal `(v, w)` command."""
        if not _is_finite_num(dt) or float(dt) < 0.0:
            raise ValueError("dt must be finite and >= 0")
        dt = float(dt)
        if detections is None:
            return {
                "t": float(t),
                "source": "edge",
                "v": 0.0,
                "w": 0.0,
                "state": "STOP",
                "reason": "no_frame",
                "repulsive_w": 0.0,
                "nearest_m": None,
                "blocked": False,
                "unresolved": 0,
                "legal": True,
            }

        res = self.process_detections(detections, t, mode=mode, rectified=rectified, floor_type=floor_type)
        blocked = res["blocked"]
        side = res["block_side"]

        if blocked and self.state != "TURN":
            self.state = "TURN"
            self.spin_dir = -side if side else self.centre_turn
            self.clear_count = 0
            self.spin_t = 0.0

        if self.state == "TURN":
            self.spin_t += dt
            self.clear_count = 0 if blocked else self.clear_count + 1
            if self.clear_count >= self.clear_frames:
                self.state = "FORWARD"
            elif self.spin_t > self.max_spin_s:
                return self._out(res, 0.0, 0.0, "STOP", "stuck")
            else:
                return self._out(res, 0.0, float(self.spin_dir * self.w_spin), "TURN", "blocked")

        w = max(-self._w_forward_max, min(self._w_forward_max, res["repulsive_w"]))
        return self._out(res, self.v_forward, w, "FORWARD", "clear" if w == 0.0 else "steer")

    def _out(self, res, v, w, state, reason):
        is_legal = _mix_legal(v, w, self._dead)
        if not is_legal:
            v, w, state, reason = 0.0, 0.0, "STOP", "illegal_command"
            is_legal = True
        return {
            "t": res["t"],
            "source": "edge",
            "v": float(v),
            "w": float(w),
            "state": state,
            "reason": reason,
            "repulsive_w": res["repulsive_w"],
            "nearest_m": res["nearest_m"],
            "blocked": res["blocked"],
            "unresolved": res["unresolved"],
            "legal": is_legal,
        }


class FallbackSwitch(object):
    """Switch between the on-robot obstacle layer (`edge`) and the `laptop` backup.

    Guarantees the laptop takes over within `timeout_s` (<= 1.0 s) when the
    robot layer is switched off, errors, or goes silent (`Implementation Plan.md` §4.3).
    """

    def __init__(self, timeout_s=0.5, recovery_frames=3, enabled=True):
        if not _is_finite_num(timeout_s) or not 0.0 < float(timeout_s) <= 1.0:
            raise ValueError("timeout_s must be in (0, 1.0] s, got %r" % (timeout_s,))
        if isinstance(recovery_frames, bool) or not isinstance(recovery_frames, int) or recovery_frames < 1:
            raise ValueError("recovery_frames must be int >= 1, got %r" % (recovery_frames,))
        self.timeout_s = float(timeout_s)
        self.recovery_frames = recovery_frames
        self.enabled = bool(enabled)
        self.active_source = "edge" if self.enabled else "laptop"
        self.last_edge_t = None
        self.last_edge_result = None
        self.switch_off_t = None if self.enabled else 0.0
        self.last_fallback_reason = None if self.enabled else "edge_switched_off"
        self.takeover_latency_s = None
        self.fallback_count = 0 if self.enabled else 1
        self._healthy_streak = 0

    def set_edge_enabled(self, enabled, now):
        if not _is_finite_num(now):
            raise ValueError("timestamp must be finite")
        now = float(now)
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if not enabled:
            self.switch_off_t = now
            self._healthy_streak = 0
            self._activate_laptop("edge_switched_off", now, ref_t=now)
        else:
            self.switch_off_t = None
            self._healthy_streak = 0

    def on_edge_error(self, now, reason="edge_error"):
        if not _is_finite_num(now):
            raise ValueError("timestamp must be finite")
        now = float(now)
        self._healthy_streak = 0
        self._activate_laptop(str(reason), now, ref_t=now)

    def on_edge_result(self, result, now):
        if not _is_finite_num(now):
            raise ValueError("timestamp must be finite")
        now = float(now)
        if result is None:
            return
        v, w = float(result["v"]), float(result["w"])
        if not (math.isfinite(v) and math.isfinite(w)):
            self.on_edge_error(now, reason="non_finite_edge_command")
            return
        self.last_edge_t = now
        self.last_edge_result = dict(result)
        if not self.enabled:
            return
        if self.active_source == "laptop":
            self._healthy_streak += 1
            if self._healthy_streak >= self.recovery_frames:
                self.active_source = "edge"
                self.last_fallback_reason = None
                self.takeover_latency_s = None
        else:
            self._healthy_streak = self.recovery_frames

    def _activate_laptop(self, reason, now, ref_t=None):
        if self.active_source != "laptop":
            self.active_source = "laptop"
            self.fallback_count += 1
        self.last_fallback_reason = reason
        if ref_t is not None:
            self.takeover_latency_s = max(0.0, now - ref_t)

    def select(self, now, laptop_result=None):
        """Return the active command dict at wall/sim time `now`."""
        if not _is_finite_num(now):
            raise ValueError("timestamp must be finite")
        now = float(now)

        if not self.enabled:
            if self.active_source != "laptop":
                self._activate_laptop("edge_switched_off", now, ref_t=self.switch_off_t or now)
        elif self.last_edge_t is None or (now - self.last_edge_t) > self.timeout_s:
            self._healthy_streak = 0
            if self.active_source != "laptop":
                ref = self.last_edge_t if self.last_edge_t is not None else now
                self._activate_laptop("edge_timeout" if self.last_edge_t is not None else "no_edge_yet", now, ref_t=ref)

        if self.active_source == "edge" and self.last_edge_result is not None:
            res = self.last_edge_result
            return {
                "source": "edge",
                "v": float(res["v"]),
                "w": float(res["w"]),
                "state": res.get("state", "FORWARD"),
                "reason": res.get("reason", "edge"),
                "fallback_active": False,
                "fallback_reason": None,
                "takeover_latency_s": None,
                "fallback_count": self.fallback_count,
            }

        if laptop_result is None:
            return {
                "source": "laptop",
                "v": 0.0,
                "w": 0.0,
                "state": "STOP",
                "reason": "no_laptop_result",
                "fallback_active": True,
                "fallback_reason": self.last_fallback_reason,
                "takeover_latency_s": self.takeover_latency_s,
                "fallback_count": self.fallback_count,
            }

        return {
            "source": "laptop",
            "v": float(laptop_result["v"]),
            "w": float(laptop_result["w"]),
            "state": laptop_result.get("state", "FORWARD"),
            "reason": laptop_result.get("reason", "laptop"),
            "fallback_active": True,
            "fallback_reason": self.last_fallback_reason,
            "takeover_latency_s": self.takeover_latency_s,
            "fallback_count": self.fallback_count,
        }


def encode_edge_status(seq, result):
    """Serialize an EdgeObstacleLayer step dict to compact UTF-8 JSON bytes."""
    payload = {
        "seq": int(seq),
        "t": float(result["t"]),
        "v": float(result["v"]),
        "w": float(result["w"]),
        "state": str(result.get("state", "STOP")),
        "reason": str(result.get("reason", "")),
        "blocked": bool(result.get("blocked", False)),
        "nearest_m": None if result.get("nearest_m") is None else float(result["nearest_m"]),
        "repulsive_w": float(result.get("repulsive_w", 0.0)),
    }
    return json.dumps(payload).encode("utf-8")


def decode_edge_status(data):
    """Validate and decode a serialized edge obstacle status packet."""
    msg = json.loads(data.decode("utf-8"))
    if not isinstance(msg, dict):
        raise ValueError("expected JSON object")
    seq = msg.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int):
        raise ValueError("seq must be int")
    v = float(msg["v"])
    w = float(msg["w"])
    t = float(msg["t"])
    if not all(math.isfinite(x) for x in (v, w, t)):
        raise ValueError("non-finite numbers in edge status")
    return {
        "seq": seq,
        "t": t,
        "v": max(-1.0, min(1.0, v)),
        "w": max(-1.0, min(1.0, w)),
        "state": str(msg.get("state", "STOP")),
        "reason": str(msg.get("reason", "")),
        "blocked": bool(msg.get("blocked", False)),
        "nearest_m": None if msg.get("nearest_m") is None else float(msg["nearest_m"]),
        "repulsive_w": float(msg.get("repulsive_w", 0.0)),
    }
