---
license: apache-2.0
language:
- en
tags:
- mujoco
- reinforcement-learning
- musculoskeletal
- sensorimotor
---
# MS-Human-700: Whole-body Human Musculoskeletal Model

<p align="center">
  <a href="https://lnsgroup.cc/research/MS-Human">Project Page</a> |
  <a href="https://github.com/LNSGroup/MS-Human-700">Model Repository</a> |
  <a href="https://github.com/LNSGroup/msgym">msgym</a>
</p>

<p align="center">
  <img src="pictures/ms_human_render_front.png" width="45%" alt="MS-Human-700 musculoskeletal model">
</p>

## Overview

**MS-Human-700** is a whole-body human musculoskeletal model with anatomically detailed bodies, joints and 700 muscle–tendon units. This repository combines MuJoCo models and assets, Gymnasium environments, DynSyn-SAC training source and motion references for locomotion and right-hand manipulation.

DynSyn-SAC maps sensory features to muscle-group actions and expands them into individual muscle excitations through a learned synergy layer.

This release includes task environments, training code, and reference motions. Trained policy checkpoints and evaluation results are not included.

Related papers:

- [MS-Human-700 (ICRA 2024)](https://arxiv.org/abs/2312.05473)
- [DynSyn (ICML 2024)](https://arxiv.org/abs/2407.11472)

## Models and tasks

Model XML files and their shared assets are in `msgym/MS-Human-700/`. Open an entry XML with MuJoCo's `simulate` viewer to inspect the model.

| Model entry                       | Tasks                                  | Muscle actuators |
| --------------------------------- | -------------------------------------- | ---------------- |
| `MS-Human-700.xml`              | Walking, stairs, perturbation recovery | 700              |
| `MS-Human-700-FarmerWalk.xml`   | Walking with two fixed 5 kg dumbbells      | 700              |
| `MS-Human-700-Manipulation.xml` | Vision-guided right-hand manipulation  | 81               |

| Gymnasium environment        | Task configs in`DynSyn-SAC/configs/`                                                                 |
| ---------------------------- | ------------------------------------------------------------------------------------------------------ |
| `msgym/LocomotionEnv-v1`   | `tracking_walk.json`, `tracking_stairs.json`, `tracking_farmer.json`, `tracking_recovery.json` |
| `msgym/ManipulationEnv-v1` | `vision/manipulation_vision.json`                                                                    |

## Sensory observations

Environments return a dictionary with `proprio`, `sensors` and `reference`, plus channel-first RGB `left_eye` and `right_eye` when vision is enabled.

- **Full body:** proprioception, vestibular and tactile channels.
- **Manipulation:** proprioception, vestibular and tactile channels.
- **Stereo vision:** enabled in the supplied manipulation config and optional for locomotion. The manipulation environment also supports a nonvisual mode that includes object and target poses in the task reference.

For tracking, `vision_enabled=false` skips image rendering and the visual encoder; `StateSACPolicy` consumes the vector observations. Visual configs use `VisionSACPolicy`. Tracking renders 32x32 stereo images every 20 control steps; manipulation renders 128x128 images every five steps (`eye_camera_size`, `vision_render_interval`). Configs otherwise share task parameters and training budgets. Visual training uses a shared, frozen ImageNet ResNet-18 in evaluation mode, with torchvision's image preprocessing and 512-dimensional pooled features per eye, before the classification head.

## Installation

Requires Python 3.12 or newer. From the downloaded repository directory:

```bash
uv venv --python 3.12
uv pip install -e ".[dynsyn]"
```

Models are bundled with the package; no separate model checkout is needed. On headless Linux systems, set `MUJOCO_GL=egl` for offscreen rendering.

## Training

```bash
# Walking with stereo vision.
uv run --no-sync python DynSyn-SAC/SB3-Scripts/train.py -f DynSyn-SAC/configs/vision/tracking_walk.json

# Walking with vector observations only.
uv run --no-sync python DynSyn-SAC/SB3-Scripts/train.py -f DynSyn-SAC/configs/tracking_walk.json

# Vision-guided right-hand manipulation.
uv run --no-sync python DynSyn-SAC/SB3-Scripts/train.py -f DynSyn-SAC/configs/vision/manipulation_vision.json
```

Use the other task configs in the table above for stairs, fixed-load walking and recovery. Training outputs are written under `logs/`.

## Evaluation

```bash
uv run --no-sync python DynSyn-SAC/SB3-Scripts/eval.py --log_path <training_run_directory> --num_episodes 5
```

Evaluation uses deterministic actions and the same observation processing as training. By default, it loads `checkpoint/best_model.zip` with its matching normalization statistics and writes `evaluation.json`. Add `--video` to record a video.

## License

Code and models are released under the [Apache-2.0 License](LICENSE).

## Citation

If you use MS-Human-700 or msgym, please cite:

```bibtex
@inproceedings{zuo2024self,
  title={Self model for embodied intelligence: Modeling full-body human musculoskeletal system and locomotion control with hierarchical low-dimensional representation},
  author={Zuo, Chenhui and He, Kaibo and Shao, Jing and Sui, Yanan},
  booktitle={2024 IEEE International Conference on Robotics and Automation (ICRA)},
  pages={13062--13069},
  year={2024},
  organization={IEEE}
}
```
