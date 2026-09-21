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

# Fun-ASR-Nano-2512 vLLM 官方转换包

这是
[`FunAudioLLM/Fun-ASR-Nano-2512`](https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512)
的官方 vLLM 原生布局。它保留官方 checkpoint 的张量，只补充 vLLM
`FunASRForConditionalGeneration` 所需的文件结构。

这个仓库不是一个新模型，也没有增加 LoRA 权重。`model.safetensors`
中的 1,261 个张量与官方源 revision
`272c57b82523ada6fd87095e955f8e29100979ab` 的 `model.pt` 逐张量 bitwise
相同。

## 使用 vLLM 部署

已验证路径使用 float32，以保持最高转写准确度：

```bash
python -m pip install "vllm==0.27.1"

vllm serve FunAudioLLM/Fun-ASR-Nano-2512-vllm \
  --revision vllm-0.27.1-20260830 \
  --served-model-name fun-asr-nano \
  --dtype float32 \
  --gpu-memory-utilization 0.40 \
  --enforce-eager
```

发送 OpenAI-compatible 转写请求：

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

固定样例的预期文字：

```text
开饭时间早上九点至下午五点。
```

## 来源与完整性

| 项目 | 值 |
| --- | --- |
| 官方来源 | `FunAudioLLM/Fun-ASR-Nano-2512` |
| 源 revision | `272c57b82523ada6fd87095e955f8e29100979ab` |
| 源 `model.pt` SHA-256 | `55ae0d2fee369f0f11cce0795f6927934ad17cf11b278a7e56a51272074160bb` |
| 张量数 | 1,261 |
| LoRA 张量数 | 0 |
| 转换后 `model.safetensors` SHA-256 | `96dfbec48282dd24d3334369a01e9e909f321ee39a1b0003c528c5379f68c1a6` |
| 样例 `example/zh.mp3` SHA-256 | `0e64de19e4ff9a02e682955c9112f32d2317cfdbb5bc2f3504664044c993f195` |

完整机器可读记录见
[`MODEL_PROVENANCE.json`](./MODEL_PROVENANCE.json)，可通过
[`convert_from_official.py`](./convert_from_official.py) 复现转换。

vLLM 原生布局最初来自社区仓
[`allendou/Fun-ASR-Nano-2512-vllm`](https://huggingface.co/allendou/Fun-ASR-Nano-2512-vllm)
和 vLLM [#33247](https://github.com/vllm-project/vllm/pull/33247)，后续格式与初始化修复见
[#36108](https://github.com/vllm-project/vllm/pull/36108) 与
[#44215](https://github.com/vllm-project/vllm/pull/44215)。本官方转换包保留这些贡献的署名，
同时把权重来源锚定到 FunAudioLLM 官方 checkpoint。

## 验证边界

当前证据覆盖 vLLM 0.27.1、PyTorch 2.13.0+cu129、Transformers 5.15.0
和单张 NVIDIA H100 80 GB。固定中文样例连续三次确定性请求均返回预期结果。
其他 vLLM 版本、加速卡、量化格式和更广泛数据集上的质量需要单独验证。

常规 FunASR Python 推理、时间戳、说话人识别和流式服务仍以
[`modelscope/FunASR`](https://github.com/modelscope/FunASR) 与原始 checkpoint
为 canonical 入口。

## 许可证

官方源模型声明 Apache License 2.0，详见 [`LICENSE`](./LICENSE)。vLLM
等第三方软件仍适用各自许可证。
