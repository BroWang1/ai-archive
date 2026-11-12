---
library_name: transformers
tags:
- decision-model
- typed-decisions
- multimodal
- safetensors
---

# Sing VL S1

Sing VL S1 is a multimodal decision model built on Qwen3.5. It answers named questions over text or JSON and up to four images. Each question uses a single Transformers forward pass to score the supplied options.

- **Choice** selects an option and returns a probability for each candidate.
- **Noul** returns the probability that a yes/no proposition is true.
- **Score** rates the input against 2–10 levels ordered from low to high. It returns the probability of each level and the expected level, computed as the sum of each zero-based level index times its probability.

## Public Decision Index 0.3

| Panel | Sing VL S1 | TypeSafe Jev 1.14 | StartLux-Decision v1.1 4B |Perplexity Decider Flash v1.2 (4B) |
| :---: | ---: | ---: | ---: | ---: |
| Text | **69.76** | 60.70 | 67.8 | 60.1 |
| Vision | **73.94** | — | 67.90 |72.5 |


### Per-dataset results

<details>
<summary>Show the Vision and Text breakdown</summary>

#### Public Vision (11 datasets)

| Dataset | Non-Skill (Accuracy) | Skill |
| --- | ---: | ---: |
| CV-Bench | 87.34 | 79.12 |
| BLINK | 72.11 | 56.83 |
| RealWorldQA | 82.17 | 70.87 |
| CharXiv | 86.65 | 82.21 |
| InfographicVQA | 96.31 | 95.08 |
| Mind2Web | 87.67 | 83.56 |
| Winoground | 93.12 | 86.25 |
| KIE (CORD+FUNSD) | 95.82 | 93.12 |
| Moderation (Hateful Memes) | 71.64 | 43.28 |
| R-Bench-M | 49.77 | 39.72 |
| MMMU-Pro vision | 50.17 | 42.85 |
| **Public Vision Index** | — | **73.94** |

#### Public Text (43 datasets)

| Dataset | Original metric | Non-Skill | Skill |
| --- | --- | ---: | ---: |
| BFCL | Case exact accuracy | 96.81 | 95.70 |
| ToolRet | nDCG@10 | 67.96 | 63.00 |
| API-Bank | Accuracy | 84.45 | 84.15 |
| BANKING77 | Macro-F1 | 94.00 | 93.92 |
| CLINC150+OOS | Macro-F1 | 97.03 | 97.01 |
| RouterBench † | Selected quality | 79.83 | 52.71 |
| Home appliance simulator | Case exact accuracy | 100.00 | 100.00 |
| SGD/SGD-X † | Macro-F1 | 8.33 | 0.00 |
| ContractNLI | Macro-F1 | 84.05 | 76.94 |
| ANLI | Macro-F1 | 78.29 | 67.48 |
| BPoMP \* | Accuracy | 95.18 | 90.70 |
| Humicroedit | Accuracy | 67.16 | 34.32 |
| POP909-CL \* | Accuracy | 80.60 | 79.74 |
| cfcolor \* | Accuracy | 70.14 | 44.04 |
| MMLU † | Accuracy | 82.93 | 77.24 |
| GPQA Diamond | Accuracy | 53.06 | 37.41 |
| ARC-Easy † | Accuracy | 99.03 | 98.71 |
| ARC-Challenge † | Accuracy | 96.25 | 95.00 |
| WinoGrande | Accuracy | 89.82 | 79.64 |
| HellaSwag | Accuracy | 96.48 | 95.31 |
| GSM8K | Accuracy | 73.84 | 68.68 |
| ChessBench | Accuracy | 26.88 | 20.36 |
| MuSR | Accuracy | 65.82 | 45.66 |
| SATA-Bench | Case exact accuracy | 53.88 | 53.27 |
| SimpleBench † | Accuracy | 50.00 | 40.00 |
| BRIGHT | nDCG@10 | 47.51 | 40.62 |
| Amazon ESCI | Macro-F1 | 60.74 | 50.75 |
| ACOS | Per-review F1 | 64.56 | 63.43 |
| FinEntity | Macro-F1 | 95.19 | 92.93 |
| iSarcasmEval | Sarcasm F1 (A · English) | 64.98 | 54.95 |
| VAST | Macro-F1 | 79.69 | 69.53 |
| NLI4CT | Macro-F1 | 86.41 | 73.56 |
| CRUXEval | Accuracy | 78.07 | 65.21 |
| CLadder | Accuracy | 94.72 | 89.44 |
| HLE | Accuracy | 12.77 | 0.00 |
| Habermas Machine | Accuracy | 63.60 | 47.18 |
| PhishNChips | Accuracy | 85.55 | 71.10 |
| MMLU-Pro | Accuracy | 68.40 | 64.46 |
| BBH | Accuracy | 88.61 | 83.49 |
| RAGTruth | Hallucinated-class F1 | 83.49 | 65.77 |
| HoVer | Accuracy | 89.25 | 78.50 |
| When2Call MCQ | Accuracy | 90.61 | 87.48 |
| New Yorker caption matching | Accuracy | 80.49 | 75.61 |
| **Public Text Index** | **Weighted aggregate** | **77.26** | **69.76** |

† Decision Index reports these datasets separately and excludes them from the Text Index.

</details>

## Usage

Use Python 3.12 and hardware-compatible PyTorch and torchvision builds. From the model repository root, enter `inference/` before running the examples. If you have a standalone copy of the inference code, run the examples from that directory and replace `..` with the checkpoint path.

```bash
cd inference
python -m pip install -r requirements.txt
```

### Python

```python
from PIL import Image

from model import SingVLS1

model = SingVLS1("..", device="cuda:0")

# Text
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

# Images in blue-then-red order. Both state values work.
questions = {
    "which": {
        "type": "choice",
        "instructions": "Which image is red?",
        "criteria": {"first": "The first image", "second": "The second image"},
    }
}
with Image.open("examples/blue.png") as blue, Image.open("examples/red.png") as red:
    for state in ({}, "<image>\n<image>\n"):
        vision, _ = model.predict(state=state, questions=questions, images=[blue, red])
        print(vision["answers"])
```

With no `<image>` markers, the model inserts them before the state text. With explicit markers, use one per image. The markers match the images in list order.

Use the same `score` question format with images. The answer includes `probabilities` and a `legend`, both keyed by the zero-based level number as a string. For example, probabilities of `0.1`, `0.3`, and `0.6` on three levels give `0 × 0.1 + 1 × 0.3 + 2 × 0.6 = 1.5`.

### HTTP API

Start the FastAPI server. Send requests to `POST http://127.0.0.1:8173/v1/systemone` from another terminal on the same machine. Interactive API docs are at `http://127.0.0.1:8173/docs`.

```bash
python serve.py --model .. --port 8173 --image-root ./examples
```

Send a text request with an inline JSON body.

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

For a Vision request, add an ordered `images` array. Its entries can be Base64 data URLs (`data_url`), raw Base64 strings (`base64`), or server-side file paths (`path`). Paths are relative to `--image-root` or absolute paths inside that directory. With the server command above, send the example filenames directly.

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

For the same request with explicit image markers, use `"state": "<image>\n<image>\n"`.

The response puts results under `answers` using the supplied question IDs. The text example selects `red` and returns `answers.redness.score` on a 0–2 scale. The Vision example selects `second`.

## Decision Index compatibility and submission

Start the HTTP service above and prepare both Public 0.3 suites using the [Decision Index kit](https://github.com/apolinario/decision-index#quickstart-local) and the [Vision build instructions](https://github.com/apolinario/decision-index/blob/main/docs/vision.md#rebuild). Run the ni qcommands below from the evaluation workspace on the same machine. Text uses `http`, which calls `/v1/systemone`. Vision uses `decide` with the `decisions` payload and an explicit path to the same endpoint. The runner sends images as data URLs and resizes images above 1,638,400 pixels before sending them.

```bash
python -m decision_index pipeline --edition 0.3 --suite-dir suite-0.3 \
  --engine http --option base_url=http://127.0.0.1:8173 \
  --option model=sing-vl-s1 --out runs/sing-vl-s1-text

python -m decision_index vision pipeline --dir work/vision \
  --engine decide --workers 1 --option base_url=http://127.0.0.1:8173 \
  --option model=sing-vl-s1 --option protocol=decisions \
  --option path=/v1/systemone --option image_encoding=data_url \
  --option max_pixels=1638400 --out runs/sing-vl-s1-vision
```

1. Put the exact checkpoint revision, processor, and inference code in a Hugging Face model repository that the maintainers can access.
2. Upload the untouched run directories to a Hugging Face dataset. Include the per-request `results.jsonl` and run metadata. Check that Text `scores.json` and Vision `vision-scores.json` both report `"complete": true`. The Vision `environment.json` records the effective image budget.
3. Open a pull request to `apolinario/decision-index` and add the Text and Vision entries to `submissions/README.md`, marking the Vision entry `vision`. Include the model revision, results links, evaluation kit commit, hardware, engine options, and capacity limits. Sing VL S1 accepts up to four images per request, with a per-question input limit of 65,536 tokens for text or 10,000 with images.
