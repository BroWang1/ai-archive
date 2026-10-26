"""Single right-arm environment with optional stereo feedback and a moving target.

The nonvisual baseline exposes object/target poses as privileged task reference.
"""
from typing import Any

import mujoco
import numpy as np
from gymnasium import spaces
from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
from gymnasium.utils import EzPickle, seeding

from msgym.envs.sensorimotor import SensorimotorObservations
from msgym.envs.utils import (
    euler2quat,
    get_ms_human_model_path,
    get_render_fps,
)


class ManipulationEnvV1(SensorimotorObservations, MujocoEnv, EzPickle):
    """Right-arm manipulation environment: reach, lift, and orient an object to a target."""

    metadata: dict[str, Any] = {
        "render_modes": [
            "human",
            "rgb_array",
            "depth_array",
        ],
        "render_fps": 10,
    }
    DEFAULT_RWD_KEYS_AND_WEIGHTS = {
        "w_pos": 50, "k_pos": 10.0,
        "w_ori": 10, "k_ori": 2.0,
        "w_reach": 10, "k_reach": 10.0,
        "w_lift": 1, "k_lift": 0.02,
        "w_act": 1,
        "w_drop": 100.0, "k_drop": 0.3,
    }

    def __init__(
        self,
        render_mode: str | None = None,
        skip_frames: int = 10,
        reset_noise_scale: float = 1e-3,
        target_pos_range: tuple[np.ndarray, np.ndarray] | None = None,
        target_ori_range: tuple[np.ndarray, np.ndarray] | None = None,
        reward_dict: dict[str, float] | None = None,
        eye_camera_size: int = 96,
        vision_render_interval: int = 5,
        vision_enabled: bool = True,
        target_moving: bool = True,
        target_speed_range: tuple[float, float] = (0.1, 0.1),
        start_moving_time: float = 0.5,
        target_lift_interpolation: bool = False,
        terminate_time: float = 2.0,
        **kwargs: Any,
    ) -> None:
        """Initialize the manipulation environment.

        Args:
            render_mode: One of "human", "rgb_array", "depth_array", or None.
            skip_frames: Simulation steps per environment step.
            reset_noise_scale: Scale of uniform noise added to qpos/qvel on reset.
            target_pos_range: Optional (low, high) for sampling target position.
            target_ori_range: Optional (low, high) for sampling target orientation.
            reward_dict: Optional dict of reward weights; defaults to DEFAULT_RWD_KEYS_AND_WEIGHTS.
            **kwargs: Passed to MujocoEnv.
        """
        if not np.isfinite(terminate_time) or terminate_time <= 0:
            raise ValueError("terminate_time must be a positive finite number of seconds")
        if target_lift_interpolation and start_moving_time <= 0:
            raise ValueError("Interpolated lift requires positive start_moving_time")
        self.target_lift_interpolation = target_lift_interpolation
        self.target_moving = target_moving
        self.target_speed_range = target_speed_range
        self.start_moving_time = start_moving_time
        self.terminate_time = float(terminate_time)
        if reward_dict is None:
            reward_dict = self.DEFAULT_RWD_KEYS_AND_WEIGHTS
        model_path = get_ms_human_model_path("MS-Human-700-Manipulation.xml")

        assert render_mode is None or render_mode in self.metadata["render_modes"]

        fps = get_render_fps(model_path, skip_frames)
        self.metadata = dict(self.metadata)
        self.metadata["render_fps"] = fps
        self.control_timestep = 1 / fps

        EzPickle.__init__(
            self,
            render_mode=render_mode,
            skip_frames=skip_frames,
            reset_noise_scale=reset_noise_scale,
            target_pos_range=target_pos_range,
            target_ori_range=target_ori_range,
            reward_dict=reward_dict,
            eye_camera_size=eye_camera_size,
            vision_render_interval=vision_render_interval,
            vision_enabled=vision_enabled,
            target_moving=target_moving,
            target_speed_range=target_speed_range,
            start_moving_time=start_moving_time,
            target_lift_interpolation=target_lift_interpolation,
            terminate_time=terminate_time,
            **kwargs,
        )

        self.render_mode = render_mode
        self._reset_noise_scale = reset_noise_scale
        self.reward_weight = reward_dict

        observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32
        )
        MujocoEnv.__init__(
            self,
            model_path,
            skip_frames,
            observation_space=observation_space,
            render_mode=render_mode,
            camera_name="record_camera",
            **kwargs,
        )

        self.target_pos_range = target_pos_range
        self.target_ori_range = target_ori_range
        self.target_pos = np.array([0, 0, 0.3])
        self.target_ori = np.array([0, 0])  # Rx and Ry

        self.pos_threshold = 0.02
        self.ori_threshold = 0.1

        self.init_qpos[:] = self.model.key_qpos[0].copy()
        self.body_name_list = [self.model.body(i).name for i in range(self.model.nbody)]
        self.joint_name_list = [self.model.joint(i).name for i in range(self.model.njnt)]
        self.muscle_name_list = [self.model.actuator(i).name for i in range(self.model.nu)]
        self.object_sid = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_SITE, "Object"
        )
        self.target_bid = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "target"
        )
        self.success_indicator_sid = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_SITE, "target_indicator"
        )
        self.hand_body_list = [
            "proximal_thumb", "distal_thumb",
            "2proxph", "2midph", "2distph",
            "3proxph", "3midph", "3distph",
            "4proxph", "4midph", "4distph",
            "5proxph", "5midph", "5distph",
        ]
        self.obj_init_xpos = self.data.site_xpos[self.object_sid].copy()

        # All joints are scalar; bottle joints are excluded from human proprioception.
        object_body = self.model.body("waterbottle").id
        human_joints = np.flatnonzero(self.model.jnt_bodyid != object_body)
        self._human_qpos = self.model.jnt_qposadr[human_joints]
        self._human_qvel = self.model.jnt_dofadr[human_joints]
        self._base_target_pos = self.target_pos.copy()
        self._base_target_ori = self.target_ori.copy()
        self._obj_init_ori = self.init_qpos[-3:-1].copy()
        self._target_velocity = 0.0
        self._init_senses(eye_camera_size, vision_render_interval, vision_enabled)
        proprio, reference = self._split_observation(self._observation_components())
        self.observation_space = self._sensory_space(len(proprio), len(reference))

    def seed(self, seed: int = 0) -> list[int]:
        """Compatibility API for callers that still use env.seed(seed)."""
        self._np_random, seeded = seeding.np_random(seed)
        self._np_random_seed = seeded
        return [seeded]

    @property
    def terminated(self) -> bool:
        """True if the episode is done (e.g. object dropped or out of bounds)."""
        return self._get_done()

    def _observation_components(self) -> dict[str, np.ndarray]:
        """Collect human state and task diagnostics without rendering."""
        qpos = self.data.qpos.copy()
        qvel = self.data.qvel.copy()

        act = self.data.act.copy()
        actuator_forces = self.data.actuator_force.copy() / 1000
        actuator_forces = actuator_forces.clip(-100, 100)
        actuator_length = self.data.actuator_length.copy()
        actuator_velocity = self.data.actuator_velocity.copy().clip(-100, 100)

        sim_time = np.array([self.data.time])
        self.obj_xpos = self.data.site_xpos[self.object_sid].copy()
        self.target_xpos = self.target_pos + self.obj_init_xpos
        self.obj_xpos_dist = self.target_xpos - self.obj_xpos
        self.obj_ori = qpos[-3:-1].copy()
        self.obj_ori_dist = self.target_ori - self.obj_ori

        reach_dist = 0
        for body_name in self.hand_body_list:
            body_xpos = self.data.body(body_name).xpos.copy()
            reach_dist += np.linalg.norm(body_xpos - self.obj_xpos)
        self.reach_dist = np.abs(reach_dist) / len(self.hand_body_list)

        return {
            "qpos": qpos,
            "qvel": qvel,
            "act": act,
            "actuator_forces": actuator_forces,
            "actuator_length": actuator_length,
            "actuator_velocity": actuator_velocity,
            "sim_time": sim_time,
            "obj_xpos": self.obj_xpos,
            "target_xpos": self.target_xpos,
            "obj_ori": self.obj_ori,
            "target_ori": self.target_ori,
            "obj_xpos_dist": self.obj_xpos_dist,
            "obj_ori_dist": self.obj_ori_dist,
            "reach_dist": np.array([self.reach_dist]),
        }

    def _split_observation(
        self, components: dict[str, np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray]:
        proprio = np.concatenate([
            components["qpos"][self._human_qpos],
            components["qvel"][self._human_qvel],
            components["act"],
            components["actuator_forces"],
            components["actuator_length"],
            components["actuator_velocity"],
        ]).astype(np.float32)
        reference = components["sim_time"]
        if not self.vision_enabled:
            # Privileged task state for the explicitly nonvisual baseline.
            reference = np.concatenate([
                reference, components["obj_xpos"], components["target_xpos"],
                components["obj_ori"], components["target_ori"],
            ]).astype(np.float32)
        return proprio, reference

    def _get_obs(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        components = self._observation_components()
        proprio, reference = self._split_observation(components)
        return self._sensory_obs(proprio, reference), components

    def step(
        self, action: np.ndarray
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        """Step the environment with the given action."""
        self._update_target(self.data.time + self.dt)
        self.do_simulation(action, self.frame_skip)

        observation, components = self._get_obs()

        pos_distance = np.linalg.norm(components["obj_xpos_dist"])
        ori_distance = np.linalg.norm(components["obj_ori_dist"])
        reach_distance = components["reach_dist"][0]
        pos_reward = self.reward_weight["w_pos"] * np.exp(
            -self.reward_weight["k_pos"] * pos_distance
        )
        ori_reward = self.reward_weight["w_ori"] * np.exp(
            -self.reward_weight["k_ori"] * ori_distance
        )
        reach_reward = self.reward_weight["w_reach"] * np.exp(
            -self.reward_weight["k_reach"] * reach_distance
        )
        drop = reach_distance > self.reward_weight["k_drop"]
        lift_bonus = (
            components["obj_xpos"][2] - self.obj_init_xpos[2]
            >= self.reward_weight["k_lift"]
        ) and not drop
        lift_reward = self.reward_weight["w_lift"] * float(lift_bonus)
        act_penalty = -self.reward_weight["w_act"] * np.linalg.norm(action) / self.model.na

        terminated = self.terminated
        truncated = self.data.time >= self.terminate_time - 1e-9
        done_penalty = -self.reward_weight["w_drop"] * float(terminated)
        reward = (
            pos_reward * ori_reward + reach_reward + lift_reward + act_penalty + done_penalty
        )
        solved = (
            pos_distance < self.pos_threshold
            and ori_distance < self.ori_threshold
            and not drop
        )
        self.model.site_rgba[self.success_indicator_sid, :2] = (
            np.array([0, 2]) if solved else np.array([2, 0])
        )
        self.model.site_size[self.success_indicator_sid, :] = (
            np.array([0.1]) if solved else np.array([0.001])
        )

        info = {
            "task/position_error_m": float(pos_distance),
            "task/orientation_error_rad": float(ori_distance),
            "task/reach_distance_m": float(reach_distance),
            "task/lifted": float(lift_bonus),
            "task/success": float(solved),
            "episode/duration_s": float(self.data.time),
            "reward": reward,
            "reward_pos": pos_reward,
            "reward_ori": ori_reward,
            "reward_reach": reach_reward,
            "reward_lift": lift_reward,
            "reward_act": act_penalty,
            "reward_done": done_penalty,
            "solved": solved,
        }

        return observation, reward, terminated, truncated, info

    def reset_model(self) -> dict[str, np.ndarray]:
        """Reset the model state with optional noise and target sampling."""
        noise_low = -self._reset_noise_scale
        noise_high = self._reset_noise_scale

        qpos = self.init_qpos + self.np_random.uniform(
            low=noise_low, high=noise_high, size=self.model.nq
        )
        qvel = self.init_qvel + self.np_random.uniform(
            low=noise_low, high=noise_high, size=self.model.nv
        )

        self.data.act[:] = self.data.ctrl
        self.set_state(qpos, qvel)

        self.obj_init_xpos = self.data.site_xpos[self.object_sid].copy()

        # Start from the episode's sampled origin, not its last moving position.
        self.target_pos = self._base_target_pos.copy()
        self.target_ori = self._base_target_ori.copy()
        self._obj_init_ori = self.data.qpos[-3:-1].copy()
        if self.target_pos_range is not None:
            self.target_pos = self.np_random.uniform(
                low=self.target_pos_range[0], high=self.target_pos_range[1]
            )
        if self.target_ori_range is not None:
            self.target_ori = self.np_random.uniform(
                low=self.target_ori_range[0], high=self.target_ori_range[1]
            )

        target_euler = np.array([self.target_ori[0], self.target_ori[1], 0])
        self.model.body_pos[self.target_bid] = self.target_pos + self.obj_init_xpos
        self.model.body_quat[self.target_bid] = euler2quat(target_euler)

        self._base_target_pos = self.target_pos.copy()
        self._base_target_ori = self.target_ori.copy()
        self._target_velocity = (
            self.np_random.uniform(*self.target_speed_range) * self.np_random.choice([-1, 1])
        )
        self._update_target(0.0)
        mujoco.mj_forward(self.model, self.data)
        self._image_cache = None
        return self._get_obs()[0]

    def _update_target(self, time: float) -> None:
        self.target_pos = self._base_target_pos.copy()
        self.target_ori = self._base_target_ori.copy()
        if self.target_lift_interpolation:
            # Interpolate target position and orientation, using smoothstep interpolation for the lateral offset.
            phase = np.clip(time / self.start_moving_time, 0.0, 1.0)
            self.target_pos *= phase
            self.target_pos[1] = self._base_target_pos[1] * phase**2 * (3.0 - 2.0 * phase)
            self.target_ori = self._obj_init_ori + phase * (self._base_target_ori - self._obj_init_ori)
        if self.target_moving:
            self.target_pos[1] += self._target_velocity * max(0, time - self.start_moving_time)
        self.model.body_pos[self.target_bid] = self.obj_init_xpos + self.target_pos
        self.model.body_quat[self.target_bid] = euler2quat(np.array([*self.target_ori, 0.0]))

    def _get_done(self) -> bool:
        """True if object is dropped or out of allowed bounds."""
        x, y, z = self.data.site_xpos[self.object_sid]
        if self.reach_dist > self.reward_weight["k_drop"]:
            return True
        if x < 0 or x > 0.7:
            return True
        if y < -0.5 or y > 0.5:
            return True
        if z < (self.obj_init_xpos[2] - 0.02) or z > 1.7:
            return True

        return False
