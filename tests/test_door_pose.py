import json
import math

import numpy as np
import pytest

from tools.door_pose import fit_pose, locate_joint, scan_from_record, solve_scan
from tools.find_door import add_stop, new_scan, summarise, unreliable_text
from tools.scan_boards import PRIOR_PULSE_RAD, wrap

BOARDS = {0: (3.0, 0.3), 1: (-0.4, -2.2), 2: (-1.5, 2.0)}
DOOR = (2.6, -2.4)


def spin(pos, heading, pulses_deg, boards=BOARDS, door=DOOR, fov_deg=60.0):
    """A noise-free spin scan through tools.find_door.add_stop: the robot at pos turns by pulses_deg (left), boards and door are seen within +/- fov_deg. -> the scan dict."""
    scan = new_scan()
    for k in range(len(pulses_deg) + 1):
        def polar(p):
            return wrap(math.atan2(p[1] - pos[1], p[0] - pos[0]) - heading), math.hypot(p[0] - pos[0], p[1] - pos[1])
        seen = {m: (b, r, r * math.cos(b), r * math.sin(b), 6) for m, (b, r) in ((m, polar(p)) for m, p in boards.items()) if abs(b) <= math.radians(fov_deg)}
        b = polar(door)[0] if door else 9.0
        add_stop(scan, seen, [(b, 100)] * 3 if abs(b) <= math.radians(fov_deg) else [], spin_s=0.2)
        if k < len(pulses_deg):
            heading += math.radians(pulses_deg[k])
    return scan


PULSES = [30, 29, 27, 22, 28, 31, 24, 26, 27, 23, 29, 28, 25, 12]          # 361 deg: uneven on purpose, the last stop sees the first board again


def test_loop_closure_recovers_the_headings_where_the_running_sum_drifts():
    sc = spin((0, 0), 0.0, PULSES)
    s = scan_from_record(sc["record"])
    true = np.cumsum([0] + PULSES)
    assert abs(math.degrees(sc["heading"]) - 361) > 3                                    # the on-line sum fills the pulses without a shared board with the prior / running median
    assert abs(s["headings_deg"][-1] - 361) < 0.3                                        # board 0 at the first and at the last stop closes the loop
    assert np.max(np.abs(np.array(s["headings_deg"]) - true)) < 4.0
    for m, p in BOARDS.items():                                                           # board directions in the start frame, ranges kept
        assert abs(wrap(math.radians(s["boards"][str(m)]["dir_deg"]) - math.atan2(p[1], p[0]))) < math.radians(2.0)
        assert s["boards"][str(m)]["range_m"] == pytest.approx(math.hypot(*p), abs=0.01)
    assert abs(s["door_bearing_deg"] - math.degrees(math.atan2(DOOR[1], DOOR[0]))) < 2.0 and s["door_sd_deg"] < 3.0
    assert s["heading_sd_deg"][0] == 0.0 and s["heading_sd_deg"][-1] < 1.5


def test_no_board_at_all_falls_back_to_the_prior_with_a_growing_sd():
    s = solve_scan([], 6)
    assert s["headings_deg"] == pytest.approx([math.degrees(PRIOR_PULSE_RAD) * k for k in range(6)], abs=0.01)
    assert s["boards"] == {} and s["door_bearing_deg"] is None and s["bearing_resid_rms_deg"] is None
    assert s["heading_sd_deg"][1] > 2.5 and all(b > a for a, b in zip(s["heading_sd_deg"], s["heading_sd_deg"][1:]))
    one = solve_scan([(0, 7, 0.1, 2.0)], 1)                                              # a single stop (dry run)
    assert one["headings_deg"] == [0.0] and one["boards"]["7"]["x_m"] == pytest.approx(2.0 * math.cos(0.1))


def test_the_door_is_the_dominant_cluster_and_false_sightings_are_dropped():
    boards = [(k, 0, math.radians(40 - 25 * k), 3.0) for k in range(4)]
    door = [(k, math.radians(10 - 25 * k), 90) for k in range(3) for _ in range(3)] + [(2, math.radians(55), 28), (3, math.radians(-50), 27)]
    s = solve_scan(boards, 4, door)
    assert abs(s["door_bearing_deg"] - 10.0) < 0.5 and s["door_cluster_sightings"] == 9 and s["door_sightings"] == 11
    assert solve_scan(boards, 4)["door_bearing_deg"] is None


def test_an_irregular_pulse_seen_by_a_board_is_believed_over_the_prior():
    b = [40, 15, -21, -46]                                                               # pulses 25, 36, 25 deg: the 36 is real (measured by the board)
    s = solve_scan([(k, 0, math.radians(v), 2.5) for k, v in enumerate(b)], 4)
    assert np.diff(s["headings_deg"]) == pytest.approx([25, 36, 25], abs=1.5)


def test_fit_pose_recovers_a_known_pose_and_weights_the_accurate_direction():
    th, t = math.radians(40), np.array([0.8, -0.5])
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    pb = [np.array(p) for p in ((2.0, 0.0), (0.0, 3.0), (-2.5, -1.0))]
    pa = [R @ p + t for p in pb]
    eye = [np.eye(2) * 1e-4] * 3
    assert fit_pose(pa, eye, pb, eye)[:3] == pytest.approx((th, 0.8, -0.5), abs=1e-6)
    pa2 = [pa[0] + (0.3, 0.0), pa[1], pa[2]]                                            # point 0 is 0.3 m off along x in frame A...
    loose = [np.diag([1.0, 1e-4]), eye[1], eye[2]]                                       # ...and is declared poor along x: the fit must hardly move
    assert fit_pose(pa2, loose, pb, eye)[:3] == pytest.approx((th, 0.8, -0.5), abs=0.01)
    assert abs(fit_pose(pa2, eye, pb, eye)[1] - 0.8) > 0.05


def test_two_scans_give_the_door_and_an_interval_that_holds_it():
    p2, h2 = (0.9, 0.9), math.radians(140)
    r = locate_joint(scan_from_record(spin((0, 0), 0.0, PULSES)["record"]), scan_from_record(spin(p2, h2, PULSES)["record"]))
    true = math.hypot(DOOR[0] - p2[0], DOOR[1] - p2[1])
    assert r["range_from_second_m"] == pytest.approx(true, rel=0.08)
    lo, hi = r["range_from_second_interval_m"]
    assert lo < true < hi and r["boards_used"] == ["0", "1", "2"] and r["fit_dof"] == 3
    assert (r["door_x_m"], r["door_y_m"]) == pytest.approx(DOOR, abs=0.3)
    assert r["second_position_in_first_frame"] == pytest.approx(list(p2), abs=0.15)
    assert math.hypot(*r["door_in_second_frame"]) == pytest.approx(r["range_from_second_m"], abs=0.01)
    assert r == locate_joint(scan_from_record(spin((0, 0), 0.0, PULSES)["record"]), scan_from_record(spin(p2, h2, PULSES)["record"]))      # fixed seed: reproducible


def test_refusals_are_loud():
    first = scan_from_record(spin((0, 0), 0.0, PULSES)["record"])
    with pytest.raises(ValueError, match="2 boards"):                                    # one common board: the second pose is undetermined
        locate_joint(first, scan_from_record(spin((0.9, 0.9), 2.4, PULSES, boards={0: BOARDS[0]})["record"]))
    with pytest.raises(ValueError, match="not seen"):                                    # no door sighting in the second scan
        locate_joint(first, scan_from_record(spin((0.9, 0.9), 2.4, PULSES, door=None)["record"]))
    with pytest.raises(ValueError, match="do not meet"):                                 # no baseline: the two rays are the same line
        locate_joint(first, scan_from_record(spin((0, 0), 0.0, PULSES)["record"]))
    along = (0.25 * DOOR[0], 0.25 * DOOR[1] + 0.05)                                      # a baseline almost along the line of sight: tiny ray angle -> not reliable, and it says why
    r = locate_joint(first, scan_from_record(spin(along, 0.3, PULSES)["record"]))
    assert not r["range_reliable"] and any("ray angle" in t for t in r["reasons"])


def test_add_stop_keeps_the_online_estimate_and_records_everything_for_replay():
    sc = spin((0, 0), 0.0, PULSES)
    rec = json.loads(json.dumps(sc["record"], allow_nan=False))                          # what find_door writes to observations.json
    assert len(rec["stops"]) == len(PULSES) + 1 and len(rec["pulses"]) == len(PULSES)
    assert rec["stops"][0]["boards"][0][:2] == [0, pytest.approx(math.degrees(math.atan2(0.3, 3.0)), abs=0.01)] and len(rec["stops"][0]["boards"][0]) == 6
    assert rec["pulses"][0] == dict(cmd_w=0.45, cmd_s=0.2, measured_deg=30.0, boards=1)   # measured from board 0
    assert any(p["boards"] == 0 for p in rec["pulses"])                                  # filled pulses are marked
    assert rec["stops"][-1]["heading_deg"] == pytest.approx(math.degrees(sc["heading"]), abs=0.01) == pytest.approx(sum(p["measured_deg"] for p in rec["pulses"]), abs=0.1)
    assert sum(len(st["door"]) for st in rec["stops"]) == len(sc["doors"]) > 0
    s = summarise(sc["boards"], sc["doors"])                                             # the on-line summary is unchanged in shape
    assert set(s["boards"]) == {"0", "1", "2"} and s["door_sightings"] == len(sc["doors"])
    assert scan_from_record(rec)["headings_deg"] == scan_from_record(sc["record"])["headings_deg"]


def test_the_warning_says_what_is_wrong():
    t = unreliable_text(dict(baseline_m=0.94, ray_angle_deg=4.3, board_fit_rms_m=0.291, boards_used=["0", "2"]))
    assert "4.3 deg" in t and "0.94" not in t and "0.29 m" in t and "did not happen" not in t
    assert "0.31 m" in unreliable_text(dict(baseline_m=0.31, ray_angle_deg=12.0, board_fit_rms_m=0.1, boards_used=["0", "2"]))


def test_synthetic_runs_the_new_estimate_beats_the_running_sum():
    from tools.door_pose_sim import one, stats
    s = stats([one(seed, 3, first_boost_deg=4.0) for seed in range(25)])
    assert s["new"]["median_pct"] < s["old"]["median_pct"] and s["new"]["p90_pct"] < s["old"]["p90_pct"] and s["interval_coverage_pct"] >= 80


@pytest.mark.parametrize("name,running_sum_error", [("t2_1111_scan_1", -1.7), ("t2_1111_scan2_1", -8.2)])
def test_real_full_circle_scans_close_the_loop(name, running_sum_error):
    """The two 2026-11-11 scans with per-stop rows: board 0 is seen at the first and at the last stop, so the last heading is 360 + (first bearing - last bearing)."""
    import csv
    from pathlib import Path
    rows = list(csv.DictReader(open(Path(__file__).parent.parent / "reports/DoanQuocKien/week-06/find_door_pose/data" / (name + "_stops.csv"))))
    obs = [(int(r["stop"]), int(r["marker_id"]), math.radians(float(r["bearing_deg"])), float(r["range_m"])) for r in rows]
    n = max(o[0] for o in obs) + 1
    b0 = {o[0]: o[2] for o in obs if o[1] == 0}
    truth = 360 + math.degrees(b0[0] - b0[n - 1])
    assert float(rows[-1]["heading_deg"]) - truth == pytest.approx(running_sum_error, abs=0.05)      # what the running sum did
    s = solve_scan(obs, n)
    assert abs(s["headings_deg"][-1] - truth) < 0.5 and s["heading_sd_deg"][-1] < 1.5 and s["bearing_resid_rms_deg"] < 1.0
