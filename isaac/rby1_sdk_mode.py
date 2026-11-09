# Isaac Sim GUI의 Script Editor에서 실행: 공식 RBY1Task로 RB-Y1 A를 띄우고 WSL의 rby1 core(rby1-sdk 서버)와 연결
"""Mode B - rby1 software (rby1 core + rby1-sdk).

Runs the official rby1-sim-isaac RBY1Task (2 ms physics, motor servo model, torque control) inside the GUI app.
USE_CORE=True : joints follow the rby1 core in WSL (wsl/start_core.sh), which serves rby1-sdk on 127.0.0.1:50051.
USE_CORE=False: the task's built-in test trajectory, no core needed.
WARNING: replaces the currently open stage with a new one.
"""
import asyncio
import importlib.util
import os
import sys
import types

USE_CORE = True

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:  # Script Editor runs without __file__
    ROOT = r"E:/Github/IsaacSim-rby1"
SRC = os.path.join(ROOT, "rby1-sim-isaac", "src")
for p in (SRC, os.path.join(ROOT, "isaac")):
    if p not in sys.path:
        sys.path.insert(0, p)

# Kit resolves a top-level "config" to the bundled cv2/config.py whatever sys.path says, so load the official
# src/config.py by file path and register it under that name before rby1_task imports it.
_spec = importlib.util.spec_from_file_location("config", os.path.join(SRC, "config.py"))
config = importlib.util.module_from_spec(_spec)
sys.modules["config"] = config
_spec.loader.exec_module(config)

from rby1_link import TcpBridge  # noqa: E402

# rby1_task imports rby1_udp_bridge, whose codec is a Linux-only .so. Serve the TCP bridge under that name instead.
_shim = types.ModuleType("rby1_udp_bridge")
_shim.RBY1UdpBridge = TcpBridge
sys.modules["rby1_udp_bridge"] = _shim

import omni.usd  # noqa: E402
from isaacsim.core.api import World  # noqa: E402

from rby1_task import RBY1Task  # noqa: E402

PHYSICS_DT, RENDER_DT = config.PHYSICS_DT, config.RENDER_DT


async def start():
    old = globals().get("_rby1_bridge")
    if old is not None:  # re-run in the same Script Editor session: free the previous connection
        old.close()
    await omni.usd.get_context().new_stage_async()
    World.clear_instance()
    world = World(
        physics_dt=PHYSICS_DT,
        rendering_dt=RENDER_DT,
        stage_units_in_meters=1.0,
        sim_params={"solver_type": 0, "use_gpu_pipeline": False, "enable_scene_query_support": False,
                    "use_fabric": True},
        device="cpu",
    )
    bridge = TcpBridge() if USE_CORE else None
    globals()["_rby1_bridge"] = bridge
    task = RBY1Task(udp_bridge=bridge, robot_model="a")
    world.add_task(task)
    await world.initialize_simulation_context_async()
    await world.reset_async()

    # Same order as the official loop: pre_step -> physics -> post_physics_step (send state) -> pre_step ...
    def on_physics_step(dt):
        if task._last_pre_step_sim_time is not None:
            task.post_physics_step(dt)
        world.step_async(dt)

    world.add_physics_callback("rby1_lockstep", on_physics_step)
    await world.play_async()
    mode = "rby1 core via WSL relay (tcp 127.0.0.1:5010)" if USE_CORE else "built-in trajectory"
    print(f"[RBY1 SDK mode] playing, control = {mode}")


asyncio.ensure_future(start())
