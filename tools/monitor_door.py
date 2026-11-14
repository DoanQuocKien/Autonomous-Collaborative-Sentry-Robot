"""ESP32 Phase 2 monitoring and timestamped replay, with private entry logs."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from sentry.app.phase2_live import DoorMonitor, DoorSettings
from sentry.app.phase2_pipeline import OSNetAppearanceExtractor, Phase2Pipeline
from sentry.config import DEFAULT_PATH, load
from sentry.net.frame import VideoFrame
from sentry.net.mjpeg_rx import MJPEGReceiver
from sentry.perception.face import FaceVerifier, InsightFaceEncoder, load_whitelist
from sentry.perception.obstacle import YOLOPredictor
from sentry.perception.sector import SectorConfig
from sentry.perception.tracker import PersonTracker

ROOT = Path(__file__).resolve().parents[1]


def private_path(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to((ROOT / "data").resolve()):
        raise ValueError("private logs, images and recordings must stay under data/")
    return resolved


def read_manifest(path):
    """Validate a private ESP32 replay before loading models or creating output."""
    path = private_path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("camera") != "esp32" or not raw.get("timestamp_source"):
        raise ValueError("declare camera=esp32 and timestamp_source")
    frames = raw.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("nonempty replay frames required")
    seen = set()
    previous = None
    for row in frames:
        t, seq = row["t"], row["seq"]
        if (isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t) or t < 0
                or type(seq) is not int or seq < 0):
            raise ValueError("nonnegative finite timestamps and integer sequences required")
        if previous is not None and (t <= previous[0] or seq <= previous[1]):
            raise ValueError("replay timestamps and sequences must increase; split restarts")
        image = private_path(path.parent / row["image"])
        if image in seen:
            raise ValueError("duplicate replay image")
        payload = image.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["image_sha256"]:
            raise ValueError("replay image hash mismatch")
        if cv2.imread(str(image)) is None:
            raise ValueError("corrupt replay image")
        seen.add(image)
        previous = t, seq
    return raw


def replay_frames(path, manifest):
    for row in manifest["frames"]:
        image = private_path(Path(path).parent / row["image"])
        payload = image.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["image_sha256"]:
            raise ValueError("replay changed after validation")
        bgr = cv2.imread(str(image))
        yield VideoFrame(row["seq"], row["t"], row["t"], row["t"], bgr, payload)


def load_door_encoder(config_path):
    cfg = load(config_path)
    base = Path(config_path).resolve().parent
    face_root = (base / cfg["pipeline_profile"]["face_root"]).resolve()
    for name in ("det_500m.onnx", "w600k_mbf.onnx"):
        if not (face_root / "models" / "buffalo_s" / name).is_file():
            raise FileNotFoundError("fetch local InsightFace weights first: " + name)
    face_device = "cpu" if str(cfg["reid"]["device"]) == "cpu" else "cuda"
    return InsightFaceEncoder(device=face_device, model_root=face_root)


def warmup_models(monitor, iterations):
    """Warm model execution before the stream, without creating entry evidence."""
    if type(iterations) is not int or iterations < 0:
        raise ValueError("nonnegative integer warmup iterations required")
    image = np.zeros((480, 640, 3), np.uint8)
    body = np.zeros((256, 128, 3), np.uint8)
    face = np.zeros((112, 112, 3), np.uint8)
    started = time.perf_counter()
    try:
        for i in range(iterations):
            monitor.tracker(image, i / monitor.s.inference_hz)
            monitor.tracker.encoder.encode([body])
            monitor.face_encoder.extract(image)
            monitor.face_encoder.app.models["recognition"].get_feat(face)
    finally:
        monitor.tracker.reset()
    return dict(iterations=iterations, synthetic_input=True, image_shape=list(image.shape),
                duration_s=time.perf_counter() - started, excluded_from_entries=True)


def build_monitor(config_path, whitelist_dir, settings, emit, *, live, warmup=True):
    cfg = load(config_path)
    base = Path(config_path).resolve().parent
    whitelist = load_whitelist(whitelist_dir)
    appearance = OSNetAppearanceExtractor(config_path=config_path, device=cfg["reid"]["device"])
    rs, ts = cfg["reid"], cfg["tracking"]
    detector = YOLOPredictor(base / rs["person_weights"],
        dict(cfg["obstacle"], class_ids=[0], confidence=ts["track_low_thresh"],
             imgsz=rs["person_imgsz"], device=rs["person_device"]))
    tracker = PersonTracker(detector, appearance.encoder, ts, rs)
    encoder = load_door_encoder(config_path)
    pipeline = Phase2Pipeline(FaceVerifier(whitelist, cfg["thresholds"]["whitelist_cosine"]),
                              appearance, sector_config=SectorConfig.from_toml(cfg))
    monitor = DoorMonitor(tracker, encoder, pipeline, settings, emit,
                          decision_clock=time.perf_counter if live else None)
    monitor.runtime_info = dict(
        osnet_device=str(appearance.encoder.device),
        person_weights_sha256=hashlib.sha256((base / rs["person_weights"]).read_bytes()).hexdigest(),
        face_models={name: dict(sha256=hashlib.sha256(Path(model.model_file).read_bytes()).hexdigest(),
                               providers=model.session.get_providers())
                     for name, model in encoder.app.models.items()},
    )
    monitor.warmup_info = warmup_models(monitor, cfg["pipeline_profile"]["warmup"]) if warmup else None
    return monitor


def run_receiver(receiver, monitor, seconds, consume, *, clock=time.perf_counter, source_event=None):
    """One receiver connection. A timeout aborts evidence, then awaits reconnection."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("positive finite duration required")
    start = clock()
    state = "waiting"
    last_received = start
    consumed = 0
    notify = source_event if source_event is not None else lambda row: None
    notify(dict(t=start, state=state, reconnects=0))
    with receiver as source:
        try:
            while clock() - start < seconds:
                frame = source.read(timeout=min(0.2, seconds))
                now = clock()
                if frame is None or now - frame.t_rx > monitor.s.max_gap_s:
                    monitor.tick(now)
                    if now - last_received > monitor.s.max_gap_s and state != "unavailable":
                        state = "unavailable"
                        notify(dict(t=now, state=state, reconnects=source.reconnects))
                    continue
                last_received = now
                consumed += 1
                if state != "available":
                    state = "available"
                    notify(dict(t=now, state=state, reconnects=source.reconnects))
                processed = monitor.process(frame.frame_bgr, frame.t_rx, int(frame.seq), source.reconnects)
                if processed and consume(frame) is False:
                    break
        finally:
            monitor.interrupt(clock(), "shutdown")
    return dict(duration_s=clock() - start, consumed_frames=consumed,
                decoded_frames=getattr(receiver, "frames", None), reconnects=receiver.reconnects)


def overlay(image, monitor):
    shown = image.copy()
    for face in monitor.last_faces:
        x1, y1, x2, y2 = map(int, face["bbox"])
        cv2.rectangle(shown, (x1, y1), (x2, y2), (255, 180, 0), 1)
        cv2.putText(shown, "face %d px %.2f" % (x2 - x1, face["confidence"]),
                    (x1, min(shown.shape[0] - 5, y2 + 15)), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 180, 0), 1)
    for track in monitor.last_tracks:
        x1, y1, x2, y2 = map(int, track.xyxy)
        entry = monitor.entries.get(track.key)
        label = "track %s" % (track.key,)
        if entry is not None:
            label += " faces=%d%s" % (entry.hits, " done" if entry.completed else "")
        cv2.rectangle(shown, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.putText(shown, label, (x1, max(15, y1)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 0), 1)
    cv2.putText(shown, "Phase 2 | provisional threshold | %s" % monitor.s.crop_scope,
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)
    return shown


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="ESP32 HTTP MJPEG URL, one stream client")
    source.add_argument("--replay-manifest", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--whitelist", type=Path, default=ROOT / "data/whitelist")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--save-snapshots", action="store_true")
    parser.add_argument("--save-overlay", action="store_true", help="save private MJPEG AVI and timestamp index")
    parser.add_argument("--display", action="store_true", help="preview, Esc finishes the run")
    parser.add_argument("--diagnostics", action="store_true", help="private per-frame rejection counts and wall timings")
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("seconds must be positive and finite")
    out = private_path(args.out_dir)
    if out.exists():
        raise FileExistsError("choose a new run directory")
    cfg = load(args.config)
    settings = DoorSettings(**cfg["door_live"])
    manifest = read_manifest(args.replay_manifest) if args.replay_manifest else None
    rows = []
    log = None
    writer = None
    index = None
    video_shape = None
    diagnostic_log = None

    def emit(row):
        log.write(json.dumps(row, allow_nan=False) + "\n")
        log.flush()
        rows.append(row)

    monitor = build_monitor(args.config, args.whitelist, settings, emit, live=manifest is None)
    # Reserve a new output after preflight. Partial runs keep logs and a failed status.
    out.mkdir(parents=True, exist_ok=False)
    metadata = dict(settings=asdict(settings), threshold=monitor.pipeline.face_verifier.threshold,
                    session_id=monitor.session_id,
                    threshold_calibrated=False, appearance_model_id=monitor.tracker.encoder.model_id,
                    camera="esp32", timestamp_source="laptop_mjpeg_receive" if manifest is None else manifest["timestamp_source"],
                    replay=manifest is not None, t1_passed=False, motor_commands_sent=0,
                    config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest(),
                    model_runtime=getattr(monitor, "runtime_info", {}),
                    warmup=getattr(monitor, "warmup_info", None),
                    whitelist_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in sorted(args.whitelist.glob("*.npz"))})
    (out / "session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if args.save_snapshots:
        monitor.pipeline.snapshot_dir = out / "snapshots"
        monitor.pipeline.snapshot_dir.mkdir()

    def consume(frame):
        nonlocal writer, index, video_shape
        started = time.perf_counter()
        def write_diagnostic():
            if diagnostic_log is not None:
                row = dict(monitor.last_diagnostic, consume_ms=(time.perf_counter() - started) * 1000)
                diagnostic_log.write(json.dumps(row, allow_nan=False) + "\n")
                diagnostic_log.flush()
        if not args.display and not args.save_overlay:
            write_diagnostic()
            return True
        shown = overlay(frame.frame_bgr, monitor)
        if args.save_overlay:
            shape = shown.shape[:2]
            if writer is None:
                writer = cv2.VideoWriter(str(out / "overlay.avi"), cv2.VideoWriter_fourcc(*"MJPG"),
                                         settings.inference_hz, (shape[1], shape[0]))
                if not writer.isOpened():
                    raise OSError("cannot open overlay video")
                index = (out / "overlay_frames.jsonl").open("x", encoding="utf-8")
                video_shape = shape
            if shape != video_shape:
                raise ValueError("overlay size changed; start a new recording")
            writer.write(shown)
            index.write(json.dumps(dict(seq=frame.seq, receive_t=frame.t_rx)) + "\n")
        if args.display:
            cv2.imshow("ESP32 Phase 2", shown)
            keep_running = cv2.waitKey(1) != 27
            write_diagnostic()
            return keep_running
        write_diagnostic()
        return True

    status = "failed"
    source_summary = None
    try:
        if args.diagnostics:
            diagnostic_log = (out / "frames.jsonl").open("x", encoding="utf-8")
        with (out / "entries.jsonl").open("x", encoding="utf-8") as log, \
                (out / "source.jsonl").open("x", encoding="utf-8") as source_log:
            if manifest is None:
                def source_event(row):
                    source_log.write(json.dumps(row, allow_nan=False) + "\n")
                    source_log.flush()
                source_summary = run_receiver(
                    MJPEGReceiver(url=args.url, request_timeout_s=2.0, join_timeout_s=3.0),
                    monitor, args.seconds, consume, source_event=source_event)
            else:
                last_t = 0.0
                try:
                    for frame in replay_frames(args.replay_manifest, manifest):
                        last_t = frame.t_rx
                        if monitor.process(frame.frame_bgr, frame.t_rx, frame.seq) and consume(frame) is False:
                            break
                finally:
                    monitor.interrupt(last_t, "replay_end")
            status = "completed"
    finally:
        if diagnostic_log is not None:
            diagnostic_log.close()
        if writer is not None:
            writer.release()
        if index is not None:
            index.close()
        if args.display:
            cv2.destroyAllWindows()
        summary = dict(status=status, processed_frames=monitor.processed, skipped_schedule_frames=monitor.skipped,
                       confirmed_unresolved=sum(r["decision"] == "unresolved" and r.get("person_confirmed", False) for r in rows),
                       source=source_summary,
                       evidence_counts=monitor.evidence_counts,
                       decisions={name: sum(r["decision"] == name for r in rows)
                                  for name in ("authorized", "queued", "unresolved", "interrupted")},
                       t1_passed=False, motor_commands_sent=0)
        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
