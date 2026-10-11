"""Clock-corrected video telemetry; CSV rows retain all raw timestamps."""
import csv
import math
from pathlib import Path

from sentry.config import load


def percentile(values, q):
    values = sorted(values)
    if not values or not 0 <= q <= 1:
        raise ValueError("need values and a quantile in [0, 1]")
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


class LatencyLogger:
    def __init__(self, path, estimate):
        self.estimate = estimate
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["seq", "t_cap_jetson_s", "t_rx_laptop_s", "t_decode_laptop_s",
                               "offset_jetson_minus_laptop_s", "sync_rtt_s",
                               "receive_latency_ms", "decoded_latency_ms", "negative_latency"])
        self._latencies = []
        self._times = []
        self._seqs = []
        self._negative = 0

    def write(self, frame):
        local_cap = self.estimate.to_local(frame.t_cap)
        rx_ms = (frame.t_rx - local_cap) * 1000
        decoded_ms = (frame.t_decode - local_cap) * 1000
        if not all(math.isfinite(x) for x in (rx_ms, decoded_ms)):
            raise ValueError("nonfinite frame timestamps")
        self._writer.writerow([frame.seq, frame.t_cap, frame.t_rx, frame.t_decode,
                               self.estimate.offset_s, self.estimate.rtt_s,
                               rx_ms, decoded_ms, int(rx_ms < 0 or decoded_ms < 0)])
        self._file.flush()
        self._latencies.append(decoded_ms)
        self._times.append(frame.t_decode)
        self._seqs.append(frame.seq)
        self._negative += int(rx_ms < 0 or decoded_ms < 0)

    def summary(self):
        cfg = load()["telemetry"]
        count = len(self._times)
        duration = self._times[-1] - self._times[0] if count > 1 else 0
        fps = (count - 1) / duration if duration > 0 else 0
        p95 = percentile(self._latencies, 0.95) if count else None
        negative = self._negative
        resets = sum(b <= a for a, b in zip(self._seqs, self._seqs[1:]))
        # Seq gaps include deliberate latest-frame drops; never call them packet loss.
        gaps = sum(max(0, b - a - 1) for a, b in zip(self._seqs, self._seqs[1:]))
        return {"frames": count, "observed_duration_s": duration, "delivered_fps": fps,
                "decoded_latency_p50_ms": percentile(self._latencies, 0.5) if count else None,
                "decoded_latency_p95_ms": p95,
                "negative_latency_frames": negative, "sequence_resets": resets,
                "sequence_gaps": gaps, "clock_offset_s": self.estimate.offset_s,
                "clock_rtt_s": self.estimate.rtt_s, "clock_samples": self.estimate.samples,
                "clock_uncertainty_ms": self.estimate.rtt_s * 500,
                "pass": count > 1 and negative == 0 and resets == 0
                and p95 < cfg["latency_p95_limit_ms"] and fps >= cfg["min_fps"]}

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
