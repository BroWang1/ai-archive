---
license: apache-2.0
base_model: Qwen/Qwen3-30B-A3B
language:
- en
tags:
- sparse-autoencoder
- sae
- interpretability
- mixture-of-experts
- qwen3
---

# Qwen3-30B-A3B MoE-Output Sparse Autoencoders

TopK sparse autoencoders (k = 100, 2^20 latents) trained on the MoE block output of
[Qwen3-30B-A3B](https://huggingface.co/Qwen/Qwen3-30B-A3B) at layers 4, 30 and 46, released with
the paper *Sparse AutoEncoders Reveal That MoE Experts Exhibit Human-Interpretable Fine-Grained
Specialization* ([project page](https://bytedance-seed.github.io/SAE-interprets-MoE/),
[code](https://github.com/ByteDance-Seed/SAE-interprets-MoE), paper: TODO).

## Files

```
layer_4/sae.safetensors     layer_4/config.json
layer_30/sae.safetensors    layer_30/config.json
layer_46/sae.safetensors    layer_46/config.json
```

Each SAE reads the output of `model.model.layers[L].mlp` (the `Qwen3MoeSparseMoeBlock`, before
the residual addition, layers 0-indexed) as is, without any normalization. `sae.safetensors`
(about 17.2 GB) holds four float32 tensors:

| Tensor | Shape |
|--------|-------|
| `W_enc` | `[2048, 1048576]` |
| `b_enc` | `[1048576]` |
| `W_dec` | `[1048576, 2048]`, rows have unit norm |
| `b_dec` | `[2048]` |

```
f     = TopK_100(ReLU(y @ W_enc + b_enc))
y_hat = f @ W_dec + b_dec
```

Latent `i` is column `i` of `W_enc` and row `i` of `W_dec`; the paper writes it as `L-F<i>`, e.g.
`30-F97783`. `config.json` lists the same settings.

## Usage

```python
import torch
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

LAYER, K = 30, 100
DEVICE = "cuda"  # the SAE takes about 17 GB on top of the model

sae = load_file(
    hf_hub_download("ByteDance-Seed/Qwen3-30B-A3B-MoE-SAE", f"layer_{LAYER}/sae.safetensors"),
    device = DEVICE,
)

def encode(y):
    """y: [..., 2048] raw MoE output. Returns the activations and ids of the top-K latents, [..., K]."""
    pre_acts = y.float() @ sae["W_enc"] + sae["b_enc"]
    return torch.topk(torch.relu(pre_acts), K, dim = -1)

def decode(acts, ids):
    return torch.einsum("...k,...kd->...d", acts, sae["W_dec"][ids]) + sae["b_dec"]

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-30B-A3B", torch_dtype = torch.bfloat16, device_map = "auto")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-30B-A3B")

captured = {}
def hook(module, inputs, output):
    # Qwen3MoeSparseMoeBlock returns (hidden_states, router_logits) in transformers 4.x
    captured["y"] = output[0] if isinstance(output, tuple) else output

handle = model.model.layers[LAYER].mlp.register_forward_hook(hook)
inputs = tokenizer("def binary_search(arr, x):", return_tensors = "pt").to(model.device)
with torch.no_grad():
    model(**inputs)
handle.remove()

y = captured["y"][0].to(DEVICE)   # [seq_len, 2048]
acts, ids = encode(y)             # [seq_len, 100] each
y_hat = decode(acts, ids)         # [seq_len, 2048]
```

The dense pre-activation takes 4 MiB per token, so encode long inputs in chunks.

## Training

Each SAE was trained independently on MoE block outputs collected from the Olmo 3 training
corpus: 5/8 Dolma 3 pretraining data, 1/4 Dolci-Think-SFT (reasoning chains of thought) and 1/8
Dolci-Instruct-SFT (instruction following). Training used a TopK activation with k decaying
from 1000 to 100 over the first 10,000 steps, an auxiliary loss, AdamW and about 3.2B tokens
per SAE; the full recipe is given in the appendix "SAE training details" of the paper.

## Evaluation

Fraction of variance unexplained (FVU) of the reconstruction, as reported in the paper:

| Layer | FVU |
|-------|-----|
| 4 | 12.6% |
| 30 | 25.1% |
| 46 | 7.6% |

## License

Apache License 2.0. The base model Qwen3-30B-A3B is released under the Apache License 2.0. The SAEs
were trained on activations computed from Dolma 3, Dolci-Think-SFT and Dolci-Instruct-SFT, which
Ai2 makes available under the [ODC-BY v1.0](https://opendatacommons.org/licenses/by/1-0/) license.

## Citation

```bibtex
@article{zhuo2026moesae,
  title   = {Sparse AutoEncoders Reveal That MoE Experts Exhibit Human-Interpretable Fine-Grained Specialization},
  author  = {Zhuo, Anyuan and Zhang, Shaohua and Lin, Yuan and Lu, Pinyan},
  year    = {2026},
  journal = {TODO}
}
```
