"""Boot logger: battery word decoding matches tools/jetbot_status.py."""
import threading

from jetson.boot_log import battery_volts, sample_loop
from tools.jetbot_status import ina219_bus_volts


def test_battery_decoding_matches_status_tool():
    assert battery_volts("0xd25d") == ina219_bus_volts("0xd25d")
    assert 12.0 < battery_volts("0xd25d") < 13.0


def test_sample_loop_writes_one_line_per_sample_and_stops():
    stop, lines = threading.Event(), []

    def emit(s):
        lines.append(s)
        if len(lines) == 3:
            stop.set()

    sample_loop(lambda: "12.03", emit, 1000.0, stop)     # 1 kHz so the test is instant
    assert len(lines) == 3 and all(l.endswith("| 12.03 V") for l in lines)
