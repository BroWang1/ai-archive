<div align="center">
  <img src="./figures/bailing-logo.png" width="60" alt="百灵 Logo" />
  <h1>Ming-3.0-asr-tiny</h1>
  <p><i>听懂中英文、方言，也听懂上下文。</i></p>
</div>

[English](https://huggingface.co/inclusionAI/Ming-3.0-asr-tiny) · 简体中文

[GitHub 代码与教程](https://github.com/inclusionAI/Ming-3.0-asr) · [快速开始](#快速开始) · [评测](#评测)

**Ming-3.0-asr-tiny** 基于 Ling-tiny-v3 语言模型与音频编码器构建，支持单轮中英文语音转写、方言识别，并可利用热词或对话上文改善领域术语识别。本仓库提供完整权重、tokenizer、Transformers 自定义实现和可运行的推理示例。

## 模型能力

- **中英文语音识别：** 使用统一接口将语音转写为文本。
- **方言识别：** 在包括粤语、闽南语、上海话在内的 15 组地区方言测试集上评测。
- **Context ASR：** 可在转写提示中加入相关热词或对话上文。
- **复杂场景：** 覆盖高噪语音及五类应用领域评测。

## 模型架构

<p align="center"><img src="./figures/model.jpg" width="850" alt="Ming-3.0-asr-tiny 模型架构" /></p>

## 快速开始

### 下载与安装

使用 Python 3.12 和兼容 CUDA 的 Linux GPU。下载完整模型后，安装模型依赖，包括 PyTorch 与 torchaudio：

```bash
python -m pip install "huggingface_hub[cli]"
hf download inclusionAI/Ming-3.0-asr-tiny --local-dir Ming-3.0-asr-tiny
cd Ming-3.0-asr-tiny
python -m pip install -r requirements.txt
```

### 运行 PyTorch / Transformers 推理脚本

```bash
python examples/transcribe.py \
  --model . \
  --audio /path/to/speech.wav
```

已知语种时可加 `--language-hint zh` 或 `--language-hint en`。示例使用 CUDA、BF16、SDPA、greedy decoding，最多生成 256 个新 token，并通过 `trust_remote_code=True` 加载仓库内的自定义实现。依赖版本见 `requirements.txt`，其中包括 Transformers 5.12.1、fla-core 0.5.2 和 PyTorch 2.11.0。若需其他 CUDA 版本，先按 [PyTorch 官方说明](https://pytorch.org/get-started/previous-versions/)安装匹配的 PyTorch 与 torchaudio 2.11.0 wheel，再运行 `pip install -r requirements.txt`。

### PyTorch / Transformers Python 示例

在下载后的模型目录运行，并将 `speech.wav` 换成自己的音频文件。该代码与仓库内的[可执行示例](./examples/transcribe.py)使用同一推理路径：

```python
import soundfile as sf
import torch
from transformers import AutoModelForCausalLM, AutoProcessor
from asr_request import decode_transcript, prepare_asr_request

processor = AutoProcessor.from_pretrained(".", trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    ".", trust_remote_code=True, dtype=torch.bfloat16,
    device_map="cuda:0", attn_implementation="sdpa",
).eval()
waveform, rate = sf.read("speech.wav", dtype="float32", always_2d=True)
inputs = prepare_asr_request(
    processor, (waveform.T, rate), return_tensors="pt",
).to(model.device)
eos = model.config.text_config.eos_token_id
with torch.inference_mode():
    output = model.generate(
        **inputs, max_new_tokens=256, do_sample=False,
        eos_token_id=eos, pad_token_id=eos, no_repeat_ngram_size=10,
    )
print(decode_transcript(
    processor.tokenizer, output[0, inputs.input_ids.shape[1]:].tolist(),
))
```

### Context ASR

普通转写和 Context ASR 使用同一输入格式。将主题和热词连续拼接在基础指令之后，不插入换行。对于语种已知、长度不超过 60 秒的音频，`--context-chunks` 会在 30 秒以内选择 3000 mel 帧，超过 30 秒选择 6000 mel 帧：

```bash
python examples/transcribe.py --model . --audio /path/to/speech.wav \
  --language-hint zh --context-chunks \
  --prompt $'Please recognize the language of this speech and transcribe it, placing a `\t` between the identified language and the transcribe.This is an audio about 电影蜥蜴.This audio may contains the following words or phrases:蜥蜴,姜知垠,曹承佑,姜惠贞,八音盒.'
```

英文音频将语言提示改为 `--language-hint en`。这里的主题与热词仅供演示，也可以在提示词中加入对话上文。Python 调用可通过 `prepare_asr_request(..., prompt=...)` 传入完整提示。

### SGLang 加速服务

GPU 服务请参阅 [Ming SGLang 适配仓库](https://github.com/inclusionAI/sglang_ling_v3/tree/ling_v3_audio_for_pr)和 [ASR 服务指南](https://github.com/inclusionAI/Ming-3.0-asr/blob/main/cookbook/sglang/README.en.md)，其中包含固定版本适配补丁、环境配置、启动脚本和客户端示例。服务启动后，可通过音频接口转写 WAV 文件：

```bash
curl --fail-with-body --max-time 600 \
  http://127.0.0.1:8000/v1/audio/transcriptions \
  -F 'file=@/path/to/speech.wav' -F 'model=ming-asr' \
  -F 'response_format=json' -F 'temperature=0'
```

响应中的 `text` 字段即为转写结果。数据集评测参数见 SGLang 指南。

## 评测

### ASR 整体表现

<p align="center"><img src="./figures/asr.png" width="1000" alt="ASR 整体表现" /></p>

[观看 Ming-3.0-asr-tiny 发版视频](https://github.com/NiniAndy/Ming-3.0-asr-tiny-blog/releases/download/media-2026-10-19/ming-3.0-asr-final.mp4)

### 中英文语音识别

<p align="center"><img src="./figures/开源asr.png" width="1000" alt="开源中英文 ASR 评测" /></p>

### 方言与领域识别

<p align="center"><img src="./figures/自建asr.png" width="1000" alt="方言与领域 ASR 评测" /></p>

### Context ASR

<p align="center"><img src="./figures/contextasr.png" width="1000" alt="Context ASR 评测" /></p>

## 使用说明

- 输出为转写文本，不提供词级时间戳或说话人分离。
- 当前示例不支持流式输入；模型不接受图像或视频。
- 长音频可用 `--audio-chunk-frames` 分块编码，仍受模型上下文长度限制。
- 热词仅是识别提示，不保证输出一定包含指定词语。

本地 Transformers 推理可使用仓库内置的 [PyTorch 示例](./examples/transcribe.py)。

## 许可证

模型权重及项目原创代码采用 [MIT 许可证](./LICENSE)，与 [Ming 项目](https://github.com/inclusionAI/Ming)保持一致。模型包中标注 Apache-2.0 的源码保留原有声明和[许可证文本](./LICENSE-APACHE-2.0)；`modeling_whisper_encoder.py` 保留基于 OpenAI Whisper 代码的 MIT 声明。

## 引用

如果在研究或产品中使用 Ming-3.0-asr-tiny，请引用 [GitHub 仓库](https://github.com/inclusionAI/Ming-3.0-asr)。[CITATION.cff](./CITATION.cff) 也提供机器可读的引用信息。

```bibtex
@misc{ming_3_0_asr_tiny_2026,
  author = {{inclusionAI}},
  title = {Ming-3.0-asr-tiny: Context-Aware Speech Recognition},
  year = {2026},
  url = {https://github.com/inclusionAI/Ming-3.0-asr}
}
```
