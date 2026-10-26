"""Stereo and vector-only encoders for the two sensory training settings."""
import gymnasium as gym
import numpy as np
import torch
from torch import nn
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.utils import get_device
from stable_baselines3.common.vec_env import VecEnvWrapper
from DynSyn.SAC_DynSyn import SACPolicy_DynSyn


class FrozenResNet18VecWrapper(VecEnvWrapper):
    """Encode stereo images once, before observations enter the replay buffer."""

    def __init__(self, venv, device='auto'):
        from torchvision.models import ResNet18_Weights, resnet18

        self.device = get_device(device)
        weights = ResNet18_Weights.IMAGENET1K_V1
        self.resnet18 = resnet18(weights=weights).to(self.device).eval()
        feature_dim = self.resnet18.fc.in_features
        self.resnet18.fc = nn.Identity()
        self.resnet18.requires_grad_(False)
        self.preprocess_transformer = weights.transforms().to(self.device)
        self.image_keys = ('left_eye', 'right_eye')
        spaces = dict(venv.observation_space.spaces)
        for key in self.image_keys:
            spaces[key] = gym.spaces.Box(
                -np.inf, np.inf, shape=(feature_dim,), dtype=np.float32
            )
        super().__init__(venv, observation_space=gym.spaces.Dict(spaces))

    def _encode_images(self, observations):
        images = np.concatenate([observations[key] for key in self.image_keys])
        with torch.no_grad():
            images = torch.as_tensor(images, device=self.device)
            features = self.resnet18(self.preprocess_transformer(images)).cpu().numpy()
        return dict(zip(self.image_keys, np.split(features, len(self.image_keys))))

    def reset(self):
        observations = self.venv.reset()
        return {**observations, **self._encode_images(observations)}

    def step_wait(self):
        observations, rewards, dones, infos = self.venv.step_wait()
        terminal_infos = [info for done, info in zip(dones, infos) if done]
        images = observations
        if terminal_infos:
            images = {
                key: np.concatenate([
                    observations[key],
                    np.stack([info['terminal_observation'][key] for info in terminal_infos]),
                ])
                for key in self.image_keys
            }
        features = self._encode_images(images)
        observations = {**observations, **{
            key: features[key][:self.num_envs] for key in self.image_keys
        }}
        for index, info in enumerate(terminal_infos, start=self.num_envs):
            info['terminal_observation'] = {**info['terminal_observation'], **{
                key: features[key][index] for key in self.image_keys
            }}
        return observations, rewards, dones, infos


class StereoResNetExtractor(BaseFeaturesExtractor):
    """Combine frozen visual features with a trainable vector projection."""

    def __init__(self, observation_space):
        vision_dim = sum(observation_space[key].shape[0] for key in ('left_eye', 'right_eye'))
        super().__init__(observation_space, features_dim=vision_dim + 128)
        self.state_keys = ('proprio', 'sensors', 'reference')
        state_dim = sum(observation_space[k].shape[0] for k in self.state_keys)
        self.proprio = nn.Sequential(nn.Linear(state_dim, 128), nn.ReLU())

    def forward(self, obs):
        return torch.cat([obs['left_eye'], obs['right_eye'],
                          self.proprio(torch.cat([obs[k] for k in self.state_keys], dim=-1))], dim=-1)


class VisionSACPolicy(SACPolicy_DynSyn):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('features_extractor_class', StereoResNetExtractor)
        super().__init__(*args, **kwargs)


class StateFeaturesExtractor(BaseFeaturesExtractor):
    """Encode proprioception, physical sensors and task reference without images."""
    def __init__(self, observation_space):
        super().__init__(observation_space, features_dim=128)
        self.state_keys = ('proprio', 'sensors', 'reference')
        state_dim = sum(observation_space[k].shape[0] for k in self.state_keys)
        self.state = nn.Sequential(nn.Linear(state_dim, 128), nn.ReLU())

    def forward(self, obs):
        return self.state(torch.cat([obs[k] for k in self.state_keys], dim=-1))


class StateSACPolicy(SACPolicy_DynSyn):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('features_extractor_class', StateFeaturesExtractor)
        super().__init__(*args, **kwargs)
