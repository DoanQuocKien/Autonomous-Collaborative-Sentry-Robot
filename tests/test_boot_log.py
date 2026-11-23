"""Boot logger: battery word decoding matches tools/jetbot_status.py."""
from jetson.boot_log import battery_volts
from tools.jetbot_status import ina219_bus_volts


def test_battery_decoding_matches_status_tool():
    assert battery_volts("0xd25d") == ina219_bus_volts("0xd25d")
    assert 12.0 < battery_volts("0xd25d") < 13.0
