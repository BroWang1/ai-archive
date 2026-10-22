---
library_name: sglang
pipeline_tag: text-generation
license: mit
base_model:
  - inclusionAI/Ling-3.0-flash
tags:
  - speculative-decoding
  - tree-speculative-decoding
  - ubtree
  - dflash
  - sglang
  - ling3
  - arxiv:2609.39972
language:
  - zh
  - en
---

# Ling3-Flash-UBTree-B16

[Paper](https://arxiv.org/abs/2609.39972) · [Target model](https://huggingface.co/inclusionAI/Ling-3.0-flash)

**Ling3-Flash-UBTree-B16** is a UBTree speculative-decoding draft model for
[inclusionAI/Ling-3.0-flash](https://huggingface.co/inclusionAI/Ling-3.0-flash). It combines a
five-layer DFlash backbone with a learned bigram selector to propose multiple
candidate continuations for target-model verification.

> **SGLang integration — stay tuned!** Our UBTree adaptation for Ling3 has not
> yet been released to the open-source SGLang community. Public installation
> instructions and serving recipes will be added here when it becomes available.

This checkpoint is used alongside the matching target model; it cannot serve
as a standalone text-generation model.

## How UBTree works

![UBTree architecture and tree-native training pipeline](assets/ubtree_pipeline.png)

*UBTree pipeline*

UBTree pairs a **unigram proposer** with a **bigram selector**:

1. A DFlash backbone proposes candidate tokens for future positions in parallel.
2. The selector scores transitions between adjacent candidates in parallel.
3. Tree construction retains promising branches within a verification budget.
4. The target verifies the tree and commits the accepted continuation.

The paper also introduces tree-native training with renormalized KL supervision
on high-temperature target traces, encouraging plausible alternative branches.
See the [paper](https://arxiv.org/abs/2609.39972) for the method and experiments.

## Model specifications

| Item | Value |
|---|---|
| Target model | [inclusionAI/Ling-3.0-flash](https://huggingface.co/inclusionAI/Ling-3.0-flash) |
| Draft architecture | `Ling3UBTreeModel` |
| Draft backbone | 5 full-attention Transformer layers |
| Parameters stored in this checkpoint | 481,983,774 (482.0M) |
| Weight dtype | BF16 |
| Hidden size | 2,560 |
| Attention heads / KV heads | 32 / 32 |
| Target auxiliary feature layers (zero-based) | 1, 11, 23, 29, 35 |
| Draft block size | 16 (anchor-inclusive runtime convention) |
| Candidate top-k | 64 per draft position |
| Default verification tree budget | 64 non-root nodes + 1 anchor |
| Training | DFlash warm start, then joint backbone + UBTree selector training |

The parameter count covers tensors distributed in this repository. The draft
shares token embeddings and the language-model head with the target; these
shared weights are not included here. B16 denotes the draft block size, not
the verification tree's node budget.

## Serving with SGLang

UBTree support for Ling3 in SGLang is coming soon. We will share installation
instructions and serving examples once the integration is publicly available.
**Stay tuned!**

## Benchmark results

All methods use **block size 16**, TP4, concurrency 1, BF16, and greedy
no-thinking decoding. UBTree uses a 32-node tree.

Each cell shows **acceptance length / E2E speedup over target-only AR**.

| Dataset | UBTree | DFlash | DSpark |
| --- | ---: | ---: | ---: |
| GSM8K | **9.70 / 3.227×** | 7.44 / 2.927× | 8.00 / 2.899× |
| MATH-500 | **9.58 / 3.761×** | 7.07 / 3.284× | 7.69 / 3.252× |
| AIME 2025 | **8.18 / 3.497×** | 5.75 / 2.864× | 6.39 / 2.883× |
| HumanEval | **10.40 / 3.479×** | 7.79 / 3.128× | 8.03 / 3.014× |
| MBPP | **9.55 / 3.415×** | 7.01 / 3.011× | 6.89 / 2.730× |
| LiveCodeBench | **7.53 / 3.191×** | 5.13 / 2.543× | 5.53 / 2.484× |

AL and throughput use three-round medians; the matched AR baseline uses one round.

## Citation

If you use UBTree in your work, please cite:

```bibtex
@article{liang2026ubtree,
  title   = {UBTree: Parallel Tree Drafting via Unigram and Bigram Models for Speculative Decoding},
  author  = {Liang, Chumeng and Wang, Linxuan and Peng, Xinyu and Liu, Huabin and Chen, Yuxin and Liu, Ge and Lin, Guang and Song, Qifan and Li, Jianguo},
  journal = {arXiv preprint arXiv:2609.39972},
  year    = {2026},
  url     = {https://arxiv.org/abs/2609.39972}
}
```

## License

The model weights are released under the **MIT License**. The pipeline figure
is from [Liang et al., Figure 2](https://arxiv.org/html/2609.39972v1#S2.F2),
reproduced without modification under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
