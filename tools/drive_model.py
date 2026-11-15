"""One place for the forward-drive distance model of the JetBot on the classroom tile (find_door and approach_door; audit 2026-11-12: the clear-space rule ignored --drive-v and approach_door had no distance bound).

Worst case seen at v 0.85: 0.34 m/s on 2026-11-12 (1.9 m in 5.6 s, battery 11.64 V); 0.21 m/s in an earlier run (0.75 m in 3.5 s): it varies with battery and floor, so the CONSERVATIVE value is used.
At v 1.0 sentry/nav/wheel_model.py gives 0.435 m/s; below 0.85 the speed is scaled linearly (an overestimate near the dead zone: the safe direction)."""
SPEED_AT_V085_M_S = 0.35
SPEED_AT_V100_M_S = 0.435
CLEAR_MARGIN_M = 0.6                                    # veer arc (up to 25 deg/m), the robot's own size and the stopping distance


def drive_speed_m_s(v):
    """Conservative forward speed for the command v (0..1)."""
    if v >= 0.85:
        return SPEED_AT_V085_M_S + (v - 0.85) * (SPEED_AT_V100_M_S - SPEED_AT_V085_M_S) / 0.15
    return SPEED_AT_V085_M_S * max(v, 0.0) / 0.85


def drive_distance_m(v, seconds):
    return drive_speed_m_s(v) * seconds
