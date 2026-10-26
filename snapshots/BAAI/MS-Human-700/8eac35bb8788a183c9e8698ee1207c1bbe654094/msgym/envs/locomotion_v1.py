import os
from typing import Any

import mujoco
import numpy as np
from gymnasium import spaces
from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
from gymnasium.utils import EzPickle, seeding

from msgym.envs.imitation_trajectory import LocomotionTrajectory
from msgym.envs.sensorimotor import SensorimotorObservations
from msgym.envs.utils import get_ms_human_model_path, get_render_fps, load_task_model


class LocomotionEnvV1(SensorimotorObservations, MujocoEnv, EzPickle):
    """Full-body locomotion imitation using one or more reference trajectories."""

    metadata: dict[str, Any] = {
        "render_modes": [
            "human",
            "rgb_array",
            "depth_array",
        ],
        "render_fps": 50,
    }

    DEFAULT_RWD_KEYS_AND_WEIGHTS = {
        "w_qpos": 50,
        "w_xpos": 50,
        "w_pelvis": 50,
        "w_energy": 0.1,
        "w_healthy": 100,
    }

    def __init__(
        self,
        motion_dir: str | None = None,
        motion_list: list[int] | None = None,
        terminate_time: float = 5.0,
        skip_frames: int = 10,
        reset_noise_scale: float = 1e-3,
        random_init: bool = True,
        qpos_diff_th: float = 0.05,
        kinematic_play: bool = False,
        render_mode: str | None = None,
        reward_dict: dict[str, float] | None = None,
        model_file: str = "MS-Human-700.xml",
        trajectory_mode: str = "repeat",
        scene: str | None = None,
        scene_kwargs: dict | None = None,
        perturbations: list | None = None,
        eye_camera_size: int = 64,
        vision_render_interval: int = 5,
        vision_enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize the full-body locomotion imitation environment.

        Args:
            motion_dir: Path to a single .npz file or directory of .npz files; None uses default.
            motion_list: Indices of .npz files to load from motion_dir (0-based).
            terminate_time: Maximum episode simulation time in seconds, including clip restarts.
            skip_frames: Simulation steps per environment step.
            reset_noise_scale: Scale of noise added to qpos/qvel on reset.
            random_init: If True, start at a random time in the trajectory.
            qpos_diff_th: Threshold on mean qpos error for healthy state.
            kinematic_play: If True, gravity off and state follows reference.
            render_mode: One of "human", "rgb_array", "depth_array", or None.
            reward_dict: Reward weights; None uses DEFAULT_RWD_KEYS_AND_WEIGHTS.
            vision_enabled: Include stereo observations in multimodal mode; false retains all vector senses.
            **kwargs: Passed to MujocoEnv.
        """
        if reward_dict is None:
            reward_dict = self.DEFAULT_RWD_KEYS_AND_WEIGHTS
        if trajectory_mode not in ("finite", "repeat"):
            raise ValueError("Unknown trajectory mode")
        if not np.isfinite(terminate_time) or terminate_time <= 0:
            raise ValueError("terminate_time must be a positive finite number of seconds")
        self.terminate_time = float(terminate_time)
        self.trajectory_mode = trajectory_mode
        self.scene, self.scene_kwargs = scene, scene_kwargs
        self.perturbations = perturbations or []
        self.reward_weight = reward_dict
        self._reset_noise_scale = reset_noise_scale
        self.random_init = random_init
        self.kinematic_play = kinematic_play
        self.qpos_diff_th = qpos_diff_th
        model_path = get_ms_human_model_path(model_file)

        assert render_mode is None or render_mode in self.metadata["render_modes"]
        self.metadata = dict(self.metadata)
        fps = get_render_fps(model_path, skip_frames)
        self.metadata["render_fps"] = fps
        self.control_timestep = 1 / fps

        if motion_dir is None:
            # Default walking reference, replayed within the episode
            motion_dir = os.path.join(os.path.dirname(__file__), "..", "motion_data", "tracking_walk.npz")
            motion_dir = os.path.abspath(motion_dir)
            motion_list = None

        if not os.path.exists(motion_dir):
            packaged = os.path.join(os.path.dirname(__file__), "..", "motion_data", motion_dir)
            if os.path.isfile(packaged):
                motion_dir = os.path.abspath(packaged)
        self.trajectory = LocomotionTrajectory(motion_dir, motion_list)
        self.current_traj_index = 0
        self._reference_start_time = 0.0
        self.future_traj_steps = 5

        self.trajectory_duration, _, _ = self.trajectory.get_trajectory_properties(self.current_traj_index)

        EzPickle.__init__(
            self,
            motion_dir=motion_dir,
            motion_list=motion_list,
            terminate_time=terminate_time,
            skip_frames=skip_frames,
            reset_noise_scale=reset_noise_scale,
            random_init=random_init,
            qpos_diff_th=qpos_diff_th,
            kinematic_play=kinematic_play,
            render_mode=render_mode,
            reward_dict=reward_dict,
            model_file=model_file,
            trajectory_mode=trajectory_mode,
            scene=scene,
            scene_kwargs=scene_kwargs,
            perturbations=perturbations,
            eye_camera_size=eye_camera_size,
            vision_render_interval=vision_render_interval,
            vision_enabled=vision_enabled,
            **kwargs,
        )

        # Dummy observation space to initialize MujocoEnv
        observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32)
        MujocoEnv.__init__(
            self,
            model_path,
            skip_frames,
            observation_space=observation_space,
            render_mode=render_mode,
            camera_name="record_camera",
            max_geom=10000,
            **kwargs,
        )

        self.init_qpos[:] = self.model.key_qpos[0].copy()
        self.key_body_names = [
            "sternum", "head_neck", "toes_r", "toes_l", "proximal_row_r", "proximal_row_l",
        ]
        self.pelvis_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        root = self.model.jnt_bodyid == self.pelvis_id
        self._root_translation = self.model.jnt_qposadr[root & (self.model.jnt_type == mujoco.mjtJoint.mjJNT_SLIDE)]
        self._root_rotation = self.model.jnt_qposadr[root & (self.model.jnt_type == mujoco.mjtJoint.mjJNT_HINGE)]
        self._other_qpos = self.model.jnt_qposadr[~root]
        self._joint_scales = [
            max(float(np.ptp(t["qpos_traj"][:, self._other_qpos], axis=0).mean()), 1e-8)
            for t in self.trajectory.trajectories
        ]
        self._last_right_contact = False
        self._right_strikes = 0
        self._last_strike_time = -1.0
        self.key_body_ids = [
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
            for name in self.key_body_names
        ]
        self.body_name_list = [self.model.body(body_id).name for body_id in range(self.model.nbody)]
        self.joint_name_list = [self.model.joint(jnt_id).name for jnt_id in range(self.model.njnt)]
        self.muscle_name_list = [self.model.actuator(act_id).name for act_id in range(self.model.nu)]

        # Reference includes the current state and five future control steps.
        init_times = self.data.time + np.arange(self.future_traj_steps + 1, dtype=np.float64) * self.dt
        qpos_batch, xpos_batch, _ = self.trajectory.query_batch(init_times, self.current_traj_index)
        self.qpos_ref = qpos_batch[0]
        self.xpos_ref = xpos_batch[0]
        self.qpos_ref_future = np.zeros((self.future_traj_steps, self.model.nq))
        self.qpos_ref_future[:, :] = qpos_batch[1 : 1 + self.future_traj_steps]

        for event in self.perturbations:
            if event["duration"] <= 0 or event["start"] < 0 or len(event["force"]) != 3:
                raise ValueError("Invalid perturbation timing or world-frame force")
            if mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, event["body"]) < 0:
                raise ValueError(f"Unknown perturbation body: {event['body']}")
        self._init_senses(eye_camera_size, vision_render_interval, vision_enabled)
        proprio, reference = self._split_observation(self._observation_components())
        self.observation_space = self._sensory_space(len(proprio), len(reference))

        if self.kinematic_play:
            self.model.opt.gravity[2] = 0.0

    def seed(self, seed: int = 0) -> list[int]:
        """Compatibility API for callers that still use env.seed(seed)."""
        self._np_random, seeded = seeding.np_random(seed)
        self._np_random_seed = seeded
        return [seeded]

    @property
    def is_healthy(self) -> bool:
        """Check if the model is in a healthy state (e.g., not fallen over)."""
        qpos_diff = np.abs(self.data.qpos[3:] - self.qpos_ref[3:]).mean()
        return not qpos_diff > self.qpos_diff_th

    @property
    def terminated(self) -> bool:
        """True when the physical task fails; time limits are truncations."""
        return not self.is_healthy

    def _observation_components(self) -> dict[str, np.ndarray]:
        """Collect measured state and reference components."""
        pelvis_xpos = self.data.xpos[self.pelvis_id]
        pelvis_xpos_ref = self.xpos_ref[self.pelvis_id]
        key_xpos = (self.data.xpos[self.key_body_ids] - pelvis_xpos).ravel()
        self.key_xpos_ref = (self.xpos_ref[self.key_body_ids] - pelvis_xpos_ref).ravel()
        return {
            "qpos": self.data.qpos.copy(),
            "qvel": self.data.qvel.copy(),
            "act": self.data.act.copy(),
            "actuator_forces": (self.data.actuator_force / 1000).clip(-100, 100),
            "actuator_length": self.data.actuator_length.copy(),
            "actuator_velocity": self.data.actuator_velocity.clip(-100, 100),
            "key_xpos": key_xpos,
            "qpos_ref": self.qpos_ref,
            "qpos_ref_future": self.qpos_ref_future.flatten(),
            "key_xpos_ref": self.key_xpos_ref,
        }

    @staticmethod
    def _split_observation(components: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        proprio_keys = (
            "qpos", "qvel", "act", "actuator_forces",
            "actuator_length", "actuator_velocity", "key_xpos",
        )
        reference_keys = ("qpos_ref", "qpos_ref_future", "key_xpos_ref")
        proprio = np.concatenate([components[key] for key in proprio_keys])
        reference = np.concatenate([components[key] for key in reference_keys])
        return proprio, reference

    def _get_obs(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        components = self._observation_components()
        proprio, reference = self._split_observation(components)
        return self._sensory_obs(proprio, reference), components

    def step(
        self, action: np.ndarray
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        """Step the environment with the given action."""
        if self.kinematic_play:
            self.data.qpos[:] = self.qpos_ref
            self.data.qvel[:] = 0
            self.data.qacc[:] = 0
            action = action * 0

        impulse = np.zeros(3)
        if self.perturbations:
            for _ in range(self.frame_skip):
                self.data.xfrc_applied[:] = 0
                for event in self.perturbations:
                    if event["start"] <= self.data.time < event["start"] + event["duration"]:
                        force = np.asarray(event["force"], dtype=float)
                        self.data.body(event["body"]).xfrc_applied[:3] += force
                        impulse += force * self.model.opt.timestep
                self.do_simulation(action, 1)
            self.data.xfrc_applied[:] = 0
        else:
            self.do_simulation(action, self.frame_skip)
        reference_time = self.data.time - self._reference_start_time + self.init_time
        self._update_reference(reference_time)

        pelvis_xpos = self.data.xpos[self.pelvis_id]
        pelvis_xpos_ref = self.xpos_ref[self.pelvis_id]

        qpos_reward = self._get_qpos_reward(self.data.qpos, self.qpos_ref) * self.reward_weight["w_qpos"]
        xpos_reward = self._get_xpos_reward(
            self.data.xpos[self.key_body_ids] - pelvis_xpos,
            self.xpos_ref[self.key_body_ids] - pelvis_xpos_ref,
        ) * self.reward_weight["w_xpos"]
        pelvis_reward = self._get_pelvis_reward(pelvis_xpos, pelvis_xpos_ref) * self.reward_weight["w_pelvis"]
        energy_reward = self._get_energy_reward() * self.reward_weight["w_energy"]
        terminated = self.terminated
        healthy_reward = float(not terminated) * self.reward_weight["w_healthy"]

        reward = qpos_reward + xpos_reward + pelvis_reward + energy_reward + healthy_reward

        episode_complete = self.data.time >= self.terminate_time - 1e-9
        reference_complete = (
            self.trajectory_mode == "finite"
            and reference_time >= self.trajectory_duration - 1e-9
        )
        truncated = episode_complete or reference_complete
        if terminated:
            termination_reason = "unhealthy"
        elif episode_complete:
            termination_reason = "terminate_time"
        elif reference_complete:
            termination_reason = "reference_complete"
        else:
            termination_reason = ""

        observation, _ = self._get_obs()

        info = {
            "reward_qpos": qpos_reward,
            "reward_xpos": xpos_reward,
            "reward_pelvis": pelvis_reward,
            "reward_energy": energy_reward,
            "reward_healthy": healthy_reward,
            "total_reward": reward,
            "perturbation_impulse": impulse,
            "qpos_mae_rad": float(np.abs(self.data.qpos[3:] - self.qpos_ref[3:]).mean()),
            "reference_time": float(reference_time),
            "termination_reason": termination_reason,
        }
        error = np.abs(self.data.qpos - self.qpos_ref)
        # Joint tracking error includes non-root rotational and translational joint coordinates.
        scale = self._joint_scales[self.current_traj_index]
        joint_mae = float(error[self._other_qpos].mean())
        right_force = sum(float(self.data.sensordata[s].sum()) for name, s in self.sensor_slices.items()
                          if name.endswith("_r") and "touch" in name)
        contact = right_force > 10.0
        if contact and not self._last_right_contact and self.data.time - self._last_strike_time > 0.3:
            self._right_strikes += 1
            self._last_strike_time = float(self.data.time)
        self._last_right_contact = contact
        info.update({
            "tracking/root_translation_mae_m": float(error[self._root_translation].mean()),
            "tracking/root_rotation_mae_rad": float(error[self._root_rotation].mean()),
            "tracking/joint_mae": joint_mae,
            "tracking/joint_nmae_percent": 100.0 * joint_mae / max(scale, 1e-8),
            "tracking/root_position_error_m": float(np.linalg.norm(pelvis_xpos - pelvis_xpos_ref)),
            "episode/duration_s": float(self.data.time),
            "episode/completed": float(truncated and not terminated),
            "episode/gait_cycles": float(max(0, self._right_strikes - 1)),
            "task/perturbation_impulse_ns": float(np.linalg.norm(impulse)),
        })

        if (
            self.trajectory_mode == "repeat"
            and reference_time >= self.trajectory_duration - 1e-9
            and not terminated
            and not truncated
        ):
            info["trajectory_reset"] = True
            observation = self._restart_trajectory()

        return observation, reward, terminated, truncated, info

    def reset_model(self) -> dict[str, np.ndarray]:
        """Reset the model to a (possibly random) state from the trajectory."""

        self.data.xfrc_applied[:] = 0
        self._last_right_contact = False
        self._right_strikes = 0
        self._last_strike_time = -1.0
        self._reference_start_time = self.data.time
        self._image_cache = None
        self.data.act[:] = self.data.ctrl
        if self.trajectory.num_trajectories > 1:
            if self.kinematic_play:
                self.current_traj_index = (self.current_traj_index + 1) % self.trajectory.num_trajectories
            else:
                self.current_traj_index = self.np_random.integers(0, self.trajectory.num_trajectories)

        self.trajectory_duration, _, _ = self.trajectory.get_trajectory_properties(self.current_traj_index)

        if self.random_init:
            self.init_time = self.np_random.integers(
                0, max(1, int(self.trajectory_duration // self.dt))
            ) * self.dt
        else:
            self.init_time = 0.0

        ref_times = self.init_time + np.arange(self.future_traj_steps + 1, dtype=np.float64) * self.dt
        qpos_batch, xpos_batch, qvel_batch = self.trajectory.query_batch(ref_times, self.current_traj_index)
        self.qpos_ref = qpos_batch[0]
        self.xpos_ref = xpos_batch[0]
        init_qvel = qvel_batch[0]
        self.qpos_ref_future[:, :] = qpos_batch[1 : 1 + self.future_traj_steps]

        noise_low = -self._reset_noise_scale
        noise_high = self._reset_noise_scale
        init_qpos = self.qpos_ref + self.np_random.uniform(low=noise_low, high=noise_high, size=self.model.nq)
        init_qvel += self.np_random.uniform(low=noise_low, high=noise_high, size=self.model.nv)

        self.set_state(init_qpos, init_qvel)

        observation, _ = self._get_obs()
        return observation

    def _restart_trajectory(self) -> dict[str, np.ndarray]:
        """Restart this clip without resetting episode time or wrapper step counts."""
        episode_time = self.data.time
        ctrl = self.data.ctrl.copy()
        mujoco.mj_resetData(self.model, self.data)
        self.data.time = episode_time
        self.data.ctrl[:] = ctrl
        self.data.act[:] = self.data.ctrl
        self.init_time = 0.0
        self._reference_start_time = episode_time
        self._update_reference(0.0)
        _, _, qvel = self.trajectory.query(0.0, self.current_traj_index)
        self.set_state(self.qpos_ref.copy(), qvel)
        self._image_cache = None
        return self._get_obs()[0]

    def _get_qpos_reward(
        self, qpos_real: np.ndarray, qpos_ref: np.ndarray
    ) -> float:
        """Reward for matching reference joint positions (excluding pelvis translation)."""
        return -np.sum(np.square(qpos_real[3:] - qpos_ref[3:]))

    def _get_xpos_reward(
        self, xpos_real: np.ndarray, xpos_ref: np.ndarray
    ) -> float:
        """Reward for matching reference body positions."""
        return -np.sum(np.square(xpos_real - xpos_ref))

    def _get_energy_reward(self) -> float:
        """Penalty for high muscle force (energy usage)."""
        return np.sum(self.data.actuator_force) / self.model.na

    def _get_pelvis_reward(
        self, pelvis_pos: np.ndarray, pelvis_pos_ref: np.ndarray
    ) -> float:
        """Reward for matching reference pelvis position."""
        return -np.sum(np.square(pelvis_pos - pelvis_pos_ref))

    def _initialize_simulation(self) -> tuple[mujoco.MjModel, mujoco.MjData]:
        if self.scene is None:
            return super()._initialize_simulation()
        model = load_task_model(self.fullpath, self.scene, self.scene_kwargs)
        model.vis.global_.offwidth = max(model.vis.global_.offwidth, self.width)
        model.vis.global_.offheight = max(model.vis.global_.offheight, self.height)
        return model, mujoco.MjData(model)

    def _update_reference(self, time: float) -> None:
        times = time + np.arange(self.future_traj_steps + 1) * self.dt
        qpos, xpos, _ = self.trajectory.query_batch(times, self.current_traj_index)
        self.qpos_ref, self.xpos_ref = qpos[0], xpos[0]
        self.qpos_ref_future[:] = qpos[1:]
