"""Quick health check of the JetBot over SSH: battery, Wi-Fi, power saving.

    python -m tools.jetbot_status 192.168.137.62

Run it at the start and end of every robot session (and between long tests). Needs `pip install paramiko`.
Password: --password, the JETBOT_PASSWORD environment variable, or a prompt; host key pinned (tools/jetbot_ssh.py).
Assumes the INA219 at I2C 0x41 measures the 3S Li-ion pack (about 12.6 V full). Thresholds are our rule of thumb:
  >= 11.1 V OK, 10.5-11.1 V LOW (charge soon), < 10.5 V CRITICAL (stop and charge).
"""
import argparse
import sys

LOW_V, CRITICAL_V = 11.1, 10.5


def ina219_bus_volts(i2cget_output):
    """`i2cget -y 1 0x41 0x02 w` prints a byte-swapped word like 0xd25d. Bus voltage = bits 15..3, 4 mV per step."""
    raw = int(i2cget_output.split()[-1], 16)
    raw = ((raw & 0xFF) << 8) | (raw >> 8)
    return (raw >> 3) * 4 / 1000.0


def battery_status(volts):
    if volts >= LOW_V:
        return "OK"
    return "LOW - charge soon" if volts >= CRITICAL_V else "CRITICAL - stop and charge"


def main():
    from tools.find_jetbot import resolve
    from tools import jetbot_ssh

    ap = argparse.ArgumentParser()
    ap.add_argument("host", nargs="?", default="auto", help="IP, or auto to search the network")
    ap.add_argument("--user", default="jetbot")
    ap.add_argument("--password", help="default: JETBOT_PASSWORD, else asked")
    a = ap.parse_args()

    pw = jetbot_ssh.password(a.password)
    c = jetbot_ssh.connect(resolve(a.host), a.user, pw)

    def run(cmd):
        return jetbot_ssh.run(c, cmd)

    v = ina219_bus_volts(jetbot_ssh.sudo(c, "i2cget -y 1 0x41 0x02 w", pw))
    print("battery   : %.2f V -> %s" % (v, battery_status(v)))
    print("uptime    :", run("uptime -p"))
    print("wifi      :", run("iw dev wlan0 link | grep -E 'SSID|freq|signal'").replace("\n", " | "))
    chains = run("grep -E 'rx_ofdm_pwr' /proc/net/rtl88x2ce/wlan0/rx_signal").split("\n")
    print("antennas  :", " / ".join(x.strip() for x in chains), "(two paths; a gap over about 10 dB means one antenna is missing or poor)")
    ps = run("grep -E 'IPS mode|LPS mode' /proc/net/rtl88x2ce/wlan0/ps_info").replace("\n", " |")
    print("power save:", ps, "(want NO IPS / NO LPS; ignore what `iw ... get power_save` says)")
    print("containers:", jetbot_ssh.sudo(c, "docker ps --format '{{.Names}} {{.Status}}'", pw).replace("\n", " ; "))
    c.close()
    return 0 if battery_status(v) != "CRITICAL - stop and charge" else 2


if __name__ == "__main__":
    sys.exit(main())
