---
library_name: transformers
pipeline_tag: image-text-to-text
datasets:
- inclusionAI/ZwZ2-RL-VQA
base_model: Qwen/Qwen3.5-9B
language:
- en
tags:
- zwz2
- vision-language
- visual-reasoning
- reinforcement-learning
- grpo
---

# ZwZ2-9B

<!-- Replace PAPER_URL with the final v2 paper URL. -->
<p align="center">
  📃 <a href="https://arxiv.org/pdf/2610.37037">Paper</a> | 🏠 <a href="https://github.com/inclusionAI/Zooming-without-Zooming-v2">Project</a> | 🤗 <a href="https://huggingface.co/collections/inclusionAI/zooming-without-zooming-v2">Collection</a>
</p>

## ✨ Model Summary

**ZwZ2-9B** is the **Qwen3.5-9B**-based model in **Zooming-without-Zooming-v2 (ZwZ2)**. It learns to connect visual evidence across regions through comparison, aggregation, matching, and multi-step reasoning. Training uses full images; inference requires no zooming tools.

On **25 benchmarks across six domains**, it improves over its base model on every benchmark, increasing overall accuracy from **51.63 to 56.59 (+4.96 points)**. Gains extend from fine-grained perception to spatial reasoning, long-context understanding, multimodal agents, and general visual reasoning.

## ⚙️ Method and Data

**EvidenceConnect** builds verified multi-region questions from SA-1B images:

1. Group 3–7 related regions and generate questions using privileged zoomed views.
2. Check answers through cross-model agreement and drop-one region tests.
3. Convert verified questions to four-option tasks and train with **GRPO**, without an additional supervised fine-tuning stage.

All three model sizes use approximately **20K training examples**. The policy sees full images with colored region outlines; privileged crop layouts are used only for data construction. See [ZwZ2-RL-VQA](https://huggingface.co/datasets/inclusionAI/ZwZ2-RL-VQA) for the data schema and synthesis process.

## 📊 Performance

![ZwZ2 performance on eight representative benchmarks](assets/zwz2_performance_highlights.png)

[Editable vector PDF](assets/zwz2_performance_highlights_editable.pdf). The figure shows eight representative benchmarks; the complete results follow.

![All 25 benchmark results](assets/zwz2_9b_results.png)

[Full-resolution results](assets/zwz2_9b_results.png). Scores are accuracies (%); domain and overall averages weight the corresponding benchmarks equally. **MMLongBench\*** uses the visual core: V-RAG, Image MM-NIAH, and VH-Multi, comprising **25 non-Counting tasks**. Advanced-model image resolution is constrained by their serving platforms.

## 🚀 Quickstart

### Installation

Install a PyTorch build compatible with your hardware, then:

```bash
pip install "transformers==5.13.1" accelerate pillow huggingface_hub
```

### Inference

```python
from pathlib import Path
import torch
from huggingface_hub import hf_hub_download
from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration

model_id = "inclusionAI/ZwZ2-9B"
model = Qwen3_5ForConditionalGeneration.from_pretrained(
    model_id, dtype=torch.bfloat16, device_map="auto"
).eval()
processor = AutoProcessor.from_pretrained(model_id)
processor.chat_template = Path(
    hf_hub_download(model_id, "chat_template.jinja")
).read_text(encoding="utf-8")

messages = [{"role": "user", "content": [
    {"type": "image", "url": "/path/to/image.jpg"},
    {"type": "text", "text": "Describe this image."},
]}]
inputs = processor.apply_chat_template(
    messages, tokenize=True, add_generation_prompt=True,
    return_dict=True, return_tensors="pt", enable_thinking=False,
).to(model.device)

with torch.inference_mode():
    generated_ids = model.generate(
        **inputs, max_new_tokens=2048, do_sample=False
    )
output_text = processor.batch_decode(
    generated_ids[:, inputs["input_ids"].shape[1]:],
    skip_special_tokens=True, clean_up_tokenization_spaces=False,
)[0]
print(output_text)
```

Replace `/path/to/image.jpg` with an existing image. All three sizes use `Qwen3_5ForConditionalGeneration`, including the Qwen3.6-27B-based model. The example preserves the released chat template and uses **non-thinking mode**. The template requests final answers inside `<answer>...</answer>`; a custom system message replaces that default instruction.

## 🤗 Models and Data

| Model | Base model |
|---|---|
| [ZwZ2-4B](https://huggingface.co/inclusionAI/ZwZ2-4B) | Qwen3.5-4B |
| [ZwZ2-9B](https://huggingface.co/inclusionAI/ZwZ2-9B) | Qwen3.5-9B |
| [ZwZ2-27B](https://huggingface.co/inclusionAI/ZwZ2-27B) | Qwen3.6-27B |

[🤗 ZwZ2-RL-VQA training dataset](https://huggingface.co/datasets/inclusionAI/ZwZ2-RL-VQA)

## 📄 Limitations and License

The model can hallucinate details, misread text, and make counting or spatial errors. Performance depends on image resolution, context length, and prompt format. Refer to the license accompanying the released weights and the applicable backbone license for usage terms.

**First-generation ZwZ:** [Paper](https://huggingface.co/papers/2602.11858) · [Code](https://github.com/inclusionAI/Zooming-without-Zooming).
