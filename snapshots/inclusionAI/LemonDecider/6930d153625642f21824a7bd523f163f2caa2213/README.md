---
license: apache-2.0
base_model: Qwen/Qwen3.5-4B
library_name: transformers
tags:
  - jev
  - decision
  - autojev
  - typed-decision
  - classification
  - distillation
---

# LemonDecider

A typed decision engine derived from [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B): it answers structured **choice / noul / score** questions in a **single forward pass** with an explicit **unknown** (abstention) candidate. There is no autoregressive generation head — the backbone is kept full-weight, and a 255-way single-token readout replaces the LM head.

## Model description

| Property | Value |
|---|---|
| Architecture | `AutoJevForDecisionClassification` (custom code, `trust_remote_code=True`) |
| Base model | `Qwen/Qwen3.5-4B` (Qwen3.5 text + vision backbones) |
| Parameters | ~4B backbone + 255×2560 readout head |
| Readout | 255 single-token answer codes (`A` … `JT`), initialized from the Qwen LM-head rows of those tokens |
| Decision head | `Linear(hidden_size=2560, 255, bias=False)` over the last prompt position |
| Dtype / context | `bfloat16`; `max_input_length = 8192` (**no silent truncation**) |
| Options per question | 1–255 (`option_counts` required per row; invalid option logits are masked) |
| Multimodal | Optional images (PIL, decoded) via the Qwen3 vision processor |
| Serving temperature | `1.0` (post-processing softmax only; **not** used in CE loss) |

Each input is rendered as one user message (state + instructions + options + an appended `__unknown__` slot), then scored in one forward pass. The forward pass rejects KV-cache decoding and right padding (left padding is required).

## Question types and output semantics

`decision_utils.py` implements the native `_known()` semantics: probabilities over known candidates are renormalized, and the unknown slot gets its own probability.

| `question.type` | Candidates | Output |
|---|---|---|
| `choice` | 1–254 named options (+unknown) | `choice` (argmax key), per-option `probabilities`, `confidence` |
| `noul` | `true`, `false` (+unknown) | `noul = P(true) + 0.5 * P(unknown)` |
| `score` | 2–10 ordered descriptions (+unknown) | `score = Σ i · P(i)` plus legend and probabilities |
| — | — | `abstained = True` iff the raw argmax lands on `unknown`; `unknown_probability` is always returned |

`confidence = concentration · (1 − P(unknown))`, where `concentration = (n·p_max − 1)/(n − 1)` (1 for single-candidate questions).

## Quickstart

**Standalone CLI** (bundled `model.py`):

```bash
python model.py --checkpoint . \
  --input inputs.json \
  --device cuda:0
```

**With transformers**:

```python
import torch
from transformers import AutoModel, AutoProcessor
from decision_utils import predict_batch

model = AutoModel.from_pretrained(
    "inclusionAI/LemonDecider",
    trust_remote_code=True,
    dtype=torch.bfloat16,
    device_map="cuda:0",
    attn_implementation="sdpa",
).eval()
processor = AutoProcessor.from_pretrained(
    "inclusionAI/LemonDecider", trust_remote_code=True
)
processor.tokenizer.padding_side = "left"

rows = [{
    "state": "我想申请退款。",
    "question": {
        "type": "choice",
        "instructions": "判断主要诉求",
        "criteria": {
            "refund": "退款相关",
            "delivery": "物流相关",
            "account": "账户相关",
        },
    },
}]

result = predict_batch(model, processor, rows)
print(result["answers"][0])
# {"type": "choice", "choice": "refund", "probabilities": {...},
#  "confidence": ..., "unknown_probability": ..., "abstained": ...}
```

Images are passed as decoded `PIL.Image` objects in `row["images"]`; paths/URLs are not fetched.

## Training

Distilled via supervised fine-tuning from **imajev-4b**, a larger Jev-class decision model:

- **Checkpoint**: step 24 (6,144 examples seen)
- **Loss**: cross-entropy over the masked 255-way readout (supports hard option indices and soft teacher distributions)
- **Dev set (n=574) accuracy@T=1**: `0.7735` (best step: 3, `0.7805`)

**Temperature fit (not applied)**: an NLL scan over `T ∈ [0.30, 5.00]` on the dev set found `T = 0.60` (NLL `0.56265`, Brier `0.28261`, vs `0.6016 / 0.29885` at `T=1`). The checkpoint still **serves at `T = 1.0`**; adopting `T*` is deliberately blocked until the public evaluation suite is re-evaluated (argmax is invariant at `T*` except at the noul decision boundary).

## Intended use and limitations

- Intended for **typed decision inputs** (`choice` / `noul` / `score`) rendered through `decision_utils.decision_messages()`; prompt-layout divergence will degrade results.
- It is **not** a generative chat model: never use it for free-form text generation.
- Results come from a small internal dev split (n=574); validate on your own distribution before production use.
- Long inputs are rejected above 8,192 tokens instead of being silently truncated; handle your own context budget upstream.

## Files

| File | Purpose |
|---|---|
| `model-00001/2-of-00002.safetensors`(+`index`) | Weights (bfloat16) |
| `configuration_autojev.py` / `modeling_autojev.py` | Custom architecture (decision forward, option masking, hard/soft-target loss) |
| `decision_utils.py` | Prompt rendering, `_known()` scoring, batching (`prepare_batch` / `predict_batch`) |
| `model.py` | Standalone inference CLI |
| `chat_template.jinja`, `processor_config.json` | Qwen3-style chat template and image processor |
| `sft_receipt.json` | Training artifact receipt (step, dev metrics, temperature fit) |

## License

Apache-2.0 (see `LICENSE` / `LICENSE.code`).
