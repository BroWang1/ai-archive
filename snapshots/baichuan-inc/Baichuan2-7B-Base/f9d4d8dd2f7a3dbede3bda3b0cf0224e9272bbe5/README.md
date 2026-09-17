---
language:
  - en
  - zh
license: other
tasks:
  - text-generation
---

<!-- markdownlint-disable first-line-h1 -->
<!-- markdownlint-disable html -->
<div align="center">
<h1>
  Baichuan 2
</h1>
</div>

<div align="center">
<a href="https://github.com/baichuan-inc/Baichuan2" target="_blank">🦉GitHub</a> | <a href="https://github.com/baichuan-inc/Baichuan-7B/blob/main/media/wechat.jpeg?raw=true" target="_blank">💬WeChat</a>
</div>
<div align="center">
  百川API支持搜索增强和192K长窗口，新增百川搜索增强知识库、限时免费！<br>
🚀 <a href="https://www.baichuan-ai.com/" target="_blank">百川大模型在线对话平台</a> 已正式向公众开放 🎉
</div>

# 目录/Table of Contents

- [📖 模型介绍/Introduction](#Introduction)
- [⚙️ 快速开始/Quick Start](#Start)
- [📊 Benchmark评估/Benchmark Evaluation](#Benchmark)
- [📜 声明与协议/Terms and Conditions](#Terms)


# <span id="Introduction">模型介绍/Introduction</span>

Baichuan 2 是[百川智能]推出的新一代开源大语言模型，采用 **2.6 万亿**  Tokens 的高质量语料训练，在权威的中文和英文 benchmark
上均取得同尺寸最好的效果。本次发布包含有 7B、13B 的 Base 和 Chat 版本，并提供了 Chat 版本的 4bits
量化，所有版本不仅对学术研究完全开放，开发者也仅需[邮件申请]并获得官方商用许可后，即可以免费商用。具体发布版本和下载见下表：

Baichuan 2 is the new generation of large-scale open-source language models launched by [Baichuan Intelligence inc.](https://www.baichuan-ai.com/). 
It is trained on a high-quality corpus with 2.6 trillion tokens and has achieved the best performance in authoritative Chinese and English benchmarks of the same size. 
This release includes 7B and 13B versions for both Base and Chat models, along with a 4bits quantized version for the Chat model. 
All versions are fully open to academic research, and developers can also use them for free in commercial applications after obtaining an official commercial license through [email request](mailto:opensource@baichuan-inc.com). 
The specific release versions and download links are listed in the table below:

|     |          Base Model        |          Chat Model        |       4bits Quantized Chat Model        |
|:---:|:--------------------:|:--------------------:|:--------------------------:|
| 7B  | [Baichuan2-7B-Base](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base)  | [Baichuan2-7B-Chat](https://huggingface.co/baichuan-inc/Baichuan2-7B-Chat)  | [Baichuan2-7B-Chat-4bits](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base-4bits)  |
| 13B | [Baichuan2-13B-Base](https://huggingface.co/baichuan-inc/Baichuan2-13B-Base) | [Baichuan2-13B-Chat](https://huggingface.co/baichuan-inc/Baichuan2-13B-Chat) | [Baichuan2-13B-Chat-4bits](https://huggingface.co/baichuan-inc/Baichuan2-13B-Chat-4bits) |

# <span id="Start">快速开始/Quick Start</span>

在Baichuan2系列模型中，我们为了加快推理速度使用了Pytorch2.0加入的新功能F.scaled_dot_product_attention，因此模型需要在Pytorch2.0环境下运行。

In the Baichuan 2 series models, we have utilized the new feature `F.scaled_dot_product_attention` introduced in PyTorch 2.0 to accelerate inference speed. Therefore, the model needs to be run in a PyTorch 2.0 environment.

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("baichuan-inc/Baichuan2-7B-Base", use_fast=False, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained("baichuan-inc/Baichuan2-7B-Base", device_map="auto", trust_remote_code=True)
inputs = tokenizer('登鹳雀楼->王之涣\n夜雨寄北->', return_tensors='pt')
inputs = inputs.to('cuda:0')
pred = model.generate(**inputs, max_new_tokens=64, repetition_penalty=1.1)
print(tokenizer.decode(pred.cpu()[0], skip_special_tokens=True))
```

# <span id="Benchmark">Benchmark 结果/Benchmark Evaluation</span>

我们在[通用]、[法律]、[医疗]、[数学]、[代码]和[多语言翻译]六个领域的中英文权威数据集上对模型进行了广泛测试，更多详细测评结果可查看[GitHub]。

We have extensively tested the model on authoritative Chinese-English datasets across six domains: [General](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md#general-domain), [Legal](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md#law-and-medicine), [Medical](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md#law-and-medicine), [Mathematics](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md#mathematics-and-code), [Code](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md#mathematics-and-code), and [Multilingual Translation](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md#multilingual-translation). For more detailed evaluation results, please refer to [GitHub](https://github.com/baichuan-inc/Baichuan2/blob/main/README_EN.md).

### 7B Model Results

|                         | **C-Eval** | **MMLU** | **CMMLU** | **Gaokao** | **AGIEval** | **BBH** |
|:-----------------------:|:----------:|:--------:|:---------:|:----------:|:-----------:|:-------:|
|                         |  5-shot    |  5-shot  |  5-shot   | 5-shot     | 5-shot      | 3-shot  |
|        **GPT-4**        | 68.40      | 83.93    | 70.33     | 66.15      | 63.27       | 75.12   |
|    **GPT-3.5 Turbo**    | 51.10      | 68.54    | 54.06     | 47.07      | 46.13       | 61.59   |
|      **LLaMA-7B**       | 27.10      | 35.10    | 26.75     | 27.81      | 28.17       | 32.38   |
|      **LLaMA2-7B**      | 28.90      | 45.73    | 31.38     | 25.97      | 26.53       | 39.16   |
|       **MPT-7B**        | 27.15      | 27.93    | 26.00     | 26.54      | 24.83       | 35.20   |
|      **Falcon-7B**      | 24.23      | 26.03    | 25.66     | 24.24      | 24.10       | 28.77   |
|     **ChatGLM2-6B**     | 50.20      | 45.90    | 49.00     | 49.44      | 45.28       | 31.65   |
|    **[Baichuan-7B]**    | 42.80      | 42.30    | 44.02     | 36.34      | 34.44       | 32.48   |
| **[Baichuan2-7B-Base]** | 54.00      | 54.16    | 57.07     | 47.47      | 42.73       | 41.56   |

### 13B Model Results

|                             | **C-Eval** | **MMLU** | **CMMLU** | **Gaokao** | **AGIEval** | **BBH** |
|:---------------------------:|:----------:|:--------:|:---------:|:----------:|:-----------:|:-------:|
|                             |  5-shot    |  5-shot  |  5-shot   | 5-shot     | 5-shot      | 3-shot  |
|          **GPT-4**          | 68.40      | 83.93    | 70.33     | 66.15      | 63.27       | 75.12   |
|      **GPT-3.5 Turbo**      | 51.10      | 68.54    | 54.06     | 47.07      | 46.13       | 61.59   |
|        **LLaMA-13B**        | 28.50      | 46.30    | 31.15     | 28.23      | 28.22       | 37.89   |
|       **LLaMA2-13B**        | 35.80      | 55.09    | 37.99     | 30.83      | 32.29       | 46.98   |
|       **Vicuna-13B**        | 32.80      | 52.00    | 36.28     | 30.11      | 31.55       | 43.04   |
| **Chinese-Alpaca-Plus-13B** | 38.80      | 43.90    | 33.43     | 34.78      | 35.46       | 28.94   |
|       **XVERSE-13B**        | 53.70      | 55.21    | 58.44     | 44.69      | 42.54       | 38.06   |
|   **[Baichuan-13B-Base]**    | 52.40      | 51.60    | 55.30     | 49.69      | 43.20       | 43.01   |
|  **[Baichuan2-13B-Base]**   | 58.10      | 59.17    | 61.97     | 54.33      | 48.17       | 48.78   |

## 训练过程模型/Training Dynamics

除了训练了 2.6 万亿 Tokens 的 [Baichuan2-7B-Base](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base) 模型，我们还提供了在此之前的另外 11 个中间过程的模型（分别对应训练了约 0.2 ~ 2.4 万亿 Tokens）供社区研究使用
（[训练过程checkpoint下载](https://huggingface.co/baichuan-inc/Baichuan2-7B-Intermediate-Checkpoints)）。下图给出了这些 checkpoints 在 C-Eval、MMLU、CMMLU 三个 benchmark 上的效果变化：

In addition to the [Baichuan2-7B-Base](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base) model trained on 2.6 trillion tokens, we also offer 11 additional intermediate-stage models for community research, corresponding to training on approximately 0.2 to 2.4 trillion tokens each ([Intermediate Checkpoints Download](https://huggingface.co/baichuan-inc/Baichuan2-7B-Intermediate-Checkpoints)). The graph below shows the performance changes of these checkpoints on three benchmarks: C-Eval, MMLU, and CMMLU.

![checkpoint](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base/resolve/main/checkpoints.jpeg)

# <span id="Terms">声明与协议/Terms and Conditions</span>

## 声明

我们在此声明，我们的开发团队并未基于 Baichuan 2 模型开发任何应用，无论是在 iOS、Android、网页或任何其他平台。我们强烈呼吁所有使用者，不要利用
Baichuan 2 模型进行任何危害国家社会安全或违法的活动。另外，我们也要求使用者不要将 Baichuan 2
模型用于未经适当安全审查和备案的互联网服务。我们希望所有的使用者都能遵守这个原则，确保科技的发展能在规范和合法的环境下进行。

我们已经尽我们所能，来确保模型训练过程中使用的数据的合规性。然而，尽管我们已经做出了巨大的努力，但由于模型和数据的复杂性，仍有可能存在一些无法预见的问题。因此，如果由于使用
Baichuan 2 开源模型而导致的任何问题，包括但不限于数据安全问题、公共舆论风险，或模型被误导、滥用、传播或不当利用所带来的任何风险和问题，我们将不承担任何责任。

We hereby declare that our team has not developed any applications based on Baichuan 2 models, not on iOS, Android, the web, or any other platform. We strongly call on all users not to use Baichuan 2 models for any activities that harm national / social security or violate the law. Also, we ask users not to use Baichuan 2 models for Internet services that have not undergone appropriate security reviews and filings. We hope that all users can abide by this principle and ensure that the development of technology proceeds in a regulated and legal environment.

We have done our best to ensure the compliance of the data used in the model training process. However, despite our considerable efforts, there may still be some unforeseeable issues due to the complexity of the model and data. Therefore, if any problems arise due to the use of Baichuan 2 open-source models, including but not limited to data security issues, public opinion risks, or any risks and problems brought about by the model being misled, abused, spread or improperly exploited, we will not assume any responsibility.

## 协议

社区使用 Baichuan 2 模型需要遵循 [Apache 2.0](https://github.com/baichuan-inc/Baichuan2/blob/main/LICENSE) 和[《Baichuan 2 模型社区许可协议》](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base/resolve/main/Baichuan%202%E6%A8%A1%E5%9E%8B%E7%A4%BE%E5%8C%BA%E8%AE%B8%E5%8F%AF%E5%8D%8F%E8%AE%AE.pdf)。Baichuan 2 模型支持商业用途，如果您计划将 Baichuan 2 模型或其衍生品用于商业目的，请您确认您的主体符合以下情况：
  1. 您或您的关联方的服务或产品的日均用户活跃量（DAU）低于100万。
  2. 您或您的关联方不是软件服务提供商、云服务提供商。
  3. 您或您的关联方不存在将授予您的商用许可，未经百川许可二次授权给其他第三方的可能。

在符合以上条件的前提下，您需要通过以下联系邮箱 opensource@baichuan-inc.com ，提交《Baichuan 2 模型社区许可协议》要求的申请材料。审核通过后，百川将特此授予您一个非排他性、全球性、不可转让、不可再许可、可撤销的商用版权许可。

The community usage of Baichuan 2 model requires adherence to [Apache 2.0](https://github.com/baichuan-inc/Baichuan2/blob/main/LICENSE) and [Community License for Baichuan2 Model](https://huggingface.co/baichuan-inc/Baichuan2-7B-Base/resolve/main/Baichuan%202%E6%A8%A1%E5%9E%8B%E7%A4%BE%E5%8C%BA%E8%AE%B8%E5%8F%AF%E5%8D%8F%E8%AE%AE.pdf). The Baichuan 2 model supports commercial use. If you plan to use the Baichuan 2 model or its derivatives for commercial purposes, please ensure that your entity meets the following conditions:

  1. The Daily Active Users (DAU) of your or your affiliate's service or product is less than 1 million.
  2. Neither you nor your affiliates are software service providers or cloud service providers.
  3. There is no possibility for you or your affiliates to grant the commercial license given to you, to reauthorize it to other third parties without Baichuan's permission.

Upon meeting the above conditions, you need to submit the application materials required by the Baichuan 2 Model Community License Agreement via the following contact email: opensource@baichuan-inc.com. Once approved, Baichuan will hereby grant you a non-exclusive, global, non-transferable, non-sublicensable, revocable commercial copyright license.


[GitHub]:https://github.com/baichuan-inc/Baichuan2
[Baichuan2]:https://github.com/baichuan-inc/Baichuan2

[Baichuan-7B]:https://huggingface.co/baichuan-inc/Baichuan-7B
[Baichuan2-7B-Base]:https://huggingface.co/baichuan-inc/Baichuan2-7B-Base
[Baichuan2-7B-Chat]:https://huggingface.co/baichuan-inc/Baichuan2-7B-Chat
[Baichuan2-7B-Chat-4bits]:https://huggingface.co/baichuan-inc/Baichuan2-7B-Chat-4bits
[Baichuan-13B-Base]:https://huggingface.co/baichuan-inc/Baichuan-13B-Base
[Baichuan2-13B-Base]:https://huggingface.co/baichuan-inc/Baichuan2-13B-Base
[Baichuan2-13B-Chat]:https://huggingface.co/baichuan-inc/Baichuan2-13B-Chat
[Baichuan2-13B-Chat-4bits]:https://huggingface.co/baichuan-inc/Baichuan2-13B-Chat-4bits

[通用]:https://github.com/baichuan-inc/Baichuan2#%E9%80%9A%E7%94%A8%E9%A2%86%E5%9F%9F
[法律]:https://github.com/baichuan-inc/Baichuan2#%E6%B3%95%E5%BE%8B%E5%8C%BB%E7%96%97
[医疗]:https://github.com/baichuan-inc/Baichuan2#%E6%B3%95%E5%BE%8B%E5%8C%BB%E7%96%97
[数学]:https://github.com/baichuan-inc/Baichuan2#%E6%95%B0%E5%AD%A6%E4%BB%A3%E7%A0%81
[代码]:https://github.com/baichuan-inc/Baichuan2#%E6%95%B0%E5%AD%A6%E4%BB%A3%E7%A0%81
[多语言翻译]:https://github.com/baichuan-inc/Baichuan2#%E5%A4%9A%E8%AF%AD%E8%A8%80%E7%BF%BB%E8%AF%91

[《Baichuan 2 模型社区许可协议》]:https://huggingface.co/baichuan-inc/Baichuan2-7B-Base/blob/main/Baichuan%202%E6%A8%A1%E5%9E%8B%E7%A4%BE%E5%8C%BA%E8%AE%B8%E5%8F%AF%E5%8D%8F%E8%AE%AE.pdf

[邮件申请]: mailto:opensource@baichuan-inc.com
[Email]: mailto:opensource@baichuan-inc.com
[opensource@baichuan-inc.com]: mailto:opensource@baichuan-inc.com
[训练过程heckpoint下载]: https://huggingface.co/baichuan-inc/Baichuan2-7B-Intermediate-Checkpoints
[百川智能]: https://www.baichuan-ai.com
