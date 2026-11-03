"""Navigation package: localization, mapping, vantage point selection, coverage planning, and controllers."""
from sentry.nav.controllers import (
    ControllerOutput,
    HoldBehaviorConfig,
    HoldController,
    InterceptionController,
    PursuitConfig,
    PursuitController,
)
from sentry.nav.hold_detector import (
    HoldConfig,
    HoldDetector,
    HoldState,
    local_to_world_coords,
)
from sentry.nav.localization import (
    LocalizationTracker,
    MarkerAnchor,
    MarkerDetection,
    RobotPose,
)
from sentry.nav.wheel_model import WheelModel

__all__ = [
    "ControllerOutput",
    "HoldBehaviorConfig",
    "HoldConfig",
    "HoldController",
    "HoldDetector",
    "HoldState",
    "InterceptionController",
    "LocalizationTracker",
    "MarkerAnchor",
    "MarkerDetection",
    "PursuitConfig",
    "PursuitController",
    "RobotPose",
    "WheelModel",
    "local_to_world_coords",
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
