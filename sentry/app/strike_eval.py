"""False-trigger and strike-evaluation harness (`Implementation Plan.md` §4.3, Week 8).

Evaluates strike detection false-trigger rate on normal walking (and optional
onset recall/latency when D4 lunge labels are supplied), gating raw detections
through both the `StateMachine` (`EVADE` + `evade_cooldown_s`) and `EvasionOverride`.

Pure CPU logic: works offline on synthetic trajectories, recorded JSONL
predictions, or any pluggable detector callable (e.g. `sentry.perception.pose`).
"""
from collections import deque
from dataclasses import dataclass
import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from sentry.app.state_machine import State, StateMachine, StateMachineConfig
from sentry.config import load as load_config
from sentry.nav.evasion import EvasionOverride


@dataclass(frozen=True)
class StrikeEvalConfig:
    strike_area_growth: float = 0.40
    strike_window_s: float = 0.10
    evade_duration_s: float = 0.40
    evade_cooldown_s: float = 1.00
    max_false_triggers_per_5min: float = 1.0
    min_neg_duration_s: float = 600.0
    min_recall: float = 0.90
    max_latency_ms: float = 150.0

    @classmethod
    def from_toml(cls, cfg: Optional[Dict[str, Any]] = None) -> "StrikeEvalConfig":
        raw = load_config() if cfg is None else cfg
        t = raw.get("thresholds", {})
        sm = raw.get("state_machine", {})
        return cls(
            strike_area_growth=float(t.get("strike_area_growth", 0.40)),
            strike_window_s=float(t.get("strike_window_s", 0.10)),
            evade_duration_s=float(t.get("evade_duration_s", 0.40)),
            evade_cooldown_s=float(sm.get("evade_cooldown_s", 1.00)),
        )


def bbox_area(bbox: Optional[Sequence[float]]) -> float:
    if bbox is None or len(bbox) != 4:
        return 0.0
    x1, y1, x2, y2 = (float(v) for v in bbox)
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return 0.0
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


class BboxStrikeBaseline:
    """Reference timestamp-windowed `dA/A > strike_area_growth` detector for T0/baseline checks.

    Uses elapsed timestamps (`strike_window_s`), never frame counts. Replaced or
    wrapped by HNHL's `sentry/perception/pose.py` lunge detector when integrated.
    """

    def __init__(
        self,
        area_growth: float = 0.40,
        window_s: float = 0.10,
        min_area_px2: float = 400.0,
    ):
        if not (math.isfinite(area_growth) and area_growth > 0.0):
            raise ValueError(f"area_growth must be finite and > 0, got {area_growth!r}")
        if not (math.isfinite(window_s) and window_s > 0.0):
            raise ValueError(f"window_s must be finite and > 0, got {window_s!r}")
        self.area_growth = float(area_growth)
        self.window_s = float(window_s)
        self.min_area_px2 = float(min_area_px2)
        self._hist: deque = deque()
        self._last_t: Optional[float] = None
        self._last_epoch: Optional[Any] = None

    def reset(self) -> None:
        self._hist.clear()
        self._last_t = None
        self._last_epoch = None

    def __call__(self, t: float, sample: Dict[str, Any]) -> bool:
        epoch = sample.get("epoch", 0)
        if self._last_epoch is not None and epoch != self._last_epoch:
            self._hist.clear()
        if self._last_t is not None and t <= self._last_t:
            self._hist.clear()
        self._last_t = t
        self._last_epoch = epoch

        area = bbox_area(sample.get("bbox"))
        if area < self.min_area_px2:
            self._hist.clear()
            return False
        cutoff = t - self.window_s
        while self._hist and self._hist[0][0] < cutoff:
            self._hist.popleft()
        triggered = False
        for t_prev, a_prev in self._hist:
            if t > t_prev and a_prev >= self.min_area_px2:
                if (area - a_prev) / a_prev > self.area_growth:
                    triggered = True
                    break
        self._hist.append((t, area))
        return triggered


def _normalize_sample(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        if "t" not in item:
            raise ValueError("sample dict must contain 't'")
        out = dict(item)
        out["t"] = float(out["t"])
        return out
    if isinstance(item, (tuple, list)) and len(item) == 2:
        t, payload = float(item[0]), item[1]
        if isinstance(payload, bool):
            return {"t": t, "strike": payload}
        return {"t": t, "bbox": payload}
    raise TypeError(f"unsupported sample type: {type(item).__name__}")


def _merge_intervals(intervals: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    cleaned = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not cleaned:
        return []
    merged = [cleaned[0]]
    for a, b in cleaned[1:]:
        pa, pb = merged[-1]
        if a <= pb:
            merged[-1] = (pa, max(pb, b))
        else:
            merged.append((a, b))
    return merged


def _in_intervals(t: float, intervals: Sequence[Tuple[float, float]]) -> bool:
    return any(a <= t <= b for a, b in intervals)


def _subtract_intervals(
    base: Sequence[Tuple[float, float]],
    excluded: Sequence[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    result = list(base)
    for ex_a, ex_b in _merge_intervals(excluded):
        next_res: List[Tuple[float, float]] = []
        for a, b in result:
            if ex_b <= a or ex_a >= b:
                next_res.append((a, b))
            else:
                if ex_a > a:
                    next_res.append((a, ex_a))
                if ex_b < b:
                    next_res.append((ex_b, b))
        result = next_res
    return result


def evaluate_false_triggers(
    samples: Iterable[Any],
    *,
    detector: Optional[Callable[[float, Dict[str, Any]], bool]] = None,
    cfg: Optional[StrikeEvalConfig] = None,
    sm_cfg: Optional[StateMachineConfig] = None,
    negative_intervals: Optional[Sequence[Tuple[float, float]]] = None,
    exclude_onsets: Optional[Sequence[float]] = None,
    exclude_window: Tuple[float, float] = (-0.5, 1.5),
    episode_gap_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluate false triggers per minute and per 5 min on normal walking samples."""
    cfg = StrikeEvalConfig.from_toml() if cfg is None else cfg
    sm_cfg = StateMachineConfig.from_toml() if sm_cfg is None else sm_cfg
    det = BboxStrikeBaseline(cfg.strike_area_growth, cfg.strike_window_s) if detector is None else detector
    ep_gap = cfg.evade_duration_s if episode_gap_s is None else float(episode_gap_s)
    if not (math.isfinite(ep_gap) and ep_gap >= 0.0):
        raise ValueError(f"episode_gap_s must be finite and >= 0, got {ep_gap!r}")

    norm = [_normalize_sample(s) for s in samples]
    if len(norm) < 2:
        raise ValueError("at least two samples are required to evaluate false-trigger rate")
    prev_t = None
    for s in norm:
        t = s["t"]
        if not math.isfinite(t):
            raise ValueError(f"sample timestamp must be finite, got {t!r}")
        if prev_t is not None and t < prev_t:
            raise ValueError(f"sample timestamps must be non-decreasing: {t} < {prev_t}")
        prev_t = t

    t_start, t_end = norm[0]["t"], norm[-1]["t"]
    active_intervals = _merge_intervals(negative_intervals) if negative_intervals else [(t_start, t_end)]
    if exclude_onsets:
        pre, post = float(exclude_window[0]), float(exclude_window[1])
        ex = [(float(o) + pre, float(o) + post) for o in exclude_onsets]
        active_intervals = _subtract_intervals(active_intervals, ex)

    duration_s = sum(max(0.0, min(b, t_end) - max(a, t_start)) for a, b in active_intervals)
    if duration_s <= 0.0:
        raise ValueError("effective negative-evaluation duration must be > 0 s")

    # Shift machine start slightly before t_start to avoid exact-zero boundary issues
    sm = StateMachine(sm_cfg, initial_state=State.PURSUE, t0=t_start)
    sm.active_target = "eval_target"
    evasion = EvasionOverride(sm_cfg.evade_v, sm_cfg.evade_w, sm_cfg.evade_duration_s, sm_cfg.evade_cooldown_s)

    raw_strike_frames = 0
    false_trigger_episodes = 0
    last_raw_trigger_t: Optional[float] = None
    evade_entries = 0
    cooldown_suppressed = 0
    evade_timestamps: List[float] = []
    evaluated_samples = 0

    for s in norm:
        t = s["t"]
        sm.tick(t)
        if not _in_intervals(t, active_intervals):
            continue
        evaluated_samples += 1

        if detector is not None:
            is_strike = bool(det(t, s))
        elif "strike" in s:
            is_strike = bool(s["strike"])
        else:
            is_strike = bool(det(t, s))

        if not is_strike:
            continue

        raw_strike_frames += 1
        if last_raw_trigger_t is None or (t - last_raw_trigger_t) > ep_gap:
            false_trigger_episodes += 1
        last_raw_trigger_t = t

        ev_data = {}
        if "obstacle_side" in s and s["obstacle_side"] is not None:
            ev_data["obstacle_side"] = s["obstacle_side"]
        res = sm.handle_event("STRIKE", data=ev_data or None, t=t)
        ov_accepted = evasion.trigger(t, s.get("obstacle_bearing_rad"))
        if not res.ignored and res.state == State.EVADE and ov_accepted:
            evade_entries += 1
            evade_timestamps.append(round(t, 6))
        else:
            cooldown_suppressed += 1

    duration_min = duration_s / 60.0
    rate_per_min = evade_entries / duration_min
    rate_per_5min = rate_per_min * 5.0
    raw_ep_per_min = false_trigger_episodes / duration_min
    limit_met = rate_per_5min <= cfg.max_false_triggers_per_5min
    protocol_complete = duration_s >= cfg.min_neg_duration_s

    return {
        "samples_total": len(norm),
        "samples_evaluated": evaluated_samples,
        "duration_s": round(duration_s, 3),
        "duration_min": round(duration_min, 4),
        "raw_strike_frames": raw_strike_frames,
        "false_trigger_episodes": false_trigger_episodes,
        "evade_entries": evade_entries,
        "cooldown_suppressed": cooldown_suppressed,
        "raw_episodes_per_min": round(raw_ep_per_min, 4),
        "false_triggers_per_min": round(rate_per_min, 4),
        "false_triggers_per_5min": round(rate_per_5min, 4),
        "max_allowed_per_5min": cfg.max_false_triggers_per_5min,
        "limit_met": bool(limit_met),
        "protocol_complete": bool(protocol_complete),
        "t1_passed": bool(protocol_complete and limit_met),
        "trigger_timestamps": evade_timestamps,
    }


def evaluate_onsets(
    samples: Iterable[Any],
    onset_times: Sequence[float],
    *,
    detector: Optional[Callable[[float, Dict[str, Any]], bool]] = None,
    cfg: Optional[StrikeEvalConfig] = None,
    pre_tol_s: float = 0.15,
    post_tol_s: float = 0.60,
) -> Dict[str, Any]:
    """Match detected strike timestamps against labeled lunge onset timestamps for recall & delay."""
    cfg = StrikeEvalConfig.from_toml() if cfg is None else cfg
    det = BboxStrikeBaseline(cfg.strike_area_growth, cfg.strike_window_s) if detector is None else detector

    triggers: List[float] = []
    for item in samples:
        s = _normalize_sample(item)
        t = s["t"]
        if detector is not None:
            hit = bool(det(t, s))
        elif "strike" in s:
            hit = bool(s["strike"])
        else:
            hit = bool(det(t, s))
        if hit:
            triggers.append(t)

    onsets = sorted(float(o) for o in onset_times)
    if not onsets:
        return {
            "total_onsets": 0,
            "matched_onsets": 0,
            "missed_onsets": 0,
            "recall": None,
            "recall_met": False,
            "delays_ms": [],
            "median_delay_ms": None,
            "p95_delay_ms": None,
        }

    delays_ms: List[float] = []
    matched = 0
    for onset in onsets:
        lo, hi = onset - pre_tol_s, onset + post_tol_s
        hits = [tr for tr in triggers if lo <= tr <= hi]
        if hits:
            matched += 1
            delays_ms.append(round((hits[0] - onset) * 1000.0, 2))

    recall = matched / len(onsets)
    return {
        "total_onsets": len(onsets),
        "matched_onsets": matched,
        "missed_onsets": len(onsets) - matched,
        "recall": round(recall, 4),
        "recall_met": recall >= cfg.min_recall,
        "delays_ms": delays_ms,
        "median_delay_ms": round(float(np.median(delays_ms)), 2) if delays_ms else None,
        "p95_delay_ms": round(float(np.percentile(delays_ms, 95)), 2) if delays_ms else None,
    }


def _bbox_for_person(range_m: float, x_norm: float, width_px: int = 640, height_px: int = 480) -> Tuple[float, float, float, float]:
    """Simple pinhole projection of a 1.7 m x 0.45 m person at `range_m` and normalized x in [0, 1]."""
    fy = 360.0
    box_h = min(float(height_px), fy * 1.70 / max(0.5, range_m))
    box_w = fy * 0.45 / max(0.5, range_m)
    cx = x_norm * width_px
    cy = height_px * 0.52
    x1 = max(0.0, cx - box_w / 2.0)
    x2 = min(float(width_px), cx + box_w / 2.0)
    y1 = max(0.0, cy - box_h / 2.0)
    y2 = min(float(height_px), cy + box_h / 2.0)
    return (x1, y1, x2, y2)


def generate_synthetic_walking_stream(
    duration_s: float = 600.0,
    fps: float = 20.0,
    seed: int = 532,
    jitter_frac: float = 0.02,
) -> List[Dict[str, Any]]:
    """Generate a deterministic 10-min synthetic walking + hard-negative stream (D4 section 6 profile).

    Covers:
      - cross-view walking at 1.8..3.0 m
      - walking directly toward the robot at 1.25 m/s stopping at 1.2 m
      - standing/waving/bending width/height perturbations
      - realistic detector bbox jitter (`jitter_frac`)
    """
    rng = np.random.RandomState(seed)
    n = int(round(duration_s * fps)) + 1
    dt = 1.0 / fps
    samples: List[Dict[str, Any]] = []

    for i in range(n):
        t = round(i * dt, 4)
        phase = t % 60.0
        if phase < 20.0:
            # Walking across the room at 2.4 m
            r = 2.4
            x_norm = 0.5 + 0.30 * math.sin(2.0 * math.pi * phase / 20.0)
        elif phase < 36.0:
            # Hard negative: walk toward robot at 1.2 m/s (2.4 m -> 1.2 m), pause, walk back to 2.4 m
            sub = (phase - 20.0) % 8.0
            if sub < 1.0:
                r = 2.4 - 1.2 * sub
            elif sub < 3.0:
                r = 1.2
            elif sub < 4.5:
                r = 1.2 + 0.8 * (sub - 3.0)
            else:
                r = 2.4
            x_norm = 0.5
        elif phase < 50.0:
            # Standing / bending / waving between 2.4 m and 1.8 m (continuous at boundaries)
            u = (phase - 36.0) / 14.0
            r = 2.4 - 0.6 * (0.5 - 0.5 * math.cos(2.0 * math.pi * u))
            x_norm = 0.5 + 0.04 * math.sin(2.0 * math.pi * u)
        else:
            # Crossing paths at 2.4 m
            u = (phase - 50.0) / 10.0
            r = 2.4
            x_norm = 0.5 + 0.25 * math.sin(2.0 * math.pi * u)

        x1, y1, x2, y2 = _bbox_for_person(r, x_norm)
        w, h = x2 - x1, y2 - y1
        dw = float(rng.normal(0.0, jitter_frac)) * w
        dh = float(rng.normal(0.0, jitter_frac)) * h
        bbox = (
            max(0.0, x1 - dw / 2.0),
            max(0.0, y1 - dh / 2.0),
            min(640.0, x2 + dw / 2.0),
            min(480.0, y2 + dh / 2.0),
        )
        samples.append({"t": t, "bbox": bbox, "scenario": "synthetic_normal_walking"})
    return samples


def generate_synthetic_lunge_burst_stream(
    duration_s: float = 30.0,
    fps: float = 20.0,
    onset_times: Sequence[float] = (5.0, 15.0, 25.0),
) -> List[Dict[str, Any]]:
    """Generate a short stream containing fast lunge area-growth bursts at `onset_times`."""
    n = int(round(duration_s * fps)) + 1
    dt = 1.0 / fps
    samples: List[Dict[str, Any]] = []
    for i in range(n):
        t = round(i * dt, 4)
        r = 2.4
        for onset in onset_times:
            if onset <= t <= onset + 0.35:
                # Rapid forward commit from 2.4 m toward 1.1 m in 0.25 s
                prog = min(1.0, (t - onset) / 0.25)
                r = 2.4 - 1.3 * prog
                break
        samples.append({"t": t, "bbox": _bbox_for_person(r, 0.5)})
    return samples
