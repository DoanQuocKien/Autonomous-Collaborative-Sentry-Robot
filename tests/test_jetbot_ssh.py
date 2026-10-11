import pytest

from tools import jetbot_ssh

paramiko = pytest.importorskip("paramiko")


def test_host_key_is_pinned_on_first_use_and_a_different_host_is_refused(tmp_path):
    pin = tmp_path / "jetbot_host_key"
    robot, impostor = paramiko.RSAKey.generate(1024), paramiko.RSAKey.generate(1024)
    policy = jetbot_ssh._policy(pin)
    policy.missing_host_key(None, "192.168.137.62", robot)        # first use: pinned
    assert pin.read_text().startswith("ssh-rsa ")
    policy.missing_host_key(None, "192.168.137.80", robot)        # same robot, new hotspot IP: fine
    with pytest.raises(paramiko.SSHException, match="not the pinned JetBot"):
        policy.missing_host_key(None, "192.168.137.62", impostor)  # refused before any password is sent


def test_password_comes_from_cli_env_or_prompt_never_a_default():
    assert jetbot_ssh.password("x", env={"JETBOT_PASSWORD": "y"}) == "x"
    assert jetbot_ssh.password(None, env={"JETBOT_PASSWORD": "y"}) == "y"
    assert jetbot_ssh.password(None, env={}, prompt=lambda p: "z") == "z"


def test_sudo_password_goes_to_stdin_not_the_command_line():
    class Stream(object):
        def __init__(self, data=b""):
            self.data, self.written = data, ""

        def read(self):
            return self.data

        def write(self, s):
            self.written += s

        def flush(self):
            pass

    class Client(object):
        def exec_command(self, cmd, timeout):
            self.cmd, self.stdin = cmd, Stream()
            return self.stdin, Stream(b"0xd25d\n"), Stream()

    c = Client()
    assert jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", "s3cr;et") == "0xd25d"
    assert "s3cr" not in c.cmd and c.stdin.written == "s3cr;et\n"
