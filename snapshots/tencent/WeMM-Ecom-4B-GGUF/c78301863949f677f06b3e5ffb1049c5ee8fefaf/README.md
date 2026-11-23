---
library_name: llama.cpp
pipeline_tag: image-text-to-text
license: apache-2.0
license_link: https://huggingface.co/tencent/WeMM-Ecom-4B-GGUF/blob/main/LICENSE
base_model: tencent/WeMM-Ecom-4B
base_model_relation: quantized
tags:
- wemm
- qwen3_5
- gguf
- quantized
- multimodal
- e-commerce
- conversational
language:
- zh
- en
---


<h1 align="center">WeMM-Ecom-4B-GGUF</h1>

<p align="center"><b>Advancing Multimodal Content Understanding for WeChat E-Commerce</b></p>

<p align="center">
  <a href="https://huggingface.co/collections/tencent/wemm-ecom"><img src="https://img.shields.io/badge/%F0%9F%A4%97-Hugging%20Face-yellow" alt="Hugging Face Model Collection"></a>
  <a href="https://huggingface.co/tencent/WeMM-Ecom-4B-GGUF"><img src="https://img.shields.io/badge/%F0%9F%93%84-Technical%20Report-red" alt="Technical Report"></a>
  <a href="https://github.com/Tencent/WeMM-Ecom"><img src="https://img.shields.io/badge/GitHub-WeMM--Ecom-black?logo=github" alt="GitHub: WeMM-Ecom"></a>
  <a href="https://huggingface.co/tencent/WeMM-Ecom-4B-GGUF"><img src="https://img.shields.io/badge/%F0%9F%93%9A-Hugging%20Face%20Paper-blue" alt="Hugging Face Paper"></a>
</p>

<p align="center">
  <a href="#family-evaluation">Evaluation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#best-practices">Best Practices</a>
</p>

**WeMM-Ecom-4B-GGUF** is the GGUF edition of **WeMM-Ecom-4B**, developed by **WeChat Vision, Tencent**. It pairs **Q4_K_M** language-model weights with an **F16 multimodal projector** for deployment with **llama.cpp** and supports **hybrid thinking**.

The WeMM-Ecom family delivers leading e-commerce performance, with WeMM-Ecom-35B-A3B outperforming open-source models with hundreds of billions of parameters. Across model sizes, it also maintains general-purpose capabilities on par with state-of-the-art models of comparable size.


## Highlights

The highlights and benchmark figures summarize the corresponding **WeMM-Ecom-4B** family checkpoint.

- **E-commerce understanding:** Outperforms Qwen3.5-4B by **6.47 points** in average benchmark score.
- **Broad general capabilities:** Outperforms Qwen3.5-4B by **0.40 points** in average benchmark score.
- **GGUF deployment:** Q4_K_M language-model weights and an F16 projector, with command-line inference and an OpenAI-compatible local server.

## Model Overview

- **Architecture:** 4B dense model.
- **Language-model quantization:** Q4_K_M.
- **Multimodal projector:** F16 GGUF.
- **Context window:** 262,144 tokens.

**GGUF family:** [0.8B](https://huggingface.co/tencent/WeMM-Ecom-0.8B-GGUF) · [2B](https://huggingface.co/tencent/WeMM-Ecom-2B-GGUF) · [4B](https://huggingface.co/tencent/WeMM-Ecom-4B-GGUF) · [9B](https://huggingface.co/tencent/WeMM-Ecom-9B-GGUF) · [35B-A3B](https://huggingface.co/tencent/WeMM-Ecom-35B-A3B-GGUF)

**More formats:** [BF16](https://huggingface.co/tencent/WeMM-Ecom-4B) · [FP8](https://huggingface.co/tencent/WeMM-Ecom-4B-FP8) · [GPTQ](https://huggingface.co/tencent/WeMM-Ecom-4B-GPTQ)

## Family Evaluation

The following comparisons report the **WeMM-Ecom-4B** family checkpoint, following the technical report: **28 e-commerce benchmarks across eight scenarios** and **64 general benchmarks across eight categories**. Scores use a 0–100 scale.

### E-commerce Benchmarks

The suite covers product attributes, moderation, OCR, retrieval, grounding, reasoning, public e-commerce benchmarks, and product knowledge.

![WeMM-Ecom-4B e-commerce comparisons](assets/ecommerce-benchmarks.png)

<details>
<summary><b>Full e-commerce benchmark results</b></summary>

#### Instruct Mode

![WeMM-Ecom-4B Instruct Mode e-commerce results](assets/ecommerce-instruct-table.png)

#### Thinking Mode

![WeMM-Ecom-4B Thinking Mode e-commerce results](assets/ecommerce-thinking-table.png)

</details>

### General Benchmarks

The suite spans general VQA, document and chart understanding, STEM reasoning, spatial understanding, grounding and counting, multi-image understanding, instruction following, and text-centric tasks.

![WeMM-Ecom-4B general comparisons](assets/general-benchmarks.png)

<details>
<summary><b>Full general benchmark results</b></summary>

#### Instruct Mode

![WeMM-Ecom-4B Instruct Mode general results](assets/general-instruct-table.png)

#### Thinking Mode

![WeMM-Ecom-4B Thinking Mode general results](assets/general-thinking-table.png)

</details>

## Quick Start

Use [llama.cpp](https://github.com/ggml-org/llama.cpp) at the tested revision below. The language-model GGUF and its matching projector are provided together in this repository. Replace the local image and video paths with your own content.

### Download

```bash
pip install -U huggingface_hub
MODEL_DIR="$PWD/WeMM-Ecom-4B-GGUF"
hf download tencent/WeMM-Ecom-4B-GGUF \
    WeMM-Ecom-4B-GGUF.gguf mmproj-F16.gguf \
    --local-dir "$MODEL_DIR"
```

If authentication is required, run `hf auth login` before downloading.

| File | Contents |
| --- | --- |
| `WeMM-Ecom-4B-GGUF.gguf` | Q4_K_M language model |
| `mmproj-F16.gguf` | F16 multimodal projector |

### Build llama.cpp

For NVIDIA CUDA:

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
git checkout a8f8294c45076538f4509754e4c79fc51a1a486b
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build build --config Release -j --target llama-cli llama-server
```

<details>
<summary>CPU and other backends</summary>

For a CPU build, use a separate build directory:

```bash
cmake -B build-cpu -DCMAKE_BUILD_TYPE=Release
cmake --build build-cpu --config Release -j --target llama-cli llama-server
```

Use `./build-cpu/bin/` in the commands below. For CPU-only inference, set `-ngl 0` and add `--no-mmproj-offload` when loading the projector. For Metal, Vulkan, and other accelerators, follow the [official build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md).

</details>

### Prepare Images

For camera photos, apply their EXIF orientation before passing a local image to llama.cpp. The API helper below prepares images automatically.

```bash
pip install -U pillow
```

```python
from PIL import Image, ImageOps

with Image.open("./image.jpg") as source:
    image = ImageOps.exif_transpose(source).convert("RGBA")
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    image = Image.alpha_composite(background, image).convert("RGB")
    image.save("./image-normalized.png")
```

Use the prepared file with `--image`. Repeat this preparation for additional camera photos, updating the input and output paths.

### Image Understanding

The example uses Instruct Mode and the chat template embedded in the GGUF. The CLI examples run one turn; omit `--single-turn` for an interactive conversation.

```bash
./build/bin/llama-cli \
    -m "$MODEL_DIR/WeMM-Ecom-4B-GGUF.gguf" \
    --mmproj "$MODEL_DIR/mmproj-F16.gguf" \
    --image ./image-normalized.png \
    --jinja --reasoning off --single-turn \
    -ngl 99 -c 8192 -n 4096 \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
    --presence-penalty 1.5 --repeat-penalty 1.0 \
    -p "Describe the image and identify its visible details."
```

<details>
<summary>Text-only Conversations</summary>

```bash
./build/bin/llama-cli \
    -m "$MODEL_DIR/WeMM-Ecom-4B-GGUF.gguf" \
    --jinja --reasoning off --single-turn \
    -ngl 99 -c 8192 -n 4096 \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
    --presence-penalty 1.5 --repeat-penalty 1.0 \
    -p "Explain how to compare two visually similar items."
```

</details>

<details>
<summary>Multi-Image Understanding</summary>

Pass multiple image paths as a comma-separated list:

```bash
./build/bin/llama-cli \
    -m "$MODEL_DIR/WeMM-Ecom-4B-GGUF.gguf" \
    --mmproj "$MODEL_DIR/mmproj-F16.gguf" \
    --image ./image_front-normalized.png,./image_back-normalized.png \
    --jinja --reasoning off --single-turn \
    -ngl 99 -c 8192 -n 4096 \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
    --presence-penalty 1.5 --repeat-penalty 1.0 \
    -p "Compare these views and summarize their similarities and differences."
```

</details>

<details>
<summary>Video Understanding</summary>

Install FFmpeg and make sure `ffmpeg` and `ffprobe` are available on your `PATH`.

```bash
./build/bin/llama-cli \
    -m "$MODEL_DIR/WeMM-Ecom-4B-GGUF.gguf" \
    --mmproj "$MODEL_DIR/mmproj-F16.gguf" \
    --video ./video.mp4 --video-fps 2 \
    --jinja --reasoning off --single-turn \
    -ngl 99 -c 8192 -n 4096 \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
    --presence-penalty 1.5 --repeat-penalty 1.0 \
    -p "Summarize what happens in the video."
```

</details>

<details>
<summary>Visual Input Settings</summary>

For small text and fine image details, you can raise the image token budget:

```bash
./build/bin/llama-cli \
    -m "$MODEL_DIR/WeMM-Ecom-4B-GGUF.gguf" \
    --mmproj "$MODEL_DIR/mmproj-F16.gguf" \
    --image ./image-normalized.png --image-min-tokens 1024 \
    --jinja --reasoning off --single-turn \
    -ngl 99 -c 8192 -n 4096 \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
    --presence-penalty 1.5 --repeat-penalty 1.0 \
    -p "Read the visible text in the image."
```

This example sets the budget for image inputs. For video, choose a context size that accommodates the visual tokens across all frames and the generated answer.

</details>

### Hybrid Thinking

Select the operating mode with llama.cpp's `--reasoning` option:

- **Instruct Mode:** `--reasoning off --temp 0.7 --top-p 0.8`.
- **Thinking Mode:** `--reasoning on --temp 1.0 --top-p 0.95`.

Keep `--top-k 20 --min-p 0.0 --presence-penalty 1.5 --repeat-penalty 1.0` for the general-task profile. The same mode switch applies when starting `llama-server`.

### OpenAI-compatible Server

Start a local server in Instruct Mode:

```bash
./build/bin/llama-server \
    -m "$MODEL_DIR/WeMM-Ecom-4B-GGUF.gguf" \
    --mmproj "$MODEL_DIR/mmproj-F16.gguf" \
    --alias tencent/WeMM-Ecom-4B-GGUF \
    --jinja --reasoning off \
    -ngl 99 -c 8192 \
    --temp 0.7 --top-p 0.8 --top-k 20 --min-p 0.0 \
    --presence-penalty 1.5 --repeat-penalty 1.0 \
    --video-fps 2 \
    --host 127.0.0.1 --port 8000
```

Install the Python client:

```bash
pip install -U openai pillow
```

```python
import base64
import io
import mimetypes
from pathlib import Path
from PIL import Image, ImageOps
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")
request_kwargs = {
    "model": "tencent/WeMM-Ecom-4B-GGUF",
    "max_tokens": 4096,
    "temperature": 0.7,
    "top_p": 0.8,
    "presence_penalty": 1.5,
    "extra_body": {"top_k": 20, "min_p": 0.0, "repeat_penalty": 1.0},
}

def image_bytes(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
        background = Image.new('RGBA', image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, image).convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

def data_url(path):
    mime = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    if mime.startswith('image/'):
        data = image_bytes(path)
        mime = 'image/png'
    else:
        data = Path(path).read_bytes()
    return f'data:{mime};base64,' + base64.b64encode(data).decode('ascii')

def complete(messages):
    response = client.chat.completions.create(messages=messages, **request_kwargs)
    message = response.choices[0].message
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        print("Reasoning:\n" + reasoning)
    print("Answer:\n" + (message.content or ""))
    return message.content or ""

messages = [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": data_url("./image.jpg")}},
    {"type": "text", "text": "Describe the image and identify its visible details."},
]}]
answer = complete(messages)
```

For Thinking Mode, start the server with `--reasoning on`, and set `temperature=1.0` and `top_p=0.95` in `request_kwargs`.

<details>
<summary>Text, Multi-Image, and Video Requests</summary>

The requests below reuse the client and helper above:

```python
answer = complete([{
    "role": "user",
    "content": "Explain how to compare two visually similar items.",
}])

answer = complete([{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": data_url("./image_front.jpg")}},
    {"type": "image_url", "image_url": {"url": data_url("./image_back.jpg")}},
    {"type": "text", "text": "Compare the visible details in these two images."},
]}])

answer = complete([{"role": "user", "content": [
    {"type": "input_video", "input_video": {"url": data_url("./video.mp4")}},
    {"type": "text", "text": "Summarize what happens in the video."},
]}])
```

</details>

## Best Practices

- **Choose the mode explicitly:** use `--reasoning off` for Instruct Mode and `--reasoning on` for Thinking Mode. Match the API sampling settings to the server's mode.
- **Use the matching projector:** load `mmproj-F16.gguf` from this repository with its language-model file for image inputs.
- **Size the deployment context:** these examples use `-c 8192` and an output budget of `4096` tokens. Set `-c` and `max_tokens`/`-n` to accommodate both the input and generated output. Adjust `-ngl` to choose how many model layers are offloaded to the GPU.
- **Set the task's output format:** state the requested fields, labels, or coordinate convention for extraction and grounding. For additional task-specific sampling profiles, see the [family model card](https://huggingface.co/tencent/WeMM-Ecom-4B#best-practices); llama.cpp calls the repetition setting `repeat_penalty` in its API and `--repeat-penalty` on the command line.

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
