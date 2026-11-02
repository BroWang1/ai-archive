---
license: other
library_name: transformers
base_model: Qwen/Qwen3.5-9B
pipeline_tag: any-to-any
tags:
  - video-editing
  - agent
  - tool-use
  - long-horizon
  - reinforcement-learning
  - qwen3.5
---

# WeVisCut: A Long-Horizon Tool Agent for Edited Videos

**WeVisCut** is a 9B tool-using agent that turns knowledge articles or narration scripts into multi-minute edited videos. At each step, it reads the current editing state and selects one of 12 tools for planning, narration, asset retrieval, composition, inspection, or repair. It is not a standalone text-to-video model; use it with the [WeVisCut runtime](https://github.com/Tencent/WeVisCut), which executes the model's tool calls.

## Deploy

Requirements: Python 3.11 or later and an NVIDIA GPU with about 24 GB of memory for bf16 inference. Install a PyTorch build compatible with your CUDA version before the GPU requirements below. The setup script installs Node.js, FFmpeg, and the renderer.

```bash
git clone https://github.com/Tencent/WeVisCut.git
cd WeVisCut
pip install -r requirements.txt
pip install -r requirements-gpu.txt
bash scripts/setup_external_tools.sh
pip install -U "huggingface_hub[cli]"
hf download tencent/WeVisCut --local-dir checkpoints/weviscut-9b
bash run_studio.sh
```

Open `http://<host>:8081/` to use the Studio. For UI-only mode without loading model weights, run `bash run_studio.sh --no-model`.

## Model

The policy is based on Qwen3.5-9B and is trained on executable editing trajectories. Its runtime provides an editable timeline with pause/resume, manual and chat-based revisions, per-shot rerendering, and version rollback. Video quality depends on the configured retrieval, TTS, and rendering services and available templates.

## Intended Use and Limitations

WeVisCut is intended for research and production assistance in long-form video editing. It does not guarantee factual accuracy or production quality; review generated narration and video before publication. The model weights require the WeVisCut tool environment to produce a video.

## Citation

```bibtex
@misc{mu2026weviscuteditingroomagent,
      title={WeVisCut: The Whole Editing Room in One Agent From Narration to Long-Form Video}, 
      author={Chenyu Mu and Wenming Weng and Qinrui Wang and Xingsong Ye and Hao Yu and Jun He and Chong Sun and Chen Li and Jing Lyu and Erkun Yang and Cheng Deng},
      year={2026},
      eprint={2610.38352},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2610.38352}, 
}
```

## License

The WeVisCut code is released under the [Apache License 2.0](https://github.com/Tencent/WeVisCut/blob/main/LICENSE). Model weights and third-party components are subject to their respective license terms.
