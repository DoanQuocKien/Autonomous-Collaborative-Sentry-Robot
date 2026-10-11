import hashlib

from tools.fetch_models import verified


def test_pinned_hash_is_enforced(tmp_path):
    good = tmp_path / "w600k_mbf.onnx"
    good.write_bytes(b"model")
    pins = {"w600k_mbf.onnx": hashlib.sha256(b"model").hexdigest()}
    assert verified(good, pins)
    good.write_bytes(b"tampered")
    assert not verified(good, pins)
    assert not good.exists() and (tmp_path / "w600k_mbf.onnx.bad").exists()   # never loaded, fetched again next run
    other = tmp_path / "new.onnx"
    other.write_bytes(b"x")
    assert verified(other, pins)                                             # not pinned yet: accepted, hash printed
