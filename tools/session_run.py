"""One take: find the door + tower + handshake + reverse to STANDBY (tools.deploy_live --find-door), then, on YOUR key press, the pursuit (tools.pursue_live --tower-avoid --search).

  python -m tools.session_run --label take1 --camera-pose calib/camera_pose_self_<today>.json -- --handshake data/handshake/class_door_1120 --tower-place --wait 120

Everything after `--` goes to deploy_live unchanged. The two stages are separate processes with their own safety interlock (R1 + armed e-stop, battery, link watchdog): nothing is relaxed here.
After STANDBY the model loading of the pursuit takes 30-60 s, so R1 is released in between; the pursuit beeps for a fresh R1 hold. The pursuit starts only when the deploy stage reports success
(summary.json `success`) AND the key `p` is pressed (any other key ends the session); `--no-pursuit` stops after the first stage."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

PY = [sys.executable, "-X", "utf8", "-u", "-m"]


def newest_summary(root, label, previous=None):
    runs = sorted((p for p in Path(root).glob(label + "_*") if previous is None or p not in previous),
                  key=lambda p: p.stat().st_mtime)
    if previous is not None and len(runs) != 1:
        return None
    f = runs[-1] / "summary.json" if runs else None
    return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None


def wait_key(prompt):
    print(prompt, flush=True)
    try:
        import msvcrt
        return msvcrt.getwch()
    except ImportError:                                   # not Windows: a line on stdin
        return (sys.stdin.readline() or "q")[:1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--camera-pose", required=True, help="camera pose JSON for the pursuit (python -m tools.self_pose --tower)")
    ap.add_argument("--stand-off", type=float, default=None, help="deploy stage stand-off (default: [find_door] stand_off_m of config.toml)")
    ap.add_argument("--no-pursuit", action="store_true")
    ap.add_argument("--pursuit-seconds", type=float, default=90.0)
    ap.add_argument("deploy_args", nargs=argparse.REMAINDER, help="after `--`: passed to tools.deploy_live")
    a = ap.parse_args()
    extra = [x for x in a.deploy_args if x != "--"]
    d = PY + ["tools.deploy_live", "--label", a.label + "_a", "--find-door"] + (["--stand-off", str(a.stand_off)] if a.stand_off is not None else []) + extra
    output_args = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    output_args.add_argument("--label")
    output_args.add_argument("--out", default="data/deploy")
    output, _ = output_args.parse_known_args(d[len(PY) + 1:])
    previous = set(Path(output.out).glob(output.label + "_*"))
    print("STAGE 1:", " ".join(d), flush=True)
    if subprocess.call(d) != 0:
        raise SystemExit("stage 1 exited with an error")
    s = newest_summary(output.out, output.label, previous=previous)
    if not s or not s.get("success"):
        raise SystemExit("stage 1 did not reach STANDBY (end_reason: %s): no pursuit" % (s or {}).get("end_reason"))
    if a.no_pursuit:
        return
    if wait_key("STANDBY reached. Press p for the PURSUIT (any other key ends the session)") != "p":
        return
    p = PY + ["tools.pursue_live", "--label", a.label + "_b", "--camera-pose", a.camera_pose, "--tower-avoid", "--search", "--seconds", str(a.pursuit_seconds)]
    print("STAGE 2:", " ".join(p), flush=True)
    raise SystemExit(subprocess.call(p))


if __name__ == "__main__":
    main()
