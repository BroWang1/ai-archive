---
library_name: transformers
language:
  - en
  - zh
tags:
  - mathematics
  - proof-verification
  - advancedmathbench
  - qwen3_5_moe
---
# AdvancedMathBench AutoVerifier

[Paper](https://arxiv.org/abs/2607.11849) ·
[HF Paper](https://huggingface.co/papers/2607.11849) ·
[GitHub](https://github.com/InternLM/AdvancedMathBench) ·
[Dataset](https://huggingface.co/datasets/debouter/AdvancedMathBench) ·
[AutoVerifier](https://huggingface.co/debouter/AdvancedMathBench-AutoVerifier)

AutoVerifier evaluates natural-language mathematical proofs, explains errors,
and identifies the earliest incorrect step. It serves as the automatic grader
for AdvancedMathBench's ProverBench.

## Model

- Architecture: `Qwen3_5MoeForConditionalGeneration`.
- Tokenizer: bundled `InternS1Tokenizer`; requires `sentencepiece` and
  `trust_remote_code=True` after reviewing the tokenizer code.
- Weights: 40 safetensors shards, approximately 68 GiB.

## Input

Use [proof_verifier.md](prompts/proof_verifier.md) with a problem, an optional
reference solution, and a candidate proof split into zero-indexed steps.
The following constructs the input without loading the model weights:

```python
from pathlib import Path
from transformers import AutoTokenizer

model_dir = "."  # Local model repository directory
tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)

steps = ["A candidate proof step.", "Another candidate proof step."]
proof = "\n\n".join(
    f"<step{i}>\n\n{step}\n\n</step{i}>" for i, step in enumerate(steps)
)
template = Path(model_dir, "prompts/proof_verifier.md").read_text(encoding="utf-8")
prompt = template.format(
    problem="The mathematical problem.", human_solution="", solution=proof,
)
text = tokenizer.apply_chat_template(
    [{"role": "user", "content": prompt}],
    tokenize=False, add_generation_prompt=True, enable_thinking=True,
)
```

## Output and scoring

The final response contains an assessment, identified errors, and the first
error index. For example, a no-error judgment is:

```xml
<assessment>The proof is correct.</assessment>
<errors></errors>
<first_error_step>-1</first_error_step>
```

`-1` means no error was found; nonnegative indices identify the earliest error,
starting from **0**. Parse the final answer after `</think>` when present.

ProverBench checks each proof **8 times** and accepts it only when all eight
valid judgments report `-1`. Missing or malformed judgments do not count as
acceptance. Sampling settings are documented in
[evaluation_settings.json](evaluation_settings.json).

## Notes

AutoVerifier is a learned grader, not a formal proof checker, and can make errors.
Tested package versions and validation scope are recorded in
[compatibility.json](compatibility.json). License notices are provided in [LICENSE](LICENSE) and
[NOTICE.md](NOTICE.md).

## Citation

If you use AdvancedMathBench AutoVerifier in your research, please cite:

```bibtex
@misc{kong2026advancedmathbenchbenchmarksuiteadvanced,
  title = {AdvancedMathBench: A Benchmark Suite for Advanced Mathematical Proof Generation and Verification},
  author = {Lingkai Kong and Zijian Wu and Yuzhe Gu and Haiteng Zhao and Wenyong Huang and Shuang Sun and Zhicheng Xiong and Xiaotian Zhang and Shuya Zhao and Yan Wang and Disheng Xu and Wenwei Zhang and Kai Chen},
  year = {2026},
  eprint = {2607.11849},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL},
  doi = {10.48550/arXiv.2607.11849},
  url = {https://arxiv.org/abs/2607.11849}
}
```
