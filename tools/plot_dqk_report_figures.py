"""DQK's report figures that can be made from existing evidence (Mid-Term Report Plan section 3): F1 and F2 (diagrams), F4, F5, F6, F20, F21. Every number is read from a committed file.

  python -m tools.plot_dqk_report_figures            # writes reports/DoanQuocKien/week-05/figures/F*.png

Not here (they need data that does not exist yet): F3 (photo), F7 (raw latency samples), F17 (pursuit run logs). Nothing in the figures is a photo or a face.
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
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 + 0.2, text, ha="center", fontsize=fs)


def f1():
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 10.5)
    ax.axis("off")
    box(ax, 0.5, 6.7, 5.0, 2.8, "JetBot (Jetson Nano)\ncamera, motors, e-stop\ncaptures frames, drives", "#e8f3e8")
    box(ax, 8.0, 5.2, 6.0, 4.6, "Laptop\nYOLOv8, pose, InsightFace, OSNet,\nXFeat + DINOv2, state machine,\nobstacle map, pursuit controller", "#dce8fa")
    box(ax, 16.5, 6.7, 5.0, 2.8, "ESP32-CAM at the door\n(placed by the robot)\nface + door view", "#f6ecd8")
    arrow(ax, 5.5, 9.2, 8.0, 9.2, "video: ZeroMQ, JPEG q60")
    arrow(ax, 8.0, 7.2, 5.5, 7.2, "UDP (v, omega)")
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
    box(ax, 0.3, 5.5, 4.5, 2.6, "Robot camera\n640x480, 10-20 fps", "#e8f3e8")
    box(ax, 0.3, 1.0, 4.5, 2.6, "Gamepad / e-stop\nR1 dead-man, Start arm", "#e8f3e8")
    box(ax, 8.5, 5.5, 5.0, 2.6, "Laptop pipeline\nundistort, detect, pose,\nverify, track", "#dce8fa")
    box(ax, 8.5, 1.0, 5.0, 2.6, "State machine +\ncontrollers (30 Hz)", "#dce8fa")
    box(ax, 17.0, 5.5, 4.5, 2.6, "ESP32-CAM\nOV2640 VGA MJPEG", "#f6ecd8")
    box(ax, 17.0, 1.0, 4.5, 2.6, "Robot motors\nwatchdog 0.3 s", "#e8f3e8")
    arrow(ax, 4.8, 6.8, 8.5, 6.8, "ZeroMQ JPEG q60, seq + t_cap")
    arrow(ax, 17.0, 6.8, 13.5, 6.8, "HTTP MJPEG :81")
    arrow(ax, 11, 5.5, 11, 3.6, "events")
    arrow(ax, 13.5, 2.3, 17.0, 2.3, "UDP (v, omega) 30 Hz")
    arrow(ax, 4.8, 2.3, 8.5, 2.3, "latch file ESTOP via SSH poll 5 Hz")
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
    ax.set_title("F4 Fisheye calibration (equidistant model, 2026-10-11): per-view error of the FIRST fit (all views); red = the %d views then dropped" % len(dropped))
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
    rows.append(("deployment runs 10-30 (video)", 6.1, None))
    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=150)
    ax.bar(range(len(rows)), [r[1] for r in rows], color=[RED if r[0].startswith("deployment") else BLUE for r in rows])
    for i, r in enumerate(rows):
        ax.text(i, r[1] + (0.3 if r[1] >= 0 else -0.9), "%.1f" % r[1], ha="center", fontsize=8)
    ax.axhline(0, c="#444", lw=0.8)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([r[0] for r in rows], rotation=25, ha="right", fontsize=7)
    ax.set_ylabel("camera pitch, positive = looking down (deg)")
    ax.set_title("F5 Camera pitch over sessions (mount is tiltable; lens height fixed at 0.100 m): methods differ, see the pose files")
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
    runs = {"11.58-11.70 V\n(0.2239-0.2245)": 0.2242, "11.39-11.44 V\n(0.2156-0.2159)": 0.2157}   # means of the per-drive fits in classroom_1030/analysis
    c.bar(list(runs), list(runs.values()), color=BLUE)
    for i, v in enumerate(runs.values()):
        c.text(i, v + 0.002, "%.4f" % v, ha="center", fontsize=8)
    c.set_ylim(0.2, 0.23)
    c.set_ylabel("speed at v = 0.55 (m/s)")
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
        rev = subprocess.run(["git", "rev-list", "-1", "--before=" + when, "origin/main"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        out = subprocess.run(["git", "grep", "-c", "^ *def test_", rev, "--", "tests"], cwd=ROOT, capture_output=True, text=True).stdout
        counts.append(sum(int(line.rsplit(":", 1)[1]) for line in out.splitlines() if line.strip()))
    fig, a = plt.subplots(figsize=(8, 4), dpi=150)
    a.bar([w[0] for w in weeks], counts, color=BLUE)
    for i, c in enumerate(counts):
        a.text(i, c + 8, str(c), ha="center", fontsize=9)
    a.set_ylabel("test functions on main")
    a.set_title("F19 Test growth by week (def test_ in tests/, from git history)")
    fig.tight_layout()
    fig.savefig(OUT / "F19_test_growth.png")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (f1, f2, f4, f5, f6, f19, f20, f21):
        fn()
        print("made", fn.__name__)


if __name__ == "__main__":
    main()
