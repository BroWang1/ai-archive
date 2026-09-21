---
license: mit
base_model:
- google/videoprism-large-f8r288
- google/t5gemma-l-l-ul2-it
tags:
- audio
- music
- generation
- video2audio
pipeline_tag: text-to-audio
---
<h1 align="center">PrismAudio</h1>
<p align="center">
  <img src="https://img.shields.io/badge/ICLR 2026-Main Conference-blue.svg" alt="ICLR 2026"/>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2511.18833">
    <img src="https://img.shields.io/badge/arXiv-2511.18833-b31b1b.svg" alt="arXiv"/>
  </a>
  &nbsp;
  <a href="http://prismaudio-project.github.io/">
    <img src="https://img.shields.io/badge/Online%20Demo-🌐-blue" alt="Online Demo"/>
  </a>
  &nbsp;
  <a href="https://github.com/FunAudioLLM/ThinkSound/tree/prismaudio">
    <img src="https://img.shields.io/badge/GitHub-Code-black?logo=github" alt="GitHub"/>
  </a>
  &nbsp;
  <a href="https://huggingface.co/spaces/FunAudioLLM/PrismAudio">
    <img src="https://img.shields.io/badge/HuggingFace-Spaces-orange?logo=huggingface" alt="Hugging Face"/>
  </a>
  &nbsp;
  <a href="https://www.modelscope.cn/studios/iic/PrismAudio">
    <img src="https://img.shields.io/badge/ModelScope-在线体验-green" alt="ModelScope"/>
  </a>
</p>

---

**PrismAudio** is the first framework to integrate reinforcement learning into video-to-audio (V2A) generation, equipped with a dedicated Chain-of-Thought (CoT) planning mechanism. Building on the pioneering CoT-based V2A framework of ThinkSound, PrismAudio further decomposes single-step reasoning into four specialized CoT modules — **semantic**, **temporal**, **aesthetic**, and **spatial** — each with targeted reward functions, enabling multi-dimensional RL optimization that simultaneously improves reasoning across all perceptual dimensions.
---

## Quick Start

For full training and inference details, please refer to the [ThinkSound `prismaudio` branch](https://github.com/FunAudioLLM/ThinkSound/tree/prismaudio).
```bash
git clone -b prismaudio https://github.com/liuhuadai/ThinkSound.git
cd ThinkSound

conda create -n prismaudio python=3.10
conda activate prismaudio
chmod +x scripts/PrismAudio/setup/build_env.sh
./scripts/PrismAudio/setup/build_env.sh

# Download pretrained weights to ckpts/
# From Hugging Face:  https://huggingface.co/FunAudioLLM/PrismAudio
# From ModelScope:    https://www.modelscope.cn/models/iic/PrismAudio
git lfs install
git clone https://huggingface.co/FunAudioLLM/PrismAudio ckpts
```

---


## License

This project is released under the [MIT License](https://opensource.org/licenses/MIT).

> **Note:** The code, model weights, and datasets are intended for **research and educational purposes only**. Commercial use is not permitted without explicit authorization from the authors.

---


## Citation

If you find PrismAudio useful in your research, please consider citing our papers:


```bibtex
@misc{liu2025thinksoundchainofthoughtreasoningmultimodal,
      title={ThinkSound: Chain-of-Thought Reasoning in Multimodal Large Language Models for Audio Generation and Editing}, 
      author={Huadai Liu and Jialei Wang and Kaicheng Luo and Wen Wang and Qian Chen and Zhou Zhao and Wei Xue},
      year={2025},
      eprint={2506.21448},
      archivePrefix={arXiv},
      primaryClass={eess.AS},
      url={https://arxiv.org/abs/2506.21448}, 
}

@misc{liu2025prismaudiodecomposedchainofthoughtsmultidimensional,
        title={PrismAudio: Decomposed Chain-of-Thoughts and Multi-dimensional Rewards for Video-to-Audio Generation}, 
        author={Huadai Liu and Kaicheng Luo and Wen Wang and Qian Chen and Peiwen Sun and Rongjie Huang and Xiangang Li and Jieping Ye and Wei Xue},
        year={2025},
        eprint={2511.18833},
        archivePrefix={arXiv},
        primaryClass={cs.SD},
        url={https://arxiv.org/abs/2511.18833}, 
}
```

---
## Contact

If you have any questions or suggestions, feel free to [open an issue](https://github.com/liuhuadai/ThinkSound/issues)