"""Offline model smoke/latency on generated BGR input; never an accuracy benchmark."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np

from sentry.config import DEFAULT_PATH
from sentry.perception.reid import ARCHITECTURES, OSNetEncoder, PersonReID


def run(out, iterations=20, config_path=DEFAULT_PATH):
    if iterations < 1:
        raise ValueError('positive iterations required')
    import torch
    crop = np.random.default_rng(532).integers(0, 256, (256, 128, 3), np.uint8)
    rows = {}
    for name in ARCHITECTURES:
        encoder = OSNetEncoder.from_config(name, config_path)
        for _ in range(3):
            encoder.encode([crop])
        timings = []
        for _ in range(iterations):
            start = time.perf_counter()
            vector = encoder.encode([crop])[0]
            timings.append((time.perf_counter() - start) * 1000)
        repeat = encoder.encode([crop])[0]
        rows[name] = dict(model_id=encoder.model_id, device=str(next(encoder.model.parameters()).device),
                          dtype=str(next(encoder.model.parameters()).dtype), dimensions=len(vector),
                          norm=float(np.linalg.norm(vector)), repeat_max_abs=float(np.max(np.abs(vector - repeat))),
                          latency_p50_ms=float(np.median(timings)), latency_p95_ms=float(np.percentile(timings, 95)))
    pipeline = PersonReID.from_config(config_path)
    result = pipeline(np.full((480, 640, 3), 128, np.uint8), 1)
    report = dict(kind='synthetic runtime smoke; not D2/D3 accuracy or model selection', models=rows,
                  person_pipeline_candidates=len(result.people), warmup=3, iterations=iterations,
                  gpu=torch.cuda.get_device_name() if torch.cuda.is_available() else None,
                  versions={n: importlib.metadata.version(n) for n in ('torch', 'torchreid', 'torchvision')},
                  config_sha256=hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
                  t1_passed=False, recommended_model=None, motor_commands_sent=0)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    ap.add_argument('--iterations', type=int, default=20)
    a = ap.parse_args()
    print(json.dumps(run(a.out, a.iterations), indent=2))


if __name__ == '__main__':
    main()
