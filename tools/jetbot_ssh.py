"""SSH to the JetBot for the laptop tools (tools.jetbot_status, tools.calibrate_motion).

* Host key pinned on first use, independent of the IP (the hotspot hands out a new IP after each restart): the first
  connection stores the robot's key in data/jetbot_host_key (gitignored); later connections to a host with any other key
  are refused BEFORE the password is sent, so an `auto` scan that lands on another Ubuntu machine cannot collect it.
  After a re-flash of the robot, delete that file.
* Password: --password, else the JETBOT_PASSWORD environment variable, else a prompt. Never a default in the code.
* sudo reads the password on stdin, so it never appears in a command line (`ps` on the robot) or in a shell string.
"""
import getpass
import os
from pathlib import Path

PIN = Path(__file__).resolve().parent.parent / "data" / "jetbot_host_key"


def password(cli_value=None, env=os.environ, prompt=getpass.getpass):
    return cli_value or env.get("JETBOT_PASSWORD") or prompt("JetBot password: ")


def _policy(pin):
    import paramiko

    class PinnedHostKey(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            line = "%s %s" % (key.get_name(), key.get_base64())
            if pin.exists():
                if pin.read_text(encoding="ascii").strip() != line:
                    raise paramiko.SSHException(
                        "%s is not the pinned JetBot (host key differs from %s). Wrong host from the network scan? "
                        "If the robot was re-flashed, delete %s." % (hostname, pin, pin))
                return
            pin.parent.mkdir(parents=True, exist_ok=True)
            pin.write_text(line + "\n", encoding="ascii")
            print("first SSH connection: pinned the JetBot host key (%s, %s) in %s"
                  % (key.get_name(), key.get_fingerprint().hex(), pin))

    return PinnedHostKey()


def connect(ip, user, pw, pin=PIN, timeout=20):
    import paramiko  # imported here so the pure functions of the tools can be tested without it
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(_policy(pin))
    c.connect(ip, username=user, password=pw, timeout=timeout, look_for_keys=False, allow_agent=False)
    return c


def run(c, cmd, timeout=40):
    """stdout + stderr of a command, as text."""
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return (out.read() + err.read()).decode(errors="replace").strip()


def sudo(c, cmd, pw, timeout=40):
    """Run `cmd` with sudo; the password goes to sudo's stdin (-S), not into the command line."""
    stdin, out, err = c.exec_command("sudo -S -p '' " + cmd, timeout=timeout)
    stdin.write(pw + "\n")
    stdin.flush()
    return (out.read() + err.read()).decode(errors="replace").strip()
