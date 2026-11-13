"""DQK's report figures that can be made from existing evidence (Mid-Term Report Plan section 3): F1 and F2 (diagrams), F4, F5, F6, F20, F21. Every number is read from a committed file (F19 from git history).

  python -m tools.plot_dqk_report_figures            # writes reports/DoanQuocKien/week-05/figures/F*.png

Not here (they need data that does not exist yet): F3 (photo), F7 (raw latency samples). Nothing in the figures is a photo or a face.
"""
import csv
import glob
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "reports" / "DoanQuocKien"
OUT = R / "week-05" / "figures"
BLUE, RED, GREEN, GREY = "#1f5fbf", "#b03030", "#2a7f3f", "#777777"


def box(ax, x, y, w, h, text, color="#dce8fa", fs=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fc=color, ec="#335", lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def arrow(ax, x0, y0, x1, y1, text="", fs=7):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="->", color="#335"))
    if text:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 + 0.25, text, ha="center", va="bottom", fontsize=fs, bbox=dict(fc="white", ec="none", pad=1))


def f1():
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 10.5)
    ax.axis("off")
    box(ax, 0.5, 6.7, 4.0, 2.8, "JetBot (Jetson Nano)\ncamera, motors, e-stop\ncaptures frames, drives", "#e8f3e8")
    box(ax, 8.0, 5.2, 6.0, 4.6, "Laptop\nYOLOv8, pose, InsightFace, OSNet,\nXFeat + DINOv2, state machine,\nobstacle map, pursuit controller", "#dce8fa")
    box(ax, 16.5, 6.7, 5.0, 2.8, "ESP32-CAM at the door\n(placed by the robot)\nface + door view", "#f6ecd8")
    arrow(ax, 4.5, 8.8, 8.0, 8.8, "video: ZeroMQ, JPEG q60")
    arrow(ax, 8.0, 7.4, 4.5, 7.4, "UDP (v, omega)")
    arrow(ax, 16.5, 8.1, 14.0, 8.1, "HTTP MJPEG, VGA")
    phases = [("Phase 1: deploy", "explore -> find the door -> sweet spot\n-> place the ESP32 -> verified -> standby"),
              ("Phase 2: monitor", "face verification at the door,\nintruder queue, departure sector"),
              ("Phase 3: pursue", "re-ID lock, 1.2 m standoff, HOLD\nwhen the target stops")]
    for i, (t, d) in enumerate(phases):
        box(ax, 0.5 + i * 7.2, 0.5, 6.6, 3.4, t + "\n" + d, "#f1e0e0" if i == 2 else "#eeeeee", 8)
    arrow(ax, 7.1, 2.2, 7.7, 2.2)
    arrow(ax, 14.3, 2.2, 14.9, 2.2)
    ax.text(11, 4.3, "evasion and coverage search follow after the mid-term", ha="center", fontsize=7, color=GREY)
    fig.suptitle("F1 System overview: three phases, three devices", fontsize=11)
    fig.savefig(OUT / "F1_system_overview.png")
    plt.close(fig)


def f2():
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 9)
    ax.axis("off")
    box(ax, 0.3, 5.5, 3.6, 2.6, "Robot camera\n640x480, 10-20 fps", "#e8f3e8")
    box(ax, 0.3, 1.0, 3.6, 2.6, "Gamepad / e-stop\nR1 dead-man, Start arm", "#e8f3e8")
    box(ax, 8.5, 5.5, 5.0, 2.6, "Laptop pipeline\nundistort, detect, pose,\nverify, track", "#dce8fa")
    box(ax, 8.5, 1.0, 5.0, 2.6, "State machine +\ncontrollers (30 Hz)", "#dce8fa")
    box(ax, 17.0, 5.5, 4.5, 2.6, "ESP32-CAM\nOV2640 VGA MJPEG", "#f6ecd8")
    box(ax, 17.0, 1.0, 4.5, 2.6, "Robot motors\nwatchdog 0.3 s", "#e8f3e8")
    arrow(ax, 3.9, 6.8, 8.5, 6.8, "ZeroMQ JPEG q60, seq + t_cap")
    arrow(ax, 17.0, 6.8, 13.5, 6.8, "HTTP MJPEG :81")
    arrow(ax, 11, 5.5, 11, 3.6, "events")
    arrow(ax, 13.5, 2.3, 17.0, 2.3, "UDP (v, omega) 30 Hz")
    arrow(ax, 3.9, 2.3, 8.5, 2.3, "ESTOP latch file, SSH poll 5 Hz")
    fig.suptitle("F2 Data flow: links, rates and formats", fontsize=11)
    fig.savefig(OUT / "F2_data_flow.png")
    plt.close(fig)


def f4():
    d = json.load(open(R / "week-02" / "fisheye_metrics.json"))
    errs = d["first_fit_view_errors"]
    dropped = set(d["views_dropped"])
    names = sorted(errs, key=lambda k: errs[k])
    fig, ax = plt.subplots(figsize=(11, 4), dpi=150)
    ax.bar(range(len(names)), [errs[n] for n in names], color=[RED if n in dropped else BLUE for n in names])
    ax.axhline(d["rms_px"], c=GREEN, ls="--", lw=1, label="final RMS %.2f px (%d views, limit %.1f)" % (d["rms_px"], d["views_used"], d["max_rms"]))
    ax.axhline(d["first_fit_rms_px"], c=GREY, ls=":", lw=1, label="first fit RMS %.2f px (all %d views)" % (d["first_fit_rms_px"], len(errs)))
    ax.set_xlabel("checkerboard view (sorted)")
    ax.set_ylabel("reprojection error (px)")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("F4 Fisheye calibration (equidistant model, 2026-10-11)\nper-view error of the FIRST fit (all views); red = the %d views then dropped" % len(dropped), fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "F4_fisheye_error.png")
    plt.close(fig)


def f5():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "calib" / "camera_pose_*.json"))):
        j = json.load(open(f))
        if j.get("pitch_down_deg") is None or "attempt1" in f or "locked" in f:
            continue
        rows.append((Path(f).stem.replace("camera_pose_", ""), j["pitch_down_deg"], j.get("H_cam_m")))
    fm = json.load(open(R / "week-04" / "classroom_1030" / "analysis" / "floor_model_1030.json"))["camera"]["pitch_down_deg_marker"]
    dep = list(fm["deploy_runs"].values())
    rows.append(("deployment runs 10-30\n(marker in the video)", sum(dep) / len(dep), None))
    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=150)
    ax.bar(range(len(rows)), [r[1] for r in rows], color=[RED if r[0].startswith("deployment") else BLUE for r in rows])
    for i, r in enumerate(rows):
        ax.text(i, r[1] + (0.3 if r[1] >= 0 else -0.9), "%.1f" % r[1] + ("" if r[2] is None else "\nH %.3f m" % r[2]), ha="center", fontsize=7)
    ax.axhline(0, c="#444", lw=0.8)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([r[0] for r in rows], rotation=25, ha="right", fontsize=7)
    ax.set_ylabel("camera pitch, positive = looking down (deg)")
    ax.set_title("F5 Camera pitch per session (tiltable mount). Pose files from different fit methods and heights H (shown); the red bar is the mean of %d\n"
                 "marker readings %.2f-%.2f deg in the 10-30 videos (classroom_1030/analysis/floor_model_1030.json)" % (len(dep), min(dep), max(dep)), fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "F5_camera_pitch_sessions.png")
    plt.close(fig)


def f6():
    rows = [r for r in csv.DictReader(open(R / "week-02" / "motion_runs.csv")) if r["kind"] == "straight" and float(r["moving_s"] or 0) > 1]
    sp = [float(r["forward_m"]) / float(r["moving_s"]) for r in rows]
    bat = [float(r["battery_v"]) for r in rows]
    lat = [float(r["lateral_m"]) / float(r["forward_m"]) for r in rows]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(14, 4), dpi=150)
    a.scatter(bat, sp, c=BLUE)
    a.set_xlabel("battery (V)")
    a.set_ylabel("forward speed (m/s)")
    a.set_ylim(0, 0.5)
    a.set_title("A. Straight runs, v = 1.0 (10-11)")
    b.scatter(range(len(lat)), lat, c=RED)
    b.axhline(0, c="#444", lw=0.8)
    b.set_xlabel("run")
    b.set_ylabel("lateral / forward (m per m)")
    b.set_title("B. Drift to the side per metre")
    sv = json.load(open(R / "week-04" / "classroom_1030" / "analysis" / "speed_vs_battery.json"))["data"]
    for name, row in sv.items():
        c.errorbar(row["battery_mean"], row["speed"], yerr=row["speed_se"], fmt="o", color=BLUE)
        c.annotate(name, (row["battery_mean"], row["speed"]), textcoords="offset points", xytext=(4, 5), fontsize=7)
    c.set_xlabel("battery (V)")
    c.set_ylim(0.2, 0.23)
    c.set_ylabel("speed at v = 0.55 (m/s), one drive each")
    c.set_title("C. Speed vs battery (10-30, -3.9 %)")
    fig.suptitle("F6 Motion model: measured speed, drift and battery dependence (end points from the committed runs)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "F6_motion_model.png")
    plt.close(fig)


def f20():
    rows = []
    for f in ("engine_builds_first_run", "engine_builds_dinov2"):
        rows += [r for r in json.load(open(R / "week-02" / "edge_deploy" / (f + ".json"))) if r.get("gpu_ms")]
    rows.sort(key=lambda r: r["gpu_ms"])
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.4), dpi=150, gridspec_kw={"width_ratios": [1.3, 1]})
    names = [r["model"].replace("_op11", "") for r in rows]
    a.barh(names, [r["gpu_ms"] for r in rows], color=BLUE)
    for i, r in enumerate(rows):
        a.text(r["gpu_ms"] * 1.02, i, "%.1f ms, %s MB" % (r["gpu_ms"], r["engine_mb"]), va="center", fontsize=7)
    a.set_xscale("log")
    a.set_xlim(5, 3000)
    a.set_xlabel("TensorRT 7.1 FP16 GPU time per inference on the Nano (ms, log scale)")
    a.set_title("F20 Engines built on the robot (2026-10-16)")
    b.barh(names, [r["build_s"] for r in rows], color=GREY)
    b.set_xlabel("engine build time (s)")
    b.set_yticks([])
    b.set_title("Build time")
    fig.text(0.01, 0.01, "DINOv2 builds only with a workaround and is far too slow on this GPU; the parity (cosine, box IoU) table is in docs/Edge Deployment.md.", fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "F20_edge_engines.png")
    plt.close(fig)


def f21():
    items = [("detector + pose, nobody in view (60 s)", "bench_stageB"), ("+ door pipeline on a still image (60 s)", "bench_stageC"), ("sustained 600 s", "bench_C_sustained")]
    fig, a = plt.subplots(figsize=(10, 4), dpi=150)
    labels = []
    for i, (label, f) in enumerate(items):
        d = json.load(open(R / "week-02" / "edge_deploy" / (f + ".json")))
        e = d["stage_ms"]["e2e"]
        a.bar(i - 0.2, e["mean"], 0.4, color=BLUE, label="mean" if i == 0 else None)
        a.bar(i + 0.2, e["p95"], 0.4, color=RED, label="p95" if i == 0 else None)
        a.text(i - 0.2, e["mean"] + 1.5, "%.0f" % e["mean"], ha="center", fontsize=8)
        a.text(i + 0.2, e["p95"] + 1.5, "%.0f" % e["p95"], ha="center", fontsize=8)
        labels.append("%s\n%.1f fps" % (label, d["fps"]))
    a.set_xticks(range(len(items)))
    a.set_xticklabels(labels, fontsize=8)
    a.set_ylabel("capture-to-result latency on the robot (ms)")
    a.legend(fontsize=8)
    a.set_title("F21 On-robot live bench (2026-10-16, nobody in view); the person-in-view runs are in week-03/edge_deploy")
    fig.tight_layout()
    fig.savefig(OUT / "F21_robot_bench.png")
    plt.close(fig)


def f19():
    """Test functions (`def test_` in tests/) on main at the end of each week, counted from git history; parametrised cases and skipped tests are not separated (pytest counts, e.g. 618 passed on 2026-11-03, are higher)."""
    import subprocess
    weeks = [("W1\nOct 11", "2026-10-11 23:59"), ("W2\nOct 18", "2026-10-18 23:59"), ("W3\nOct 25", "2026-10-25 23:59"), ("W4\nNov 1", "2026-11-01 23:59"), ("W5 so far\nNov 3", "2026-11-03 23:59")]
    counts = []
    for label, when in weeks:
        rev = subprocess.run(["git", "rev-list", "-1", "--before=" + when + " +0700", "origin/main"], cwd=ROOT, capture_output=True, text=True).stdout.strip()   # Asia/Bangkok, first-parent history of origin/main
        out = subprocess.run(["git", "grep", "-c", "^ *def test_", rev, "--", "tests"], cwd=ROOT, capture_output=True, text=True).stdout
        counts.append(sum(int(line.rsplit(":", 1)[1]) for line in out.splitlines() if line.strip()))
    fig, a = plt.subplots(figsize=(8, 4), dpi=150)
    a.bar([w[0] for w in weeks], counts, color=BLUE)
    for i, c in enumerate(counts):
        a.text(i, c + 8, str(c), ha="center", fontsize=9)
    a.set_ylabel("test functions on main")
    head = subprocess.run(["git", "rev-parse", "--short", "origin/main"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    a.set_title("F19 Test growth by week (def test_ in tests/, git history of origin/main @ %s,\nweek ends Sunday 23:59 Asia/Bangkok)" % head, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "F19_test_growth.png")
    plt.close(fig)


PM = R / "week-06" / "classroom_1111_pm" / "data"
OUT6 = R / "week-06" / "figures"


def f22():
    """Open-loop forward drive: heading change per metre vs commanded v (every logged speed run with a marker in view, 2026-10-15..11-11). Source: week-06/classroom_1111_pm/data/veer_per_run.csv."""
    rows = list(csv.DictReader(open(PM / "veer_per_run.csv")))
    fig, ax = plt.subplots(figsize=(7, 4.2))
    style = {"classroom v sweep": (BLUE, "o"), "head_* runs": (GREEN, "s"), "low battery 10.97 V": ("#c08a00", "^"), "today 2026-11-11": (RED, "D")}
    for grp, (c, m) in style.items():
        pts = [(float(r["cmd_v"]), float(r["deg_per_m"])) for r in rows if r["group"] == grp]
        if pts:
            ax.scatter(*zip(*pts), color=c, marker=m, s=45, label=grp, zorder=3)
    ax.axhline(0, color=GREY, lw=0.8)
    ax.axhline(-10.7, color=GREY, ls="--", lw=1)
    ax.text(0.99, -10.7, "motion.json calibration (2026-10-11): -0.19 rad/m", transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=7, color=GREY)
    ax.set_xlabel("commanded v (speed cap 0.3 m/s at v = 1)")
    ax.set_ylabel("heading change per metre (deg/m, left +)")
    ax.set_title("F22 Open-loop drive veers unpredictably: the same command gives -16 to +59 deg/m", fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT6 / "F22_drive_veer.png")
    plt.close(fig)


def f23():
    """Autonomous approach run ap_1: range estimate (outline area scaled from the tape at the first sighting) and door bearing vs step; tape afterwards 1.67 m. Source: classroom_1111_pm/data/approach_ap_1_log.csv."""
    rows = [r for r in csv.DictReader(open(PM / "approach_ap_1_log.csv")) if r["range_m"] != ""]
    st = [int(r["step"]) for r in rows]
    fig, ax = plt.subplots(2, 1, figsize=(7.5, 5.2), sharex=True)
    ax[0].plot(st, [float(r["range_m"]) for r in rows], color=BLUE, marker=".", lw=1)
    ax[0].axhspan(1.5, 3.0, color=GREEN, alpha=0.1, label="legal sweet-spot window 1.5-3.0 m")
    ax[0].axhline(2.0, color=GREY, ls="--", lw=0.8, label="stand-off 2.0 m")
    ax[0].scatter([st[-1]], [1.67], color=RED, marker="*", s=120, zorder=4, label="tape after the run: 1.67 m")
    ax[0].set_ylabel("range estimate (m)")
    ax[0].legend(fontsize=7)
    ax[1].plot(st, [float(r["bearing_deg"]) for r in rows], color=RED, marker=".", lw=1)
    ax[1].axhspan(-4, 4, color=GREY, alpha=0.2, label="+/- 4 deg window used (hunting)")
    ax[1].axhspan(-8, 8, color=GREEN, alpha=0.1, label="+/- 8 deg window proposed")
    for r in rows:
        if r["action"] == "drive":
            ax[1].axvline(int(r["step"]), color=BLUE, alpha=0.25, lw=2)
    ax[1].set_ylabel("door bearing (deg, left +)")
    ax[1].set_xlabel("step (blue bars = drive bursts)")
    ax[1].legend(fontsize=7)
    fig.suptitle("F23 Autonomous door approach (ap_1): pulse, re-measure, drive\n51 steps, 10 bursts, arrived at 1.67 m by tape (estimate 1.97 m)", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT6 / "F23_door_approach.png")
    plt.close(fig)


def f24():
    """Person ranging, three people at the tape marks 1.2 / 1.8 / 2.4 m (tape from the robot front; the lens sits about 0.2-0.26 m behind: expected = tape + 0.23). Source: person_ranges_1111.json."""
    sets = json.load(open(PM / "person_ranges_1111.json"))["sets"]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ser = [("foot row, 0 px", lambda d: d["foot_row"]["0.0"]["median"], "#999999", "o"), ("foot row, 3.5 px", lambda d: d["foot_row"]["3.5"]["median"], BLUE, "s"),
           ("foot row, 5 px", lambda d: d["foot_row"]["5.0"]["median"], "#7fa6d8", "^"), ("trunk, prior 0.50 m", lambda d: d["trunk"]["median"], RED, "D")]
    for k, (name, fn, c, m) in enumerate(ser):
        xs, ys = [], []
        for tag, d in sets.items():
            xs.append(d["tape_m"] + (k - 1.5) * 0.06)
            ys.append(fn(d))
        ax.scatter(xs, ys, color=c, marker=m, s=34, label=name, zorder=3)
    xx = [1.1, 2.5]
    ax.plot(xx, [x + 0.23 for x in xx], color=GREEN, lw=1.2, label="expected: tape + 0.23 m (lens offset, unmeasured +/- 0.03)")
    ax.fill_between(xx, [x + 0.03 for x in xx], [x + 0.43 for x in xx], color=GREEN, alpha=0.08)
    ax.set_xlabel("tape distance, robot front to feet (m); three people per mark")
    ax.set_ylabel("median forward range from the lens (m)")
    ax.set_title("F24 Foot-row range depends on the box-bottom offset; trunk range needs none (12 frames per point)", fontsize=8.5)
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT6 / "F24_person_ranges.png")
    plt.close(fig)


def f25():
    """D2 face width at the door ESP32: the cafe pilot (2026-10-28) vs the classroom clips (2026-11-11, low tilted placement), 45 px = the pipeline's walker threshold. Source: d2_face_widths_*.csv."""
    new = [float(r["width_px"]) for r in csv.DictReader(open(PM / "d2_face_widths_1111.csv"))]
    old = [float(r["width_px"]) for r in csv.DictReader(open(PM / "d2_face_widths_pilot_1028.csv"))]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bins = range(20, 66, 2)
    ax.hist(old, bins=bins, color=GREEN, alpha=0.6, label="cafe pilot 2026-10-28 (%d frames, median %.0f px)" % (len(old), sorted(old)[len(old) // 2]))
    ax.hist(new, bins=bins, color=RED, alpha=0.6, label="classroom 2026-11-11 (%d frames, median %.0f px)" % (len(new), sorted(new)[len(new) // 2]))
    ax.axvline(45, color="k", ls="--", lw=1)
    ax.text(45.5, ax.get_ylim()[1] * 0.92, "45 px walker threshold", fontsize=7)
    ax.set_xlabel("walker face width in the ESP32 frame (px, 640x480)")
    ax.set_ylabel("frames")
    ax.set_title("F25 Faces at the classroom door placement are 22-53 px: below the pilot's 45-60 px", fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT6 / "F25_d2_face_width.png")
    plt.close(fig)


def f7():
    """Video latency (JetBot capture -> laptop decode, after UDP clock sync) of two 120 s runs on 2026-11-11, robot stationary next to the laptop (-31 dBm), and the delivered frame rate.
    Source: week-06/latency_1111/*.csv and .json (tools.log_latency). The e-stop / watchdog stop times are NOT in this figure (they need motion)."""
    base = R / "week-06" / "latency_1111"
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    for tag, name, c in (("video_latency_1111", "run 1 (2 min after boot, Jetson load 3.6)", BLUE), ("video_latency_1111_settled", "run 2 (4 min after boot, load 1.0)", RED)):
        x = sorted(float(r["decoded_latency_ms"]) for r in csv.DictReader(open(base / (tag + ".csv"))))
        d = json.load(open(base / (tag + ".json")))
        ax.plot(x, [(i + 1) / len(x) for i in range(len(x))], color=c, label="%s: %.1f fps, p50 %.0f, p95 %.0f, max %.0f ms" % (name, d["run_fps"], x[len(x) // 2], x[int(0.95 * len(x))], x[-1]))
    ax.axvline(50, color=GREY, ls="--", lw=1)
    ax.text(52, 0.05, "config p95 limit 50 ms", fontsize=7, color=GREY)
    ax.axvline(500, color=GREEN, ls=":", lw=1)
    ax.text(470, 0.5, "video-freshness guard 0.5 s", fontsize=7, color=GREEN, rotation=90, ha="right")
    ax.set_xlabel("decoded latency (ms)")
    ax.set_ylabel("cumulative fraction of frames")
    ax.set_xlim(0, 550)
    ax.set_title("F7 Video latency CDF, 2 x 120 s (2,351 and 2,325 frames); delivered 19.6 and 19.4 fps (config minimum 20)", fontsize=8.5)
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT6 / "F7_video_latency.png")
    plt.close(fig)


def f8():
    """ESP32-CAM door stream, 2026-11-12 (desk, USB power). Left: delivered fps per second: the original firmware on a fresh boot (VGA), the camera clock pin at 20 MHz with the default drive strength (sends stall: the
    0.2 fps signature), the same clock with drive strength 0, and the final 'opt4' build over 10 minutes (640x480 sensor crop, clock doubler); dots = the original firmware's readings during the evening (fps fell 8.8 to 0.2 at identical settings).
    Right: an empty-door frame at VGA full field from the tower placement. Source: week-06/esp32_stream_1112/data (per-second counts from the laptop, meas.py)."""
    import cv2
    base = R / "week-06" / "esp32_stream_1112" / "data"

    def load(name):
        rows = list(csv.DictReader(open(base / (name + ".csv"))))
        return [float(r["sec"]) for r in rows], [float(r["fps"]) for r in rows]

    def smooth(v, k=5):
        return [sum(v[max(0, i - k + 1):i + 1]) / len(v[max(0, i - k + 1):i + 1]) for i in range(len(v))]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1.5, 1]})
    for name, label, c in (("base_fresh", "original firmware, fresh boot (VGA, clock 10 MHz)", GREY), ("r2d", "clock pin 20 MHz, drive 2: sends stall", RED),
                           ("r3b_d0", "clock pin 20 MHz, drive strength 0", GREEN), ("r3c", "opt4: 640x480 sensor crop + doubler, 10 min", BLUE)):
        x, y = load(name)
        ax[0].plot(x, smooth(y), color=c, lw=1.3, label=label)
    rd = list(csv.DictReader(open(base / "original_firmware_readings.csv")))
    ax[0].text(0.99, 0.62, "original firmware, same settings (VGA, q25, clock 10 MHz),\nreadings over about 90 min:  " + ", ".join(r["fps"] for r in rd) + " fps", transform=ax[0].transAxes, ha="right", va="top", fontsize=7, color="#8a6200",
               bbox=dict(boxstyle="round", fc="#fff6dd", ec="#c08a00", lw=0.6))
    ax[0].set_xlabel("time (s)")
    ax[0].set_ylabel("delivered frames per second (5 s mean)")
    ax[0].set_ylim(0, 15)
    ax[0].legend(fontsize=6.5, loc="lower right")
    ax[0].set_title("F8 ESP32-CAM stream rate, desk measurements", fontsize=9)
    img = cv2.cvtColor(cv2.imread(str(base / "door_view_vga_empty.jpg")), cv2.COLOR_BGR2RGB)
    ax[1].imshow(img)
    ax[1].axis("off")
    ax[1].set_title("sample frame, empty door, VGA full field\n(faces 22-40 px wide here; opt4 crop: about 77 px at 2.1 m)", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT6 / "F8_esp32_stream.png")
    plt.close(fig)


def f17():
    """Pursuit, classroom runs of 2026-11-09 (first live trials, no acceptance): distance from the foot-row range and bbox-centre error vs time, hold events from summary.json."""
    base = R / "week-06" / "classroom_1109" / "pursuit"
    runs = ["tile_1_1", "tile_2_1", "tile_3_1"]
    fig, ax = plt.subplots(2, 3, figsize=(13, 6), sharex="col")
    for j, name in enumerate(runs):
        rows = list(csv.DictReader(open(base / name / "log.csv")))
        sm = json.load(open(base / name / "summary.json"))
        t = [float(r["t"]) for r in rows]
        d, c = ax[0][j], ax[1][j]
        d.plot(t, [float(r["dist_m"]) if r["dist_m"] else float("nan") for r in rows], color=BLUE, lw=1)
        d.axhspan(1.0, 1.4, color=GREEN, alpha=0.15, label="1.2 +/- 0.2 m")
        d.set_ylabel("distance (m, foot-row range)")
        d.set_title("%s: in band %.0f %%, centred %.0f %% of the run" % (name, 100 * sm["time_fraction_distance_in_band_of_run"], 100 * sm["time_fraction_centred_of_run"]), fontsize=9)
        c.plot(t, [float(r["yaw_err"]) / 2 if r["yaw_err"] else float("nan") for r in rows], color=RED, lw=1)  # yaw_err is relative to HALF the width
        c.axhspan(-0.1, 0.1, color=GREEN, alpha=0.15, label="+/- 10 % of the frame width")
        c.set_ylabel("bbox centre error / frame width")
        c.set_xlabel("time (s)")
        for ev in sm["hold_events"]:
            for a in (d, c):
                a.axvline(ev[0], color=GREY, ls="--", lw=0.8)
            d.text(ev[0], d.get_ylim()[1], " " + ev[1].replace("TARGET_", ""), fontsize=6, va="top", rotation=90)
    ax[0][0].legend(fontsize=7)
    ax[1][0].legend(fontsize=7)
    fig.suptitle("F17 Pursuit, classroom 2026-11-09, first supervised trials (NOT the plan's 80 % acceptance). Distances are foot-row ranges, not tape-verified;\nDQK measured the true standoff at about 1.7 m in two runs of that session. Dashed = HOLD entered/left.", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "F17_pursuit_classroom.png")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    OUT6.mkdir(parents=True, exist_ok=True)
    for fn in (f1, f2, f4, f5, f6, f17, f19, f20, f21, f7, f8, f22, f23, f24, f25):
        fn()
        print("made", fn.__name__)


if __name__ == "__main__":
    main()
