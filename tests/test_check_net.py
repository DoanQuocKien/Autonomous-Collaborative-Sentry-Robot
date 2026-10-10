import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import check_net


@pytest.mark.parametrize("offset", ["nan", "inf", "-inf"])
def test_nonfinite_offset_is_rejected_before_workers_start(monkeypatch, offset):
    monkeypatch.setattr(sys, "argv", ["check_net", "--offset=" + offset])
    with pytest.raises(SystemExit) as error:
        check_net.main()
    assert error.value.code == 2


@pytest.mark.loopback
def test_slow_publisher_stops_promptly_without_leaking_workers(tmp_path):
    out = tmp_path / "slow.csv"
    process = subprocess.run(
        [sys.executable, "-m", "tools.check_net", "--fps", "0.1", "--seconds", "0.2",
         "--out", str(out)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=15)
    assert process.returncode == 1, process.stdout + process.stderr
    metrics = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert not metrics["pass"]
    assert metrics["scope"] == "synthetic localhost only; not HIL"
    assert "worker failed" not in process.stderr
