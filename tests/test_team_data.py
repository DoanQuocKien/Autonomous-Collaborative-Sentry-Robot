import zipfile

import pytest

from tools import team_data


def make(tmp_path):
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "a" / "x.txt").write_text("hello")
    (src / "y.bin").write_bytes(b"\x00\x01\x02" * 100)
    return src


def test_round_trip_restores_every_file(tmp_path):
    src = make(tmp_path)
    z = tmp_path / "out" / "d.zip"
    assert team_data.pack(src, z) == 2
    assert team_data.unpack(z, tmp_path / "dst") == 2
    assert (tmp_path / "dst" / "a" / "x.txt").read_text() == "hello" and (tmp_path / "dst" / "y.bin").read_bytes() == b"\x00\x01\x02" * 100


def test_the_zip_is_encrypted_and_a_wrong_password_fails(tmp_path):
    src = make(tmp_path)
    z = tmp_path / "d.zip"
    team_data.pack(src, z)
    with pytest.raises(Exception):
        with zipfile.ZipFile(str(z)) as plain:
            plain.read("a/x.txt")                                   # the standard library cannot read an AES zip without the library
    with pytest.raises(RuntimeError):
        team_data.unpack(z, tmp_path / "dst", password="wrong")


def test_unpack_refuses_a_path_that_leaves_the_destination(tmp_path):
    import pyzipper
    z = tmp_path / "evil.zip"
    with pyzipper.AESZipFile(str(z), "w", encryption=pyzipper.WZ_AES) as f:
        f.setpassword(team_data.PASSWORD.encode())
        f.writestr("../escape.txt", "x")
    with pytest.raises(SystemExit):
        team_data.unpack(z, tmp_path / "dst")
    assert not (tmp_path / "escape.txt").exists()
