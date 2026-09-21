---
license: apache-2.0
library_name: vllm
pipeline_tag: automatic-speech-recognition
base_model: FunAudioLLM/Fun-ASR-Nano-2512
language:
  - zh
  - en
  - ja
tags:
  - funasr
  - vllm
  - speech-recognition
  - automatic-speech-recognition
  - openai-compatible
  - qwen3
---

# Fun-ASR-Nano-2512 for vLLM

This is the official vLLM-native packaging of
[`FunAudioLLM/Fun-ASR-Nano-2512`](https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512).
It preserves the official checkpoint tensors and adds the layout required by
vLLM's `FunASRForConditionalGeneration` implementation.

This repository does not define a new model and does not add LoRA weights. The
1,261 tensors in `model.safetensors` are bitwise equal to the tensors in the
official source `model.pt` at revision
`272c57b82523ada6fd87095e955f8e29100979ab`.

## Run with vLLM

The validated path uses float32 for the highest transcription fidelity:

```bash
python -m pip install "vllm==0.27.1"

vllm serve FunAudioLLM/Fun-ASR-Nano-2512-vllm \
  --revision vllm-0.27.1-20260830 \
  --served-model-name fun-asr-nano \
  --dtype float32 \
  --gpu-memory-utilization 0.40 \
  --enforce-eager
```

Send an OpenAI-compatible transcription request:

```bash
curl -fL \
  https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512-vllm/resolve/vllm-0.27.1-20260830/example/zh.mp3 \
  -o zh.mp3

curl -sS http://127.0.0.1:8000/v1/audio/transcriptions \
  -F file=@zh.mp3 \
  -F model=fun-asr-nano \
  -F language=zh \
  -F temperature=0 \
  -F response_format=json
```

Expected text for the pinned sample:

```text
开饭时间早上九点至下午五点。
```

## Provenance

| Item | Value |
| --- | --- |
| Official source | `FunAudioLLM/Fun-ASR-Nano-2512` |
| Source revision | `272c57b82523ada6fd87095e955f8e29100979ab` |
| Source `model.pt` SHA-256 | `55ae0d2fee369f0f11cce0795f6927934ad17cf11b278a7e56a51272074160bb` |
| Tensor count | 1,261 |
| LoRA tensors | 0 |
| Converted `model.safetensors` SHA-256 | `96dfbec48282dd24d3334369a01e9e909f321ee39a1b0003c528c5379f68c1a6` |
| Sample `example/zh.mp3` SHA-256 | `0e64de19e4ff9a02e682955c9112f32d2317cfdbb5bc2f3504664044c993f195` |

The complete machine-readable record is in
[`MODEL_PROVENANCE.json`](./MODEL_PROVENANCE.json). The conversion can be
reproduced with [`convert_from_official.py`](./convert_from_official.py).

The vLLM-native layout originated in the community work by
[`allendou/Fun-ASR-Nano-2512-vllm`](https://huggingface.co/allendou/Fun-ASR-Nano-2512-vllm)
and vLLM [PR #33247](https://github.com/vllm-project/vllm/pull/33247), with
subsequent format and initialization fixes in vLLM PRs
[#36108](https://github.com/vllm-project/vllm/pull/36108) and
[#44215](https://github.com/vllm-project/vllm/pull/44215). This official
packaging keeps that attribution while anchoring the weights to the official
FunAudioLLM checkpoint.

## Validation boundary

The published evidence covers vLLM 0.27.1, PyTorch 2.13.0+cu129,
Transformers 5.15.0, and one NVIDIA H100 80 GB GPU. The pinned Chinese sample
returned the expected text in three consecutive deterministic requests. Other
vLLM releases, accelerators, quantizations, and model quality across broader
datasets require separate validation.

For the regular FunASR Python runtime, timestamps, speaker diarization, and
streaming services, use the canonical
[`modelscope/FunASR`](https://github.com/modelscope/FunASR) toolkit and the
original checkpoint.

## License

The official source model declares Apache License 2.0. See
[`LICENSE`](./LICENSE). Third-party software such as vLLM remains subject to
its own license.
