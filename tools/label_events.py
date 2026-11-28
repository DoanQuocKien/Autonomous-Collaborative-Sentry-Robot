"""Keypress event labeller for D4 onset timestamps (`Implementation Plan.md` §4.2, `docs/Lunge Protocol.md`).

Run alongside `python -m tools.record D4 --no-esp32` on the same laptop so `t_local`
(`time.time()`) and `t_perf` (`time.perf_counter()`) match `data/D4/jetbot_meta.jsonl`.

Live keypress controls (single key, no Enter required on TTY/Windows):
    Space / Enter / l  : record `lunge` onset in the active set (A..F)
    c                  : record `clap` (phone/laptop clock alignment marker)
    n                  : toggle `neg_start` / `neg_end` (normal walking segment)
    h                  : toggle `hard_neg_start` / `hard_neg_end` (hard-negative segment)
    1..6 or a,b,d,e,f,C : switch active lunge set (A..F; lowercase c is clap)
    x / u              : mark the most recent `lunge` event invalid (`valid=false`)
    q                  : quit and print summary counts

Post-recording helpers:
    python -m tools.label_events --out data/D4/events.csv --summary
    python -m tools.label_events --out data/D4/events.csv --align data/D4/jetbot_meta.jsonl
    python -m tools.label_events --out data/D4/events.csv --shift-refined -0.25
    python -m tools.label_events --out data/D4/events.csv --review data/D4
"""
import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import time
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


COLS = [
    "event_id",
    "label",
    "set_id",
    "t_local",
    "t_local_iso",
    "t_perf",
    "refined_t_local",
    "valid",
    "notes",
]

ALIGNED_COLS = COLS + [
    "frame_seq",
    "frame_file",
    "frame_t_cap",
    "frame_t_local",
    "dt_ms",
]

SETS = ("A", "B", "C", "D", "E", "F")
SET_KEYS = {
    "1": "A", "2": "B", "3": "C", "4": "D", "5": "E", "6": "F",
    "a": "A", "b": "B", "d": "D", "e": "E", "f": "F",
}


def stamp_iso(t_epoch: float) -> str:
    """Format epoch seconds as local 'YYYY-MM-DD HH:MM:SS.mmm' (matches tools/d1_label.py)."""
    return datetime.fromtimestamp(float(t_epoch)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


@dataclass
class EventRow:
    event_id: int
    label: str
    set_id: str
    t_local: float
    t_local_iso: str
    t_perf: float
    refined_t_local: Optional[float] = None
    valid: bool = True
    notes: str = ""

    def effective_t(self) -> float:
        return self.t_local if self.refined_t_local is None else self.refined_t_local

    def to_csv_row(self) -> Dict[str, str]:
        return {
            "event_id": str(self.event_id),
            "label": self.label,
            "set_id": self.set_id,
            "t_local": f"{self.t_local:.6f}",
            "t_local_iso": self.t_local_iso,
            "t_perf": f"{self.t_perf:.6f}",
            "refined_t_local": "" if self.refined_t_local is None else f"{self.refined_t_local:.6f}",
            "valid": "true" if self.valid else "false",
            "notes": self.notes,
        }

    @classmethod
    def from_csv_row(cls, row: Dict[str, str]) -> "EventRow":
        ref_raw = (row.get("refined_t_local") or "").strip()
        valid_raw = (row.get("valid") or "true").strip().lower()
        return cls(
            event_id=int(row["event_id"]),
            label=row["label"].strip(),
            set_id=(row.get("set_id") or "").strip(),
            t_local=float(row["t_local"]),
            t_local_iso=(row.get("t_local_iso") or "").strip(),
            t_perf=float(row.get("t_perf", "0.0") or 0.0),
            refined_t_local=float(ref_raw) if ref_raw else None,
            valid=valid_raw not in ("false", "0", "no", "n"),
            notes=(row.get("notes") or "").strip(),
        )


def load_events(path: Path) -> List[EventRow]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [EventRow.from_csv_row(r) for r in reader if (r.get("event_id") or "").strip()]


def save_events(path: Path, rows: Sequence[EventRow]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
        fh.flush()
    tmp.replace(path)


class EventRecorder:
    """Pure state & persistence controller for keypress onset labelling."""

    def __init__(
        self,
        out_path: Path,
        *,
        initial_set: str = "A",
        wall_clock: Callable[[], float] = time.time,
        perf_clock: Callable[[], float] = time.perf_counter,
        rows: Optional[List[EventRow]] = None,
    ):
        self.out_path = Path(out_path)
        self.active_set = self._validate_set(initial_set)
        self._wall_clock = wall_clock
        self._perf_clock = perf_clock
        self.rows: List[EventRow] = list(rows) if rows is not None else load_events(self.out_path)
        self._in_neg = False
        self._in_hard_neg = False
        self._reconcile_segment_flags()

    @staticmethod
    def _validate_set(value: str) -> str:
        s = value.strip().upper()
        if s not in SETS:
            raise ValueError(f"set_id must be one of {SETS}, got {value!r}")
        return s

    def _reconcile_segment_flags(self) -> None:
        for row in self.rows:
            if row.label == "neg_start":
                self._in_neg = True
            elif row.label == "neg_end":
                self._in_neg = False
            elif row.label == "hard_neg_start":
                self._in_hard_neg = True
            elif row.label == "hard_neg_end":
                self._in_hard_neg = False

    def _next_id(self) -> int:
        return max((r.event_id for r in self.rows), default=0) + 1

    def _append(self, label: str, set_id: str = "", notes: str = "") -> EventRow:
        t_local = float(self._wall_clock())
        t_perf = float(self._perf_clock())
        if not (math.isfinite(t_local) and math.isfinite(t_perf)):
            raise ValueError("clock timestamps must be finite")
        row = EventRow(
            event_id=self._next_id(),
            label=label,
            set_id=set_id,
            t_local=t_local,
            t_local_iso=stamp_iso(t_local),
            t_perf=t_perf,
            refined_t_local=None,
            valid=True,
            notes=notes,
        )
        self.rows.append(row)
        save_events(self.out_path, self.rows)
        return row

    def invalidate_last_lunge(self, reason: str = "marked invalid") -> Optional[EventRow]:
        for row in reversed(self.rows):
            if row.label == "lunge" and row.valid:
                row.valid = False
                row.notes = f"{row.notes}; {reason}".strip("; ") if row.notes else reason
                save_events(self.out_path, self.rows)
                return row
        return None

    def handle_key(self, key: str) -> Tuple[str, Optional[EventRow]]:
        """Process one pressed key -> (action_tag, created_or_updated_EventRow_or_None)."""
        if key is None or key == "":
            return "noop", None

        if key in (" ", "\r", "\n"):
            row = self._append("lunge", set_id=self.active_set)
            return "recorded", row

        if key == "C":
            self.active_set = "C"
            return "set_changed", None

        low = key.lower()
        if low == "l":
            row = self._append("lunge", set_id=self.active_set)
            return "recorded", row
        if low == "c":
            row = self._append("clap", set_id="")
            return "recorded", row
        if low == "n":
            lbl = "neg_end" if self._in_neg else "neg_start"
            self._in_neg = not self._in_neg
            row = self._append(lbl, set_id="")
            return "recorded", row
        if low == "h":
            lbl = "hard_neg_end" if self._in_hard_neg else "hard_neg_start"
            self._in_hard_neg = not self._in_hard_neg
            row = self._append(lbl, set_id="")
            return "recorded", row
        if low in SET_KEYS:
            self.active_set = SET_KEYS[low]
            return "set_changed", None
        if low in ("x", "u"):
            updated = self.invalidate_last_lunge()
            return ("invalidated", updated) if updated is not None else ("noop", None)
        if low == "q":
            return "quit", None
        return "noop", None


def summarize_events(rows: Sequence[EventRow]) -> Dict[str, object]:
    """Compute counts of valid/invalid lunges per set, claps, and negative intervals."""
    lunges = [r for r in rows if r.label == "lunge"]
    valid_lunges = [r for r in lunges if r.valid]
    invalid_lunges = [r for r in lunges if not r.valid]
    by_set = {s: sum(1 for r in valid_lunges if r.set_id == s) for s in SETS}
    claps = sum(1 for r in rows if r.label == "clap")
    neg_intervals = extract_intervals(rows, "neg_start", "neg_end")
    hard_neg_intervals = extract_intervals(rows, "hard_neg_start", "hard_neg_end")
    return {
        "total_events": len(rows),
        "total_lunges": len(lunges),
        "valid_lunges": len(valid_lunges),
        "invalid_lunges": len(invalid_lunges),
        "valid_by_set": by_set,
        "claps": claps,
        "negative_intervals": neg_intervals,
        "negative_duration_s": round(sum(b - a for a, b in neg_intervals), 3),
        "hard_negative_intervals": hard_neg_intervals,
        "hard_negative_duration_s": round(sum(b - a for a, b in hard_neg_intervals), 3),
    }


def extract_intervals(rows: Sequence[EventRow], start_label: str, end_label: str) -> List[Tuple[float, float]]:
    """Pair start/end segment events using effective timestamps."""
    intervals: List[Tuple[float, float]] = []
    open_t: Optional[float] = None
    for row in sorted(rows, key=lambda r: (r.effective_t(), r.event_id)):
        if not row.valid:
            continue
        t = row.effective_t()
        if row.label == start_label and open_t is None:
            open_t = t
        elif row.label == end_label and open_t is not None:
            if t > open_t:
                intervals.append((open_t, t))
            open_t = None
    return intervals


def apply_refined_shift(rows: Sequence[EventRow], offset_s: float, *, overwrite: bool = False) -> int:
    """Populate `refined_t_local = t_local + offset_s` for rows without a refined time (or all if overwrite=True)."""
    if not math.isfinite(offset_s):
        raise ValueError(f"offset_s must be finite, got {offset_s!r}")
    updated = 0
    for row in rows:
        if overwrite or row.refined_t_local is None:
            row.refined_t_local = row.t_local + offset_s
            updated += 1
    return updated


def load_meta_frames(meta_path: Path) -> List[Dict]:
    """Load `jetbot_meta.jsonl` frame records sorted by `t_local`."""
    meta_path = Path(meta_path)
    frames = []
    with meta_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if "t_local" in item:
                frames.append(item)
    frames.sort(key=lambda m: float(m["t_local"]))
    return frames


def align_events_to_frames(rows: Sequence[EventRow], frames: Sequence[Dict]) -> List[Dict[str, str]]:
    """Match each event's effective timestamp to the nearest frame in `jetbot_meta.jsonl`."""
    if not frames:
        raise ValueError("at least one frame metadata entry is required for alignment")
    times = [float(f["t_local"]) for f in frames]
    import bisect

    aligned = []
    for row in rows:
        t_ev = row.effective_t()
        idx = bisect.bisect_left(times, t_ev)
        candidates = []
        if idx < len(times):
            candidates.append(idx)
        if idx > 0:
            candidates.append(idx - 1)
        best_i = min(candidates, key=lambda i: abs(times[i] - t_ev))
        frame = frames[best_i]
        dt_ms = (times[best_i] - t_ev) * 1000.0
        out = row.to_csv_row()
        out.update({
            "frame_seq": str(frame.get("seq", "")),
            "frame_file": str(frame.get("file", "")),
            "frame_t_cap": "" if frame.get("t_cap") is None else f"{float(frame['t_cap']):.6f}",
            "frame_t_local": f"{float(frame['t_local']):.6f}",
            "dt_ms": f"{dt_ms:.2f}",
        })
        aligned.append(out)
    return aligned


def save_aligned_events(path: Path, aligned_rows: Sequence[Dict[str, str]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ALIGNED_COLS)
        writer.writeheader()
        writer.writerows(aligned_rows)


def _read_key_nonblocking_or_blocking() -> str:
    """Read one key press without Enter on Windows or POSIX TTY; line fallback when piped."""
    try:
        import msvcrt
        ch = msvcrt.getwch()
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    except ImportError:
        pass

    if sys.stdin is not None and sys.stdin.isatty():
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ch = sys.stdin.read(1)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    line = sys.stdin.readline()
    if line == "":
        return "q"
    return line[0]


def run_live_session(
    recorder: EventRecorder,
    *,
    read_key: Callable[[], str] = _read_key_nonblocking_or_blocking,
    output: Callable[[str], None] = print,
) -> Dict[str, object]:
    """Run the interactive keypress loop until `q` or EOF."""
    output(
        f"D4 event labeller -> {recorder.out_path} (set={recorder.active_set})\n"
        "Keys: [Space/Enter/l]=lunge  [c]=clap  [n]=neg_start/end  [h]=hard_neg_start/end  "
        "[1..6/a,b,d,e,f,C]=set  [x/u]=mark last lunge invalid  [q]=quit"
    )
    while True:
        try:
            key = read_key()
        except KeyboardInterrupt:
            output("\nInterrupted; saving and exiting.")
            break
        action, row = recorder.handle_key(key)
        if action == "quit":
            break
        if action == "recorded" and row is not None:
            set_txt = f" set={row.set_id}" if row.set_id else ""
            output(f"  [#{row.event_id:02d}] {row.label}{set_txt}  t={row.t_local:.3f} ({row.t_local_iso[11:]})")
        elif action == "invalidated" and row is not None:
            output(f"  [#{row.event_id:02d}] INVALIDATED (set={row.set_id}, t={row.t_local:.3f})")
        elif action == "set_changed":
            output(f"  active set -> {recorder.active_set}")
    summary = summarize_events(recorder.rows)
    output(
        f"Summary: {summary['valid_lunges']} valid lunges "
        f"({summary['invalid_lunges']} invalid), {summary['claps']} claps, "
        f"neg={summary['negative_duration_s']} s, by_set={summary['valid_by_set']}"
    )
    return summary


def run_review_ui(out_path: Path, data_dir: Path) -> None:
    """Optional OpenCV frame scrubber to refine `refined_t_local` against recorded JetBot frames."""
    import cv2

    data_dir = Path(data_dir)
    frames = load_meta_frames(data_dir / "jetbot_meta.jsonl")
    if not frames:
        raise SystemExit(f"no frames in {data_dir / 'jetbot_meta.jsonl'}")
    rows = load_events(out_path)
    if not rows:
        raise SystemExit(f"no events in {out_path}")

    import bisect
    frame_times = [float(f["t_local"]) for f in frames]
    ev_idx = 0

    def nearest_frame(t_val: float) -> int:
        pos = bisect.bisect_left(frame_times, t_val)
        if pos == 0:
            return 0
        if pos >= len(frame_times):
            return len(frame_times) - 1
        return pos if abs(frame_times[pos] - t_val) < abs(frame_times[pos - 1] - t_val) else pos - 1

    f_idx = nearest_frame(rows[ev_idx].effective_t())
    win = "D4 Event Review (a/d=+/-1, j/k=+/-10, p/n=prev/next event, Space=set refined, x=toggle valid, s=save, q=quit)"
    while True:
        meta = frames[f_idx]
        img = cv2.imread(str(data_dir / "jetbot" / meta["file"]))
        if img is None:
            f_idx = min(f_idx + 1, len(frames) - 1)
            continue
        ev = rows[ev_idx]
        dt_ms = (float(meta["t_local"]) - ev.effective_t()) * 1000.0
        hud = (
            f"Event #{ev.event_id} {ev.label} set={ev.set_id or '-'} valid={ev.valid} | "
            f"frame {f_idx + 1}/{len(frames)} dt={dt_ms:+.0f}ms"
        )
        cv2.putText(img, hud, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.imshow(win, img)
        k = cv2.waitKey(0) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("a"):
            f_idx = max(0, f_idx - 1)
        elif k == ord("d"):
            f_idx = min(len(frames) - 1, f_idx + 1)
        elif k == ord("j"):
            f_idx = max(0, f_idx - 10)
        elif k == ord("k"):
            f_idx = min(len(frames) - 1, f_idx + 10)
        elif k == ord("n"):
            ev_idx = min(len(rows) - 1, ev_idx + 1)
            f_idx = nearest_frame(rows[ev_idx].effective_t())
        elif k == ord("p"):
            ev_idx = max(0, ev_idx - 1)
            f_idx = nearest_frame(rows[ev_idx].effective_t())
        elif k in (ord(" "), 13):
            rows[ev_idx].refined_t_local = float(meta["t_local"])
            save_events(out_path, rows)
        elif k == ord("x"):
            rows[ev_idx].valid = not rows[ev_idx].valid
            save_events(out_path, rows)
        elif k == ord("s"):
            save_events(out_path, rows)
    cv2.destroyAllWindows()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/D4/events.csv"), help="Events CSV path")
    ap.add_argument("--set", dest="set_id", default="A", choices=SETS, help="Initial lunge set (A..F)")
    ap.add_argument("--summary", action="store_true", help="Print summary of an existing events CSV and exit")
    ap.add_argument("--align", type=Path, default=None, help="Path to jetbot_meta.jsonl to align events to frames")
    ap.add_argument("--aligned-out", type=Path, default=None, help="Output CSV path for --align (default: <out_stem>_aligned.csv)")
    ap.add_argument("--shift-refined", type=float, default=None, help="Shift raw t_local by offset_s into refined_t_local where blank")
    ap.add_argument("--overwrite-refined", action="store_true", help="With --shift-refined, overwrite existing refined_t_local values")
    ap.add_argument("--review", type=Path, default=None, help="OpenCV frame scrubber on a recorded data directory (e.g. data/D4)")
    args = ap.parse_args(argv)

    if args.summary:
        rows = load_events(args.out)
        print(json.dumps(summarize_events(rows), indent=2))
        return 0

    if args.shift_refined is not None:
        rows = load_events(args.out)
        n = apply_refined_shift(rows, args.shift_refined, overwrite=args.overwrite_refined)
        save_events(args.out, rows)
        print(f"Updated refined_t_local on {n} event(s) in {args.out}")
        return 0

    if args.align is not None:
        rows = load_events(args.out)
        frames = load_meta_frames(args.align)
        aligned = align_events_to_frames(rows, frames)
        dest = args.aligned_out or args.out.with_name(f"{args.out.stem}_aligned.csv")
        save_aligned_events(dest, aligned)
        print(f"Aligned {len(aligned)} event(s) to {dest}")
        return 0

    if args.review is not None:
        run_review_ui(args.out, args.review)
        return 0

    recorder = EventRecorder(args.out, initial_set=args.set_id)
    run_live_session(recorder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
