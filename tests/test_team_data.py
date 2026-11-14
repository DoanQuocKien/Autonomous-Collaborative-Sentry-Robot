import zipfile

import pytest

from tools import team_data


PASSWORD = "test-only-password"


def make(tmp_path):
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "a" / "x.txt").write_text("hello")
    (src / "y.bin").write_bytes(b"\x00\x01\x02" * 100)
    return src


def test_round_trip_restores_every_file(tmp_path):
    src = make(tmp_path)
    archive = tmp_path / "out" / "d.zip"
    assert team_data.pack(src, archive, PASSWORD) == 2
    assert team_data.unpack(archive, tmp_path / "dst", PASSWORD) == 2
    assert (tmp_path / "dst" / "a" / "x.txt").read_text() == "hello"
    assert (tmp_path / "dst" / "y.bin").read_bytes() == b"\x00\x01\x02" * 100


def test_the_zip_is_encrypted_and_a_wrong_password_fails(tmp_path):
    src = make(tmp_path)
    archive = tmp_path / "d.zip"
    team_data.pack(src, archive, PASSWORD)
    with pytest.raises(Exception):
        with zipfile.ZipFile(str(archive)) as plain:
            plain.read("a/x.txt")
    with pytest.raises(RuntimeError):
        team_data.unpack(archive, tmp_path / "dst", "wrong-password")


def test_unpack_refuses_a_path_that_leaves_the_destination(tmp_path):
    import pyzipper

    archive = tmp_path / "evil.zip"
    with pyzipper.AESZipFile(str(archive), "w", encryption=pyzipper.WZ_AES) as file:
        file.setpassword(PASSWORD.encode())
        file.writestr("../escape.txt", "x")
    with pytest.raises(SystemExit):
        team_data.unpack(archive, tmp_path / "dst", PASSWORD)
    assert not (tmp_path / "escape.txt").exists()


def test_password_resolution_precedence(monkeypatch):
    monkeypatch.setenv('TEAM_DATA_PASSWORD', 'environment-fixture')
    monkeypatch.setattr(team_data.getpass, 'getpass', lambda *_: 'prompt-fixture')
    assert team_data.resolve_password('argument-fixture') == 'argument-fixture'
    assert team_data.resolve_password(None) == 'environment-fixture'
    monkeypatch.delenv('TEAM_DATA_PASSWORD')
    assert team_data.resolve_password(None) == 'prompt-fixture'
