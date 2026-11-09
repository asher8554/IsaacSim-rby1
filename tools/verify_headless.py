# GUI용 두 스크립트(Action Graph 모드, SDK 모드)를 headless Isaac Sim에서 실행해 관절이 실제로 움직이는지 검사
"""Usage: C:\\isaacsim-6.2\\python.bat tools\\verify_headless.py [actiongraph|builtin|core]
  actiongraph : isaac/rby1_actiongraph.py, arms must reach the Action Graph targets
  builtin     : isaac/rby1_sdk_mode.py with USE_CORE=False (official built-in trajectory)
  core        : isaac/rby1_sdk_mode.py with USE_CORE=True; needs wsl/start_core.sh (or tools/check_link.py --serve)
  builtin|core <seconds> : keep simulating that long and print joint angles every 2 s
"""
import math
import os
import sys

from isaacsim import SimulationApp

MODE = sys.argv[1] if len(sys.argv) > 1 else "actiongraph"
app = SimulationApp({"headless": True})

import numpy as np  # noqa: E402
import omni.timeline  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_script(name, **overrides):
    path = os.path.join(ROOT, "isaac", name)
    src = open(path, encoding="utf-8").read()
    for k, v in overrides.items():
        src = src.replace(f"{k} = {not v}", f"{k} = {v}", 1)
    g = {"__name__": "__main__", "__file__": path}
    exec(compile(src, path, "exec"), g)
    return g


def joint_positions(prim_path, names):
    from isaacsim.core.prims import SingleArticulation

    art = SingleArticulation(prim_path)
    art.initialize()
    q = art.get_joint_positions()
    return np.array([q[art.dof_names.index(n)] for n in names])


def base_upright(prim_path):
    """z component of the base's up axis: 1 = standing, < 0.9 = tipped over."""
    from isaacsim.core.prims import SingleArticulation

    art = SingleArticulation(prim_path)
    art.initialize()
    w, x, y, z = art.get_world_pose()[1]
    return 1.0 - 2.0 * (x * x + y * y)


if MODE == "actiongraph":
    g = run_script("rby1_actiongraph.py")
    omni.timeline.get_timeline_interface().play()
    for _ in range(300):  # ~5 s at 60 Hz
        app.update()
    target = np.radians(g["READY_POSE_DEG"])
    q = joint_positions(g["ROBOT_PATH"], g["ARM_JOINTS"])
    err = np.degrees(np.abs(q - target))
    print("[verify] arm joints deg:", np.round(np.degrees(q), 1).tolist())
    up = base_upright(g["ROBOT_PATH"])
    print(f"[verify] max |q - target| = {err.max():.2f} deg, base upright = {up:.3f}")
    ok = err.max() < 3.0 and up > 0.9
else:
    import time

    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0  # keep running, e.g. while an rby1-sdk example moves it
    g = run_script("rby1_sdk_mode.py", USE_CORE=(MODE == "core"))
    for _ in range(400):
        app.update()
    from isaacsim.core.api import World

    world = World.instance()
    task = world.get_task("rby1_task")
    names = ["torso_1", "torso_2", "right_arm_1", "right_arm_3", "left_arm_1", "left_arm_3"]
    peak = np.zeros(len(names))
    t_end, t_next = time.monotonic() + secs, 0.0
    while time.monotonic() < t_end:
        app.update()
        if time.monotonic() >= t_next:
            q = np.degrees(joint_positions("/World/RBY1", names))
            peak = np.maximum(peak, np.abs(q))
            print(f"[verify] sim {world.current_time:7.2f}s joints deg:", np.round(q, 1).tolist(), flush=True)
            t_next = time.monotonic() + 2.0
    q = joint_positions("/World/RBY1", names)
    up = base_upright("/World/RBY1")
    print(f"[verify] playing={world.is_playing()} sim_time={world.current_time:.3f}s steps={task.step_counter} "
          f"base upright={up:.3f}")
    print("[verify] joints deg:", dict(zip(names, np.round(np.degrees(q), 2).tolist())))
    if secs:
        print("[verify] peak |q| deg over run:", dict(zip(names, np.round(peak, 1).tolist())))
    bridge = g.get("_rby1_bridge")
    if bridge is not None:
        print(f"[verify] bridge connected={bridge.connected} commands received={bridge._seq}")
    ok = world.is_playing() and task.step_counter > 100 and up > 0.9 and (bridge is None or bridge._seq > 100)

print("[verify] RESULT:", "PASS" if ok else "FAIL", MODE)
app.close()
