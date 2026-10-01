---
license: apache-2.0
library_name: transformers
pipeline_tag: image-text-to-text
base_model: Qwen/Qwen3.8-27B
tags:
  - qwen3_5
  - agent
  - deep-research
  - reasoning
  - tool-use
  - long-context
  - self-improvement
  - safetensors
---

<div align="center">
  <img src="assets/arex-logo.png" width="40%" alt="AREX" style="display:block;margin:0 auto -2px;">
  <strong>AREX-2: Advancing Self-Improving Agents through Long-Horizon Reflective Tasks</strong><br>
  <a href="https://arxiv.org/abs/2609.38288"><img src="https://img.shields.io/badge/-Paper-B31B1B?style=for-the-badge&amp;logo=arxiv&amp;logoColor=white" alt="Paper"></a>
  <a href="https://github.com/VectorSpaceLab/AREX-2"><img src="https://img.shields.io/badge/-Homepage-24292F?style=for-the-badge&amp;logo=github&amp;logoColor=white" alt="Homepage"></a>
</div>

## Introduction

AREX-2 is a 27B-parameter long-horizon agent model from the Beijing Academy of
Artificial Intelligence (BAAI). It learns to improve a solution over multiple
test-time rounds: propose, measure, reflect, and revise.

AREX-2 is trained on machine-learning and algorithmic-programming tasks with
verifiable feedback, together with the existing AREX deep-research data. The
learned self-improvement behavior transfers to deep research without adding new
search trajectories.

- **Architecture:** Dense Qwen3.8-compatible multimodal model
- **Parameters:** 27B
- **Context length:** 262,144 tokens

## Key features

- **Long-horizon self-improvement:** turns extra test-time rounds into useful
  solution refinement.
- **Feedback-driven reflection:** reads scores, logs, errors, and timings to
  decide what to change next.
- **Cross-domain performance:** training on coding and machine-learning tasks
  also improves the model's deep-research performance.
- **Long-horizon reasoning:** sustains productive iteration as the task budget
  grows.

## Evaluation

AREX-2 is evaluated on algorithmic programming, machine-learning engineering,
deep research, and general agentic reasoning. Results follow the protocols
reported in the AREX-2 paper.

### Coding and machine-learning engineering

<table cellpadding="7" style="display:table!important;overflow:visible!important;width:auto;max-width:100%;border:0!important;border-radius:0!important;border-collapse:collapse!important;font-size:13px;table-layout:auto">
<thead>
<tr style="color:#0F766E;border-bottom:2px solid #0F766E">
<th style="padding:8px;text-align:left">Model</th>
<th style="padding:8px;text-align:center">Params</th>
<th style="padding:8px;text-align:center">Frontier-CS</th>
<th style="padding:8px;text-align:center">MLE-Lite</th>
</tr>
</thead>
<tbody>
<tr><td colspan="4" style="padding:8px 10px;font-weight:600;color:#0F766E;background:rgba(15,118,110,.1)">Closed-weight models</td></tr>
<tr><td>GPT-5.6 Sol</td><td style="text-align:center">-</td><td style="text-align:center">76.4</td><td style="text-align:center">72.7</td></tr>
<tr><td>Claude Opus 4.8</td><td style="text-align:center">-</td><td style="text-align:center">74.5</td><td style="text-align:center">63.6</td></tr>
<tr><td>GPT-5.5</td><td style="text-align:center">-</td><td style="text-align:center">72.1</td><td style="text-align:center">68.2</td></tr>
<tr><td>Gemini-3.1-Pro</td><td style="text-align:center">-</td><td style="text-align:center">68.9</td><td style="text-align:center">-</td></tr>
<tr><td>Qwen3.7-Max</td><td style="text-align:center">-</td><td style="text-align:center">61.9</td><td style="text-align:center">-</td></tr>
<tr><td colspan="4" style="padding:8px 10px;font-weight:600;color:#0F766E;background:rgba(15,118,110,.1)">Open-weight models</td></tr>
<tr><td>Kimi-K3</td><td style="text-align:center">2.8T</td><td style="text-align:center">-</td><td style="text-align:center">72.7</td></tr>
<tr><td>Naive-N0.5-Flash</td><td style="text-align:center">309B</td><td style="text-align:center">-</td><td style="text-align:center">73.7</td></tr>
<tr><td>DeepSeek-V4-Pro</td><td style="text-align:center">1.6T</td><td style="text-align:center">44.7</td><td style="text-align:center">54.5</td></tr>
<tr><td>DeepSeek-V4-Flash</td><td style="text-align:center">284B</td><td style="text-align:center">39.1</td><td style="text-align:center">51.5</td></tr>
<tr><td>Kimi-K2.7-Code</td><td style="text-align:center">1T</td><td style="text-align:center">54.7</td><td style="text-align:center">-</td></tr>
<tr><td>GLM-5.3-Flash</td><td style="text-align:center">320B</td><td style="text-align:center">50.4</td><td style="text-align:center">-</td></tr>
<tr><td>Kimi-K2.6</td><td style="text-align:center">1T</td><td style="text-align:center">46.9</td><td style="text-align:center">66.7</td></tr>
<tr><td>Frontis-MA1-35B</td><td style="text-align:center">35B</td><td style="text-align:center">-</td><td style="text-align:center">71.2</td></tr>
<tr><td>BigBang-V1</td><td style="text-align:center">35B</td><td style="text-align:center">-</td><td style="text-align:center">59.1</td></tr>
<tr><td>Qwen3.6-35B-A3B</td><td style="text-align:center">35B</td><td style="text-align:center">23.4</td><td style="text-align:center">39.4</td></tr>
<tr style="background:rgba(15,118,110,.08);font-weight:600;color:#0F766E"><td style="padding:7px 10px">AREX-2</td><td style="text-align:center">27B</td><td style="text-align:center">70.7</td><td style="text-align:center">81.8</td></tr>
</tbody>
</table>

<small>Frontier-CS is the 188-task Agent Track. MLE-Lite reports Any Medal
averaged over three seeds.</small>

### General agentic reasoning and deep research

<table cellpadding="7" style="display:table!important;overflow:visible!important;width:auto;max-width:100%;border:0!important;border-radius:0!important;border-collapse:collapse!important;font-size:13px;table-layout:auto">
<thead>
<tr style="color:#0F766E;border-bottom:2px solid #0F766E">
<th style="padding:8px;text-align:left">Model</th>
<th style="padding:8px;text-align:center">Params</th>
<th style="padding:8px;text-align:center">BrowseComp</th>
<th style="padding:8px;text-align:center">HLE</th>
<th style="padding:8px;text-align:center">GAIA</th>
<th style="padding:8px;text-align:center">DeepSearchQA</th>
</tr>
</thead>
<tbody>
<tr><td colspan="6" style="padding:8px 10px;font-weight:600;color:#0F766E;background:rgba(15,118,110,.1)">Frontier models</td></tr>
<tr><td>GPT-5.6 Sol</td><td style="text-align:center">-</td><td style="text-align:center">90.4</td><td style="text-align:center">58.0*</td><td style="text-align:center">-</td><td style="text-align:center">-</td></tr>
<tr><td>GPT-5.6 Terra</td><td style="text-align:center">-</td><td style="text-align:center">87.5</td><td style="text-align:center">-</td><td style="text-align:center">-</td><td style="text-align:center">-</td></tr>
<tr><td>GPT-5.6 Luna</td><td style="text-align:center">-</td><td style="text-align:center">83.3</td><td style="text-align:center">-</td><td style="text-align:center">-</td><td style="text-align:center">-</td></tr>
<tr><td>Kimi-K3</td><td style="text-align:center">2.8T</td><td style="text-align:center">91.2</td><td style="text-align:center">56.0*</td><td style="text-align:center">-</td><td style="text-align:center">95.0</td></tr>
<tr><td>Claude Fable 5</td><td style="text-align:center">-</td><td style="text-align:center">88.0</td><td style="text-align:center">64.5*</td><td style="text-align:center">-</td><td style="text-align:center">94.2</td></tr>
<tr><td>Claude Opus 4.8</td><td style="text-align:center">-</td><td style="text-align:center">84.3</td><td style="text-align:center">57.9*</td><td style="text-align:center">-</td><td style="text-align:center">93.1</td></tr>
<tr><td>GPT-5.5</td><td style="text-align:center">-</td><td style="text-align:center">84.4</td><td style="text-align:center">52.2*</td><td style="text-align:center">87.4</td><td style="text-align:center">-</td></tr>
<tr><td>Gemini-3.1-Pro</td><td style="text-align:center">-</td><td style="text-align:center">85.9</td><td style="text-align:center">51.4*</td><td style="text-align:center">80.6</td><td style="text-align:center">93.3</td></tr>
<tr><td colspan="6" style="padding:8px 10px;font-weight:600;color:#0F766E;background:rgba(15,118,110,.1)">Large models (&gt;40B)</td></tr>
<tr><td>GLM-5</td><td style="text-align:center">744B</td><td style="text-align:center">75.9</td><td style="text-align:center">50.4</td><td style="text-align:center">70.0</td><td style="text-align:center">-</td></tr>
<tr><td>Kimi-K2.6</td><td style="text-align:center">1T</td><td style="text-align:center">83.2</td><td style="text-align:center">54.0*</td><td style="text-align:center">80.6</td><td style="text-align:center">92.5</td></tr>
<tr><td>GLM-5.3-Flash</td><td style="text-align:center">320B</td><td style="text-align:center">-</td><td style="text-align:center">55.3*</td><td style="text-align:center">78.8</td><td style="text-align:center">-</td></tr>
<tr><td>DeepSeek-V4-Flash</td><td style="text-align:center">284B</td><td style="text-align:center">73.2</td><td style="text-align:center">45.1</td><td style="text-align:center">57.5</td><td style="text-align:center">90.6</td></tr>
<tr><td>DeepSeek-V4-Pro</td><td style="text-align:center">1.6T</td><td style="text-align:center">83.4</td><td style="text-align:center">48.2</td><td style="text-align:center">71.1</td><td style="text-align:center">88.7</td></tr>
<tr><td>MiroThinker-1.7</td><td style="text-align:center">235B</td><td style="text-align:center">74.0</td><td style="text-align:center">42.9</td><td style="text-align:center">82.7</td><td style="text-align:center">72.1</td></tr>
<tr><td>XYZ-Aquila-pro</td><td style="text-align:center">397B</td><td style="text-align:center">84.8</td><td style="text-align:center">53.3</td><td style="text-align:center">-</td><td style="text-align:center">92.5</td></tr>
<tr><td>Iris-pro</td><td style="text-align:center">397B</td><td style="text-align:center">88.6</td><td style="text-align:center">56.4</td><td style="text-align:center">-</td><td style="text-align:center">92.9</td></tr>
<tr><td>AREX-Base</td><td style="text-align:center">122B</td><td style="text-align:center">82.5</td><td style="text-align:center">52.4</td><td style="text-align:center">85.4</td><td style="text-align:center">89.9</td></tr>
<tr><td colspan="6" style="padding:8px 10px;font-weight:600;color:#0F766E;background:rgba(15,118,110,.1)">Small models (&le;40B)</td></tr>
<tr><td>Tongyi-DeepResearch-30B</td><td style="text-align:center">30B</td><td style="text-align:center">43.4</td><td style="text-align:center">32.9</td><td style="text-align:center">70.9</td><td style="text-align:center">-</td></tr>
<tr><td>Qwen3.5-35B</td><td style="text-align:center">35B</td><td style="text-align:center">61.0</td><td style="text-align:center">47.4</td><td style="text-align:center">80.0</td><td style="text-align:center">68.5</td></tr>
<tr><td>XYZ-Aquila-mini</td><td style="text-align:center">35B</td><td style="text-align:center">78.8</td><td style="text-align:center">51.1</td><td style="text-align:center">97.1</td><td style="text-align:center">89.5</td></tr>
<tr><td>BigBang-V1</td><td style="text-align:center">35B</td><td style="text-align:center">76.5</td><td style="text-align:center">50.3</td><td style="text-align:center">-</td><td style="text-align:center">-</td></tr>
<tr><td>Quest-35B</td><td style="text-align:center">35B</td><td style="text-align:center">64.6</td><td style="text-align:center">37.2</td><td style="text-align:center">80.8</td><td style="text-align:center">-</td></tr>
<tr><td>Apodex-1.0-mini</td><td style="text-align:center">35B</td><td style="text-align:center">71.5</td><td style="text-align:center">46.8</td><td style="text-align:center">-</td><td style="text-align:center">82.2</td></tr>
<tr><td>Agents-A1</td><td style="text-align:center">35B</td><td style="text-align:center">75.5</td><td style="text-align:center">47.6</td><td style="text-align:center">96.0</td><td style="text-align:center">-</td></tr>
<tr><td>MiroThinker-1.7-mini</td><td style="text-align:center">30B</td><td style="text-align:center">67.9</td><td style="text-align:center">36.4</td><td style="text-align:center">80.3</td><td style="text-align:center">67.9</td></tr>
<tr><td>Iris-mini</td><td style="text-align:center">35B</td><td style="text-align:center">82.2</td><td style="text-align:center">52.3</td><td style="text-align:center">-</td><td style="text-align:center">86.9</td></tr>
<tr><td>AREX-Turbo</td><td style="text-align:center">4B</td><td style="text-align:center">70.7</td><td style="text-align:center">40.6</td><td style="text-align:center">81.6</td><td style="text-align:center">78.5</td></tr>
<tr style="background:rgba(15,118,110,.12);font-weight:700;color:#0F766E"><td>AREX-2</td><td style="text-align:center">27B</td><td style="text-align:center">84.0</td><td style="text-align:center">52.6</td><td style="text-align:center">92.2</td><td style="text-align:center">93.8</td></tr>
</tbody>
</table>

<small>HLE values marked * are from the full HLE set; unmarked values use the
text-only subset.</small>

## Inference

Use a recent Transformers release with Qwen3.8 support.

```bash
pip install -U torch transformers accelerate
```

```python
import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor

model_id = "BAAI/AREX-2"
processor = AutoProcessor.from_pretrained(model_id)
model = AutoModelForMultimodalLM.from_pretrained(
    model_id, dtype=torch.bfloat16, device_map="auto"
)

messages = [{
    "role": "user",
    "content": "Propose a solution and explain how you would improve it over several rounds.",
}]
inputs = processor.apply_chat_template(
    messages, add_generation_prompt=True, tokenize=True,
    return_dict=True, return_tensors="pt",
).to(model.device)

with torch.inference_mode():
    outputs = model.generate(**inputs, max_new_tokens=1024)
print(processor.decode(
    outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True
))
```

## Intended use

AREX-2 is intended for research on long-horizon agents, iterative problem
solving, machine-learning engineering, algorithmic coding, and tool-augmented
deep research.

## License

AREX-2 is released under the [Apache License 2.0](LICENSE). Follow the terms
and notices for the Qwen base model and any downstream data or tools.

## Citation

```bibtex
@article{2026arex2,
  title   = {AREX-2: Advancing Self-Improving Agents through Long-Horizon Reflective Tasks},
  author  = {Qian, Hongjin and Li, Chaofan and Luo, Kun and Wei, Wenqing and Chen, Jianlyu and Lu, Shuqi and Hu, Yuyang and Xiao, Hongwang and Wang, Hui and Li, Chaozhuo and Ye, Qiwei and Dou, Zhicheng and Lian, Defu and Liu, Zheng},
  journal = {arXiv preprint arXiv:2609.38288},
  year    = {2026},
  url     = {https://arxiv.org/abs/2609.38288}
}
```
