import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from tools.detect_lunges import run


def recording(root):
    folder = root/'D4/session'
    (folder/'jetbot').mkdir(parents=True)
    rows = []
    for i in range(4):
        name = '%06d.jpg' % i
        cv2.imwrite(str(folder/'jetbot'/name), np.zeros((480, 640, 3), np.uint8))
        rows.append(dict(seq=i, t_cap=10.+i*.05, t_local=1000.+i*.25,
                         w=640, h=480, file=name))
    (folder/'jetbot_meta.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return folder


class Estimator:
    actual_device = 'cpu'

    def __init__(self, root):
        self.weights = root/'test-weights.bin'
        self.weights.write_bytes(b'fake test fixture, no inference')
        self.i = 0

    def predict(self, image):
        boxes = [[(10, 10, 20, 110)], [(10, 10, 25, 110)], [],
                 [(10, 10, 20, 110), (40, 10, 50, 110)]][self.i]
        self.i += 1
        return [SimpleNamespace(xyxy=b, keypoints_xy=np.zeros((17, 2)),
                                keypoints_conf=np.ones(17)) for b in boxes]


def test_private_offline_export_preserves_both_clocks_and_missing_frames(tmp_path):
    folder = recording(tmp_path)
    out = tmp_path/'D4/pose-01'
    result = run(folder, out, Estimator(tmp_path), data_root=tmp_path)
    predictions = [json.loads(x) for x in (out/'strikes.jsonl').read_text().splitlines()]
    assert len(predictions) == result['frames'] == 4
    assert predictions[1]['strike']  # capture interval .05; receive interval .25
    assert predictions[1]['t'] == 1000.25 and predictions[1]['t_cap'] == 10.05
    assert predictions[2]['bbox'] is None and predictions[3]['bbox'] is None
    assert result['missing'] == result['ambiguous'] == result['strikes'] == 1
    assert not result['t1_passed'] and result['motor_commands_sent'] == 0
    assert 'strike' not in json.loads((out/'pose.jsonl').read_text().splitlines()[0])
    with pytest.raises(FileExistsError):
        run(folder, out, Estimator(tmp_path), data_root=tmp_path)


def test_output_outside_private_data_and_missing_label_clock_are_rejected(tmp_path):
    folder = recording(tmp_path)
    estimator = Estimator(tmp_path)
    with pytest.raises(ValueError, match='under data'):
        run(folder, tmp_path.parent/'public-output', estimator, data_root=tmp_path)
    path = folder/'jetbot_meta.jsonl'
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[1].pop('t_local')
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(ValueError, match='t_local'):
        run(folder, tmp_path/'output', estimator, data_root=tmp_path)
    assert not (tmp_path/'output').exists()
