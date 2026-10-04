"""Frame contract for live receivers and the record/replay tools."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VideoFrame:
    seq: int
    t_cap: float  # source monotonic seconds (NOT the laptop clock)
    t_rx: float  # laptop perf_counter seconds, immediately after receiving the message
    t_decode: float  # same high-resolution monotonic domain, after JPEG decode
    frame_bgr: np.ndarray
    jpeg: bytes  # original wire bytes, useful for lossless recording

    @property
    def w(self):
        return self.frame_bgr.shape[1]

    @property
    def h(self):
        return self.frame_bgr.shape[0]
