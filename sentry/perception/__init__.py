"""Perception package: obstacle avoidance, entrance detection, face verification, tracking."""

__all__ = []

try:
    from sentry.perception.entrance import (
        EntranceConfig,
        EntranceDetector,
        EntranceFilter,
        EntranceResult,
    )
    EntranceMatcher = EntranceDetector
    __all__.extend([
        "EntranceConfig",
        "EntranceDetector",
        "EntranceFilter",
        "EntranceMatcher",
        "EntranceResult",
    ])
except ImportError:
    pass

try:
    from sentry.perception.camera import CameraGeometry, GroundPoint
    from sentry.perception.obstacle import (
        Detection,
        Obstacle,
        ObstacleDetector,
        ObstacleResult,
        repulsive_w,
    )

    __all__.extend([
        "CameraGeometry",
        "GroundPoint",
        "Detection",
        "Obstacle",
        "ObstacleDetector",
        "ObstacleResult",
        "repulsive_w",
    ])
except ImportError:
    pass

try:
    from sentry.perception.face import (
        FaceVerifier,
        InsightFaceEncoder,
        load_whitelist,
        normalize_embedding,
    )

    __all__.extend([
        "FaceVerifier",
        "InsightFaceEncoder",
        "load_whitelist",
        "normalize_embedding",
    ])
except ImportError:
    pass
