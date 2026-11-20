import json

from tools import session_run


def test_newest_summary_picks_the_latest_run_of_a_label(tmp_path):
    for n, ok in ((1, False), (2, True)):
        d = tmp_path / ("take_a_%d" % n)
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"success": ok}))
        import os, time
        os.utime(d, (time.time() + n, time.time() + n))
    assert session_run.newest_summary(tmp_path, "take_a")["success"] is True
    assert session_run.newest_summary(tmp_path, "other") is None
