---
license: other
license_name: license-yuan
license_link: https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/LICENSE-Yuan
---

<div align="center">
<h1>
  Yuan 2
</h1>
</div>

<div align="center">
<a href="https://github.com/IEIT-Yuan/Yuan-2.0" target="_blank"> 💻GitHub Repo</a> | <a href="http://arxiv.org/pdf/2311.15786.pdf" target="_blank">📃Yuan2.0-paper</a>
</div>

# 目录/Table of Contents

- [模型介绍/Introduction](#Introduction)
- [代码调用/Code Usage](#Usage)
- [Benchmark评估/Benchmark Evaluation](#Benchmark)
- [声明与协议/Terms and Conditions](#Terms)
- [引用/Cite](#Cite)


# <span id="Introduction">模型介绍/Introduction</span>
源2.0 是浪潮信息发布的新一代基础语言大模型。我们开源了全部的3个模型源2.0-102B，源2.0-51B和源2.0-2B。并且我们提供了预训练，微调，推理服务的相关脚本，以供研发人员做进一步的开发。源2.0是在源1.0的基础上，利用更多样的高质量预训练数据和指令微调数据集，令模型在语义、数学、推理、代码、知识等不同方面具备更强的理解能力。

Yuan2.0 is a new generation Fundamental Large Language Model developed by IEIT System. We have published all three models, Yuan 2.0-102B, Yuan 2.0-51B, and Yuan 2.0-2B. And we provide relevant scripts for pretraining, fine-tuning, and inference services for other developers. Yuan2.0 is based on Yuan1.0, utilizing a wider range of high-quality pre training data and instruction fine-tuning datasets to enhance the model's understanding of semantics, mathematics, reasoning, code, knowledge, and other aspects.


# <span id="Usage">代码调用/Code Usage</span>
可以通过如下代码调用 Yuan2-2B 模型来生成文本：

You can generate text by invoking the Yuan2-2B model with the following code:

```python
import torch, transformers
import sys, os
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
from transformers import AutoModelForCausalLM,AutoTokenizer,LlamaTokenizer

print("Creat tokenizer...")
tokenizer = LlamaTokenizer.from_pretrained('IEITYuan/Yuan2-2B-hf', add_eos_token=False, add_bos_token=False, eos_token='<eod>')
tokenizer.add_tokens(['<sep>', '<pad>', '<mask>', '<predict>', '<FIM_SUFFIX>', '<FIM_PREFIX>', '<FIM_MIDDLE>','<commit_before>','<commit_msg>','<commit_after>','<jupyter_start>','<jupyter_text>','<jupyter_code>','<jupyter_output>','<empty_output>'], special_tokens=True)

print("Creat model...")
model = AutoModelForCausalLM.from_pretrained('IEITYuan/Yuan2-2B-hf', device_map='auto', torch_dtype=torch.bfloat16, trust_remote_code=True)

inputs = tokenizer("请问目前最先进的机器学习算法有哪些？", return_tensors="pt")["input_ids"].to("cuda:0")
outputs = model.generate(inputs,do_sample=False,max_length=100)
print(tokenizer.decode(outputs[0]))

```

# <span id="Benchmark">Benchmark评估/Benchmark Evaluation</span>
我们提供了[HumanEval](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_humaneval.md)，[AGIEval-GK-Math](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_agieval_math.md)，[GSM8K](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_gsm8k.md)和[TruthfulQA](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_TruthfulQA.md)的评估脚本。在4个典型任务上，我们用源2.0不同版本模型上进行了性能测试。

We have provided evaluation scripts for [HumanEval](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_humaneval.md),[AGIEval-GK-Math](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_agieval_math.md),[GSM8K](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_gsm8k.md) and [TruthfulQA](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/docs/eval_TruthfulQA.md). Performance tests were conducted on different versions of the Yuan2.0 model for four typical tasks.


| Model             | GSM8K   | AGIEval-GK-Math-QA     | AGIEval-GK-Math-Cloze     | HumanEval | TurthfulQA |
| ----------------- | :----:  | :------------: | :---------------: | :-------: | ---------- |
|  GPT-4            |  92%    |     47.0%      |       16.1%       |   86.6%   |     59%    |
|  ChatGPT         | 68.6%\* |     36.5%      |        7.3%       |  66.5%\*  |     34%\*  |
|  Llama2           | 56.8%   |       -        |         -         |   29.9%   |       -    |
| 源2.0-102B      | 76.6%   |     38.7%      |       13.5%       |   67.1%   |     58%    |
| 源2.0-102B-SC   | 86.2%   |     45.5%      |       15.2%       |   77.4%   |       -    |

\* 使用与源2.0完全相同的输入数据对ChatGPT进行测试，时间2023年11月

\* Testing ChatGPT using the same input data as Yuan2.0, as of November 2023.

# <span id="Terms">声明与协议/Terms and Conditions</span>
对该模型的原代码仓库使用遵循开源许可协议 Apache 2.0。

源2.0模型支持商用，不需要申请授权，请您了解并遵循[《源2.0模型许可协议》](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/LICENSE-Yuan)，勿将开源模型和代码及基于开源项目产生的衍生物用于任何可能给国家和社会带来危害的用途以及用于任何未经过安全评估和备案的服务。

尽管模型在训练时我们已采取措施尽力确保数据的合规性和准确性，但模型参数量巨大且受概率随机性因素影响，我们无法保证输出内容的准确性，且模型易被输入指令所误导，本项目不承担开源模型和代码导致的数据安全、舆情风险或发生任何模型被误导、滥用、传播、不当利用而产生的风险和责任。**您将对通过使用、复制、分发和修改模型等方式利用该开源项目所产生的风险与后果，独自承担全部责任。**

The use of the original code repository for this model requires compliance with the open source license agreement Apache 2.0. The Yuan2.0 model supports commercial use and does not require authorization. Please understand and comply with the [《Yuan 2.0 Model License Agreement》](https://github.com/IEIT-Yuan/Yuan-2.0/blob/main/LICENSE-Yuan). Do not use the open source model and code, as well as derivatives generated from open source projects, for any purposes that may cause harm to the country and society, or for any services that have not undergone security assessment and filing. Although we have taken measures to ensure the compliance and accuracy of the data during training, the model has a huge number of parameters and is affected by probability and randomness factors. We cannot guarantee the accuracy of the output content, and the model is easily misled by input instructions. This project does not assume any data security, public opinion risks, or any model misleading, abusing, spreading caused by open-source models and code Risks and responsibilities arising from improper utilization **You will be solely responsible for the risks and consequences arising from the use, copying, distribution, and modification of the model in this open source project.**

# <span id="Cite">引用/Cite</span>
欢迎阅读我们的技术报告 [YUAN 2.0: A Large Language Model with Localized Filtering-based Attention](http://arxiv.org/pdf/2311.15786.pdf)！

Welcome to read our technical report [YUAN 2.0: A Large Language Model with Localized Filtering-based Attention](http://arxiv.org/pdf/2311.15786.pdf)！

```latex
@article{Wu2023,
title = {{YUAN 2.0: A Large Language Model with Localized Filtering-based Attention}},
author = {Wu, Shaohua and Zhao, Xudong and Wang, Shenling and Luo, Jiangang and Li, Lingjun and Chen, Xi and Zhao, Bing and Wang, Wei and Yu, Tong and Zhang, Rongguo and Zhang, Jiahua and Wang, Chao},
url = {http://arxiv.org/abs/2311.15786},
year = {2023}
}

```
