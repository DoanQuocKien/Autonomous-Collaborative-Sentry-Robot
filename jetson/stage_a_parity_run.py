"""Run the W8 detector parity inputs on Nano; Python 3.6, no motor I/O.

python jetson/stage_a_parity_run.py --bundle /workspace/stage_a \
    --onnx /workspace/yolov8n_320_op11.onnx --engine /workspace/y320_fp16.engine \
    --out /workspace/stage_a_trt

Copy the new output directory back to the laptop. TensorRT/PyCUDA are imported
only when running an engine. The ONNX hash identifies the operator-supplied
build source; it does not independently prove how an existing engine was built.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform

import numpy as np

SCHEMA = 'stage-a-yolo-v1'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_inputs(bundle):
    bundle = Path(bundle)
    manifest = json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    frames = manifest.get('frames', [])
    if (manifest.get('schema') != SCHEMA or not frames
            or len({r['id'] for r in frames}) != len(frames)):
        raise ValueError('invalid manifest or duplicate frame IDs')
    if sha256(bundle/'inputs.npz') != manifest['inputs_sha256']:
        raise ValueError('input archive hash mismatch')
    with np.load(str(bundle/'inputs.npz'), allow_pickle=False) as arrays:
        canvases = arrays['canvases']
    if canvases.dtype != np.uint8 or canvases.shape != (len(frames), 320, 320, 3):
        raise ValueError('expected uint8 N x 320 x 320 x 3 canvases')
    return manifest, canvases


def blob(canvas):
    import cv2
    return cv2.dnn.blobFromImage(canvas, 1.0 / 255.0, swapRB=True)


def run(bundle, onnx, engine, out, engine_factory=None):
    manifest, canvases = load_inputs(bundle)
    if sha256(onnx) != manifest['onnx_sha256']:
        raise ValueError('wrong ONNX build source')
    out = Path(out)
    if out.exists():
        raise FileExistsError('choose a fresh output directory')
    runtime = dict(python=platform.python_version(), numpy=np.__version__, platform=platform.platform())
    backend = 'test-double'
    if engine_factory is None:
        import tensorrt
        try:
            from .trt_runtime import TrtEngine
        except ImportError:
            from trt_runtime import TrtEngine
        engine_factory = TrtEngine
        runtime['tensorrt'] = tensorrt.__version__
        backend = 'tensorrt'
    engine_digest, manifest_digest = sha256(engine), sha256(Path(bundle)/'manifest.json')
    runner = engine_factory(str(engine))
    if tuple(runner.input_shape) != (1, 3, 320, 320):
        raise ValueError('engine input must be fixed 1x3x320x320')
    outputs = []
    for canvas in canvases:
        result = runner.infer(blob(canvas))
        if len(result) != 1 or result[0].shape != (1, 84, 2100) or not np.isfinite(result[0]).all():
            raise ValueError('engine must return one finite raw 1x84x2100 output')
        outputs.append(result[0][0].astype(np.float32))
    if sha256(engine) != engine_digest or sha256(Path(bundle)/'manifest.json') != manifest_digest:
        raise ValueError('engine/manifest changed during inference')
    out.mkdir(parents=True)
    np.savez_compressed(str(out/'raw.npz'), raw=np.stack(outputs))
    info = dict(schema=SCHEMA, backend=backend, complete=True,
        onnx_sha256=manifest['onnx_sha256'], engine_sha256=engine_digest,
        manifest_sha256=manifest_digest, inputs_sha256=manifest['inputs_sha256'],
        frame_ids=[r['id'] for r in manifest['frames']],
        raw_sha256=sha256(out/'raw.npz'), runtime=runtime, motor_commands_sent=0,
        engine_provenance='operator supplies the ONNX used for the engine build')
    (out/'result.json').write_text(json.dumps(info, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'onnx', 'engine', 'out'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    result = run(args.bundle, args.onnx, args.engine, args.out)
    print(json.dumps(dict(backend=result['backend'], frames=len(result['frame_ids']),
                         engine_sha256=result['engine_sha256'])))


if __name__ == '__main__':
    main()
