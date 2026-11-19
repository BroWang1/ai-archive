---
license: apache-2.0
base_model: Qwen/Qwen3.5-4B
library_name: peft
pipeline_tag: video-text-to-text
language:
- en
tags:
- ai-generated-video-detection
- video-forensics
- omni-modal
- audio-visual
- agent
- multi-agent
- tool-use
- reinforcement-learning
- lora
- qwen3.5
---

# WeVisForensics: Self-Evolving Agent for Omni AI-Generated Video Detection

**Paper:** [WeVisForensics: Self-Evolving Agent for Omni AI-Generated Video Detection](https://arxiv.org/abs/2611.21373) | **Code:** [Tencent/WeVisForensics](https://github.com/Tencent/WeVisForensics) | **Project Page:** [WeVisForensics](https://tencent.github.io/WeVisForensics)

**WeVisForensics** is a self-evolving agentic detector of AI-generated video. A main investigator agent coordinates forensic inspector sub-agents for visual appearance, physical consistency, common sense, on-screen text, speech content, and voice profile. This repository releases the five LoRA adapters of WeVisForensics-4B, trained with DTPO on top of Qwen3.5-4B.

## Released Adapters

| Adapter | Purpose |
| --- | --- |
| `main` | Main investigator agent |
| `visual_appearance` | Visual-appearance inspector |
| `physical_consistency` | Physical-consistency inspector |
| `common_sense` | Common-sense inspector |
| `ocr_consistency` | On-screen text inspector |

All five adapters are rank 64 and alpha 128 on [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), in BF16. `skill_card.json` holds the inspector skill cards used at inference.

## Quick Start

Clone the [code repository](https://github.com/Tencent/WeVisForensics), then deploy in one of three ways.

**Multi-GPU.** Merge each adapter into the base model, then point the inference config at the merged model and at the bundled `skill_card.json`:

```bash
python scripts/merge_lora.py --base Qwen/Qwen3.5-4B --adapters <local copy of this repo> --output <merged dir>
```

**Single GPU.** Serve all five adapters from one vLLM process without merging:

```bash
BASE=Qwen/Qwen3.5-4B ADAPTERS=<local copy of this repo> \
  GPU_MEMORY_UTILIZATION=0.66 bash scripts/serve_lora.sh
```

**Transformers.** Run the whole agent in-process on one GPU with at least 24 GB, without vLLM. This backs the Gradio demo and the Hugging Face Space:

```bash
pip install -r demo/requirements.txt "gradio>=6.0"
WVF_ADAPTERS=tencent/WeVisForensics python demo/app.py
```

See the repository README for the full commands.

## Intended Use

The release is intended for research in AI-generated video forensics. It is not intended for malicious use or for making autonomous high-impact decisions about individuals.

## License

Unless otherwise noted, the adapters and Tencent-authored code are released under the Apache License 2.0. Speech, speaker, and OCR third-party models keep their own licenses.

## Citation

If WeVisForensics is helpful to your work, please consider giving us a ⭐ and citing:

```bibtex
@misc{du2026wevisforensicsselfevolvingagentomni,
      title={WeVisForensics: Self-Evolving Agent for Omni AI-Generated Video Detection}, 
      author={Yipeng Du and Yuxi Li and Ying Zhang and Chong Sun and Chen Li and Jing Lyu and Ying Tai},
      year={2026},
      eprint={2611.21373},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2611.21373}, 
}
```
