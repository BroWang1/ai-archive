---
language:
  - en
  - zh
tags:
  - scientific-perception
  - multimodal
  - projector
  - pytorch
  - chemistry
  - biology
  - materials-science
  - time-series
thumbnail: https://huggingface.co/internlm/Sage-SciPerception/resolve/main/assets/branding/sage-sciprojector-hero-titled.png
---

<h1 align="center">Sage-SciPerception</h1>
<p align="center"><strong>Scientific perception for language models · 书生·元征</strong></p>
<p align="center">Connect crystals, spectra, biological sequences, and biosignals to language models through trained projectors.</p>
<p align="center"><strong>Continuously expanding scientific modalities, tasks, and language model support.</strong></p>

<p align="center">
  <a href="#released-projectors">Get weights</a> ·
  <a href="#examples">Examples</a> ·
  <a href="#inference">Inference</a> ·
  <a href="#framework">Framework</a> ·
  <a href="https://github.com/InternLM/Sage-SciPerception">GitHub</a> ·
  <a href="https://huggingface.co/internlm/Sage-SciPerception/blob/main/README_zh.md">简体中文</a>
</p>

<p align="center">
  <img src="assets/branding/sage-sciprojector-hero-titled.png" alt="Sage Sci Perception: a young scholar explores scientific representations." width="640">
</p>

Sage Sci Perception maps scientific representations into a language model's input space, enabling natural-language analysis and structured scientific answers. Use it to explore interfaces between your scientific workflow and a language model: material property prediction, biomolecular sequence labeling, spectral structure identification, and signal classification.

Projectors are organized by modality, task, and language-model version. Start with the available checkpoints below, or use the [inference guide](#inference) to connect projected scientific inputs to a serving workflow. Each checkpoint records its matching language model and input representation in `config.json`.

## Examples

Recorded views of scientific inputs, annotations, and task interfaces. Checkpoint evaluations are listed in [Released projectors](#released-projectors).

<table width="100%">
  <tr>
    <td width="50%" align="center">
      <img src="assets/spectra-en.gif" alt="Joint spectra, streamed analysis, and a predicted molecule." width="100%"><br>
      <b>Three spectra → molecular structure</b><br>
      <sub>IR, Raman and UV–Vis with streamed analysis and a recorded prediction.</sub>
    </td>
    <td width="50%" align="center">
      <img src="assets/protein-en.gif" alt="Protein sequence positions and reference interface annotations." width="100%"><br>
      <b>Protein interface sites</b><br>
      <sub>Sequence positions and reference residue-level annotations.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="assets/crystal-en.gif" alt="Crystal geometry and its reference formation energy." width="100%"><br>
      <b>Crystal structure and formation energy</b><br>
      <sub>Atomic geometry and a reference material property.</sub>
    </td>
    <td width="50%" align="center">
      <img src="assets/rna-iterations-en.gif" alt="Recorded RNA interface experiments and evaluation feedback." width="100%"><br>
      <b>RNA interface refinement</b><br>
      <sub>Design revisions guided by experimental feedback.</sub>
    </td>
  </tr>
</table>

## Released projectors

Open a task to browse its files, or download its weights and configuration directly. Additional modalities, tasks, and compatible language-model versions will be added as the project develops.

| Benchmark / task | Metric ↑ | Score | Projector |
|---|---|---:|---|
| [JARVIS-DFT](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/cif/jarvis)<br>Formation energy | MAD/MAE | **15.03** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/cif/jarvis/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/cif/jarvis/config.json) |
| [MPBind](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/protein-seq/mpbind)<br>PPI interface sites | Per-protein F1 (%) | **61.12** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/protein-seq/mpbind/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/protein-seq/mpbind/config.json) |
| [QM9S](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/spectra/qm9s)<br>Molecular structure identification | Acc@1 (%) | **49.75** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/spectra/qm9s/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/spectra/qm9s/config.json) |
| [SciTS PHU01](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/ecg/phu01)<br>ECG classification | Macro-F1 (%) | **71.53** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/ecg/phu01/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/ecg/phu01/config.json) |
| [GUE splice](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/dna/splice)<br>Splice-site classification | MCC (%) | **87.87** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/dna/splice/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/dna/splice/config.json) |
| [SciTS NEU06](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/eeg/neu06)<br>Sleep staging | Macro-F1 (%) | **72.01** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/eeg/neu06/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/eeg/neu06/config.json) |
| [BEACON ncRNA](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/rna/ncrna)<br>RNA family classification | Accuracy (%) | **97.35** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/rna/ncrna/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/rna/ncrna/config.json) |
| [SimXRD OL](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/xrd/simxrd)<br>Crystal-system classification | Accuracy (%) | **63.60** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/xrd/simxrd/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/xrd/simxrd/config.json) |
| [ATOM3D PSR](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/protein-struct/psr)<br>Protein structure ranking | Spearman (%) | **35.36** | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/protein-struct/psr/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/protein-struct/psr/config.json) |

Scores come from generated answers using each task's selected checkpoint. Metrics differ across rows; **MAD/MAE is a ratio where higher is better**, rather than an error to minimize. MPBind uses the assembly-1 reconstructed evaluation set and mean per-protein F1; PSR uses mean Spearman. Each projector is trained for its respective task.

## Inference

Our serving path inserts the projected scientific vectors into the language model's **full templated prompt embeddings**, then sends them to vLLM through `prompt_embeds` at `/v1/completions`. Text tokens use the matching language model's input embedding table; the scientific span uses the projector output. Scientific feature extraction and projection run in the client, while the language-model service generates the answer.

### 1. Prepare the weights and scientific inputs

The complete [crystal client example](https://huggingface.co/internlm/Sage-SciPerception/blob/main/examples/vllm_cif.py) implements feature projection, native chat-template rendering, text embedding lookup, scientific-span insertion, and the HTTP request. Download the example and loader modules, then select a projector through the repository index:

```bash
python -m pip install torch safetensors huggingface_hub
python -m pip install --upgrade transformers
hf download internlm/Sage-SciPerception \
  examples/vllm_cif.py load_projector.py modeling_projector.py \
  --local-dir ./sage-sciperception
cd sage-sciperception
python load_projector.py glm-5.3-flash/cif/jarvis --local-dir .
```

The download tool reads the root `config.json` to locate the selected projector and retrieves its configuration and weights from the same repository revision. Change the projector ID using the [component index](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/README.md).

Prepare `cif_features.pt` as a PyTorch tensor of shape `[num_atoms, 64]`: the real CHGNet 0.3.0 atom states specified by `cif/jarvis/config.json`, in atom order. The local language-model directory must match the exact revision recorded in the checkpoint's `config.json`. The client reads its tokenizer, configuration, and sharded safetensors input embedding table without loading the full language model.

### 2. Start the vLLM server

In your inference environment, start a compatible vLLM server with `--enable-prompt-embeds`. Choose tensor parallelism for the selected model and your hardware; the command below shows an eight-way deployment example.

```bash
vllm serve /path/to/matching-base-model \
  --served-model-name sage-sciperception \
  --enable-prompt-embeds \
  --tensor-parallel-size 8 \
  --generation-config vllm \
  --max-model-len 8192 \
  --host 127.0.0.1 --port 8000
```

### 3. Generate an answer

Once the server is ready, run the client from the `sage-sciperception` directory prepared in step 1:

```bash
python examples/vllm_cif.py \
  --component ./projectors/glm-5.3-flash/cif/jarvis \
  --base-model /path/to/matching-base-model \
  --features /path/to/cif_features.pt \
  --api-base http://127.0.0.1:8000/v1 \
  --model sage-sciperception
```

The transport core below is an excerpt from the client. `prompt_embeds` already includes the native system, user, and assistant-generation prefixes, with the projector vectors inserted in the scientific span:

```python
buffer = io.BytesIO()
torch.save(prompt_embeds.cpu().contiguous(), buffer)
body = {
    "model": "sage-sciperception",
    "prompt_embeds": base64.b64encode(buffer.getvalue()).decode("ascii"),
    "max_tokens": 4096,
    "temperature": 0,
}
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/completions",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
```

The Completions endpoint consumes the assembled embeddings directly. Keep the checkpoint's system prompt, template options, and scientific input representation when preparing a request. The [component index](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/README.md#scientific-inputs) describes the currently available inputs; the crystal example uses its own task's format. See the [vLLM prompt embedding documentation](https://docs.vllm.ai/en/v0.32.0/features/prompt_embeds/) for the serving interface.

Scientific encoder weights and preprocessing runners are separate dependencies. Task-adapted scientific models for DNA, MPBind, and ncRNA are not yet included here. This inference example starts from prepared scientific features.

### Optional: check projector loading on CPU

From the same downloaded directory, you can verify the projector's parameter count and output dimension on CPU without starting the language-model service:

```python
from load_projector import load_projector

projector, config = load_projector(
    "projectors/glm-5.3-flash/cif/jarvis", device="cpu"
)
print(config["task"])
print(sum(p.numel() for p in projector.parameters()))
print(config["output_dim"])
```

Expected output:

```text
cif/jarvis
4314304
4096
```

For another task, pass its ID from the [component index](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/README.md) to the same download tool. Forward inputs vary by task; consult its scientific input description when preparing predictions.

## Framework

<p align="center">
  <img src="assets/framework-en.gif" alt="Scientific inputs pass through scientific representations and trainable projectors into a language model." width="100%">
</p>

A task-specific projector maps scientific features to the language model's embedding dimension. During the language-mapping stage, the scientific models and language model stay frozen while the projector is trained. Some tasks use scientific models that were adapted to their task beforehand, or combine encoder states with scientific readouts.

## Feedback and next steps

For integration questions, missing assets, or examples you would like to see, [open a GitHub issue](https://github.com/InternLM/Sage-SciPerception/issues/new). Include the task, your scientific input format, and the step you want to run. You can also use the [Hugging Face community tab](https://huggingface.co/internlm/Sage-SciPerception/discussions) for release questions, or follow [InternLM](https://huggingface.co/internlm) for updates.

License metadata has not yet been specified for this release.

## Citation

If you use Sage-SciPerception in your work, please cite:

```bibtex
@misc{sage_sciperception,
  author       = {{InternLM}},
  title        = {{Sage-SciPerception}},
  note         = {GitHub repository},
  year         = {2026},
  url          = {https://github.com/InternLM/Sage-SciPerception}
}
```
