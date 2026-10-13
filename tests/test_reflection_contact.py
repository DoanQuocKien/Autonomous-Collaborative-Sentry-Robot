import csv
import json

import numpy as np
import pytest

from sentry.config import load
from sentry.perception.camera import CameraGeometry
from sentry.perception.contact import ReflectionContactEstimator
from sentry.perception.obstacle import Detection, ObstacleDetector


def reflected_image():
    image = np.full((80, 120, 3), 180, np.uint8)
    pattern = np.array([120, 30, 90, 50, 130, 20, 100, 40], np.uint8)
    image[35:43, 30:70] = pattern[:, None, None]
    image[43:51, 30:70] = (180 - (180-pattern[::-1].astype(float))*0.7).astype(np.uint8)[:, None, None]
    return image


def test_symmetry_recovers_contact_not_apparent_bottom():
    result = ReflectionContactEstimator(load()["obstacle"])(reflected_image(), (30, 35, 70, 51))
    assert result is not None and abs(result.v-42.5) <= 1
    assert result.v < 51-5 and result.method == "reflection_symmetry"


@pytest.mark.parametrize("kind", ["constant", "noise", "invalid_pixels"])
def test_ambiguous_reflection_abstains(kind):
    image = np.full((80, 120, 3), 100, np.uint8)
    valid = None
    if kind == "noise":
        image = np.random.default_rng(532).integers(0,256,(80,120,3), dtype=np.uint8)
    elif kind == "invalid_pixels":
        image = reflected_image()
        valid = np.zeros((80,120),bool)
    assert ReflectionContactEstimator(load()["obstacle"])(image,(30,35,70,51),valid) is None


def detector(box, flat=False, floor="matte"):
    c = load()
    c["obstacle"]["floor_type"] = floor
    g = CameraGeometry.from_files("calib/camera.json","calib/camera_pose_nowedge.json")
    return ObstacleDetector(g, lambda image: [Detection(56,0.9,box,flat)], c["obstacle"],c["thresholds"])


@pytest.mark.parametrize("box", [(0,100,100,300),(100,0,300,300),(500,100,640,300),(100,100,300,480)])
def test_every_border_is_rejected(box):
    result = detector(box)(np.zeros((480,640,3),np.uint8),1)
    assert result.unresolved and not result.ground_points
    assert "truncated" in result.obstacles[0].rejection


def test_unknown_floor_and_low_texture_glossy_never_get_false_clearance():
    frame = np.zeros((480,640,3),np.uint8)
    assert detector((280,100,300,300),floor="unknown")(frame,1).unresolved
    assert detector((280,100,300,300),floor="glossy")(frame,1).obstacles[0].rejection == "reflection_unresolved"
    r = detector((280,100,300,300),flat=True,floor="glossy")(frame,1)
    assert r.obstacles[0].contact.method == "bbox_known_flat" and r.ground_points


def test_measured_session_without_pass_flag_and_negative_pitch():
    camera = dict(K=[[300,0,320],[0,300,240],[0,0,1]],D=[0]*4,image_size=[640,480])
    pose = dict(session="synthetic classroom",H_cam_m=0.1,H_fixed_by_tape=True,
                pitch_down_deg=-2.33,rms_m=0.008,marks_m=[0.5,1,2],rows_px=[310,280,265])
    g = CameraGeometry(camera,pose)
    assert g.pose_status == "measured_session_without_pass_flag"
    assert g.ground_point(320,280).forward_m > 1
    for update in ({"rms_m":0.2},{"H_fixed_by_tape":False},{"passed":False}):
        with pytest.raises(ValueError):
            CameraGeometry(camera,dict(pose,**update))


def test_reflection_contact_flows_into_projection_and_repulsion():
    image = np.full((480,640,3),180,np.uint8)
    small = reflected_image()
    image[200:280,250:370] = small
    d = detector((280,235,320,251),floor="glossy")
    # Supply a rectified synthetic frame to isolate contact/projection integration.
    d.geometry.undistort = lambda frame: frame
    d.geometry.valid[:] = True
    result = d(image,10)
    o = result.obstacles[0]
    assert o.contact is not None and o.ground is not None
    assert o.contact.method == "reflection_symmetry" and o.contact.v < 246
    expected = d.geometry.ground_point(o.contact.u,o.contact.v)
    assert o.ground == expected
    assert result.floor_type == "glossy" and not result.unresolved


def test_single_image_tool_uses_session_pose_and_marks_manual_source(tmp_path):
    import cv2
    from tools.obstacle_image import run
    image = tmp_path / "raw.jpg"
    cv2.imwrite(str(image),np.full((480,640,3),180,np.uint8))
    pose = tmp_path / "session_pose.json"
    pose.write_text(json.dumps(dict(session="synthetic locked classroom",H_cam_m=0.1,
                                   pitch_down_deg=-2.33,H_fixed_by_tape=True,rms_m=0.008,
                                   marks_m=[0.5,1,2],rows_px=[313.5,282,267])))
    regions = tmp_path / "regions.json"
    regions.write_text(json.dumps([dict(id="flat",xyxy=[280,250,300,300],flat_on_floor=True)]))
    summary = run(image,pose,"glossy",tmp_path/"out",manual_regions=regions)
    assert summary["source"] == "manual_regions_geometric_diagnostic"
    assert summary["camera_session"] == "synthetic locked classroom"
    with (tmp_path/"out/observations.csv").open(newline="") as f:
        row = next(csv.DictReader(f))
    assert float(row["forward_m"])>0 and row["floor_type"]=="glossy"
    assert row["contact_method"]=="bbox_known_flat"
