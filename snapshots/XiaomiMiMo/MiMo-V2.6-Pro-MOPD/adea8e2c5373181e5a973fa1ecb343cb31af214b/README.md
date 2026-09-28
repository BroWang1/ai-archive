---
license: mit
language:
- en
- zh
tags:
- text-generation
- multimodal
- vision-language
- audio
- agent
- video-understanding
- long-context
- mimo_v2
- transformers
library_name: transformers
---

<br/><br/>
<div align="center">
  <picture>
    <source srcset="https://github.com/XiaomiMiMo/MiMo/raw/main/figures/Xiaomi_MiMo_darkmode.png?raw=true" media="(prefers-color-scheme: dark)">
    <img src="https://github.com/XiaomiMiMo/MiMo/raw/main/figures/Xiaomi_MiMo.png?raw=true" width="60%" alt="Xiaomi-MiMo" />
  </picture>
</div>

<br/>

<div align="center" style="line-height: 1;">
  |
  <a href="https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-MOPD" target="_blank">🤗 HuggingFace</a>
  &nbsp;|
  <a href="https://mimo.xiaomi.com/mimo-v2-6" target="_blank">📰 Blog </a>
  &nbsp;|
  <a href="https://platform.xiaomimimo.com" target="_blank">🎨 Xiaomi MiMo API Platform </a>
  &nbsp;|
  <a href="https://aistudio.xiaomimimo.com" target="_blank">🗨Xiaomi MiMo Studio </a>
  &nbsp;|
  <a href="https://mimo.xiaomimimo.com/desktop/" target="_blank">💻 Xiaomi MiMo Desktop </a>
  &nbsp;|
</div>

<br/>

<div align="center" style="line-height: 1.2;">
  <strong>Community</strong><br/>
  <a href="https://huggingface.co/XiaomiMiMo/MiMo-V2.5-Pro/blob/main/assets/wechat.jpg" target="_blank">WeChat Group</a>
  &nbsp;|&nbsp;
  <a href="https://discord.gg/kKC2kNnQEX" target="_blank">Discord</a>
  &nbsp;|&nbsp;
  <a href="https://t.me/+3T-I0pekOVIyNDBl" target="_blank">Telegram</a>
  &nbsp;|&nbsp;
  <a href="https://www.reddit.com/r/XiaomiMiMo_Official/" target="_blank">Reddit</a>
</div>

# MiMo-V2.6-Pro-MOPD

<p><a href="https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL/blob/main/MiMo_V2_6_technical_report.pdf"><b>Technical Report</b></a></p>

> [!IMPORTANT]
> **This is the MOPD upgrade of the [MiMo-V2.6-Pro-RL](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL) checkpoint.**
>
> - **MOPD2** (👉 [**Technical Report §5.6**](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL/blob/main/MiMo_V2_6_technical_report.pdf))<br>
>   Fuses several domain-specialized teachers into one model, extending to domains where reliable training-time verification is hard, such as long-horizon game development, scientific research and embodied intelligence.
> - **Diagnosing and Mitigating Tool-Call Repetition in MiMo-V2.6** (👉 [**Technical Blog**](https://mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition))<br>
>   An easy-to-overlook failure mode in which the model keeps issuing the same or highly similar tool calls, appearing busy while making no progress. Nothing fails outright, so it tends to go unnoticed. The MOPD stage handles it efficiently, with a short specialized-teacher run that converges quickly.


## 1. Introduction

### How MOPD2 works

MOPD2 distills several domain-specialized teachers into the student on-policy. The teachers fall into two families: **mixRL teachers**, trained on verifiable tasks, and **SFT teachers**, trained on synthetic demonstrations for open-domain tasks where a reliable reward is hard to design. Three streams contribute to a single update:

- **Standard MOPD**: mixRL teachers supervise full autonomous rollouts.
- **Teacher-Prefix OPD**: prefixes come from teacher rollouts. A trajectory with *k* assistant turns yields *k* history prefixes, one per turn. The model generates a single new turn from each, and the teacher scores it against the same history.
- **SFT-Prefix OPD**: prefixes come from SFT demonstrations. The demonstration supplies the history, and the model writes its own continuation.

Method details are in [Technical Report §5.6](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL/blob/main/MiMo_V2_6_technical_report.pdf).

### Tool-call repetition

Following the release of MiMo-V2.6, tool-call repetition emerged as one of the most noticeable issues in agentic settings: the model would sometimes issue the same or highly similar tool calls repeatedly, consuming time and context without making progress. This checkpoint mitigates it.

![Tool-call repetition rate on MiMo-V2.6-Pro before and after MOPD](assets/mimo-repetition-rate-pro-en.png)

*Figure: response-level repetition rate on MiMo-V2.6-Pro, RL-stage versus this checkpoint, across context lengths and agent harnesses.*

The [technical blog](https://mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition) has the full diagnosis. The fix is lightweight to train: a short specialized-teacher run that folds into the normal MOPD pass.


## Model Summary

- **Architecture**: Sparse MoE (Mixture of Experts), 1.02T total / 42B activated parameters
- **Context Length**: 1M tokens
- **Modalities**: Text, Image, Video, Audio
- **Vision Encoder**: 681M-param MiMo ViT (28 layers: 24 SWA + 4 Full)
- **Audio Encoder**: 308M AudioTokenizer + 127M audio patch encoder
- **Multi-Token Prediction (MTP)**: 5-layer speculative decoder

![Figure 1: MiMo-V2.6 architecture — omni encoders, hybrid SWA backbone, and MTP blocks](assets/architecture.png)

*Figure 1. MiMo-V2.6 architecture.*

## 2. Downloads

| Model | Download |
| --- | --- |
| **MiMo-V2.6-Pro-RL** | [🤗 HuggingFace](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL) · [🤖 ModelScope](https://www.modelscope.cn/models/XiaomiMiMo/MiMo-V2.6-Pro-RL) |
| **MiMo-V2.6-Flash-RL** | [🤗 HuggingFace](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL) · [🤖 ModelScope](https://www.modelscope.cn/models/XiaomiMiMo/MiMo-V2.6-Flash-RL) |
| **MiMo-V2.6-Pro-MOPD** | [🤗 HuggingFace](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-MOPD) · [🤖 ModelScope](https://www.modelscope.cn/models/XiaomiMiMo/MiMo-V2.6-Pro-MOPD) |
| **MiMo-V2.6-Flash-MOPD** | [🤗 HuggingFace](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-MOPD) · [🤖 ModelScope](https://www.modelscope.cn/models/XiaomiMiMo/MiMo-V2.6-Flash-MOPD) |

## 3. Model Architecture

### LLM Backbone

| Component | MiMo-V2.6-Pro-MOPD |
| --- | --- |
| Layers (Total / SWA / GA) | 70 / 60 / 10 |
| Hidden Size | 6144 |
| SWA Heads (Q/KV) | 128 / 8 |
| GA Heads (Q/KV) | 128 / 8 |
| Head Dimensions (QK / V) | 192 / 128 |
| Sliding Window Size | 128 |
| Routed Experts (Total / Activated) | 384 / 8 |
| Max Context Length | 1M |
| MTP / Speculative Decoder | 5 SWA layers, window 1024 |

The first Transformer block uses global attention with a dense FFN. Remaining blocks interleave local SWA and GA; both use sparse MoE FFNs without shared experts.

### Vision Encoder (MiMo ViT)

| Configuration | Value |
| --- | --- |
| Layers (Total / SWA / GA) | 28 / 24 / 4 |
| Hidden Size | 1280 |
| Attention Heads (Q / KV) | 32 / 8 |
| Head Dimension | 64 |
| Patch Size (T × H × W) | 2 × 16 × 16 |
| Sliding Window (Left / Right) | 64 / 64 |
| Spatial Merge Size | 2 × 2 |
| Parameters | 681M |

### Audio Encoders

AudioTokenizer encoder: 24 layers (12 SWA / 12 GA), hidden 1024, 20 RVQ codebooks, 308M parameters. Audio patch encoder: 6 layers, 127M parameters; four frames per patch (25 Hz → 6.25 Hz).

### Speculative Decoder

5-layer SWA MTP drafter (DFlash-style). Predicts 7 subsequent tokens per forward pass for parallel verification.

## 4. Deployment

For best performance, follow the [SGLang MiMo cookbook](https://docs.sglang.io/cookbook/autoregressive/Xiaomi/MiMo-V2.5). Docker image: `lmsysorg/sglang:latest`.

### SGLang

```bash
sglang serve \
  --trust-remote-code \
  --model-path XiaomiMiMo/MiMo-V2.6-Pro-MOPD \
  --tp 16 \
  --dp 2 \
  --enable-dp-attention \
  --mm-enable-dp-encoder \
  --ep 16 \
  --moe-a2a-backend deepep \
  --moe-dense-tp-size 1 \
  --mem-fraction-static 0.7 \
  --max-running-requests 128 \
  --chunked-prefill-size 32768 \
  --page-size 64 \
  --swa-full-tokens-ratio 0.3 \
  --speculative-algorithm EAGLE \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --enable-multi-layer-eagle \
  --reasoning-parser mimo \
  --tool-call-parser mimo \
  --host 0.0.0.0 \
  --port 30000 \
  --nnodes 2 \
  --node-rank <node-rank> \
  --dist-init-addr <node0-ip>:20000
```

### vLLM

Follow the [vLLM MiMo-V2.5 recipe](https://recipes.vllm.ai/XiaomiMiMo/MiMo-V2.5). Pre-built image: `docker pull vllm/vllm-openai:mimov25-cu129`.

```bash
vllm serve XiaomiMiMo/MiMo-V2.6-Pro-MOPD \
  --tensor-parallel-size 8 \
  --trust-remote-code \
  --gpu-memory-utilization 0.95 \
  --max-model-len auto \
  --reasoning-parser mimo \
  --tool-call-parser mimo \
  --enable-auto-tool-choice \
  --generation-config vllm
```

Recommended sampling: `temperature=1.0`, `top_p=0.95`.

Also available in AI Studio, MiMo Code, Xiaomi MiMo Desktop, Xiaomi MiMo Open Platform API, and OpenRouter.

## Citation

```bibtex
@misc{mimo2026v26promopd,
  title={MiMo-V2.6-Pro-MOPD},
  author={{Xiaomi MiMo Team}},
  year={2026},
  howpublished={\url{https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-MOPD}},
}
```

## Contact

For questions or feedback, reach us at [mimo@xiaomi.com](mailto:mimo@xiaomi.com) or join our community:

- [WeChat Group](https://work.weixin.qq.com/apph5/external_room/join/group_mng?plg_id=c417f99bd9014b5dd894daa8bfe19790&)
- [Discord](https://discord.gg/WX2R2uNp)
- [Telegram](https://t.me/+3T-I0pekOVIyNDBl)
- [Reddit](https://www.reddit.com/r/XiaomiMiMo_Official/)
