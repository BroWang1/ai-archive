---
license: apache-2.0
base_model: Qwen/Qwen3-8B-Base
tags:
  - interpretability
  - mechanistic-interpretability
  - transcoder
  - cross-layer-transcoder
---

# Cross-Layer Transcoder for Qwen3-8B-Base

A cross-layer transcoder (CLT) for [Qwen3-8B-Base](https://huggingface.co/Qwen/Qwen3-8B-Base): 36 layers × 32,768 latents. Each layer's latents read the residual stream right before that layer's MLP (`resid_mid`) and write to the MLP outputs (`mlp_out`) of that layer and every later layer. 94.2B parameters, fp32, 377 GB in total.

## Format

| File | Contents |
|---|---|
| `W_enc_{l}.safetensors` (l = 0..35) | `W_enc_{l}`: `[32768, 4096]`, encoder of layer `l` |
| `W_dec_{l}.safetensors` (l = 0..35) | `W_dec_{l}`: `[32768, 36 - l, 4096]`; `W_dec_norm_{l}`: `[32768]` (357 GB, decoding only) |
| `W_dec_norm.safetensors` | `W_dec_norm`: `[36, 32768]`, decoder-column norms for scoring |
| `factors.safetensors` | `resid_mid_l2`, `mlp_out_l2`: `[36]`, mean activation norms |
| `config.json` | `d_feature` (32768), `k` (10), base model and dimensions |

Hooks on the base model: `resid_mid` is the input of `model.layers[l].post_attention_layernorm`; `mlp_out` is the output of `model.layers[l].mlp`.

- **Encode:** `a_l = ReLU(W_enc_l · x_l)` (no bias). Score each latent as `a_l[i] · W_dec_norm[l, i]` and keep the `36 · k = 360` highest-scoring latents across all layers jointly.
- **Decode:** `mlp_out_hat[m] = Σ_{l ≤ m} a_l @ W_dec_{l}[:, m - l, :]`.
- The activation normalization used in training is already folded into the weights: the CLT takes **raw** `resid_mid` and reconstructs **raw** `mlp_out`. Do not apply the factors in `factors.safetensors` again.
- Tokens whose `resid_mid` or `mlp_out` norm on any layer reaches 20× that layer's mean norm are dropped, as in training (in practice the first token).
- The CLT was trained on fp32 activations; use fp32 for the base model too.

## Demo

Download the checkpoint, save the code below as `hf_encode_demo.py` next to the downloaded `clt/` directory, and run it:

```bash
huggingface-cli download ByteDance-Seed/Cross-Layer-TopK-CLT --local-dir clt
torchrun --nproc_per_node 8 hf_encode_demo.py
```

The demo encodes a hardcoded sentence, prints the active latents of every token, and decodes them back to `mlp_out`. Latents are split evenly across GPUs (any count dividing 32,768). Output (`latent_id:activation`, strongest first, ids are per layer):

```
[0] 'Let': dropped as outlier
[1] "'s"  (layer: latent_id:activation ...)
  L00: 14503:23.44 9681:11.48 11356:8.68 24242:7.10 ...
  ...
Reconstructed mlp_out (positions, layers, d_model): (7, 36, 4096)
```

In code, the result is `activations[pos][layer] = [[latent_id, activation], ...]` (`None` for outliers) and the reconstruction is `mlp_out_hat_nxlxh`.

To only encode, set `DECODE = False` in the code and skip the decoder files; one 80 GB GPU (`--nproc_per_node 1`) is then enough:

```bash
huggingface-cli download ByteDance-Seed/Cross-Layer-TopK-CLT --exclude "W_dec_[0-9]*" --local-dir clt
```

```python
# Copyright (c) 2026 ByteDance and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Encode text with the Qwen3-8B-Base Cross-Layer Transcoder on multiple GPUs.

    torchrun --nproc_per_node 8 hf_encode_demo.py

Each GPU holds 1/N of every layer's latents. A token keeps its n_layers * k
latents with the largest activation * ||W_dec|| across all layers jointly.
"""
import json
import os

import torch
import torch.distributed as dist
from safetensors import safe_open
from transformers import AutoModelForCausalLM, AutoTokenizer

CLT_PATH = "clt"
LLM_PATH = "Qwen/Qwen3-8B-Base"
TEXT = "Let's go play rhythm games."
DECODE = True  # reconstruct mlp_out from the latents; needs the W_dec_*.safetensors files (357 GB)

dist.init_process_group("nccl")
rank, world_size = dist.get_rank(), dist.get_world_size()
device = torch.device("cuda", int(os.environ["LOCAL_RANK"]))
torch.cuda.set_device(device)
torch.set_grad_enabled(False)

# This GPU's slice of the latents. Activation scaling is folded into the weights.
config = json.load(open(f"{CLT_PATH}/config.json"))
d_feature, k = config["d_feature"], config["k"]
f_local = d_feature // world_size
lo = rank * f_local


def read_rows(name):
    with safe_open(f"{CLT_PATH}/{name}.safetensors", "pt") as f:
        return f.get_slice(name)[lo:lo + f_local].float().to(device)


with safe_open(f"{CLT_PATH}/W_dec_norm.safetensors", "pt") as f:
    W_dec_norm_lxf = f.get_slice("W_dec_norm")[:, lo:lo + f_local].float().to(device)
n_layers = W_dec_norm_lxf.shape[0]
W_enc_lxfxh = torch.stack([read_rows(f"W_enc_{l}") for l in range(n_layers)])
with safe_open(f"{CLT_PATH}/factors.safetensors", "pt") as f:
    mean_norm_2xl = torch.stack([f.get_tensor("resid_mid_l2"), f.get_tensor("mlp_out_l2")])[:, :n_layers].to(device)

# Hook the MLP input (resid_mid) and output (mlp_out) of every layer. The CLT was trained on fp32 activations.
tokenizer = AutoTokenizer.from_pretrained(LLM_PATH)
llm = AutoModelForCausalLM.from_pretrained(LLM_PATH, torch_dtype=torch.float32).to(device)
resid_mid, mlp_out = [], []
for layer in llm.model.layers[:n_layers]:
    layer.post_attention_layernorm.register_forward_pre_hook(lambda m, args: resid_mid.append(args[0][0]))
    layer.mlp.register_forward_hook(lambda m, args, out: mlp_out.append(out[0]))
input_ids = tokenizer(TEXT, return_tensors="pt").input_ids.to(device)
llm.model(input_ids)
resid_mid_nxlxh, mlp_out_nxlxh = torch.stack(resid_mid, dim=1), torch.stack(mlp_out, dim=1)
del llm

# As in training, drop tokens whose norm on any layer reaches 20x the mean (in practice the first token).
norm_2xnxl = torch.stack([resid_mid_nxlxh.norm(dim=-1), mlp_out_nxlxh.norm(dim=-1)])
outlier_n = (norm_2xnxl >= 20 * mean_norm_2xl[:, None]).any(dim=2).any(dim=0)

# Local top-K candidates (score, activation, layer * d_feature + latent_id), then the global top-K.
K = n_layers * k
acts_nxlf = torch.relu(torch.einsum("nlh,lfh->nlf", resid_mid_nxlxh, W_enc_lxfxh)).flatten(1)
score_nxk, idx_nxk = (acts_nxlf * W_dec_norm_lxf.flatten()).topk(K)
gid_nxk = idx_nxk // f_local * d_feature + lo + idx_nxk % f_local
cand_nxkx3 = torch.stack([score_nxk, acts_nxlf.gather(1, idx_nxk), gid_nxk.float()], dim=-1)
gathered = [torch.empty_like(cand_nxkx3) for _ in range(world_size)]
dist.all_gather(gathered, cand_nxkx3)
cand_nxwkx3 = torch.cat(gathered, dim=1)
top_nxkx3 = cand_nxwkx3.gather(1, cand_nxwkx3[..., 0].topk(K).indices[..., None].expand(-1, -1, 3))

if DECODE:
    # Each GPU decodes the selected latents it owns, streaming W_dec one layer at a time; then sum over GPUs.
    # Latents of layer l write to the mlp_out of layers l..n_layers-1.
    n = input_ids.shape[1]
    act_nxk, gid_nxk = top_nxkx3[..., 1], top_nxkx3[..., 2].long()
    layer_nxk, latent_nxk = gid_nxk // d_feature, gid_nxk % d_feature - lo
    mine_nxk = (latent_nxk >= 0) & (latent_nxk < f_local)
    pos_nxk = torch.arange(n, device=device)[:, None].expand_as(mine_nxk)
    acts_nxlxf = torch.zeros(n, n_layers, f_local, device=device)
    acts_nxlxf[pos_nxk[mine_nxk], layer_nxk[mine_nxk], latent_nxk[mine_nxk]] = act_nxk[mine_nxk]
    mlp_out_hat_nxlxh = torch.zeros_like(mlp_out_nxlxh)
    for l in range(n_layers):
        mlp_out_hat_nxlxh[:, l:] += torch.einsum("nf,fth->nth", acts_nxlxf[:, l], read_rows(f"W_dec_{l}"))
    dist.all_reduce(mlp_out_hat_nxlxh)

if rank == 0:
    # activations[pos][layer] = [[latent_id, activation], ...], strongest first; None for outliers.
    activations = []
    for top_kx3, is_outlier in zip(top_nxkx3.tolist(), outlier_n.tolist()):
        per_layer = [[] for _ in range(n_layers)]
        for _, act, gid in sorted(top_kx3, key=lambda x: -x[1]):
            if act > 0:
                per_layer[int(gid) // d_feature].append([int(gid) % d_feature, round(act, 4)])
        activations.append(None if is_outlier else per_layer)

    for pos, per_layer in enumerate(activations):
        token = tokenizer.decode(input_ids[0, pos])
        if per_layer is None:
            print(f"[{pos}] {token!r}: dropped as outlier")
            continue
        print(f"[{pos}] {token!r}  (layer: latent_id:activation ...)")
        for layer, feats in enumerate(per_layer):
            if feats:
                print(f"  L{layer:02d}: " + " ".join(f"{i}:{a:.2f}" for i, a in feats))
    if DECODE:
        print("Reconstructed mlp_out (positions, layers, d_model):", tuple(mlp_out_hat_nxlxh.shape))

dist.destroy_process_group()
```

## Training data and license

Trained on Dolma 3, Dolci-Think and Dolci-Instruct, mixed 5 : 2 : 1 by tokens (≈3.4B tokens). These datasets are licensed under ODC-BY.

The weights and code are released under the [Apache License 2.0](LICENSE), Copyright 2026 ByteDance and/or its affiliates.
