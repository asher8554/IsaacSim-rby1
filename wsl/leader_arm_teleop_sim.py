# WSL에서 실행: 공식 35번 Leader Arm 텔레옵 예제를 Isaac Sim(rby1 core)용으로 감싸 실행 (그리퍼 제외, --mock 지원)
"""Leader Arm -> rby1 core (WSL) -> Isaac Sim, reusing rby1-sdk examples/python/35_leader_arm_teleop_with_monitor.py.

Changes against the official example, nothing else:
  - Gripper: replaced by a no-op. The official Gripper drives the real robot's /dev/rby1_gripper bus;
    the Isaac Sim scene here has no gripper.
  - 12 V: the simulated core has a single power device "main" and no tool flange power, while the real robot
    powers the leader arm and gripper from "12v" and the tool flanges. Those calls are answered as done.
  - --mock: a fake leader arm (both handle buttons held, elbows swinging) to test the pipeline without hardware.
Real hardware: the leader arm must be visible in WSL as /dev/rby1_leader_arm (see README "Leader Arm").

Usage (WSL, rby1-venv):
  python wsl/leader_arm_teleop_sim.py --mock --seconds 30
  python wsl/leader_arm_teleop_sim.py                     # real leader arm, Ctrl+C to stop
"""
import argparse
import importlib
import math
import os
import signal
import sys
import threading
import time
import types

import numpy as np

EXAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rby1-sdk", "examples", "python")
sys.path.insert(0, EXAMPLES)
teleop = importlib.import_module("35_leader_arm_teleop_with_monitor")
rby = teleop.rby
OfficialLeaderArm = teleop.LeaderArm  # kept: --mock replaces teleop.LeaderArm


class SimRobot:
    """Forwards to the real SDK robot object; only the 12 V power line and tool flange voltage are emulated."""

    def __init__(self, robot):
        self._robot = robot

    def __getattr__(self, name):
        return getattr(self._robot, name)

    def is_power_on(self, dev_name):
        return True if dev_name == "12v" else self._robot.is_power_on(dev_name)

    def power_on(self, dev_name):
        return True if dev_name == "12v" else self._robot.power_on(dev_name)

    def power_off(self, dev_name):
        return True if dev_name == "12v" else self._robot.power_off(dev_name)

    def set_tool_flange_output_voltage(self, name, voltage):
        return True


_create_robot = rby.create_robot


class NoGripper:
    """The simulated robot has no gripper; the trigger values are ignored."""

    def initialize(self, verbose=True):
        return True

    def homing(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def set_target(self, target):
        pass


class MockLeaderArm:
    """Duck-types the official LeaderArm: buttons held, elbows swing +-25 deg around the ready pose (4 s period)."""

    DOF = 14
    DEVICE_COUNT = 16
    State = OfficialLeaderArm.State
    ControlInput = OfficialLeaderArm.ControlInput

    def __init__(self, control_period=0.01, **_ignored):
        self.control_period = control_period
        self.motor_ids = list(range(self.DOF))
        self.tool_ids = [OfficialLeaderArm.RIGHT_TOOL_ID, OfficialLeaderArm.LEFT_TOOL_ID]
        self.active_ids = []
        self.active_joint_ids = self.motor_ids
        self.state = self.State(self.DOF)
        held = types.SimpleNamespace(button=1, trigger=0)  # official ButtonState is read-only
        self.state.button_right = held
        self.state.button_left = held
        self.ctrl_session_active = False
        self.is_running = False
        self._stop = threading.Event()
        # The official shutdown stops these event loops before cancelling the robot command stream
        self.ev = self.ctrl_ev = types.SimpleNamespace(stop=self._stop.set)
        self.bus = types.SimpleNamespace(group_sync_write_send_torque=lambda cmd: None)

    def set_max_retries(self, **_ignored):
        pass

    def initialize(self, verbose=False):
        self.active_ids = self.motor_ids + self.tool_ids
        return self.active_ids

    def start_control(self, callback, safety_function=None):
        pose = teleop.READY_POSE["A"]
        ready = np.concatenate([pose.right_arm, pose.left_arm])

        def loop():
            t0 = time.monotonic()
            while not self._stop.is_set():
                phase = 2.0 * math.pi * (time.monotonic() - t0) / 4.0
                q = ready.copy()
                q[3] += math.radians(25.0) * math.sin(phase)   # right_arm_3 (elbow)
                q[10] += math.radians(25.0) * math.cos(phase)  # left_arm_3 (elbow)
                self.state.q_joint[:] = q
                try:
                    callback(self.state)
                except RuntimeError:
                    if self._stop.is_set():  # stream already cancelled by the shutdown
                        break
                    raise
                time.sleep(self.control_period)

        self.ctrl_session_active = True
        threading.Thread(target=loop, daemon=True).start()
        return True

    def DisableTorque(self):
        pass

    def close(self):
        self._stop.set()
        self.ctrl_session_active = False


def main():
    ap = argparse.ArgumentParser(description="Leader arm teleoperation of the Isaac Sim RB-Y1 through the rby1 core")
    ap.add_argument("--address", default="127.0.0.1:50051")
    ap.add_argument("--mode", default="position", choices=["position", "impedance"])
    ap.add_argument("--mock", action="store_true", help="fake leader arm, no hardware")
    ap.add_argument("--seconds", type=float, default=0.0, help="stop after N s with the official soft shutdown (0 = Ctrl+C)")
    ap.add_argument("--align-duration", type=float, default=teleop.DEFAULT_ALIGN_DURATION,
                    help="official leader arm alignment to the ready pose (real hardware only)")
    args = ap.parse_args()

    teleop.Gripper = NoGripper
    rby.create_robot = lambda address, model: SimRobot(_create_robot(address, model))  # used by teleop.main
    if args.mock:
        teleop.LeaderArm = MockLeaderArm
        args.align_duration = 0.0  # alignment drives real leader arm motors
    if args.seconds > 0:
        threading.Timer(args.seconds, lambda: os.kill(os.getpid(), signal.SIGINT)).start()

    teleop.main(address=args.address, model_name="a", power=".*", servo="torso_.*|right_arm_.*|left_arm_.*",
                control_mode=args.mode, align_duration=args.align_duration)


if __name__ == "__main__":
    main()
