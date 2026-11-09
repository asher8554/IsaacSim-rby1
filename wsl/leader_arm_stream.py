# WSL에서 실행: Leader Arm 관절값 14개를 읽어 Isaac Sim(Windows)에 TCP로 보내는 서버 (rby1 core 없이 직접 구동용)
"""Leader arm -> TCP :5011 -> isaac/rby1_leader_arm_direct.py (Script Editor) -> SingleArticulation.apply_action.

Leader arm handling follows rby1-sdk examples/python/35_leader_arm_teleop_with_monitor.py:
  handle button held  -> that arm is gravity-compensated and moves freely; the robot follows it
  button released     -> that arm holds its pose; the robot holds too
The streamed value is that "pose to follow" (q[0:7] right_arm_0..6, q[7:14] left_arm_0..6, radians).

Usage (WSL, rby1-venv):
  python wsl/leader_arm_stream.py --mock     # fake leader arm, no hardware
  python wsl/leader_arm_stream.py            # real leader arm at /dev/rby1_leader_arm (README 7장), Ctrl+C to stop
"""
import argparse
import os
import socket
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "isaac"))
from leader_arm_teleop_sim import MockLeaderArm, OfficialLeaderArm, rby  # noqa: E402  (imports official 35)
from rby1_link import encode  # noqa: E402

PORT = 5011
# Leader arm torque limit and viscous gain, as in the official 35 example (ma_torque_limit, ma_viscous_gain)
TORQUE_LIMIT = np.array([0.5] * 14)
VISCOUS_GAIN = np.array([0.01, 0.01, 0.01, 0.01, 0.005, 0.005, 0.001] * 2)


class Server:
    """Accepts one Isaac Sim client at a time and pushes the latest pose to it."""

    def __init__(self, port):
        self.client = None
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen(1)
        threading.Thread(target=self._accept, args=(srv,), daemon=True).start()
        print(f"[leader-stream] waiting for Isaac Sim on tcp :{port}")

    def _accept(self, srv):
        while True:
            conn, peer = srv.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client = conn
            print(f"[leader-stream] Isaac Sim connected from {peer}")

    def send(self, q, right_button, left_button):
        conn = self.client
        if conn is None:
            return
        try:
            conn.sendall(encode((q, int(right_button), int(left_button))))
        except OSError:
            self.client = None
            print("[leader-stream] Isaac Sim disconnected")


def main():
    ap = argparse.ArgumentParser(description="Stream leader arm joint positions to Isaac Sim")
    ap.add_argument("--mock", action="store_true", help="fake leader arm, no hardware")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    server = Server(args.port)
    arm = MockLeaderArm(control_period=0.01) if args.mock else OfficialLeaderArm(control_period=0.01)
    arm.initialize(verbose=True)
    if len(arm.active_ids) != arm.DEVICE_COUNT:
        sys.exit(f"leader arm: expected {arm.DEVICE_COUNT} devices, found {len(arm.active_ids)} {arm.active_ids}")
    hold = None

    def control(state):
        nonlocal hold
        if hold is None:
            hold = state.q_joint.copy()
        torque = np.clip(state.gravity_term + VISCOUS_GAIN * state.qvel_joint, -TORQUE_LIMIT, TORQUE_LIMIT)
        ci = OfficialLeaderArm.ControlInput()
        for side, button in ((slice(0, 7), state.button_right.button), (slice(7, 14), state.button_left.button)):
            if button == 1:  # free motion with gravity compensation, the robot follows
                ci.target_operating_mode[side] = rby.DynamixelBus.CurrentControlMode
                ci.target_torque[side] = torque[side] * 0.8
                hold[side] = state.q_joint[side]
            else:  # hold the last pose
                ci.target_operating_mode[side] = rby.DynamixelBus.CurrentBasedPositionControlMode
                ci.target_torque[side] = TORQUE_LIMIT[side]
                ci.target_position[side] = hold[side]
        server.send(hold.copy(), state.button_right.button, state.button_left.button)
        return ci

    if not arm.start_control(control):
        sys.exit("leader arm: failed to start control")
    print("[leader-stream] streaming leader arm at 100 Hz (Ctrl+C to stop)")
    try:
        while arm.ctrl_session_active:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        arm.DisableTorque()
        arm.close()
        print("[leader-stream] leader arm torque off, closed")


if __name__ == "__main__":
    main()
