---
library_name: gguf
tags:
- gguf
- decision-model
- typed-decisions
- multimodal
- qwen3_5
---

# SingVL-4B GGUF

SingVL-4B GGUF is the GGUF release of Sing VL S1, a 4B-parameter multimodal decision model built on Qwen3.5. It answers named questions over text or JSON and up to four images. Each question uses one complete forward pass to score the supplied options.

- **Choice** selects an option and returns a probability for each candidate.
- **Noul** returns the probability that a yes/no proposition is true.
- **Score** rates the input against 2–10 levels ordered from low to high. It returns the probability of each level and the expected level, computed as the sum of each zero-based level index times its probability.

Full-attention layers use bidirectional attention over the complete input. GDN layers keep causal recurrence. Each question starts with cleared KV and recurrent state, and reads candidate logits at the last valid input position. The included llama.cpp adapter applies this attention contract automatically.


## Public Decision Index 0.3

| Panel | Sing VL S1 | TypeSafe Jev 1.14 | StartLux-Decision v1.1 4B |Perplexity Decider Flash v1.2 (4B) |
| :---: | ---: | ---: | ---: | ---: |
| Text | **69.76** | 60.70 | 67.8 | 60.1 |
| Vision | **73.94** | — | 67.90 |72.5 |

These reference scores come from the source model's full public rerun, covering 140,178 text requests and 12,210 vision requests. GGUF validation currently covers 9 examples and 11 questions across BF16, Q8_0 and Q4_K_M. Full public scores for the GGUF variants remain pending. [Source model results](evaluation/transformers-reference/PUBLIC_RESULTS.md) · [GGUF validation record](validation/release_validation.json)

## GGUF files

| File | Precision | Size |
|---|---|---:|
| `models/SingVL-4B-BF16.gguf` | BF16 decoder | 8.42 GB |
| `models/SingVL-4B-Q8_0.gguf` | Q8_0 decoder | 4.48 GB |
| `models/SingVL-4B-Q4_K_M.gguf` | Q4_K_M decoder | 2.71 GB |
| `models/mmproj-SingVL-4B-F16.gguf` | Shared F16 vision projector | 0.67 GB |

Select one decoder and use the shared vision projector. Checksums and exact byte sizes are in `manifest.json`.

## Usage

The included backend uses llama.cpp on Linux x86_64 CPU. Use Python 3.12 and compatible PyTorch and torchvision builds for input processing. Build the adapter once using the pinned llama.cpp commit, then run the Python or HTTP examples from this repository's root directory. The default context capacity is 4096 tokens, including image tokens. [Build instructions](docs/build.md)

### Python

```python
import os
from PIL import Image
from examples.llama_cpp.model import SingVLS1

os.environ["JEV_GGUF_MODEL"] = "models/SingVL-4B-Q8_0.gguf"
os.environ["JEV_GGUF_MMPROJ"] = "models/mmproj-SingVL-4B-F16.gguf"
os.environ["JEV_CPU_CONTEXT"] = "4096"
os.environ["JEV_CPU_THREADS"] = "8"

model = SingVLS1("config", device="cpu")
try:
    text, _ = model.predict(
        state="The color is red. ",
        questions={
            "color": {
                "type": "choice",
                "instructions": "Which color is named?",
                "criteria": {"red": "Red", "blue": "Blue"},
            },
            "yesno": {"type": "noul", "instructions": "Is the named color red?"},
            "redness": {
                "type": "score",
                "instructions": "How clearly does the text identify the color as red?",
                "criteria": ["Not red", "Possibly red", "Clearly red"],
            },
        },
    )
    print(text["answers"])

    questions = {
        "which": {
            "type": "choice",
            "instructions": "Which image is red?",
            "criteria": {"first": "The first image", "second": "The second image"},
        }
    }
    with Image.open("examples/images/blue.png") as blue, Image.open("examples/images/red.png") as red:
        for state in ({}, "<image>\n<image>\n"):
            vision, _ = model.predict(state=state, questions=questions, images=[blue, red])
            print(vision["answers"])
finally:
    model.close()
```

With implicit image placement, the processor inserts image markers before the state text. Explicit `<image>` markers match the images in list order, with one marker per image. State and question instructions are concatenated, so retain a trailing space or newline in a text state when a separator is needed.

Score questions use the same format for text and images. The response includes `score`, `probabilities` and `legend`. Probabilities of `0.1`, `0.3` and `0.6` on three levels give `0 × 0.1 + 1 × 0.3 + 2 × 0.6 = 1.5`.

### HTTP API

Start the FastAPI service after building the adapter. The server prints its attention and context settings during startup and exposes them at `/health`. Interactive API documentation is available at `/docs`.

```bash
export JEV_GGUF_MODEL="$PWD/models/SingVL-4B-Q8_0.gguf"
export JEV_GGUF_MMPROJ="$PWD/models/mmproj-SingVL-4B-F16.gguf"
export JEV_CPU_CONTEXT=4096
export JEV_CPU_THREADS=8
export OMP_NUM_THREADS=8

python examples/llama_cpp/serve.py --model "$PWD/config" \
  --device cpu --port 8173 --image-root "$PWD/examples/images"
```

Send a text request from another terminal.

```bash
curl -fsS http://127.0.0.1:8173/v1/systemone \
  -H 'Content-Type: application/json' -d '{
  "model": "sing-vl-s1",
  "state": "The color is red. ",
  "questions": {
    "color": {
      "type": "choice",
      "instructions": "Which color is named?",
      "criteria": {"red": "Red", "blue": "Blue"}
    },
    "yesno": {"type": "noul", "instructions": "Is the named color red?"},
    "redness": {
      "type": "score",
      "instructions": "How clearly does the text identify the color as red?",
      "criteria": ["Not red", "Possibly red", "Clearly red"]
    }
  }
}'
```

For Vision, supply an ordered `images` array. Entries support Base64 data URLs (`data_url`), raw Base64 (`base64`), and server-side file paths (`path`). The path form resolves within `--image-root`.

```bash
curl -fsS http://127.0.0.1:8173/v1/systemone \
  -H 'Content-Type: application/json' -d '{
  "model": "sing-vl-s1",
  "state": {},
  "images": ["blue.png", "red.png"],
  "questions": {
    "which": {
      "type": "choice",
      "instructions": "Which image is red?",
      "criteria": {"first": "The first image", "second": "The second image"}
    }
  }
}'
```

The explicit-marker form uses `"state": "<image>\n<image>\n"` with the same images array. Responses use the supplied question IDs under `answers`. The wire model ID is `sing-vl-s1`. Set `return_details` to `true` to include token and candidate-logit traces. [Protocol reference](docs/protocol.md)

## Package layout

- `models/` contains the three decoder variants and shared vision projector.
- `config/` contains the tokenizer, processor configuration and candidate-token mapping.
- `processing/` contains shared prompt, image and probability processing.
- `examples/llama_cpp/` contains the CPU backend, build script and HTTP service.
- `examples/` contains text and image requests and expected-output examples.
- `validation/` contains the sample references and validation scripts.
- `evaluation/transformers-reference/` contains source-model public results for comparison.
- `docs/build.md` contains the full build procedure and attention contract.
- `licenses/llama.cpp-LICENSE` contains the upstream llama.cpp license.
