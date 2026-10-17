"""Fetch pinned Issue #43 weights; --world prepares offline YOLO-World prompts.

Install requirements-floor.txt for segmentation and requirements-world.txt for
vocabulary preparation. CLIP downloads on first preparation, never in inference.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.request

from sentry.config import DEFAULT_PATH, load

FLOOR_REPO = "nvidia/segformer-b0-finetuned-ade-512-512"
FLOOR_REVISION = "489d5cd81a0b59fab9b7ea758d3548ebe99677da"
FLOOR_HASHES = {
    "config.json": "209caa9091e4632f7c8883c11170cd08ad29af68b23c09590aa4a5befb1a2a7f",
    "preprocessor_config.json": "8039d1d210abaa7117ad78e58cdfd6141a2ec72c03dae891b3cd76737e422c6c",
    "model.safetensors": "6ae39addd01de6b1b8bde2cf677d43a5cd733424b8d186de3f95d1c51fee23f9",
}
WORLD_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt"
WORLD_SHA256 = "9b2c17ab6124a913e9b3a5c170617920d91b0f01111a8479da69f00e2cf27792"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url, destination, expected):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if sha256(destination) != expected:
            raise ValueError('existing artifact hash mismatch: ' + str(destination))
        return destination
    part = destination.with_suffix(destination.suffix + '.part')
    with urllib.request.urlopen(url, timeout=60) as response, part.open('wb') as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
    if sha256(part) != expected:
        raise ValueError('download hash mismatch: ' + str(destination))
    part.replace(destination)
    return destination


def run(config_path=DEFAULT_PATH, world=False):
    config = load(config_path)
    root = Path(config_path).resolve().parent
    folder = root / config['floor_segmentation']['model_path']
    hashes = {}
    for name, digest in FLOOR_HASHES.items():
        path = fetch('https://huggingface.co/' + FLOOR_REPO + '/resolve/' + FLOOR_REVISION + '/' + name,
                     folder / name, digest)
        hashes[name] = sha256(path)
    source = dict(repo=FLOOR_REPO, revision=FLOOR_REVISION, sha256=hashes,
                  license_url='https://github.com/NVlabs/SegFormer/blob/master/LICENSE')
    (folder / 'source.json').write_text(json.dumps(source, indent=2), encoding='utf-8')
    if world:
        if importlib.util.find_spec('clip') is None:
            raise ImportError('preparation needs pip install -r requirements-world.txt')
        from ultralytics import YOLOWorld
        settings = config['open_vocabulary']
        destination = root / settings['weights']
        manifest_path = destination.with_suffix('.json')
        if destination.is_file() and manifest_path.is_file():
            previous = json.loads(manifest_path.read_text(encoding='utf-8'))
            if previous['prompts'] == settings['prompts'] and previous['sha256'] == sha256(destination):
                return source
        base = fetch(WORLD_URL, root / 'data/models/yolov8s-worldv2.pt', WORLD_SHA256)
        model = YOLOWorld(str(base))
        model.set_classes(settings['prompts'])
        if hasattr(model.model, 'clip_model'):
            del model.model.clip_model
        destination.parent.mkdir(parents=True, exist_ok=True)
        model.save(destination)
        manifest = dict(source_url=WORLD_URL, base_sha256=WORLD_SHA256,
                        prompts=settings['prompts'], sha256=sha256(destination),
                        clip_revision='7ffa84b3bfa40c42ecc1c77147a855e69cb2dd40')
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', default=str(DEFAULT_PATH))
    ap.add_argument('--world', action='store_true')
    a = ap.parse_args()
    print(json.dumps(run(a.config, a.world), indent=2))


if __name__ == '__main__':
    main()
