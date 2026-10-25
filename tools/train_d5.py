"""D5 YOLOv8n development fine-tuning (Week 3, HNHL).

Use the existing, manually curated D5_yolo_dev export. The exported dataset
contains one session and must NOT be described as independent D5 T1.

Read-only preflight:
    python -m tools.train_d5 --prepare-only
Optional NEW experiment (does not overwrite old runs):
    python -m tools.train_d5 --train --imgsz 320 --epochs 30 --batch 8
Revalidate an existing checkpoint:
    python -m tools.train_d5 --val PATH_TO_BEST_PT --imgsz 320
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data" / "D5_yolo_dev"
DATASET_YAML = DATASET_DIR / "data.yaml"
CLASSES = ["leg", "footwear", "backpack", "bag", "wire", "chair", "table", "plant"]
SIZES = (320, 416, 640)


def inspect_dataset(yaml_path: Optional[Path] = None) -> dict:
    """Validate an existing YOLO export without changing any file."""
    import yaml  # PyYAML, installed with Ultralytics

    config = Path(yaml_path) if yaml_path is not None else DATASET_YAML
    config = config.resolve()
    if not config.is_file():
        raise FileNotFoundError(
            f"Dataset YAML not found: {config}. "
            "First run: python -m tools.prepare_d5_yolo_dev"
        )

    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {config}")

    names = data.get("names")
    if isinstance(names, dict):
        try:
            ordered_names = [names.get(i, names.get(str(i))) for i in range(len(CLASSES))]
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid class names") from exc
    elif isinstance(names, list):
        ordered_names = names
    else:
        raise ValueError("Expected dataset 'names' mapping or list")
    if ordered_names != CLASSES:
        raise ValueError(f"D5 class ordering mismatch: {ordered_names!r}")

    raw_root = data.get("path")
    if raw_root:
        source_root = Path(str(raw_root))
        if not source_root.is_absolute():
            source_root = config.parent / source_root
    else:
        source_root = config.parent
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(
            f"Dataset root {source_root} is missing; "
            "the generated data.yaml may contain a stale absolute path. "
            "Regenerate the development export safely if the project was moved."
        )

    counts = {}
    for split in ("train", "val"):
        value = data.get(split)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing or invalid {split} path in {config}")
        if value.strip() == ".":
            raise ValueError(f"Refusing ambiguous {split}: . in {config}")
        image_dir = Path(value)
        if not image_dir.is_absolute():
            image_dir = source_root / image_dir
        image_dir = image_dir.resolve()
        if not image_dir.is_dir():
            raise FileNotFoundError(f"Missing {split} image directory: {image_dir}")
        # Standard Ultralytics convention: images/{train,val} -> labels/{train,val}
        label_dir = image_dir.parent.parent / "labels" / image_dir.name
        if not label_dir.is_dir():
            raise FileNotFoundError(f"Missing {split} label directory: {label_dir}")
        images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        labels = sorted(p for p in label_dir.iterdir() if p.suffix.lower() == ".txt")
        if not images:
            raise ValueError(f"No images in {image_dir}")
        image_stems = {p.stem for p in images}
        label_stems = {p.stem for p in labels}
        missing_labels = sorted(image_stems - label_stems)
        orphan_labels = sorted(label_stems - image_stems)
        if missing_labels or orphan_labels:
            raise ValueError(
                f"Mismatched {split} images/labels: "
                f"missing={missing_labels[:5]}, orphan={orphan_labels[:5]}"
            )
        if len(image_stems) != len(images):
            raise ValueError(f"Duplicate image stems in {image_dir}")
        counts[split] = len(images)

    return {
        "evaluation_tier": "INTERNAL_DEVELOPMENT_SAME_SESSION_NOT_T1",
        "dataset_yaml": str(config),
        "dataset_root": str(source_root),
        "class_names": CLASSES,
        "train_images": counts["train"],
        "val_images": counts["val"],
    }


def prepare_d5_dataset(yaml_path: Optional[Path] = None) -> Path:
    """Backward-compatible name: inspect an existing export; do NOT write a YAML."""
    info = inspect_dataset(yaml_path)
    return Path(info["dataset_yaml"])


def write_training_spec(out_path: Path) -> dict:
    """Write a reproducibility specification, not manufactured benchmark metrics."""
    info = inspect_dataset()
    spec = {
        "status": "TRAINING_HARNESS_READY",
        "evaluated": False,  # the spec file is not a training or eval result
        "evaluation_tier": info["evaluation_tier"],
        "dataset_yaml": info["dataset_yaml"],
        "train_images": info["train_images"],
        "val_images": info["val_images"],
        "resolutions_to_compare": list(SIZES),
        "training_defaults": {
            "weights": "yolov8n.pt", "epochs": 30, "batch": 8,
            "workers": 0, "seed": 42, "device": "0"
        },
        "note": (
            "This is a reproducibility plan, not measured accuracy. Actual "
            "320/416/640 results came from earlier Ultralytics CLI runs and "
            "are recorded separately in d5_finetune_results_real.json."
        ),
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite existing spec: {out}")
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return spec


def _model_metrics(metrics) -> dict:
    box = getattr(metrics, "box", None)
    if box is None:
        return {"note": "Ultralytics did not provide a box metrics object"}
    return {
        "precision_all": float(box.mp),
        "recall_all": float(box.mr),
        "mAP50_all": float(box.map50),
        "mAP50_95_all": float(box.map),
    }


def run_training(
    weights: str = "yolov8n.pt",
    imgsz: int = 320,
    epochs: int = 30,
    batch: int = 8,
    device: str = "0",
    project: Optional[str] = None,
    name: Optional[str] = None,
    workers: int = 0,
    seed: int = 42,
    yaml_path: Optional[Path] = None,
) -> Dict:
    """Start a NEW run. Never overwrite checkpoints/metrics of a prior run."""
    if imgsz not in SIZES:
        raise ValueError(f"Allowed Week-3 resolutions: {SIZES}")
    if epochs <= 0 or batch <= 0 or workers < 0:
        raise ValueError("epochs/batch must be positive, workers nonnegative")
    dataset = inspect_dataset(yaml_path)
    run_root = Path(project).resolve() if project else (ROOT / "runs" / "d5_repro")
    run_name = name or f"yolov8n_{imgsz}_repro"
    destination = run_root / run_name
    if destination.exists():
        raise FileExistsError(f"Run already exists: {destination}. Choose another --name.")

    from ultralytics import YOLO
    model = YOLO(weights)
    print(f"Training D5 dev only: {dataset['train_images']} train, {dataset['val_images']} val")
    metrics = model.train(
        data=dataset["dataset_yaml"], imgsz=imgsz, epochs=epochs,
        batch=batch, device=device, workers=workers, seed=seed,
        project=str(run_root), name=run_name, exist_ok=False,
    )
    trainer = getattr(model, "trainer", None)
    save_dir = Path(trainer.save_dir) if trainer is not None else destination
    result = {
        "status": "TRAINING_COMPLETED_INTERNAL_DEV_NOT_T1",
        "dataset_yaml": dataset["dataset_yaml"],
        "weights_init": weights,
        "imgsz": imgsz, "epochs": epochs, "batch": batch,
        "device": device, "workers": workers, "seed": seed,
        "save_dir": str(save_dir),
        "best_checkpoint": str(save_dir / "weights" / "best.pt"),
        **_model_metrics(metrics),
    }
    return result


def evaluate_checkpoint(
    weights_path: str,
    imgsz: int = 320,
    device: str = "0",
    yaml_path: Optional[Path] = None,
) -> Dict:
    if imgsz not in SIZES:
        raise ValueError(f"Allowed Week-3 resolutions: {SIZES}")
    dataset = inspect_dataset(yaml_path)
    checkpoint = Path(weights_path).resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Missing checkpoint: {checkpoint}")
    from ultralytics import YOLO
    metrics = YOLO(str(checkpoint)).val(
        data=dataset["dataset_yaml"], imgsz=imgsz, device=device,
    )
    return {
        "status": "EVALUATED_INTERNAL_DEV_NOT_T1",
        "weights": str(checkpoint),
        "dataset_yaml": dataset["dataset_yaml"],
        "imgsz": imgsz,
        **_model_metrics(metrics),
    }


def _save_new_record(result: Dict, out_path: Path) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:  # atomic refusal to overwrite
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"New run record: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-only", action="store_true", help="Read-only dataset preflight")
    group.add_argument("--train", action="store_true", help="Start a NEW real GPU training run")
    group.add_argument("--val", metavar="BEST.PT", help="Validate an existing checkpoint")
    group.add_argument("--write-spec", action="store_true", help="Write reproducibility spec only")
    parser.add_argument("--data", type=Path, default=None, help="Existing D5 exported data.yaml")
    parser.add_argument("--weights", default="yolov8n.pt")
    parser.add_argument("--imgsz", type=int, choices=SIZES, default=320)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--out", type=Path, default=None, help="New JSON record; never overwrite")
    args = parser.parse_args()

    if args.write_spec:
        default_out = ROOT / "reports" / "HuynhNguyenHoaiLoc" / "week-03" / "d5_training_entrypoint_spec.json"
        print(json.dumps(write_training_spec(args.out or default_out), indent=2))
    elif args.train:
        result = run_training(
            weights=args.weights, imgsz=args.imgsz, epochs=args.epochs,
            batch=args.batch, device=args.device, workers=args.workers,
            seed=args.seed, project=args.project, name=args.name,
            yaml_path=args.data,
        )
        print(json.dumps(result, indent=2))
        if args.out:
            _save_new_record(result, args.out)
    elif args.val:
        result = evaluate_checkpoint(args.val, imgsz=args.imgsz, device=args.device, yaml_path=args.data)
        print(json.dumps(result, indent=2))
        if args.out:
            _save_new_record(result, args.out)
    else:
        print(json.dumps(inspect_dataset(args.data), indent=2, ensure_ascii=False))
        print("Dataset preflight PASS. No files modified, no training started.")


if __name__ == "__main__":
    main()
