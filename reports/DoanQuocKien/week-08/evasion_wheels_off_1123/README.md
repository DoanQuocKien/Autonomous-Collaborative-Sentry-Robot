# Wheels-off evasion trials, 2026-11-23 (DQK)

Run data without the phone videos (about 430 MB, kept locally in `data/pursuit/evade_1_1` and `evade_2_1`, gitignored).

- `evade_1`: pursuit active, so its reverse command is mixed in; NOT a clean strike measurement.
- `evade_2`: `--evade-only` (zero command between strikes), 6 strikes at 5 s intervals; the clean run.

Measured:
- Screen flash seen on the phone clip (240 fps): 6 flashes of 404-421 ms, matching the 0.40 s configured pulse (flash timing +-15-30 ms from the screen refresh).
- Robot log (`robot_udp.log`) for two of the strikes: `motors -0.30 +0.00` for 0.41 s and 0.37 s, so ONE wheel is driven per strike (below).
- Seen by DQK on the clip: the other wheel did not turn at all during evade_2.

NOT measured: wheel start delay, how far the driven wheel turned and the stop lag. The video wheel-motion measure (phase correlation on the tread) was not reliable and its numbers are not used. Wheel tests without video, wheels off the ground, R1 held (robot log + DQK's eyes): both wheels forward at 0.30 for 8 s, both in reverse at 0.30 for 10 s, equal speed each time.

Why one wheel: `mix(-1.0, +0.8)` = (-1.0, -0.11) after the rescale; times the 0.3 cap = (-0.30, -0.033); `min_pwm` 0.12 sends the second to 0. The turn side comes from the obstacle bearing (`EvasionOverride.turn_sign`, away from the nearer obstacle, left when unknown); the runs used `--no-obstacles`, so every strike turned the same way.
