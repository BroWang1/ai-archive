from gymnasium.envs.registration import register

register(id="msgym/LocomotionEnv-v1", entry_point="msgym.envs:LocomotionEnvV1", max_episode_steps=3000)
register(id="msgym/ManipulationEnv-v1", entry_point="msgym.envs:ManipulationEnvV1", max_episode_steps=200)
