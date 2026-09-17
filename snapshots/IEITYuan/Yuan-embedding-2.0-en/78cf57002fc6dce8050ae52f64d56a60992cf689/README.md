---
tags:
- mteb
language:
- en
license: apache-2.0
library_name: sentence-transformers
---
<h2 align="left">Yuan-embedding-2.0-en</h2>

Yuan-embedding-2.0-en is an embedding model specifically designed for English text retrieval tasks. Built on the foundation of [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), we have further optimized it for both Retrieval and Reranking tasks. The key work is as follows:

- Data Augmentation
  - Hard negative sampling: Dual evaluation is conducted using a Rerank model and LLM to filter out high-quality positive and negative samples
  - LLM-synthesized data: The [Yuan2-M32](https://huggingface.co/IEITYuan/Yuan2-M32) is employed to perform LLM-based rewriting on the query data within the training dataset
- Loss function design
  - Multi-Task loss
  - Matryoshka Representation Learning
  - The Retrieval tasks adopt InfoNCE with in-batch-negative
  - The Reranking tasks adopt InfoNCE with in-batch-negative

Yuan-embedding-2.0-en 是专门为英文文本检索任务设计的嵌入模型。我们在[Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)的基础上，针对Retrieval任务与Reranking任务进行了进一步优化。主要工作如下：

- 数据增强
  - Hard negative sampling：利用Rerank模型与LLM进行双重评估，筛选出高质量正负样本
  - LLM合成数据：利用[Yuan2-M32](https://huggingface.co/IEITYuan/Yuan2-M32)针对训练数据query进行LLM重写
- 损失函数设计
  - Multi-Task loss
  - Matryoshka Representation Learning
  - Retrieval任务使用InfoNCE with in-batch-negative
  - 针对Reranking任务使用InfoNCE with in-batch-negative


<h2 align="left">Usage</h2>

```bash
pip install -U sentence-transformers==3.4.1
```

使用示例：

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("IEITYuan/Yuan-embedding-2.0-en")
sentences_1 = ["data-1", "data-2"]
sentences_2 = ["data-3", "data-4"]
embeddings_1 = model.encode(sentences_1, normalize_embeddings=True)
embeddings_2 = model.encode(sentences_2, normalize_embeddings=True)
similarity = embeddings_1 @ embeddings_2.T
print(similarity)
```
