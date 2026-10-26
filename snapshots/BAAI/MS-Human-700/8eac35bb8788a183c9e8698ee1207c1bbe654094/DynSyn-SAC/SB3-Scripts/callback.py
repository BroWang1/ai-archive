import os
from typing import Any, Optional
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback
from utils import record_video

class SaveConfigToTensorboardCallback(BaseCallback):
    """Log hyperparameters and config to TensorBoard at training start."""

    def __init__(
        self,
        log_dir: str,
        config_str: str,
        verbose: int = 1,
    ) -> None:
        super().__init__(verbose)
        self.log_dir = log_dir
        self.config_str = config_str

    def _on_training_start(self) -> None:
        self.logger.record(
            "configs",
            self.config_str.replace("\n", "<br>")
        )
        
    def add_environment_info(self, env_info: str) -> None:
        """Log environment info string to TensorBoard."""
        self.logger.record("env_info", env_info)

    def _on_step(self) -> bool:
        return True


class SaveVecNormalizeOnBestCallback(BaseCallback):
    """Save VecNormalize stats when EvalCallback finds a new best model."""

    def __init__(self, save_path: str, verbose: int = 0) -> None:
        super().__init__(verbose=verbose)
        self.save_path = save_path

    def _on_step(self) -> bool:
        vec_norm = self.model.get_vec_normalize_env()
        if vec_norm is not None:
            vec_norm.save(self.save_path)
            if self.verbose >= 1:
                print(f"Saved VecNormalize to {self.save_path}")
        return True

class VideoRecorderCallback(BaseCallback):
    """Record and save videos at a fixed step frequency during training."""

    def __init__(
        self,
        args: Any,
        record_freq: int,
        video_dir: str,
        video_ep_num: int,
        env_nums: int = 4,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)

        self.record_freq = record_freq
        self.video_dir = video_dir
        self.video_ep_num = video_ep_num
        self.args = args
        self.env_nums = env_nums

    def _on_step(self) -> bool:
        if self.n_calls % self.record_freq == 0:

            record_video(
                self.training_env,
                self.model,
                self.args,
                self.video_dir,
                self.video_ep_num,
                name_prefix=f"{self.args.agent}-{self.num_timesteps}"
            )

        return True

class TensorboardCallback(BaseCallback):
    """Aggregate every transition, separating task, tracking and reward terms."""

    def __init__(self, info_keywords=None, reward_freq=1000, verbose=0):
        super().__init__(verbose)
        self.frequency = max(1, reward_freq)
        self.next_dump = self.frequency
        self.sums = {}
        self.counts = {}

    def _on_step(self):
        for info in self.locals['infos']:
            for key, value in info.items():
                if not isinstance(value, (int, float, bool, np.number)):
                    continue
                if '/' in key:
                    tag = key
                elif key.startswith('reward') or key == 'total_reward':
                    tag = 'reward/' + key
                else:
                    continue
                # Episode duration/completion/cycle counts are terminal metrics.
                if key.startswith('episode/'):
                    continue
                self.sums[tag] = self.sums.get(tag, 0.0) + float(value)
                self.counts[tag] = self.counts.get(tag, 0) + 1
        for done, info in zip(self.locals['dones'], self.locals['infos']):
            if done:
                for key, value in info.items():
                    if key.startswith('episode/'):
                        self.sums[key] = self.sums.get(key, 0.0) + float(value)
                        self.counts[key] = self.counts.get(key, 0) + 1
        if self.num_timesteps >= self.next_dump:
            for key in self.sums:
                self.logger.record(key, self.sums[key] / self.counts[key])
            self.logger.record('train/gradient_updates', self.model._n_updates)
            self.logger.record('train/updates_per_transition', self.model._n_updates / max(1, self.num_timesteps))
            self.logger.dump(self.num_timesteps)
            self.sums.clear()
            self.counts.clear()
            self.next_dump = self.num_timesteps + self.frequency
        return True


def walking_passing_fraction(episodes, criteria):
    good = [
        row.get("episode/completed", 0) == 1
        and row.get("episode/gait_cycles", 0) >= criteria["min_gait_cycles"]
        and row["tracking/joint_nmae_percent"] < criteria["joint_nmae_percent"]
        and row["tracking/root_position_error_m"] < criteria["root_position_error_m"]
        and row["tracking/root_rotation_mae_rad"] < criteria["root_rotation_mae_rad"]
        for row in episodes
    ]
    return float(np.mean(good))


class TaskEvaluationCallback(BaseCallback):
    """Evaluate rollouts, save paired model and normalization checkpoints, and optionally stop training when the configured criteria are met."""

    def __init__(self, env, frequency, checkpoint_dir, episodes=5, acceptance=None):
        super().__init__()
        self.env, self.frequency = env, frequency
        self.checkpoint_dir = checkpoint_dir
        self.episodes, self.acceptance = episodes, acceptance
        self.next_eval = frequency
        self.best_reward = -np.inf
        self.consecutive_passes = 0

    def _on_step(self):
        if self.num_timesteps < self.next_eval:
            return True
        import json
        from pathlib import Path
        from stable_baselines3.common.vec_env import sync_envs_normalization
        from eval import evaluate_episodes
        sync_envs_normalization(self.training_env, self.env)
        result = evaluate_episodes(self.model, self.env, self.episodes)
        for key, value in result['mean'].items():
            self.logger.record('eval/' + key, value)
        self.logger.dump(self.num_timesteps)
        norm = self.model.get_vec_normalize_env()
        if result['mean']['reward'] > self.best_reward:
            self.best_reward = result['mean']['reward']
            self.model.save(os.path.join(self.checkpoint_dir, 'best_model.zip'))
            if norm:
                norm.save(os.path.join(self.checkpoint_dir, 'best_env.zip'))
        result['timesteps'] = self.num_timesteps
        result['passed'] = False
        if self.acceptance:
            a = self.acceptance
            result['passing_fraction'] = walking_passing_fraction(result['episodes'], a)
            passed = result['passing_fraction'] >= a['passing_fraction']
            self.consecutive_passes = self.consecutive_passes + 1 if passed else 0
            result['passed'] = self.consecutive_passes >= a.get('consecutive_evaluations', 2)
            result['criteria'] = a
        path = Path(self.checkpoint_dir).parent / 'assessment.json'
        path.write_text(json.dumps(result, indent=2))
        with path.with_name('assessment-history.jsonl').open('a') as stream:
            stream.write(json.dumps(result) + '\n')
        self.next_eval = self.num_timesteps + self.frequency
        return not result['passed']
