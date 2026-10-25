"""Enroll 3–5 consented face photos per person."""

import argparse
import re
from pathlib import Path

import cv2
import numpy as np

from sentry.perception.face import InsightFaceEncoder, normalize_embedding


def enroll(person_id, image_paths, output_path, encoder=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", person_id):
        raise ValueError("Use an anonymous ID with letters, digits, _ or -")

    if not 3 <= len(image_paths) <= 5:
        raise ValueError("Each person needs 3 to 5 photos")

    output_path = Path(output_path)

    if output_path.exists():
        raise FileExistsError(f"Enrollment already exists: {output_path}")

    if encoder is None:
        encoder = InsightFaceEncoder()

    vectors = []

    for path in image_paths:
        image = cv2.imread(str(path))

        if image is None:
            raise ValueError(f"Cannot read image: {path}")

        faces = encoder.extract(image)

        if len(faces) != 1:
            raise ValueError(
                f"{path}: expected exactly one detected face, got {len(faces)}"
            )

        vectors.append(normalize_embedding(faces[0]["embedding"]))

    embeddings = np.stack(vectors).astype(np.float32)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(
        output_path,
        embeddings=embeddings,
    )

    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--person-id", required=True)
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--out-dir", default="data/whitelist")
    args = parser.parse_args()

    output = Path(args.out_dir) / f"{args.person_id}.npz"

    saved = enroll(args.person_id, args.images, output)

    print(f"Saved {len(args.images)} embeddings to {saved}")


if __name__ == "__main__":
    main()
