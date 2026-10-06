from tools.jetbot_status import battery_status, ina219_bus_volts


def test_voltage_from_the_real_reading():
    # 0xd25d is what the robot returned on 2026-10-04: byte-swapped 0x5dd2 -> (0x5dd2 >> 3) * 4 mV = 12.008 V
    assert abs(ina219_bus_volts("0xd25d") - 12.008) < 1e-9
    assert abs(ina219_bus_volts("some text 0xd25d") - 12.008) < 1e-9   # takes the last token


def test_status_thresholds():
    assert battery_status(12.6) == "OK" and battery_status(11.1) == "OK"
    assert battery_status(11.09).startswith("LOW") and battery_status(10.5).startswith("LOW")
    assert battery_status(10.49).startswith("CRITICAL")
