from typing import Any, Callable, List, Optional
from importlib import resources
import os
import math
import numpy as np
from gymnasium import spaces
import mujoco

def action_obs_check(cls: Any) -> None:
    """Verify that action and observation spaces have distinct low/high bounds.

    Args:
        cls: Environment class with action_space and observation_space attributes.

    Raises:
        ValueError: If any dimension of action or observation space has low == high.
    """
    low = cls.action_space.low
    high = cls.action_space.high
    if (low == high).any():
        raise ValueError("Action space has the same low and high value")

    low = cls.observation_space.low
    high = cls.observation_space.high
    if (low == high).any():
        raise ValueError("Observation space has the same low and high value")


def get_ms_human_model_path(filename: str) -> str:
    """Resolve a model file from MS_HUMAN_MODEL_DIR or bundled package data."""
    override = os.environ.get("MS_HUMAN_MODEL_DIR")
    if override:
        candidate = os.path.abspath(os.path.join(override, filename))
        if not os.path.isfile(candidate):
            raise FileNotFoundError(candidate)
        return candidate
    candidate = resources.files("msgym") / "MS-Human-700" / filename
    if not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return str(candidate)

def get_observation_space(
    xml_path: str,
    get_obs_fn: Callable[..., np.ndarray],
    obs_kwargs: Optional[dict] = None,
) -> spaces.Box:
    """Build a Box observation space from an XML model and observation function.

    Args:
        xml_path: Path to MuJoCo XML model file.
        get_obs_fn: Function that takes mujoco.MjData and optional kwargs, returns 1D obs.
        obs_kwargs: Optional keyword arguments passed to get_obs_fn.

    Returns:
        Gymnasium Box observation space with shape inferred from get_obs_fn output.
    """
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    obs = get_obs_fn(data, **(obs_kwargs or {}))
    assert obs.ndim == 1, "Observation must be 1D"
    return spaces.Box(
        low=-np.inf, high=np.inf, shape=(obs.shape[0],), dtype=np.float64
    )

def get_render_fps(xml_path: str, skip_frames: int) -> int:
    """Compute effective render FPS from model timestep and frame skip.

    Args:
        xml_path: Path to MuJoCo XML model file.
        skip_frames: Number of simulation steps per environment step.

    Returns:
        Rounded FPS (1 / (timestep * skip_frames)).
    """
    model = mujoco.MjModel.from_xml_path(xml_path)
    timestep = model.opt.timestep
    return int(round(1.0 / timestep / skip_frames))

def euler2quat(euler: np.ndarray) -> np.ndarray:
    """Convert Euler angles (ZYX order) to quaternions (w, x, y, z).

    Args:
        euler: Array of shape (..., 3) with Euler angles in radians.

    Returns:
        Array of shape (..., 4) with quaternions (w, x, y, z).
    """
    euler = np.asarray(euler, dtype=np.float64)
    assert euler.shape[-1] == 3, f"Invalid shape euler {euler.shape}"

    ai, aj, ak = euler[..., 2] / 2, -euler[..., 1] / 2, euler[..., 0] / 2
    si, sj, sk = np.sin(ai), np.sin(aj), np.sin(ak)
    ci, cj, ck = np.cos(ai), np.cos(aj), np.cos(ak)
    cc, cs = ci * ck, ci * sk
    sc, ss = si * ck, si * sk

    quat = np.empty(euler.shape[:-1] + (4,), dtype=np.float64)
    quat[..., 0] = cj * cc + sj * ss
    quat[..., 3] = cj * sc - sj * cs
    quat[..., 2] = -(cj * ss + sj * cc)
    quat[..., 1] = cj * cs - sj * sc
    return quat

def joint_name_to_dof_index(
    all_joint_name_list: List[str],
    joint_name_list: List[str],
) -> List[int]:
    """Map joint names to indices in a full joint name list.

    Args:
        all_joint_name_list: Full list of joint names (order defines indices).
        joint_name_list: Subset of joint names to look up.

    Returns:
        List of indices for each name in joint_name_list.

    Raises:
        ValueError: If any name in joint_name_list is not in all_joint_name_list.
    """
    joint_index_list = []
    for joint_name in joint_name_list:
        if joint_name in all_joint_name_list:
            joint_index_list.append(all_joint_name_list.index(joint_name))
        else:
            raise ValueError(
                f"Joint name {joint_name} not found in all joint name list"
            )
    return joint_index_list


def load_task_model(model_path, scene=None, scene_kwargs=None):
    """Compile the shared human entry with optional world-only stairs.

    Defaults match the stair reference: ascent along world +Y.
    Adding static world geoms does not change joint or actuator ordering.
    """
    if scene is None:
        if scene_kwargs:
            raise ValueError("scene_kwargs requires a scene")
        return mujoco.MjModel.from_xml_path(str(model_path))
    if scene != "stairs":
        raise ValueError(f"Unknown scene: {scene}")
    options = dict(height=0.1, depths=[0.6, 0.6, 0.6, 0.6, 0.9],
                   width=0.9, center_x=0.23, start_y=-0.42)
    supplied = scene_kwargs or {}
    unknown = set(supplied) - options.keys()
    if unknown:
        raise ValueError(f"Unknown stairs options: {sorted(unknown)}")
    options.update(supplied)
    height, width = float(options["height"]), float(options["width"])
    depths = [float(value) for value in options["depths"]]
    center_x, start_y = float(options["center_x"]), float(options["start_y"])
    if not depths or not all(math.isfinite(v) and v > 0 for v in [height, width, *depths]):
        raise ValueError("Stair height, width and depths must be finite and positive")
    if not all(math.isfinite(v) for v in [center_x, start_y]):
        raise ValueError("Stair coordinates must be finite")
    spec = mujoco.MjSpec.from_file(str(model_path))
    for index, depth in enumerate(depths, 1):
        top = index * height
        spec.worldbody.add_geom(
            name=f"stair_{index}", type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[center_x, start_y + depth / 2, top / 2],
            size=[width / 2, depth / 2, top / 2],
            rgba=[0.35, 0.43, 0.51, 1], contype=1, conaffinity=1,
            margin=0, friction=[1, 0.005, 0.0001],
        )
        start_y += depth
    return spec.compile()
