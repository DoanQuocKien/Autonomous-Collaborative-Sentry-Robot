import math

import cv2
import numpy as np

from sentry.perception.camera_pose import TiltFilter, pose_from_corners

K = np.array([[309.6, 0, 285.8], [0, 306.2, 239.1], [0, 0, 1.0]])
S, BOTTOM = 0.15, 0.12          # 150 mm marker, lower edge 12 cm above the floor


def view(pitch_deg, H, D, roll_deg=0.0, yaw_deg=0.0, offset=0.0):
    """Pixel corners of the marker seen by a camera at height H, distance D from the wall, looking down by pitch (marker frame: x right, y up, z out)."""
    p, r, w = math.radians(pitch_deg), math.radians(roll_deg), math.radians(yaw_deg)
    z = np.array([math.sin(w) * math.cos(p), -math.sin(p), -math.cos(w) * math.cos(p)])      # optical axis, into the wall
    x = np.cross(z, [0, 1, 0]); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    x, y = math.cos(r) * x - math.sin(r) * y, math.sin(r) * x + math.cos(r) * y                # camera roll about the axis
    y = np.cross(z, x)
    R = np.array([x, y, z])
    C = np.array([offset, H - (BOTTOM + S / 2), D])
    t = -R @ C
    s = S / 2
    obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], np.float64)
    px, _ = cv2.projectPoints(obj, cv2.Rodrigues(R)[0], t, K, None)
    return px.reshape(4, 2)


def est(pitch, D, H=0.10, noise=None, **kw):
    px = view(pitch, H, D, **kw)
    return pose_from_corners(px if noise is None else px + noise, K, S, BOTTOM, camera_h_m=0.10)


def test_noise_free_tilt_height_and_roll_are_exact_for_any_yaw_and_roll():
    for yaw, off, roll in ((0, 0, 0), (20, 0.2, 1.5), (20, 0.2, -1.5), (30, 0, 3)):
        e = est(2.6, 1.5, yaw_deg=yaw, offset=off, roll_deg=roll)
        assert abs(e["pitch_deg"] - 2.6) < 0.01 and abs(e["roll_deg"] - roll) < 0.01 and abs(e["pitch_ori_deg"] - 2.6) < 0.01
        assert abs(e["height_m"] - 0.10) < 1e-3 and abs(e["distance_m"] - 1.5) < 1e-3


def test_filtered_tilt_is_within_1_deg_up_to_2m_with_pixel_noise():
    rng = np.random.default_rng(0)           # 0.3 px corner noise, 15 frames; measured 90th percentile: 0.3 deg at 1 m, 0.8 at 1.5 m, 1.2 at 2 m
    for pitch in (-3.0, 2.6, 10.0):
        for D, tol in ((1.0, 0.8), (1.5, 1.2)):
            f = TiltFilter(max_distance_m=3.0)
            for _ in range(15):
                f.update(est(pitch, D, yaw_deg=20, offset=0.2, roll_deg=1.5, noise=rng.normal(0, 0.3, (4, 2))))
            assert abs(f.pitch_deg - pitch) < tol, (pitch, D, f.pitch_deg)


def test_filter_rejects_a_jump_and_keeps_the_last_value_without_marker():
    f = TiltFilter(default_pitch_deg=-2.3)
    assert f.pitch_deg == -2.3 and not f.update(None)
    for _ in range(8):
        assert f.update(est(-2.3, 1.5, yaw_deg=10))
    assert abs(f.pitch_deg + 2.3) < 0.05
    assert not f.update(est(9.0, 1.5, yaw_deg=10)) and f.rejected == 1   # a bumped frame
    assert abs(f.pitch_deg + 2.3) < 0.05 and not f.update(None)


def test_end_to_end_on_a_rendered_marker():
    px = view(2.6, 0.10, 1.2, yaw_deg=15)
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 3, 200)
    m = cv2.copyMakeBorder(m, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    src = np.float32([[20, 20], [219, 20], [219, 219], [20, 219]])   # the marker occupies [20, 219] of the 240 px sheet
    page = cv2.warpPerspective(m, cv2.getPerspectiveTransform(src, np.float32(px)), (640, 480), flags=cv2.INTER_LINEAR, borderValue=200)
    e = TiltFilter().update_frame(cv2.cvtColor(page, cv2.COLOR_GRAY2BGR), K, S, BOTTOM, marker_id=3, camera_h_m=0.10)
    assert e is not None and abs(e["pitch_deg"] - 2.6) < 1.5


def fisheye_view(pitch_deg, D, **kw):
    """The same view through the real fisheye model of calib/camera.json (equidistant + k1..k4), then undistorted back to pinhole pixels with P = K."""
    import json
    from pathlib import Path
    cam = json.loads((Path(__file__).resolve().parent.parent / "calib" / "camera.json").read_text())
    Kf, Df = np.array(cam["K"]), np.array(cam["D"])
    p, w = math.radians(pitch_deg), math.radians(kw.get("yaw_deg", 0.0))
    z = np.array([math.sin(w) * math.cos(p), -math.sin(p), -math.cos(w) * math.cos(p)])
    x = np.cross(z, [0, 1, 0]); x /= np.linalg.norm(x)
    R = np.array([x, np.cross(z, x), z])
    t = -R @ np.array([kw.get("offset", 0.0), 0.10 - (BOTTOM + S / 2), D])
    s = S / 2
    obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], np.float64).reshape(-1, 1, 3)
    raw, _ = cv2.fisheye.projectPoints(obj, cv2.Rodrigues(R)[0], t, Kf, Df)
    return cv2.fisheye.undistortPoints(raw, Kf, Df, P=Kf).reshape(4, 2), Kf


def test_fisheye_round_trip_recovers_the_tilt():
    rng = np.random.default_rng(1)
    for pitch in (-2.3, 2.6):
        px, Kf = fisheye_view(pitch, 1.5, yaw_deg=15, offset=0.1)
        e = pose_from_corners(px, Kf, S, BOTTOM, camera_h_m=0.10)
        assert abs(e["pitch_deg"] - pitch) < 0.05, (pitch, e)       # noise-free: the undistortion is the only difference
        f = TiltFilter(max_distance_m=3.0)
        for _ in range(15):
            f.update(pose_from_corners(px + rng.normal(0, 0.3, (4, 2)), Kf, S, BOTTOM, camera_h_m=0.10))
        assert abs(f.pitch_deg - pitch) < 1.2


def test_off_axis_marker_uses_the_filters_roll_not_its_own():
    f = TiltFilter(default_pitch_deg=5.0)
    f.update(pose_from_corners(view(5.0, 0.10, 1.2, roll_deg=1.0), K, S, BOTTOM, 0.10))        # centred marker: trusted roll
    assert abs(f.roll_deg - 1.0) < 0.05 and len(f.roll_hist) == 1
    far = pose_from_corners(view(5.0, 0.10, 1.2, offset=0.5, roll_deg=1.0), K, S, BOTTOM, 0.10)
    assert abs(far["bearing_rad"]) > f.centred
    f.update(far)
    assert len(f.roll_hist) == 1 and abs(f.roll_deg - 1.0) < 0.05             # off-axis roll not folded in
    g = TiltFilter()
    assert g.update(far) and not g.roll_hist                                     # no trusted roll yet: the marker's own roll is used, but not kept


def test_camera_geometry_takes_a_live_pitch():
    from sentry.perception.camera import CameraGeometry
    import json
    g = CameraGeometry(json.load(open("calib/camera.json")), {"H_cam_m": 0.1, "pitch_down_deg": 5.0, "passed": True})
    a = g.ground_point(285, 300).forward_m
    g.set_pitch_deg(6.0)
    assert g.ground_point(285, 300).forward_m < a
