<p align="center">
 <img src="https://dscache.tencent-cloud.cn/upload/uploader/hunyuan-64b418fd052c033b228e04bc77bbc4b54fd7f5bc.png" width="400"/> <br>
</p><p></p>


<p align="center">
    🤗&nbsp;<a href="https://huggingface.co/tencent/Hunyuan-A13B-Instruct"><b>Hugging Face</b></a>&nbsp;&nbsp;|&nbsp;&nbsp;
    🖥️&nbsp;<a href="https://hunyuan.tencent.com" style="color: red;"><b>Official Website</b></a>&nbsp;&nbsp;|&nbsp;&nbsp;
    🕖&nbsp;<a href="https://cloud.tencent.com/product/hunyuan"><b>HunyuanAPI</b></a>&nbsp;&nbsp;|&nbsp;&nbsp;
    🕹️&nbsp;<a href="https://hunyuan.tencent.com/?model=hunyuan-a13b"><b>Demo</b></a>&nbsp;&nbsp;|&nbsp;&nbsp;
    🤖&nbsp;<a href="https://modelscope.cn/models/Tencent-Hunyuan/Hunyuan-A13B-Instruct"><b>ModelScope</b></a>
</p>


<p align="center">
    <a href="https://github.com/Tencent-Hunyuan/Hunyuan-A13B/blob/main/report/Hunyuan_A13B_Technical_Report.pdf"><b>Technical Report</b> </a> |
    <a href="https://github.com/Tencent-Hunyuan/Hunyuan-A13B"><b>GITHUB</b></a> | 
    <a href="https://cnb.cool/tencent/hunyuan/Hunyuan-A13B"><b>cnb.cool</b></a> | 
    <a href="https://github.com/Tencent-Hunyuan/Hunyuan-A13B/blob/main/LICENSE"><b>LICENSE</b></a> | 
    <a href="https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan-A13B/main/assets/1751881231452.jpg"><b>WeChat</b></a> | 
    <a href="https://discord.gg/bsPcMEtV7v"><b>Discord</b></a>
</p>




## 模型介绍

随着人工智能技术的快速发展，大型语言模型（LLMs）在自然语言处理、计算机视觉和科学任务等领域取得了显著进展。然而，随着模型规模的扩大，如何在保持高性能的同时优化资源消耗成为一个关键挑战。为了应对这一挑战，我们研究了混合专家（MoE）模型，当前亮相的 Hunyuan-A13B 模型，拥有800亿总参数和130亿激活参数。不仅在效果上达到了高标准，而且在尺寸上也做到了极致的优化，成功平衡了模型性能与资源占用。


### 核心特性与优势
- ​**小参数量，高性能**​：仅激活130亿参数（总参数量800亿），即可在多样化基准任务中媲美更大规模模型的竞争力表现 
- ​**混合推理支持**​：同时支持快思考和慢思考两种模式，支持用户灵活选择 
- ​**超长上下文理解**​：原生支持256K上下文窗口，在长文本任务中保持稳定性能
- ​**增强Agent能力**​：优化Agent能力，在BFCL-v3、τ-Bench等智能体基准测试中领先
- ​**高效推理**​：采用分组查询注意力（GQA）策略，支持多量化格式，实现高效推理
    

### 为何选择Hunyuan-A13B？
作为兼具强大性能与计算效率的大模型，Hunyuan-A13B是研究者与开发者在资源受限条件下追求高性能的理想选择。无论学术研究、高性价比AI解决方案开发，还是创新应用探索，本模型都能提供强大的基础支持。


&nbsp;

## 新闻
<br>

* 2025.6.26 我们在Hugging Face开源了 **Hunyuan-A13B-Instruct**，**Hunyuan-A13B-Pretrain**, **Hunyuan-A13B-Instruct-FP8**， **Hunyuan-A13B-Instruct-GPTQ-Int4**。并发布了技术报告和训练推理操作手册，详细介绍了模型能力和训练与推理的操作。

## 模型结构

Hunyuan-A13B采用了细粒度混合专家（Fine-grained Mixture of Experts，Fine-grained MoE）架构，包含800亿参数和130亿激活参数，累计训练了超过 20T tokens。该模型支持 256K 的上下文长度，以下为模型结构细节:
* 总参数: 80B
* 激活参数: 13B
* 层数: 32
* Attention Heads: 32
* 共享专家数: 1
* 非共享专家数: 64
* 路由策略: Top-8
* 激活函数: SwiGLU
* 隐层维度: 4096
* 专家隐层维度: 3072 

## Benchmark评估榜单 

**Hunyuan-A13B-Pretrain** 在 12/14 个任务上超越了Hunyuan上一代52B激活参数的MoE模型Hunyuan-Large，证实了它在预训练任务上出色的能力。与业界更大参数量的Dense和MoE模型相比, Hunyuan-A13B在多个代码和数学任务上都取得了最高分数。在MMLU, MMLU-PRO等诸多众聚合任务上, Hunyuan-A13B达到了与Qwen3-A22B模型同等的水平，表现出优秀的综合能力。

| Model            | Hunyuan-Large | Qwen2.5-72B  | Qwen3-A22B | Hunyuan-A13B |
|------------------|---------------|--------------|-------------|---------------|
| MMLU             | 88.40          | 86.10         | 87.81        | 88.17          |
| MMLU-Pro         | 60.20          | 58.10        | 68.18           | 67.23          |
| MMLU-Redux              |  87.47         | 83.90         | 87.40        | 87.67          |
| BBH        | 86.30             | 85.80            | 88.87        | 87.56          |
| SuperGPQA    |  38.90         | 36.20          | 44.06           | 41.32          |
| EvalPlus       | 75.69          | 65.93         | 77.60        | 78.64          |
| MultiPL-E             | 59.13             | 60.50            | 65.94        | 69.33          |
| MBPP | 72.60             | 76.00            | 81.40        | 83.86          |
| CRUX-I             | 57.00          | 57.63          | -        | 70.13          |
| CRUX-O             | 60.63          | 66.20          | 79.00        | 77.00          |
| MATH            | 69.80          | 62.12         | 71.84        | 72.35          |
| CMATH            | 91.30          | 84.80         | -        | 91.17          |
| GSM8k         | 92.80             | 91.50           | 94.39        | 91.83          |
| GPQA            | 25.18             | 45.90            | 47.47        | 49.12          |

**Hunyuan-A13B-Instruct** 在多项基准测试中取得了极具有竞争力的表现，尤其是在数学、科学、agent等领域。我们与一些强力模型进行了对比，结果如下所示。

| Topic               | Bench                         | OpenAI-o1-1217 | DeepSeek R1 | Qwen3-A22B | Hunyuan-A13B-Instruct |
|:-------------------:|:-----------------------------:|:-------------:|:------------:|:-----------:|:---------------------:|
| **Mathematics**     | AIME 2024<br>AIME 2025<br>MATH | 74.3<br>79.2<br>96.4 | 79.8<br>70<br>94.9 | 85.7<br>81.5<br>94.0 | 87.3<br>76.8<br>94.3 |
| **Science**         | GPQA-Diamond<br>OlympiadBench | 78<br>83.1 | 71.5<br>82.4 | 71.1<br>85.7 | 71.2<br>82.7 |
| **Coding**          | Livecodebench<br>Fullstackbench<br>ArtifactsBench | 63.9<br>64.6<br>38.6 | 65.9<br>71.6<br>44.6 | 70.7<br>65.6<br>44.6 | 63.9<br>67.8<br>43 |
| **Reasoning**       | BBH<br>DROP<br>ZebraLogic    | 80.4<br>90.2<br>81 | 83.7<br>92.2<br>78.7 | 88.9<br>90.3<br>80.3 | 89.1<br>91.1<br>84.7 |
| **Instruction<br>Following** | IF-Eval<br>SysBench  | 91.8<br>82.5 | 88.3<br>77.7 | 83.4<br>74.2 | 84.7<br>76.1 |
| **Text<br>Creation**| LengthCtrl<br>InsCtrl       | 60.1<br>74.8 | 55.9<br>69 | 53.3<br>73.7 | 55.4<br>71.9 |
| **NLU**             | ComplexNLU<br>Word-Task     | 64.7<br>67.1 | 64.5<br>76.3 | 59.8<br>56.4 | 61.2<br>62.9 |
| **Agent**           | BDCL v3<br> τ-Bench<br>ComplexFuncBench<br> $C^3$-Bench | 67.8<br>60.4<br>47.6<br>58.8 | 56.9<br>43.8<br>41.1<br>55.3 | 70.8<br>44.6<br>40.6<br>51.7 | 78.3<br>54.7<br>61.2<br>63.5 |

## transformers推理

我们的模型默认使用“慢思考”（即推理模式），有两种方式可以关闭 CoT（Chain-of-Thought，思维链）推理：
1. 在调用 `apply_chat_template` 时传入参数 `"enable_thinking=False"`。
2. 在提示词（prompt）前加上 `/no_think` 可以强制模型不使用 CoT 推理。类似地，在提示词前加上 `/think` 则会强制模型启用 CoT 推理。

以下代码片段展示了如何使用 `transformers` 库加载并应用该模型。
它还演示了如何开启和关闭推理模式，
以及如何解析推理过程和最终输出。

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import os
import re

model_name_or_path = os.environ['MODEL_PATH']
# model_name_or_path = "tencent/Hunyuan-A13B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(model_name_or_path, device_map="auto",trust_remote_code=True)  # You may want to use bfloat16 and/or move to GPU here
messages = [
    {"role": "user", "content": "Write a short summary of the benefits of regular exercise"},
]

text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            enable_thinking=True
            )

model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
model_inputs.pop("token_type_ids", None)
outputs = model.generate(**model_inputs, max_new_tokens=4096)


output_text = tokenizer.decode(outputs[0])

think_pattern = r'<think>(.*?)</think>'
think_matches = re.findall(think_pattern, output_text, re.DOTALL)

answer_pattern = r'<answer>(.*?)</answer>'
answer_matches = re.findall(answer_pattern, output_text, re.DOTALL)

think_content = [match.strip() for match in think_matches][0]
answer_content = [match.strip() for match in answer_matches][0]
print(f"thinking_content:{think_content}\n\n")
print(f"answer_content:{answer_content}\n\n")
```



### 快速思考与慢速思考切换

本模型支持两种运行模式：

- **慢速思考模式（默认）**：在生成最终答案之前进行详细的内部推理步骤。
- **快速思考模式**：跳过内部推理过程，直接输出最终答案，从而实现更快的推理速度。

**切换到快速思考模式的方法：**

要禁用推理过程，请在调用 `apply_chat_template` 时设置 `enable_thinking=False`：

```python
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    enable_thinking=False  # 使用快速思考模式
)
```

## 推理和部署 

HunyuanLLM可以采用vLLM，sglang或TensorRT-LLM部署。为了简化部署过程HunyuanLLM提供了预构建docker镜像。


## 使用TensorRT-LLM推理

### BF16部署

#### Step1：执行推理

#### 方式1：命令行推理

下面我们展示一个代码片段，采用`TensorRT-LLM`快速请求chat model：
修改 examples/pytorch/quickstart_advanced.py 中如下代码：


```python
from tensorrt_llm import SamplingParams
from tensorrt_llm._torch import LLM
from tensorrt_llm._torch.pyexecutor.config import PyTorchConfig
from tensorrt_llm.llmapi import (EagleDecodingConfig, KvCacheConfig,
                                 MTPDecodingConfig)

prompt = "Write a short summary of the benefits of regular exercise"

def main():
    args = parse_arguments()

    llm, sampling_params = setup_llm(args)
    new_prompts = []
    if args.apply_chat_template:
        messages = [{"role": "user", "content": f"{prompt}"}]
        new_prompts.append(llm.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        )

    outputs = llm.generate(new_prompts, sampling_params)

    for i, output in enumerate(outputs):
        prompt = output.prompt
        generated_text = output.outputs[0].text
        print(f"[{i}] Prompt: {prompt!r}, Generated text: {generated_text!r}")
```

运行方式：

```shell
python3 quickstart_advanced.py --model_dir "HunyuanLLM模型路径" --tp_size 4 --apply_chat_template
```

#### 方式2：服务化推理

下面我们展示使用`TensorRT-LLM`服务化的方式部署模型和请求。

```shell
model_path="HunyuanLLM模型路径"
trtllm-serve <model_path> [--backend pytorch --tp_size <tp> --ep_size <ep> --host <host> --port <port>]
```

服务启动成功后, 运行请求脚本：
```python
### OpenAI Chat Client

from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="tensorrt_llm",
)

response = client.chat.completions.create(
    model="default",
    messages=[{
        "role": "user",
        "content": "Write a short summary of the benefits of regular exercise"
    }],
    max_tokens=4096,
)
print(response)
```

#### FP8/Int4量化模型部署：
目前 TensorRT-LLM 的 fp8 和 int4 量化模型正在支持中，敬请期待。


## vLLM 部署

### Docker 镜像推理

我们提供了一个基于官方 vLLM 0.8.5 版本的 Docker 镜像方便快速部署和测试。**注意：该镜像要求使用 CUDA 12.4 版本。**

- 首先，下载 Docker 镜像文件：

**从Docker Hub下载**:
```
docker pull hunyuaninfer/hunyuan-infer-vllm-cuda12.4:v1
```

**中国国内镜像**:

考虑到下载速度， 也可以选择从 CNB 下载镜像,感谢[CNB云原生构建](https://cnb.cool/)提供支持:

1. 下载镜像
``` 
docker pull docker.cnb.cool/tencent/hunyuan/hunyuan-a13b/hunyuan-infer-vllm-cuda12.4:v1
```

2. 然后更名镜像（可选，更好的和下面脚本名字匹配）
```
docker tag docker.cnb.cool/tencent/hunyuan/hunyuan-a13b/hunyuan-infer-vllm-cuda12.4:v1 hunyuaninfer/hunyuan-infer-vllm-cuda12.4:v1 
```

- 下载模型文件：
  - Huggingface：vLLM 会自动下载。
  - ModelScope：`modelscope download --model Tencent-Hunyuan/Hunyuan-A13B-Instruct`

- 启动 API 服务（从 Huggingface 下载模型）：

```bash
docker run --rm  --ipc=host \
        -v ~/.cache:/root/.cache/ \
        --security-opt seccomp=unconfined \
        --net=host \
        --gpus=all \
        -it \
        --entrypoint python3 hunyuaninfer/hunyuan-infer-vllm-cuda12.4:v1 \
        -m vllm.entrypoints.openai.api_server \
        --host 0.0.0.0 \
        --tensor-parallel-size 4 \
        --port 8000 \
        --model tencent/Hunyuan-A13B-Instruct  \
        --trust_remote_code
```

- 启动 API 服务（从 ModelScope 下载模型）：

```bash
docker run --rm  --ipc=host \
        -v ~/.cache/modelscope:/root/.cache/modelscope \
        --security-opt seccomp=unconfined \
        --net=host \
        --gpus=all \
        -it \
        --entrypoint python3 hunyuaninfer/hunyuan-infer-vllm-cuda12.4:v1 \
        -m vllm.entrypoints.openai.api_server \
        --host 0.0.0.0 \
        --tensor-parallel-size 4 \
        --port 8000 \
        --model /root/.cache/modelscope/hub/models/Tencent-Hunyuan/Hunyuan-A13B-Instruct/  \
        --trust_remote_code
```


### 源码部署

对本模型的支持已通过 [PR 20114](https://github.com/vllm-project/vllm/pull/20114) 提交至 vLLM 项目并已经合并, 可以使用 vllm git commit`ecad85`以后的版本进行源代码编译。


### 模型上下文长度支持

Hunyuan A13B 模型支持最大 **256K token（262,144 Token）** 的上下文长度。但由于大多数 GPU 硬件配置的显存限制，默认 `config.json` 中将上下文长度限制为 **32K token**，以避免出现显存溢出（OOM）问题。

#### 将上下文长度扩展至 256K

如需启用完整的 256K 上下文支持，请手动修改模型 `config.json` 文件中的 `max_position_embeddings` 字段如下：

```json
{
  ...
  "max_position_embeddings": 262144,
  ...
}
```

当使用 **vLLM** 进行服务部署时，也可以通过添加以下参数来明确设置最大模型长度：

```bash
--max-model-len 262144
```

#### 推荐的 256K 上下文长度配置

以下是在配备 **NVIDIA H20 显卡（96GB 显存）** 的系统上部署 256K 上下文长度服务的推荐配置：

| 模型数据类型 | KV-Cache 数据类型 | 设备数量 | 模型长度 |
|----------------|-------------------|------------|--------------|
| `bfloat16`     | `bfloat16`        | 4          | 262,144      |

> ⚠️ **注意：** 使用 FP8 对 KV-cache 进行量化可能会影响生成质量。上述配置是用于稳定部署 256K 长度服务的建议设置。


### 使用 vLLM 调用工具

为了支持基于 Agent 的工作流和函数调用能力，本模型包含专门的解析机制，用于处理工具调用及内部推理步骤。

关于如何在 Agent 场景中实现和使用这些功能的完整示例，请参见我们的 GitHub 示例代码：
🔗 [Hunyuan A13B Agent 示例](https://github.com/Tencent-Hunyuan/Hunyuan-A13B/blob/main/agent/)

在使用 **vLLM** 部署模型时，可以使用以下参数配置工具解析行为：

| 参数名                  | 值                                                                 |
|-------------------------|--------------------------------------------------------------------|
| `--tool-parser-plugin`  | [本地 Hunyuan A13B 工具解析器文件](https://github.com/Tencent-Hunyuan/Hunyuan-A13B/blob/main/agent/hunyuan_tool_parser.py) |
| `--tool-call-parser`    | `hunyuan`                                                         |

这些设置可使 vLLM 根据预期格式正确解析和路由模型生成的工具调用。


### Reasoning Parser（推理解析器）

目前，Hunyuan A13B 模型在 vLLM 中的推理解析器支持仍在开发中。


## SGLang

### Docker 镜像

我们还提供基于 SGLang 最新版本构建的 Docker 镜像。

快速开始方式如下：

- 拉取 Docker 镜像：

```
docker pull docker.cnb.cool/tencent/hunyuan/hunyuan-a13b:hunyuan-moe-A13B-sglang
或
docker pull hunyuaninfer/hunyuan-a13b:hunyuan-moe-A13B-sglang
```

- 启动 API 服务：

```bash
docker run --gpus all \
    --shm-size 32g \
    -p 30000:30000 \
    --ipc=host \
    docker.cnb.cool/tencent/hunyuan/hunyuan-a13b:hunyuan-moe-A13B-sglang \
    -m sglang.launch_server --model-path hunyuan/huanyuan_A13B --tp 4 --trust-remote-code --host 0.0.0.0 --port 30000
```


## 交互式Demo Web 
hunyuan-A13B 现已开放网页demo。访问 https://hunyuan.tencent.com/?model=hunyuan-a13b 即可简单体验我们的模型。

## 联系我们
如果你想给我们的研发和产品团队留言，欢迎联系我们腾讯混元LLM团队。你可以通过邮件（hunyuan_opensource@tencent.com）联系我们。
