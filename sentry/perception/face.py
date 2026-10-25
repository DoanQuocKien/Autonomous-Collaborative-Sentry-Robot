"""Face verification for Week 3 (HNHL)."""
from pathlib import Path
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
class InsightFaceEncoder:
    """Detect faces and extract normalized 512D embeddings."""

    def __init__(self, app=None, device="cuda"):
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
