---
library_name: transformers
pipeline_tag: image-text-to-text
license: apache-2.0
license_link: https://huggingface.co/tencent/WeMM-Ecom-0.8B-GPTQ/blob/main/LICENSE
base_model:
- tencent/WeMM-Ecom-0.8B
tags:
- wemm
- qwen3_5
- multimodal
- e-commerce
- conversational
- quantized
- gptq
- compressed-tensors
- 4-bit
language:
- zh
- en
base_model_relation: quantized
---

<h1 align="center">WeMM-Ecom-0.8B-GPTQ</h1>

<p align="center"><b>Advancing Multimodal Content Understanding for WeChat E-Commerce</b></p>

<p align="center">
  <a href="https://huggingface.co/collections/tencent/wemm-ecom"><img src="https://img.shields.io/badge/%F0%9F%A4%97-Hugging%20Face-yellow" alt="Hugging Face Model Collection"></a>
  <a href="https://huggingface.co/tencent/WeMM-Ecom-0.8B-GPTQ"><img src="https://img.shields.io/badge/%F0%9F%93%84-Technical%20Report-red" alt="Technical Report"></a>
  <a href="https://github.com/Tencent/WeMM-Ecom"><img src="https://img.shields.io/badge/GitHub-WeMM--Ecom-black?logo=github" alt="GitHub: WeMM-Ecom"></a>
  <a href="https://huggingface.co/tencent/WeMM-Ecom-0.8B-GPTQ"><img src="https://img.shields.io/badge/%F0%9F%93%9A-Hugging%20Face%20Paper-blue" alt="Hugging Face Paper"></a>
</p>

<p align="center">
  <a href="#family-evaluation">Evaluation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#best-practices">Best Practices</a>
</p>

**WeMM-Ecom-0.8B-GPTQ** is the **GPTQ W4A16** quantized release of [WeMM-Ecom-0.8B](https://huggingface.co/tencent/WeMM-Ecom-0.8B), developed by **WeChat Vision, Tencent**. It brings fine-grained e-commerce understanding, broad visual-language capabilities, and **hybrid thinking** to quantized deployment.

The WeMM-Ecom family delivers leading e-commerce performance, with WeMM-Ecom-35B-A3B outperforming open-source models with hundreds of billions of parameters. Across model sizes, it also maintains general-purpose capabilities on par with state-of-the-art models of comparable size.

## Highlights

The following highlights summarize the corresponding **WeMM-Ecom-0.8B** checkpoint in the WeMM-Ecom family.

- **E-commerce understanding:** Outperforms Qwen3.5-0.8B by **16.43 points** and MiniCPM-V-4.7-1B by **13.03 points** in average benchmark score.
- **Broad general capabilities:** Outperforms Qwen3.5-0.8B by **6.93 points** and MiniCPM-V-4.7-1B by **1.09 points** in average benchmark score.
- **Flexible deployment:** text, image, multi-image, and video inputs; BF16, FP8, GPTQ, and GGUF formats.

## Model Overview

- **Architecture:** 0.8B dense model.
- **Context window:** 262,144 tokens.
- **Checkpoint:** GPTQ W4A16 Safetensors (`compressed-tensors`).

**Model family:** [0.8B](https://huggingface.co/tencent/WeMM-Ecom-0.8B) · [2B](https://huggingface.co/tencent/WeMM-Ecom-2B) · [4B](https://huggingface.co/tencent/WeMM-Ecom-4B) · [9B](https://huggingface.co/tencent/WeMM-Ecom-9B) · [35B-A3B](https://huggingface.co/tencent/WeMM-Ecom-35B-A3B)

**Available formats:** [BF16](https://huggingface.co/tencent/WeMM-Ecom-0.8B) · [FP8](https://huggingface.co/tencent/WeMM-Ecom-0.8B-FP8) · [GPTQ](https://huggingface.co/tencent/WeMM-Ecom-0.8B-GPTQ) · [GGUF](https://huggingface.co/tencent/WeMM-Ecom-0.8B-GGUF)

### Quantization

- **Method:** GPTQ with 4-bit weights and 16-bit activations (**W4A16**).
- **Weight groups:** 128 values per group, with symmetric quantization.
- **Storage:** packed Safetensors in the `compressed-tensors` format.
- **Precision selection:** the vision encoder, output head, and selected sensitive projections retain their original precision.

Use vLLM's `compressed-tensors` backend for quantized serving. The checkpoint includes its quantization settings, so the launch command can detect the format automatically.

## Family Evaluation

The charts below present the **WeMM-Ecom-0.8B family results** from our technical report.

We evaluate e-commerce understanding on **28 benchmarks across eight scenarios** and general capabilities on **64 benchmarks across eight categories**. All scores use a 0–100 scale, with higher values indicating stronger performance.

### E-commerce Benchmarks

The suite covers product attributes, moderation, OCR, retrieval, grounding, reasoning, public e-commerce benchmarks, and product knowledge.

![WeMM-Ecom-0.8B e-commerce comparisons](assets/ecommerce-benchmarks.png)

<details>
<summary><b>Full e-commerce benchmark results</b></summary>

#### Instruct Mode

![WeMM-Ecom-0.8B Instruct Mode e-commerce results](assets/ecommerce-instruct-table.png)

#### Thinking Mode

![WeMM-Ecom-0.8B Thinking Mode e-commerce results](assets/ecommerce-thinking-table.png)

</details>

### General Benchmarks

The suite spans general VQA, document and chart understanding, STEM reasoning, spatial understanding, grounding and counting, multi-image understanding, instruction following, and text-centric tasks.

![WeMM-Ecom-0.8B general comparisons](assets/general-benchmarks.png)

<details>
<summary><b>Full general benchmark results</b></summary>

#### Instruct Mode

![WeMM-Ecom-0.8B Instruct Mode general results](assets/general-instruct-table.png)

#### Thinking Mode

![WeMM-Ecom-0.8B Thinking Mode general results](assets/general-thinking-table.png)

</details>

## Quick Start

Serve the checkpoint with vLLM, then use the OpenAI-compatible examples for text, image, multi-image, video, multi-turn, and streaming requests. Replace the local image and video paths with your own content.

### Installation

Use a separate environment for the serving engine. Python 3.11 is an example; follow the requirements of your chosen [vLLM release](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/).

```bash
python3.11 -m venv .venv-vllm
source .venv-vllm/bin/activate
pip install -U pip uv
uv pip install -U "vllm>=0.31.0" openai --torch-backend=auto
```

<details>
<summary>Authentication and local checkpoints</summary>

For repositories that require authentication, sign in once. To download the checkpoint to a local directory:

```bash
pip install -U huggingface_hub
hf auth login
hf download tencent/WeMM-Ecom-0.8B-GPTQ --local-dir ./WeMM-Ecom-0.8B-GPTQ
```

To serve the local checkpoint, use `MODEL=./WeMM-Ecom-0.8B-GPTQ` below and keep the served model name unchanged.

</details>

### Start vLLM

The example uses a 32,768-token serving context. Adjust the context and tensor parallelism for your deployment.

```bash
MODEL=tencent/WeMM-Ecom-0.8B-GPTQ
vllm serve "$MODEL" \
    --served-model-name "tencent/WeMM-Ecom-0.8B-GPTQ" \
    --tensor-parallel-size 1 \
    --max-model-len 32768 \
    --reasoning-parser qwen3 \
    --port 8000
```

### Hybrid Thinking

- **Instruct Mode:** set `enable_thinking=False` for a direct response.
- **Thinking Mode:** set `enable_thinking=True` for reasoning followed by the final answer.

The checkpoint default is **Instruct Mode**. The API examples pass the switch explicitly.

### OpenAI-compatible API

Install the client where you send requests:

```bash
pip install -U openai
```

Set `enable_thinking` before constructing the shared request settings; rerun this setup when changing modes. Local media are encoded in the client so the server does not need access to their file paths.

```python
import base64
from pathlib import Path
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")
enable_thinking = False
request_kwargs = {
    "model": "tencent/WeMM-Ecom-0.8B-GPTQ",
    "max_completion_tokens": 4096,
    "temperature": 1.0 if enable_thinking else 0.7,
    "top_p": 0.95 if enable_thinking else 0.8,
    "presence_penalty": 1.5,
    "extra_body": {
        "top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    },
}

def media_url(path, mime_type):
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"

def show_response(response):
    message = response.choices[0].message
    reasoning = getattr(message, "reasoning", None) or getattr(message, "reasoning_content", None)
    if reasoning:
        print("Reasoning:\n" + reasoning)
    answer = message.content or ""
    print("Answer:\n" + answer)
    return answer
```

#### Image Requests

```python
messages = [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": media_url("./product.jpg", "image/jpeg")}},
    {"type": "text", "text": "Describe this product and extract its visible attributes."},
]}]
response = client.chat.completions.create(messages=messages, **request_kwargs)
final_text = show_response(response)
```

<details>
<summary>Text Requests</summary>

```python
messages = [{"role": "user", "content": "List five attributes that distinguish product variants."}]
response = client.chat.completions.create(messages=messages, **request_kwargs)
final_text = show_response(response)
```

</details>

<details>
<summary>Multi-Image Requests</summary>

```python
messages = [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": media_url("./product_front.jpg", "image/jpeg")}},
    {"type": "image_url", "image_url": {"url": media_url("./product_back.jpg", "image/jpeg")}},
    {"type": "text", "text": "Compare these product views and extract the visible attributes."},
]}]
response = client.chat.completions.create(messages=messages, **request_kwargs)
final_text = show_response(response)
```

</details>

<details>
<summary>Video Requests</summary>

Use the engines' `video_url` input with a local MP4 clip:

```python
messages = [{"role": "user", "content": [
    {"type": "video_url", "video_url": {"url": media_url("./product_demo.mp4", "video/mp4")}},
    {"type": "text", "text": "Summarize the visible events in this product demonstration."},
]}]
response = client.chat.completions.create(messages=messages, **request_kwargs)
final_text = show_response(response)
```

</details>

<details>
<summary>Multi-turn Requests</summary>

Send the conversation history with each request and keep only the final answer in assistant messages.

```python
turns = [
    [{"type": "image_url", "image_url": {"url": media_url("./product.jpg", "image/jpeg")}},
     {"type": "text", "text": "Describe this product's visible attributes."}],
    "Which details should be included in the product title?",
]
history = []
for content in turns:
    history.append({"role": "user", "content": content})
    response = client.chat.completions.create(messages=history, **request_kwargs)
    final_text = show_response(response)
    if not final_text:
        break
    history.append({"role": "assistant", "content": final_text})
```

</details>

<details>
<summary>Streaming Responses</summary>

```python
messages = [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": media_url("./product.jpg", "image/jpeg")}},
    {"type": "text", "text": "Describe this product and extract its visible attributes."},
]}]
stream = client.chat.completions.create(messages=messages, stream=True, **request_kwargs)
channel = None
for chunk in stream:
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    reasoning = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
    for label, text in [("Reasoning", reasoning), ("Answer", delta.content)]:
        if not text:
            continue
        if label != channel:
            print(f"\n{label}:\n", end="")
            channel = label
        print(text, end="", flush=True)
print()
```

</details>

## Best Practices

### Sampling Parameters

Choose a profile by mode and task. The following settings are starting points drawn from our evaluation configurations.

- **Instruct Mode — general tasks:** `temperature=0.7`, `top_p=0.8`, `top_k=20`, `min_p=0.0`, `presence_penalty=1.5`, `repetition_penalty=1.0`.
- **Instruct Mode — structured outputs, such as attribute selection, product detection, and SKU matching:** `temperature=0.7`, `top_p=0.8`, `top_k=20`, `min_p=0.0`, `presence_penalty=0.0`, `repetition_penalty=1.0`.
- **Instruct Mode — reasoning tasks:** `temperature=1.0`, `top_p=1.0`, `top_k=40`, `min_p=0.0`, `presence_penalty=2.0`, `repetition_penalty=1.0`.
- **Thinking Mode — general tasks:** `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=1.5`, `repetition_penalty=1.0`.
- **Thinking Mode — OCR, entity recognition, and SKU matching:** `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=2.0`, `repetition_penalty=1.05`.

Use the OpenAI-compatible examples to apply all listed parameters. Pass `temperature`, `top_p`, and `presence_penalty` directly, and put `top_k`, `min_p`, and `repetition_penalty` in `extra_body`.

### Mode and Output Settings

- **Select the mode explicitly:** use `enable_thinking=False` for Instruct Mode and `enable_thinking=True` for Thinking Mode. In the serving API, pass this switch through `chat_template_kwargs` in `extra_body`.
- **Allow enough output tokens:** our evaluations use a maximum generation budget of **65,536 tokens**. The Quick Start uses **4,096 tokens** for a compact example; increase this budget for longer reasoning. Set `max_completion_tokens` in the serving API. The serving context limit must accommodate both the input and the generated output.
- **Specify the output format:** for extraction, matching, and grounding, state the required fields, labels, and coordinate format. For multiple-choice tasks, request a clear final answer. In multi-turn conversations, append the assistant's final answer to the history.

## Citation

If you find WeMM-Ecom useful, please consider starring our [GitHub repository](https://github.com/Tencent/WeMM-Ecom) and citing our technical report.

```bibtex
@misc{wemm-ecom-2026,
  title = {WeMM-Ecom: Advancing Multimodal Content Understanding for WeChat E-Commerce},
  author = {Binhui Xie and Jinmin Li and Haomiao Tang and Guangting Wang and Song Jin and Jianwei Zhu and Fengyun Rao and Jing LYU},
  year = {2026},
  url = {}
}
```

## License

The model weights are licensed under Apache-2.0, except for the third-party components listed in [LICENSE](LICENSE), which retain their respective original licenses. See that file for the full terms, notices, and dependencies.

## Acknowledgements

We thank the Qwen team for the Qwen3.5 foundation and the open-source community for the tools and benchmarks used in this project.
