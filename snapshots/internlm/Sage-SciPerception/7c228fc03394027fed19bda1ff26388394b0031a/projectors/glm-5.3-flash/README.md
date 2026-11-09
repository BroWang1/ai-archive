# Projector index

Available checkpoints are organized by modality, task, and language-model version. Scientific modalities, tasks, and language-model support will continue to expand. See the [English model card](https://huggingface.co/internlm/Sage-SciPerception#inference) or [中文模型卡](https://huggingface.co/internlm/Sage-SciPerception/blob/main/README_zh.md#推理使用) for inference setup, a vLLM client example, and an optional CPU loading check.

The root [`config.json`](https://huggingface.co/internlm/Sage-SciPerception/blob/main/config.json) maps each projector ID to its task directory. Each task directory contains `projector.safetensors` and its own `config.json`. The configuration declares the architecture, output dimension, scientific inputs, prompt, backbone revision, and training step. Scientific encoder weights and the language backbone are separate dependencies.

| Projector ID | Training step | Weights | Configuration |
|---|---:|---|---|
| `glm-5.3-flash/cif/jarvis` | 2822 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/cif/jarvis/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/cif/jarvis/config.json) |
| `glm-5.3-flash/protein-seq/mpbind` | 100 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/protein-seq/mpbind/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/protein-seq/mpbind/config.json) |
| `glm-5.3-flash/spectra/qm9s` | 8037 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/spectra/qm9s/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/spectra/qm9s/config.json) |
| `glm-5.3-flash/ecg/phu01` | 1068 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/ecg/phu01/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/ecg/phu01/config.json) |
| `glm-5.3-flash/dna/splice` | 50 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/dna/splice/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/dna/splice/config.json) |
| `glm-5.3-flash/eeg/neu06` | 4688 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/eeg/neu06/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/eeg/neu06/config.json) |
| `glm-5.3-flash/rna/ncrna` | 200 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/rna/ncrna/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/rna/ncrna/config.json) |
| `glm-5.3-flash/xrd/simxrd` | 500 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/xrd/simxrd/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/xrd/simxrd/config.json) |
| `glm-5.3-flash/protein-struct/psr` | 200 | [Weights](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/protein-struct/psr/projector.safetensors?download=true) | [config.json](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/protein-struct/psr/config.json) |

## Scientific inputs

The following is an interface summary. Exact feature extraction and preprocessing must match each checkpoint's `scientific_inputs`; arbitrary tensors with the same shape do not reproduce its scientific behavior.

| Task | Input to the projector | Scientific dependency |
|---|---|---|
| `cif/jarvis` | 64-dimensional state per atom, plus per-atom position indices | CHGNet 0.3.0 states entering the energy MLP |
| `protein-seq/mpbind` | 1,280-dimensional state per residue; 2-dimensional side features; residue counts | ESM-2 states plus a task-adapted ESMC readout; the adapted weights and side-feature construction are not included |
| `spectra/qm9s` | 50-dimensional spectral patches, positions, and a 3-way spectrum-type index | DiffSpectra-style `log10(x + 1)` transform and patch geometry for IR, Raman, and UV-Vis |
| `ecg/phu01` | 768-dimensional cached position features | The ECG encoder/cache pipeline used for the released checkpoint; extraction runner is not included |
| `dna/splice` | One 3-dimensional probability readout | Task-adapted DNABERT-2; its scientific weights are not included |
| `eeg/neu06` | 512-dimensional patch states with matching electrode and time positions | REVE-base with the position and tail-window handling declared in the configuration |
| `rna/ncrna` | 640-dimensional RNA-FM state per nucleotide; 13-dimensional side input | RNA-FM plus a task-adapted RiNALMo ensemble readout; adapted weights and the full ensemble preprocessing are not included |
| `xrd/simxrd` | 110 convolutional states, each 512-dimensional | The legacy XRD CNN and its normalized 3,501-point, square-root input pipeline; scientific weights are not included |
| `protein-struct/psr` | 384-dimensional state per residue/bin | ProteinMPNN v48-020; concatenate its three encoder layers, then use at most 256 contiguous mean bins |

The task-adapted scientific checkpoint paths in the configurations describe dependencies; those paths are not downloadable encoder directories in this release. Some encoder metadata records an upstream component but not the complete preparation pipeline. The [vLLM crystal example](https://huggingface.co/internlm/Sage-SciPerception/blob/main/examples/vllm_cif.py) shows the serving path from prepared features; raw scientific inputs require the matching preprocessing pipeline.

## Downloading and loading

After downloading the two root Python modules, install `torch`, `safetensors`, and `huggingface_hub`. Select a projector by its ID from the table:

```python
from load_projector import download_projector, load_projector

component_dir = download_projector("glm-5.3-flash/cif/jarvis", local_dir=".")
projector, config = load_projector(component_dir, device="cpu")
```

`download_projector` reads the repository's root index, selects the component path, and downloads its configuration and weights from that same revision. Omit `local_dir` to use the Hugging Face cache, or pass `revision` to select a release. From the shell, the equivalent download is:

```bash
python load_projector.py glm-5.3-flash/cif/jarvis --local-dir .
```

`load_projector` loads downloaded files locally and returns a frozen projector in evaluation mode and its configuration. It does not download scientific encoders or the language backbone. Consult the scientific input table before preparing predictions.

For integration questions or missing assets, [open a GitHub issue](https://github.com/InternLM/Sage-SciPerception/issues/new) with the task, input format, and the step you want to run.
