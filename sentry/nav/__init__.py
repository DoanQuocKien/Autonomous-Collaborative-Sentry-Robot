"""Navigation package: localization, mapping, vantage point selection, coverage planning, and controllers."""
from sentry.nav.localization import (
    LocalizationTracker,
    MarkerAnchor,
    MarkerDetection,
    RobotPose,
)

__all__ = [
    "LocalizationTracker",
    "MarkerAnchor",
    "MarkerDetection",
    "RobotPose",
]

try:
    from sentry.nav.gridmap import FREE, OCCUPIED, UNKNOWN, OccupancyGrid, Pose2D
    from sentry.nav.prescan import PreScanner, PrescanResult
    from sentry.nav.vantage import VantagePoint, VantageSelector

    __all__.extend([
        "FREE",
        "OCCUPIED",
        "UNKNOWN",
        "OccupancyGrid",
        "Pose2D",
        "PreScanner",
        "PrescanResult",
        "VantagePoint",
        "VantageSelector",
    ])
except ImportError:
    pass
