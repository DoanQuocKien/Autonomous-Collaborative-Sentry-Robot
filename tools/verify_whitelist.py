
"""Verify a face image against the enrolled whitelist."""

import argparse

import cv2

from sentry.perception.face import (
    FaceVerifier,
    InsightFaceEncoder,
    load_whitelist,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--whitelist-dir", default="data/whitelist")
    args = parser.parse_args()

    image = cv2.imread(args.image)

    if image is None:
        raise SystemExit("Cannot read image: " + args.image)

    encoder = InsightFaceEncoder()
    faces = encoder.extract(image)

    print("Detected faces:", len(faces))

    if len(faces) != 1:
        raise SystemExit("Expected exactly one face")

    whitelist = load_whitelist(args.whitelist_dir)
    verifier = FaceVerifier(whitelist)

    person_id, score, authorized = verifier.verify(
        faces[0]["embedding"]
    )

    print("Similarity:", round(score, 4))
    print("Authorized:", authorized)
    print("Matched ID:", person_id)


if __name__ == "__main__":
    main()
