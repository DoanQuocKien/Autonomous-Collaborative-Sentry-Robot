"""T0: the Python mirror of the ESP32 change detector (sentry/espcam.py: fingerprint / tile_dirty, same rules as esp32/tile_stream/tile_stream.ino: 8 rows x four 4-byte pieces per
64x32 tile; dirty when the mean difference >= 16 or >= 8 samples differ by >= 48). The firmware cannot run here, so these tests check the properties we rely on:
sensor noise and flicker do not trigger it, and thin moving edges do. If you change the constants in the firmware, change them in sentry/espcam.py too."""
import numpy as np
from sentry.espcam import MEAN_THR, OUT_COUNT, OUT_DIFF, TH, TW, fingerprint, tile_dirty as dirty  # noqa: F401


def _bg(rng):
    return np.clip(100 + rng.normal(0, 3, (TH, TW)), 0, 255)


def test_sensor_noise_is_not_motion():
    rng = np.random.default_rng(0)
    base = _bg(rng)
    false = sum(dirty(np.clip(base + rng.normal(0, 8, (TH, TW)), 0, 255), np.clip(base + rng.normal(0, 8, (TH, TW)), 0, 255)) for _ in range(2000))
    assert false / 2000 < 0.005


def test_small_flicker_is_not_motion_but_a_big_light_change_is():
    rng = np.random.default_rng(1)
    base = _bg(rng)
    assert not dirty(base + 10, base)
    assert dirty(base + 25, base)


def test_a_thin_vertical_edge_is_seen_wherever_it_is():
    rng = np.random.default_rng(2)
    base = _bg(rng)
    for width in (14, 20):
        for x in range(0, TW - width + 1):
            now = base.copy()
            now[:, x:x + width] = 235  # an object edge covering only part of the tile
            assert dirty(now, base), (width, x)


def test_a_thin_horizontal_edge_is_seen_wherever_it_is():
    rng = np.random.default_rng(3)
    base = _bg(rng)
    for y in range(0, TH - 4 + 1):
        now = base.copy()
        now[y:y + 4, :] = 235
        assert dirty(now, base), y


def test_an_unchanged_tile_is_clean():
    rng = np.random.default_rng(4)
    base = _bg(rng)
    assert not dirty(base, base)
