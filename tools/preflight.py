"""Pre-flight check before a robot session (run it first, and again after any bump or reboot):

  python -m tools.preflight                                   # robot found, battery, three services, video fps, disk space
  python -m tools.preflight --marker-m 0.15 --bottom-h 0.06    # + camera tilt from an ArUco marker in view, compared with the newest calib/camera_pose_*.json

Prints one PASS / WARN / FAIL line per check and exits 1 on any FAIL. Needs JETBOT_PASSWORD (or asks).
"""
import argparse
import glob
import json
import os
import shutil
import time

BATTERY_OK_V, BATTERY_STOP_V = 11.1, 10.5          # docs/JetBot Notes.md
SERVICES = ("sentry-estop", "sentry-camera", "sentry-control")


def battery_status(volts):
    return "PASS" if volts >= BATTERY_OK_V else ("FAIL" if volts < BATTERY_STOP_V else "WARN")


def tilt_status(live_pitch_deg, stored_pitch_deg, tol_deg=1.5):
    """The live marker estimate must agree with the stored pose within tol (1.5 deg is about 10 % distance error at 2 m)."""
    d = abs(live_pitch_deg - stored_pitch_deg)
    return ("PASS" if d <= tol_deg else "FAIL"), d


def newest_pose(pattern="calib/camera_pose_*.json"):
    files = [f for f in glob.glob(pattern) if not f.endswith("_yawfix.json")]
    if not files:
        return None, None
    f = max(files, key=os.path.getmtime)
    return f, json.load(open(f)).get("pitch_down_deg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="auto")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password")
    ap.add_argument("--marker-m", type=float)
    ap.add_argument("--bottom-h", type=float)
    ap.add_argument("--camera-h", type=float, default=0.100)
    ap.add_argument("--min-fps", type=float, default=10.0)
    ap.add_argument("--min-free-gb", type=float, default=5.0)
    a = ap.parse_args()
    from sentry.net.discover import resolve
    from tools import jetbot_ssh
    from tools.jetbot_status import ina219_bus_volts
    results = []

    def report(name, status, text):
        results.append(status)
        print("%-5s %-14s %s" % (status, name, text), flush=True)

    ip = resolve(a.ip)
    report("robot", "PASS", ip)
    try:
        pw = jetbot_ssh.password(a.password)
        c = jetbot_ssh.connect(ip, a.user, pw)
        raw = jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", pw)
        volts = ina219_bus_volts([t for t in raw.split() if t.startswith("0x")][-1])
        report("battery", battery_status(volts), "%.2f V (>= %.1f OK, < %.1f stop and charge)" % (volts, BATTERY_OK_V, BATTERY_STOP_V))
        state = jetbot_ssh.run(c, "systemctl is-active " + " ".join(SERVICES)).split()
        bad = [n for n, s in zip(SERVICES, state) if s != "active"]
        report("services", "FAIL" if bad or len(state) != len(SERVICES) else "PASS", "not active: %s (camera / control start about 1 min after boot)" % bad if bad else "all three active")
        last = jetbot_ssh.run(c, "tail -n 1 /home/jetbot/sentry/estop.log")
        report("e-stop", "PASS", last[-80:])
    except Exception as e:                                       # keep going: video and disk do not need SSH
        report("ssh", "FAIL", "%s: %s" % (type(e).__name__, e))
    frames, tilt = 0, None
    try:
        from sentry.net.zmq_rx import ZMQReceiver
        with ZMQReceiver(ip) as rx:
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 3.0:
                f = rx.read(timeout=1.0)
                if f is None:
                    continue
                frames += 1
                if a.marker_m and tilt is None or (a.marker_m and frames % 5 == 0):
                    try:
                        import cv2
                        import numpy as np
                        from perception.camera_pose import TiltFilter
                        from tools.estimate_camera_tilt import undistorter
                        tilt = tilt or (TiltFilter(max_distance_m=3.0), *undistorter(json.load(open("calib/camera.json"))))
                        tilt[0].update_frame(tilt[2](f.frame_bgr), tilt[1], a.marker_m, a.bottom_h, None, a.camera_h)
                    except ImportError:
                        report("tilt", "WARN", "perception/camera_pose.py not on this branch: skipped")
                        a.marker_m = None
            fps = frames / (time.perf_counter() - t0)
        report("video", "PASS" if fps >= a.min_fps else "FAIL", "%.1f fps over 3 s (>= %.0f)" % (fps, a.min_fps))
    except Exception as e:
        report("video", "FAIL", "%s: %s" % (type(e).__name__, e))
    if a.marker_m and tilt is not None:
        name, stored = newest_pose()
        if not tilt[0].hist:
            report("tilt", "WARN", "no usable marker in view (within about 2.5 m, vertical, 4x4_50)")
        elif stored is None:
            report("tilt", "WARN", "live %+.2f deg (no calib/camera_pose_*.json to compare)" % tilt[0].pitch_deg)
        else:
            st, d = tilt_status(tilt[0].pitch_deg, stored)
            report("tilt", st, "live %+.2f deg vs %+.2f in %s (differ %.1f deg; > 1.5 = re-measure with the strips)" % (tilt[0].pitch_deg, stored, os.path.basename(name), d))
    free = shutil.disk_usage("data" if os.path.isdir("data") else ".").free / 1e9
    report("disk", "PASS" if free >= a.min_free_gb else "WARN", "%.1f GB free for data/ (D1 sessions take about 1.3 GB)" % free)
    print("\nPREFLIGHT %s" % ("FAILED" if "FAIL" in results else ("OK with warnings" if "WARN" in results else "OK")))
    raise SystemExit(1 if "FAIL" in results else 0)


if __name__ == "__main__":
    main()
