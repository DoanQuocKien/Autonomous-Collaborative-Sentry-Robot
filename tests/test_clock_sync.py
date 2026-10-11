import pytest

from sentry.net.clock_sync import ClockSample, estimate_clock


@pytest.mark.parametrize("offset", [-125.0, 0.0, 250.0])
def test_symmetric_delays_and_clock_domains(offset):
    sample = ClockSample(10.0, 10.02 + offset, 10.04)
    estimate = estimate_clock([sample])
    assert estimate.offset_s == pytest.approx(offset)
    assert estimate.rtt_s == pytest.approx(0.04)
    assert estimate.to_local(20 + offset) == pytest.approx(20)


def test_minimum_rtt_rejects_queueing_bias():
    samples = [ClockSample(10, 60.01, 10.2), ClockSample(11, 61.01, 11.02),
               ClockSample(12, 62.09, 12.1)]
    estimate = estimate_clock(samples)
    assert estimate.offset_s == pytest.approx(50)
    assert estimate.rtt_s == pytest.approx(0.02)
    assert estimate.samples == 3
    assert estimate.t_sync == 12.1


def test_asymmetry_error_is_bounded_by_half_rtt():
    # Forward delay 5 ms, return delay 35 ms, true offset 50 s.
    sample = ClockSample(10, 60.005, 10.04)
    assert abs(sample.offset_s - 50) <= sample.rtt_s / 2


@pytest.mark.parametrize("times", [(2, 3, 1), (float("nan"), 1, 2), (0, float("inf"), 2)])
def test_bad_clock_samples(times):
    with pytest.raises(ValueError):
        ClockSample(*times)


def test_empty_samples():
    with pytest.raises(ValueError):
        estimate_clock([])
