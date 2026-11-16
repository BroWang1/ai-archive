---
license: other
license_name: minimax-h3-community-license
license_link: LICENSE
library_name: duo-world-model
tags:
- video-generation
- audio-generation
- world-model
---

<div align="center">

<img src="./assets/duo-logo.svg" width="38%" alt="Duo" />

**Duo-1.0-distill**

**A Reciprocal World Model for Full-Duplex Interaction**

[![arXiv](https://img.shields.io/badge/arXiv-2611.15131-B31B1B?logo=arxiv&logoColor=white&labelColor=555)](https://arxiv.org/abs/2611.15131)
[![Homepage](https://img.shields.io/badge/-Homepage-0A66C2?logo=googlechrome&logoColor=white&labelColor=555)](https://duo-v1.github.io/)
[![Models](https://img.shields.io/badge/-Model%20Collection-FFD21E?logo=huggingface&logoColor=white&labelColor=555)](https://huggingface.co/collections/inclusionAI/duo-v1)
[![ModelScope](https://img.shields.io/badge/-ModelScope-624AFF?logo=modelscope&logoColor=white&labelColor=555)](https://www.modelscope.cn/collections/inclusionAI/Duo-v1)
[![Code](https://img.shields.io/badge/-Code-181717?logo=github&logoColor=white&labelColor=555)](https://github.com/inclusionAI/Duo)

</div>

## Model Overview

Duo is a full-duplex multimodal world model for real-time audio-visual interaction. This repository contains the four-step distilled Realization weights for Duo 1.0.

| Field | Value |
| --- | --- |
| Version | Duo 1.0 |
| Variant | Four-step distilled Realization |
| Package | Realization overlay |
| Realization format | PyTorch Distributed Checkpoint (DCP) |
| Base dependency | `inclusionAI/Duo-1.0-causal-base` |
| Default sampler | Euler, 4 steps, flow shift 5.0 |

## Usage

Download the complete Duo 1.0 causal-base bundle, then overlay these Realization weights into the same directory:

```bash
hf download inclusionAI/Duo-1.0-causal-base --local-dir weights
hf download inclusionAI/Duo-1.0-distill --local-dir weights
```

The shared Intent, codecs, speech models, and Realization backbone are supplied by the causal-base bundle. Runtime integrations can use `realization/complete.json` to identify the distilled model family.

For code, configuration, and runtime-specific integration instructions, see [inclusionAI/Duo](https://github.com/inclusionAI/Duo).

## License

These weights were initialized from MiniMax H3 and subsequently trained by the Duo team. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE) for the applicable terms.
