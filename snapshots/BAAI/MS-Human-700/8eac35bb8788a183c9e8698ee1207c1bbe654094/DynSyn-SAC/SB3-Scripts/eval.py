"""Deterministic evaluation using the same observation pipeline as training."""
import argparse
import json
from pathlib import Path
import numpy as np
import stable_baselines3 as sb3
import sb3_contrib
from stable_baselines3.common.vec_env import VecNormalize, VecVideoRecorder
from DynSyn import SAC_DynSyn
from utils import create_vec_env, normalization_path


def evaluate_episodes(model, env, episodes=5, seed=1000):
    records = []
    for episode in range(episodes):
        env.seed(seed + episode)
        obs = env.reset()
        samples = {}
        total_reward = 0.0
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, infos = env.step(action)
            total_reward += float(reward[0])
            info = infos[0]
            for key, value in info.items():
                if key.startswith(('tracking/', 'task/')) and np.isscalar(value):
                    samples.setdefault(key, []).append(float(value))
            if done[0]:
                record = {key: float(np.mean(values)) for key, values in samples.items()}
                record.update({key: float(value) for key, value in info.items() if key.startswith('episode/')})
                record['task/final_success'] = float(info.get('task/success', info.get('episode/completed', 0)))
                record['reward'] = total_reward
                records.append(record)
                break
    means = {key: float(np.mean([row[key] for row in records])) for key in records[0]}
    return {'episodes': records, 'mean': means}


def evaluate(args):
    log_path = Path(args.log_path)
    configs = [json.loads(path.read_text()) for path in log_path.glob('*.json')]
    configs = [config for config in configs if 'env_name' in config and 'agent_kwargs' in config]
    if len(configs) != 1:
        raise ValueError('Expected one training config in log directory')
    config = configs[0]
    checkpoint = Path(args.model_path) if args.model_path else log_path / 'checkpoint/best_model.zip'
    if args.norm_path:
        norm_path = Path(args.norm_path)
    else:
        norm_path = normalization_path(checkpoint)
    env = create_vec_env(config['env_name'], config['single_env_kwargs'], 1,
                         wrapper_list=config['wrapper_list'], seed=args.seed,
                         render_mode='rgb_array' if args.video else None, vec_env_type='dummy')
    try:
        if config['vec_normalize']['is_norm']:
            env = VecNormalize.load(str(norm_path), env)
            env.training = False
            env.norm_reward = False
        if args.video:
            env = VecVideoRecorder(env, str(log_path / 'eval_video'), lambda step: step == 0,
                                   video_length=1000, name_prefix=checkpoint.stem)
        agent = SAC_DynSyn if config["agent"] == "SAC_DynSyn" else getattr(
            sb3, config["agent"], getattr(sb3_contrib, config["agent"], None))
        if agent is None:
            raise ValueError(f"Unknown agent: {config['agent']}")
        model = agent.load(str(checkpoint), env=env)
        result = evaluate_episodes(model, env, args.num_episodes, args.seed)
        result.update(checkpoint=str(checkpoint), normalization=str(norm_path), timesteps=model.num_timesteps)
        output = Path(args.output) if args.output else log_path / 'evaluation.json'
        output.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return result
    finally:
        env.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', '-f', required=True)
    parser.add_argument('--model_path', '-m')
    parser.add_argument('--norm_path')
    parser.add_argument('--num_episodes', '-n', type=int, default=5)
    parser.add_argument('--seed', type=int, default=1000)
    parser.add_argument('--output')
    parser.add_argument('--video', action='store_true')
    evaluate(parser.parse_args())
