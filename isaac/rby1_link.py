# Windows Isaac Sim과 WSL rby1 core 릴레이 사이의 TCP 프레임 코덱과, 공식 RBY1UdpBridge를 대신하는 TCP 브리지
"""Isaac Sim (Windows) <-TCP-> wsl/rby1_relay.py (WSL) <-UDP 5005/5006-> app_main isaac (rby1 core).

Why TCP: the official UDP codec (udp_protocol.*.so) is a Linux-only binary, so it runs in the WSL relay, and
WSL2 forwards Windows localhost TCP into WSL without firewall or IP setup. Both ends only exchange the
function arguments/results of the official codec, encoded here.
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Optional

import numpy as np

LINK_PORT = 5010

# ---------------------------------------------------------------------------
# Field codec: tuple of None / bool / int / float / 1-D-or-N-D numpy array
# ---------------------------------------------------------------------------


def encode(fields) -> bytes:
    out = bytearray()
    for f in fields:
        if f is None:
            out += b"N"
        elif isinstance(f, (bool, np.bool_)):
            out += b"?" + struct.pack("<?", bool(f))
        elif isinstance(f, (int, np.integer)):
            out += b"i" + struct.pack("<q", int(f))
        elif isinstance(f, (float, np.floating)):
            out += b"d" + struct.pack("<d", float(f))
        else:
            a = np.ascontiguousarray(np.asarray(f))
            dt = a.dtype.str.encode()
            out += b"a" + struct.pack("<BB", len(dt), a.ndim) + dt
            out += struct.pack("<%dI" % a.ndim, *a.shape) + a.tobytes()
    return struct.pack("<I", len(out)) + bytes(out)


def decode(payload: bytes) -> tuple:
    fields, i = [], 0
    while i < len(payload):
        kind = payload[i:i + 1]
        i += 1
        if kind == b"N":
            fields.append(None)
        elif kind == b"?":
            fields.append(struct.unpack_from("<?", payload, i)[0]); i += 1
        elif kind == b"i":
            fields.append(struct.unpack_from("<q", payload, i)[0]); i += 8
        elif kind == b"d":
            fields.append(struct.unpack_from("<d", payload, i)[0]); i += 8
        elif kind == b"a":
            dlen, ndim = struct.unpack_from("<BB", payload, i); i += 2
            dt = np.dtype(payload[i:i + dlen].decode()); i += dlen
            shape = struct.unpack_from("<%dI" % ndim, payload, i); i += 4 * ndim
            n = int(np.prod(shape)) * dt.itemsize
            fields.append(np.frombuffer(payload[i:i + n], dtype=dt).reshape(shape).copy()); i += n
        else:
            raise ValueError("bad field kind %r" % kind)
    return tuple(fields)


def recv_frame(sock: socket.socket) -> Optional[bytes]:
    """Read one length-prefixed frame; None on EOF."""
    head = _recv_exact(sock, 4)
    if head is None:
        return None
    return _recv_exact(sock, struct.unpack("<I", head)[0])


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


# ---------------------------------------------------------------------------
# Isaac Sim side: drop-in for rby1-sim-isaac's RBY1UdpBridge (same methods RBY1Task calls)
# ---------------------------------------------------------------------------


class TcpBridge:
    """Connects to the WSL relay in the background; reconnects if the relay restarts."""

    # Lockstep wait cap per physics step. The official bridge can wait forever, which would freeze the GUI.
    MAX_WAIT = 0.2

    def __init__(self, host: str = "127.0.0.1", port: int = LINK_PORT, **_ignored):
        self._addr = (host, port)
        self._sock: Optional[socket.socket] = None
        self._cv = threading.Condition()
        self._command = None
        self._seq = 0
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()
        print(f"[TcpBridge] connecting to rby1 core relay at {host}:{port} (WSL)")

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def _run(self) -> None:
        while self._running:
            try:
                s = socket.create_connection(self._addr, timeout=1.0)
            except OSError:
                time.sleep(1.0)
                continue
            s.settimeout(None)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = s
            print("[TcpBridge] connected to relay")
            try:
                while self._running:
                    frame = recv_frame(s)
                    if frame is None:
                        break
                    with self._cv:
                        self._command = decode(frame)
                        self._seq += 1
                        self._cv.notify_all()
            except OSError:
                pass
            self._sock = None
            s.close()
            with self._cv:
                self._cv.notify_all()
            print("[TcpBridge] relay disconnected, retrying")

    def send_state(self, t, is_ready, position, velocity, current, torque) -> None:
        s = self._sock
        if s is None:
            return
        try:
            s.sendall(encode((float(t), is_ready, position, velocity, current, torque)))
        except OSError:
            pass  # the reader thread notices the drop and reconnects

    def get_latest_command(self):
        with self._cv:
            return self._command

    def get_latest_command_with_status(self, last_seq: int = 0):
        with self._cv:
            return self._command, self._command is not None and self._seq != last_seq, self._seq

    def wait_for_command_after(self, last_seq: int, timeout: Optional[float] = None):
        timeout = self.MAX_WAIT if timeout is None else min(timeout, self.MAX_WAIT)
        deadline = time.monotonic() + timeout
        with self._cv:
            while self._running and self._sock is not None and self._seq == last_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    break
                self._cv.wait(remaining)
            return self._command, self._command is not None and self._seq != last_seq, self._seq

    def consume_timing_stats(self) -> dict:
        return {}

    def close(self) -> None:
        self._running = False
        s = self._sock
        if s is not None:
            s.close()


if __name__ == "__main__":
    # Self-check of the codec round trip with the field types RBY1Task and the relay exchange.
    sample = (0.002, np.ones(24, bool), np.arange(24.0), None, True, 7, np.arange(6, dtype=np.uint32).reshape(2, 3))
    frame = encode(sample)
    back = decode(frame[4:])
    assert struct.unpack("<I", frame[:4])[0] == len(frame) - 4
    assert back[0] == 0.002 and back[3] is None and back[4] is True and back[5] == 7
    for a, b in ((sample[1], back[1]), (sample[2], back[2]), (sample[6], back[6])):
        assert a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b)
    print("rby1_link codec self-check OK")
