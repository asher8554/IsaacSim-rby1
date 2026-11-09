# Isaac Sim Script Editor에서 실행: WSL Leader Arm 서버의 관절값 14개로 RB-Y1 양팔 전체를 위치 제어 (rby1 core 없이)
"""Notion 5장 코드(right_arm_1 하나만 -45°)의 확장판.

Before running: the robot is loaded at /World/RBY1 (Notion 3장) and WSL runs `python wsl/leader_arm_stream.py`
(--mock without hardware). Each physics step the 14 arm joint targets move toward the leader arm pose, at most
MAX_SPEED, so the first pose is reached smoothly instead of in one jump.
"""
import asyncio
import math
import os
import socket
import sys
import threading
import time

import numpy as np
from isaacsim.core.api.world import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.types import ArticulationAction
from pxr import PhysxSchema

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:  # Script Editor runs without __file__
    ROOT = r"E:/Github/IsaacSim-rby1"
sys.path.insert(0, os.path.join(ROOT, "isaac"))
from rby1_link import decode, recv_frame  # noqa: E402

LEADER_SERVER = ("127.0.0.1", 5011)  # wsl/leader_arm_stream.py (WSL forwards Windows localhost TCP)
# Leader arm order = official 35 example: q[0:7] right arm, q[7:14] left arm
ARM_JOINTS = [f"right_arm_{i}" for i in range(7)] + [f"left_arm_{i}" for i in range(7)]
MAX_SPEED = math.radians(90.0)  # rad/s per joint

leader = {"q": None}


def receive_leader_arm():
    """Background thread: keep the latest leader arm pose; reconnect if the WSL server restarts."""
    while True:
        try:
            s = socket.create_connection(LEADER_SERVER, timeout=2.0)
        except OSError:
            time.sleep(1.0)
            continue
        s.settimeout(None)
        print("[leader-arm] connected to", LEADER_SERVER)
        try:
            while (frame := recv_frame(s)) is not None:
                leader["q"] = decode(frame)[0]
        except OSError:
            pass
        s.close()
        print("[leader-arm] disconnected, retrying")


if not any(t.name == "leader-arm-rx" for t in threading.enumerate()):  # Script Editor re-runs: one receiver only
    threading.Thread(target=receive_leader_arm, name="leader-arm-rx", daemon=True).start()


async def drive_arms_from_leader_arm():
    world = World.instance() or World()
    await world.initialize_simulation_context_async()
    world.scene.add_default_ground_plane()  # 바닥: 없으면 로봇이 아래로 떨어진다
    PhysxSchema.PhysxArticulationAPI.Apply(world.stage.GetPrimAtPath("/World/RBY1")) \
        .CreateEnabledSelfCollisionsAttr(False)  # 자기충돌 OFF: 켜져 있으면 뒤로 넘어진다

    robot = SingleArticulation(prim_path="/World/RBY1", name="rby1_leader")
    await world.reset_async()
    robot.initialize()
    idx = np.array([list(robot.dof_names).index(n) for n in ARM_JOINTS])  # 14 arm joints
    target = None

    def on_physics_step(dt):
        nonlocal target
        q = leader["q"]
        if q is None:
            return
        if target is None:
            target = robot.get_joint_positions()[idx].astype(float)
        step = MAX_SPEED * dt
        target = target + np.clip(q - target, -step, step)  # rate-limited follow
        robot.apply_action(ArticulationAction(joint_positions=target, joint_indices=idx))

    if world.physics_callback_exists("leader_arm"):
        world.remove_physics_callback("leader_arm")
    world.add_physics_callback("leader_arm", on_physics_step)
    await world.play_async()
    print("[leader-arm] arms follow the leader arm (14 joints); press Stop to end")


asyncio.ensure_future(drive_arms_from_leader_arm())
