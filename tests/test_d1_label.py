import pytest

from tools.d1_label import parse


def test_parse():
    assert parse("2.0 -30 y backlit sun") == (2.0, -30.0, "yes", "backlit sun")
    assert parse("1.5 0 N") == (1.5, 0.0, "no", "")


@pytest.mark.parametrize("bad", ["", "2.0 30", "2.0 30 maybe", "x 30 y"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse(bad)
