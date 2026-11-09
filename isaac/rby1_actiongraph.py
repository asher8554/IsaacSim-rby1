# Isaac Sim GUI의 Script Editor에서 실행: 새 Stage에 RB-Y1 A를 불러오고 Action Graph로 양팔 관절 위치를 제어
"""Mode A - Action Graph.

Builds /World/RBY1_ActionGraph:
    On Playback Tick -> Articulation Controller (position targets for both arms)
                     -> Articulation State      (reads the same joints back)
Press Play, then edit ArticulationController > inputs:positionCommand (radians) in the Property panel.
WARNING: replaces the currently open stage with a new one.
"""
import math
import os

import omni.graph.core as og
import omni.usd
from isaacsim.core.api.scenes.scene import Scene
from pxr import PhysxSchema, UsdGeom, UsdPhysics

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:  # Script Editor runs without __file__
    ROOT = r"E:/Github/IsaacSim-rby1"
ROBOT_USD = os.path.join(ROOT, "rby1-sim-isaac", "assets", "model_v_1_2_a.usd").replace("\\", "/")
ROBOT_PATH = "/World/RBY1"
GRAPH_PATH = "/World/RBY1_ActionGraph"

ARM_JOINTS = [f"right_arm_{i}" for i in range(7)] + [f"left_arm_{i}" for i in range(7)]
# Ready pose [deg]: shoulders slightly out, elbows bent 90 deg (limits: right_arm_1 -180..0, left_arm_1 0..180, arm_3 -150..0)
READY_POSE_DEG = [0, -10, 0, -90, 0, 0, 0] + [0, 10, 0, -90, 0, 0, 0]


def build_stage():
    ctx = omni.usd.get_context()
    ctx.new_stage()
    stage = ctx.get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())

    # Same physics rate as the official simulator (rby1-sim-isaac config.PHYSICS_HZ = 500)
    scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    PhysxSchema.PhysxSceneAPI.Apply(scene.GetPrim()).CreateTimeStepsPerSecondAttr(500)
    Scene().add_default_ground_plane()  # Isaac grid environment (ground + lights), as in the official RBY1Task

    robot = stage.DefinePrim(ROBOT_PATH, "Xform")
    robot.GetReferences().AddReference(ROBOT_USD)
    # Official RBY1Task settings: self-collision off (the USD collision shapes make joints unstable), solver 4/1
    art = PhysxSchema.PhysxArticulationAPI.Apply(robot)
    art.CreateEnabledSelfCollisionsAttr(False)
    art.CreateSolverPositionIterationCountAttr(4)
    art.CreateSolverVelocityIterationCountAttr(1)
    return stage


def build_graph():
    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": GRAPH_PATH, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                ("ArticulationController", "isaacsim.core.nodes.IsaacArticulationController"),
                ("ArticulationState", "isaacsim.core.nodes.IsaacArticulationState"),
            ],
            keys.CONNECT: [
                ("OnPlaybackTick.outputs:tick", "ArticulationController.inputs:execIn"),
                ("OnPlaybackTick.outputs:tick", "ArticulationState.inputs:execIn"),
            ],
            keys.SET_VALUES: [
                ("ArticulationController.inputs:robotPath", ROBOT_PATH),
                ("ArticulationController.inputs:jointNames", ARM_JOINTS),
                ("ArticulationController.inputs:positionCommand", [math.radians(d) for d in READY_POSE_DEG]),
                ("ArticulationState.inputs:robotPath", ROBOT_PATH),
                ("ArticulationState.inputs:jointNames", ARM_JOINTS),
            ],
        },
    )


stage = build_stage()
assert stage.GetPrimAtPath(ROBOT_PATH).IsValid(), f"robot not loaded from {ROBOT_USD}"
build_graph()
print(f"[RBY1 ActionGraph] loaded {ROBOT_USD} at {ROBOT_PATH}, graph {GRAPH_PATH}. Press Play.")
