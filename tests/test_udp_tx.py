import pytest

from common.protocol import decode_control
from sentry.net.udp_tx import UDPSender


class SocketStub:
    def __init__(self, *args):
        self.packets = []
        self.blocking = None
        self.closed = False
        self.busy = False

    def setblocking(self, value):
        self.blocking = value

    def sendto(self, data, address):
        if self.busy:
            raise BlockingIOError
        self.packets.append((decode_control(data), address))

    def close(self):
        self.closed = True


@pytest.fixture
def sender(monkeypatch):
    sock = SocketStub()
    monkeypatch.setattr("sentry.net.udp_tx.socket.socket", lambda *a: sock)
    now = [0.0]
    tx = UDPSender("127.0.0.1", 12345, 30, clock=lambda: now[0])
    yield tx, sock, now
    tx.close(stop=False)


def test_rate_limit_no_catchup_and_wire_format(sender):
    tx, sock, now = sender
    assert sock.blocking is False
    assert tx.send(0.3, -0.2)
    now[0] = 0.02
    assert not tx.send(0.5, 0)
    now[0] = 0.04
    assert tx.send(0.5, 0)
    now[0] = 10  # scheduler stalled; one packet, no accumulated burst
    assert tx.send(0, 0.2)
    assert not tx.send(0, 0.2)
    assert [p[0]["seq"] for p in sock.packets] == [0, 1, 2]
    assert sock.packets[0] == ({"seq": 0, "v": 0.3, "w": -0.2}, ("127.0.0.1", 12345))


def test_busy_socket_drops_without_retry_backlog(sender):
    tx, sock, now = sender
    sock.busy = True
    assert not tx.send(0.3, 0)
    sock.busy = False
    assert not tx.send(0.3, 0)
    now[0] = 1
    assert tx.send(0, 0)
    assert tx.dropped == 1 and tx.sent == 1
    assert sock.packets[0][0]["seq"] == 1


def test_stop_bypasses_rate_limit_and_close_is_idempotent(sender):
    tx, sock, _ = sender
    tx.send(0.3, 0)
    tx.close()
    tx.close()
    assert sock.closed
    assert sock.packets[-1][0] == {"seq": 1, "v": 0.0, "w": 0.0}
    with pytest.raises(RuntimeError):
        tx.send(0, 0)


@pytest.mark.parametrize("v,w", [(float("nan"), 0), (0, float("inf")), (2, 0), (0, -2), (True, 0)])
def test_invalid_commands_do_not_reach_socket(sender, v, w):
    tx, sock, _ = sender
    with pytest.raises(ValueError):
        tx.send(v, w)
    assert not sock.packets


def test_numpy_scalars_and_rounding_overshoot_are_sent(sender):
    np = pytest.importorskip("numpy")
    tx, sock, now = sender
    assert tx.send(np.float32(0.5), np.float64(-0.25))
    now[0] = 1
    assert tx.send(1.0000001, -1.0000001)
    assert [p[0] for p in sock.packets] == [{"seq": 0, "v": 0.5, "w": -0.25}, {"seq": 1, "v": 1.0, "w": -1.0}]
