"""Face verification for Week 3 (HNHL)."""
from pathlib import Path
from collections import Counter
import math
import numpy as np

from sentry.config import load


def normalize_embedding(embedding):
    """Normalize a 512D face embedding to unit length."""
    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)

    if vector.size != 512:
        raise ValueError("Face embedding must have 512 dimensions")

    if not np.all(np.isfinite(vector)):
        raise ValueError("Face embedding contains non-finite values")

    norm = np.linalg.norm(vector)
    if norm < 1e-12:
        raise ValueError("Face embedding cannot be zero")

    return vector / norm


class FaceVerifier:
    """Verify a face against all enrolled reference embeddings."""

    def __init__(self, whitelist=None, threshold=None):
        self.threshold = (
            float(load()["thresholds"]["whitelist_cosine"])
            if threshold is None else float(threshold)
        )

        if not -1.0 <= self.threshold <= 1.0:
            raise ValueError("Invalid cosine threshold")

        self.whitelist = {}

        for person_id, embeddings in (whitelist or {}).items():
            vectors = [normalize_embedding(e) for e in embeddings]
            if vectors:
                self.whitelist[person_id] = vectors

    def verify(self, embedding):
        query = normalize_embedding(embedding)

        best_id = None
        best_score = -1.0

        for person_id, references in self.whitelist.items():
            for reference in references:
                score = float(np.dot(query, reference))

                if score > best_score:
                    best_score = score
                    best_id = person_id

        if best_id is None:
            return None, None, False

        authorized = best_score >= self.threshold

        return (
            best_id if authorized else None,
            best_score,
            authorized,
        )

    def verify_many(self, embeddings, minimum_votes):
        """Require a strict majority for the same enrolled identity."""
        samples = list(embeddings)
        if (not samples or type(minimum_votes) is not int
                or not len(samples) / 2 < minimum_votes <= len(samples)):
            raise ValueError("a strict majority of nonempty face samples is required")
        results = [self.verify(sample) for sample in samples]
        votes = Counter(identity for identity, _, accepted in results if accepted)
        winners = [identity for identity, count in votes.items() if count >= minimum_votes]
        identity = winners[0] if winners else None
        scores = [score for _, score, _ in results if score is not None]
        return identity, max(scores, default=-1.0), identity is not None


def face_yaw_ratio(kps):
    """Nose offset from the eye midpoint, in eye distances; None if unavailable."""
    if kps is None:
        return None
    points = np.asarray(kps, dtype=float)
    if points.shape != (5, 2) or not np.isfinite(points).all():
        return None
    left, right, nose = points[:3, 0]
    distance = abs(right - left)
    return None if distance < 1e-6 else float((nose - (left + right) / 2) / distance)


def face_sharpness(image, box):
    """Variance of a 112x112 grayscale face crop, shared by live and D2."""
    import cv2
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError("finite face box required")
    x1, y1, x2, y2 = map(int, box)
    h, w = image.shape[:2]
    crop = image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(cv2.resize(crop, (112, 112)), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
class InsightFaceEncoder:
    """Detect faces and extract normalized 512D embeddings."""

    def __init__(self, app=None, device="cuda", model_root=None):
        if app is None:
            if device not in ("cuda", "cpu"):
                raise ValueError("device must be cuda or cpu")

            import torch  # Load CUDA libraries before ONNX Runtime on Windows.
            from insightface.app import FaceAnalysis

            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if device == "cuda"
                else ["CPUExecutionProvider"]
            )

            app = FaceAnalysis(
                name="buffalo_s",
                **({"root": str(model_root)} if model_root is not None else {}),
                allowed_modules=["detection", "recognition"],
                providers=providers,
            )

            app.prepare(
                ctx_id=0 if device == "cuda" else -1,
                det_size=(640, 640),
            )

            if device == "cuda":
                for name in ("detection", "recognition"):
                    session = app.models[name].session
                    if session.get_providers()[0] != "CUDAExecutionProvider":
                        raise RuntimeError(
                            f"{name} is not using CUDAExecutionProvider"
                        )

        self.app = app

    def extract(self, image_bgr):
        """Return face boxes, confidence scores and 512D embeddings."""
        if (
            not isinstance(image_bgr, np.ndarray)
            or image_bgr.ndim != 3
            or image_bgr.shape[2] != 3
            or image_bgr.dtype != np.uint8
        ):
            raise ValueError("Expected uint8 BGR image with shape HxWx3")

        results = []

        for face in self.app.get(image_bgr):
            if getattr(face, "embedding", None) is None:
                raise RuntimeError("Face recognition embedding is missing")

            results.append({
                "bbox": tuple(float(v) for v in face.bbox),
                "confidence": float(face.det_score),
                "kps": None if getattr(face, "kps", None) is None else np.asarray(face.kps, dtype=float),
                "embedding": normalize_embedding(face.embedding),
            })

        return results
def load_whitelist(directory):
    """Load enrolled face embeddings without allowing pickle."""
    folder = Path(directory)

    if not folder.is_dir():
        raise FileNotFoundError(f"Whitelist directory not found: {folder}")

    whitelist = {}

    for path in sorted(folder.glob("*.npz")):
        with np.load(path, allow_pickle=False) as data:
            if set(data.files) != {"embeddings"}:
                raise ValueError(f"Invalid enrollment format: {path}")

            embeddings = data["embeddings"]

        if (
            embeddings.ndim != 2
            or embeddings.shape[1] != 512
            or not 3 <= embeddings.shape[0] <= 5
        ):
            raise ValueError(f"Invalid embedding shape: {path}")

        whitelist[path.stem] = [
            normalize_embedding(embedding)
            for embedding in embeddings
        ]

    if not whitelist:
        raise ValueError(f"No enrolled identities found in {folder}")

    return whitelist
