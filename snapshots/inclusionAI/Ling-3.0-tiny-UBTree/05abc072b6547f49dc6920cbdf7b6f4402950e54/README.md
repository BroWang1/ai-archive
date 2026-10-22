---
library_name: sglang
pipeline_tag: text-generation
license: mit
base_model:
  - inclusionAI/Ling-3.0-tiny
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

# Ling3-Tiny-UBTree-B16

[Paper](https://arxiv.org/abs/2609.39972) · [Target model](https://huggingface.co/inclusionAI/Ling-3.0-tiny)

**Ling3-Tiny-UBTree-B16** is a UBTree speculative-decoding draft model for
[inclusionAI/Ling-3.0-tiny](https://huggingface.co/inclusionAI/Ling-3.0-tiny). It combines a
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
| Target model | [inclusionAI/Ling-3.0-tiny](https://huggingface.co/inclusionAI/Ling-3.0-tiny) |
| Draft architecture | `Ling3UBTreeModel` |
| Draft backbone | 5 full-attention Transformer layers |
| Parameters stored in this checkpoint | 183,127,326 (183.1M) |
| Weight dtype | BF16 |
| Hidden size | 1,536 |
| Attention heads / KV heads | 16 / 16 |
| Target auxiliary feature layers (zero-based) | 4, 8, 12, 16, 22 |
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

All methods use **block size 16**, TP1, concurrency 1, BF16, and greedy
no-thinking decoding. UBTree uses a 49-node tree.

Each cell shows **acceptance length / E2E speedup over target-only AR**.

| Dataset | UBTree | DFlash | DSpark |
|---|---:|---:|---:|
| GSM8K | **9.53 / 3.055×** | 6.57 / 2.665× | 7.53 / 2.718× |
| MATH-500 | **9.86 / 3.518×** | 5.74 / 2.643× | 6.96 / 2.826× |
| AIME 2025 | **8.44 / 3.152×** | 4.76 / 2.261× | 5.37 / 2.263× |
| HumanEval | **10.04 / 3.411×** | 6.39 / 2.770× | 7.59 / 2.914× |
| MBPP | **9.35 / 3.062×** | 5.87 / 2.473× | 7.16 / 2.678× |
| LiveCodeBench | **7.46 / 2.794×** | 4.11 / 1.948× | 4.84 / 2.030× |

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
