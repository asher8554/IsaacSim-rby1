# Windows↔WSL TCP 링크 점검: WSL에서 --serve로 모의 core를 띄우고, Windows Isaac python으로 왕복 지연을 측정
"""Usage:
  WSL    : python3 tools/check_link.py --serve        (mock relay: answers every state with a fake command)
  Windows: C:\\isaacsim-6.2\\python.bat tools\\check_link.py   (sends 1000 states through TcpBridge, prints RTT)
Do not run --serve while wsl/start_core.sh is running (same port).
"""
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "isaac"))
import numpy as np  # noqa: E402
from rby1_link import LINK_PORT, TcpBridge, decode, encode, recv_frame  # noqa: E402

N = 24


def serve():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", LINK_PORT))
    srv.listen(1)
    print(f"mock relay on :{LINK_PORT}")
    conn, _ = srv.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    while (frame := recv_frame(conn)) is not None:
        t, _ready, q, *_ = decode(frame)
        # same 7 fields RBY1Task._apply_udp_command unpacks: mode, target, fbg, fft, finished, kp, kd
        conn.sendall(encode((np.zeros(N, bool), q + 0.01, np.full(N, 10, np.uint32), np.zeros(N), False,
                             np.zeros(N), np.zeros(N))))
    print("client left")


def client(count=1000):
    bridge = TcpBridge()
    for _ in range(150):  # WSL localhost forwarding can take a few seconds to pick up a new listener
        if bridge.connected:
            break
        time.sleep(0.1)
    assert bridge.connected, "cannot reach the WSL side on 127.0.0.1:%d" % LINK_PORT
    seq, rtts = 0, []
    for k in range(count):
        q = np.full(N, k * 1e-3)
        t0 = time.perf_counter()
        bridge.send_state(k * 0.002, np.ones(N, bool), q, np.zeros(N), np.zeros(N), np.zeros(N))
        cmd, new, seq = bridge.wait_for_command_after(seq, timeout=1.0)
        assert new, "no reply for state %d" % k
        rtts.append((time.perf_counter() - t0) * 1e3)
        assert np.allclose(cmd[1], q + 0.01) and cmd[2].dtype == np.uint32
    bridge.close()
    r = np.array(rtts)
    print(f"OK {count} round trips: mean {r.mean():.3f} ms, p99 {np.percentile(r, 99):.3f} ms, max {r.max():.3f} ms")


if __name__ == "__main__":
    serve() if "--serve" in sys.argv else client()
