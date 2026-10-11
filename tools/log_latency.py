"""Measure JetBot video latency after UDP clock sync; does not send motor commands.

    python -m tools.log_latency --ip <jetbot-ip> --seconds 30
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from sentry.config import load
from sentry.net.clock_sync import synchronize
from sentry.net.latency import LatencyLogger
from sentry.net.zmq_rx import ZMQReceiver


def main():
    cfg = load()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ip", default=cfg["net"]["jetbot_ip"])
    ap.add_argument("--video-port", type=int, default=cfg["net"]["video_port"])
    ap.add_argument("--clock-port", type=int, default=cfg["net"]["clock_port"])
    ap.add_argument("--seconds", type=float, default=cfg["telemetry"]["duration_s"])
    ap.add_argument("--out", type=Path,
                    default=Path("reports/HuynhNguyenHoaiLoc/week-01/latency.csv"))
    args = ap.parse_args()
    if not 0 < args.seconds < float("inf"):
        ap.error("--seconds must be positive and finite")
    estimate = synchronize(args.ip, args.clock_port)
    print("Clock sync:", json.dumps(asdict(estimate)))
    with ZMQReceiver(args.ip, args.video_port) as rx, LatencyLogger(args.out, estimate) as log:
        start = time.perf_counter()
        deadline = start + args.seconds
        while time.perf_counter() < deadline:
            frame = rx.read(min(cfg["telemetry"]["frame_timeout_s"], max(0, deadline - time.perf_counter())))
            if frame is not None:
                log.write(frame)
        metrics = log.summary()
        metrics.update({"scope": "live_stream_requires_HIL_validation",
                        "ip": args.ip, "measurement_duration_s": time.perf_counter() - start,
                        "laptop_clock": "perf_counter", "laptop_clock_resolution_s": time.get_clock_info("perf_counter").resolution,
                        "receiver_messages": rx.received, "receiver_invalid": rx.invalid,
                        "receiver_skipped": rx.skipped,
                        "note": "Latency starts after camera read, per camera_pub t_cap; excludes sensor exposure. "
                        "Latest-frame skips are not network packet loss. Resync after source restart."})
        # Include initial waiting/stalls in the run-level throughput criterion.
        metrics["run_fps"] = metrics["frames"] / metrics["measurement_duration_s"]
        metrics["pass"] = metrics["pass"] and metrics["run_fps"] >= cfg["telemetry"]["min_fps"]
    args.out.with_suffix(".json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0 if metrics["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
