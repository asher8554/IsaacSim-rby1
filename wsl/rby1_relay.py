# WSL에서 실행: Windows Isaac Sim(TCP)과 rby1 core app_main(UDP 5005/5006)을 공식 udp_protocol 코덱으로 중계
"""TCP :5010 (Isaac Sim on Windows) <-> UDP 127.0.0.1:5005 / :5006 (app_main isaac).

Needs PYTHONPATH with rby1-core/internal (official udp_protocol.*.so) and isaac/ (rby1_link codec).
"""
import os
import select
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "isaac"))
from rby1_link import LINK_PORT, decode, encode, recv_frame  # noqa: E402
from udp_protocol import build_robot_state_packet, parse_robot_command_packet  # noqa: E402

CORE_STATE_ADDR = ("127.0.0.1", 5005)  # app_main listens for RobotState here
CMD_PORT = 5006                         # app_main sends RobotCommand here (Isaac Sim's port in the official setup)


def serve(conn: socket.socket, udp: socket.socket) -> None:
    states = cmds = 0
    while True:
        readable, _, _ = select.select([conn, udp], [], [], 5.0)
        if not readable:
            print(f"[relay] idle 5 s (states={states}, cmds={cmds}); is Isaac Sim playing and app_main running?")
        if conn in readable:
            frame = recv_frame(conn)
            if frame is None:
                return
            udp.sendto(build_robot_state_packet(*decode(frame)), CORE_STATE_ADDR)
            states += 1
        if udp in readable:
            data, _ = udp.recvfrom(4096)
            cmd = parse_robot_command_packet(data)
            if cmd is not None:
                conn.sendall(encode(cmd))
                cmds += 1
        if states and states % 5000 == 0 and conn in readable:
            print(f"[relay] states={states} cmds={cmds}")


def main() -> None:
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", CMD_PORT))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", LINK_PORT))
    srv.listen(1)
    print(f"[relay] waiting for Isaac Sim on tcp :{LINK_PORT}, core state -> {CORE_STATE_ADDR}, cmd <- :{CMD_PORT}")
    while True:
        conn, peer = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[relay] Isaac Sim connected from {peer}")
        try:
            serve(conn, udp)
        except OSError as exc:
            print(f"[relay] connection error: {exc}")
        conn.close()
        print("[relay] Isaac Sim disconnected")


if __name__ == "__main__":
    main()
