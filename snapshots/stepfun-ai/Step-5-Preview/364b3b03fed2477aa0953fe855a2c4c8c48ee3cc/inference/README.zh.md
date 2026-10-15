# Step-5 最小推理

> English version: [README.md](README.md)

本目录包含独立的 Step-5 推理路径。完整模型的文本和图文生成已分别通过
FP8 **单节点 8 × H200、TP=EP=8** 与 BF16 **双节点共 16 × H200、TP=EP=16** 验证。
视觉编码器使用 PyTorch 和 BF16 权重。以下命令均在本目录执行，推理文件可独立使用。

默认的滑窗注意力走 PyTorch SDPA。QKNorm/RoPE、DSA 稀疏注意力、分块缩放 FP8 专家
矩阵乘法,以及关键的 MoE 基础算子用 Triton/CUDA 实现;模型编排与 NCCL 集合通信仍是
PyTorch。

同一组进程（rank）同时承担稠密主干的张量并行和 352 个路由专家的专家并行。
TP=EP=8 时每个 rank 放置 44 个专家，TP=EP=16 时放置 22 个。
TP 与 EP 共用进程组，没有独立的 `TP × EP` 进程网格。

常用术语:

| 缩写 | 含义 |
|------|------|
| TP | Tensor Parallelism，张量并行，把同一层计算拆到多张卡上。 |
| EP | Expert Parallelism，专家并行，把 MoE 专家分布到多张卡上。 |
| MoE | Mixture of Experts，混合专家网络，每个 token 只选择部分专家参与计算。 |
| FP8 | 8 位浮点数格式，用于降低模型权重和计算开销。 |
| BF16 | Brain Floating Point 16，16 位浮点数格式。 |
| SDPA | PyTorch 的缩放点积注意力实现。 |
| DSA | 稀疏注意力实现，先选出最相关的历史区域，再计算注意力。 |
| QKNorm | 对注意力中的 query 和 key 向量做归一化。 |
| RoPE | Rotary Position Embedding，旋转位置编码，用于表示 token 的相对位置。 |
| NCCL | NVIDIA 集合通信库，用于多张 GPU 之间的数据交换。 |
| KV cache | 保存历史 token 的注意力 key/value，避免解码时重复计算。 |
| MTP | Multi-Token Prediction，多 token 预测层，可用于辅助投机解码。 |
| token | 模型处理文本时使用的基本单位。 |

## 目录内容

| 文件 | 是什么 |
|------|--------|
| `convert.py` | 把原始 Step-5 模型权重转换成按进程分片的 TP 权重:`tpN/model-r{rank}.safetensors` + 对应的 `config-r{rank}.json`,外加一份共享的 `tokenizer_files/`。 |
| `generate.py` | 文本或图文贪心推理。每个 `torchrun` 进程加载一个分片；可传文本 `--prompt`，或准确 prompt IDs 与预处理后的 `--image-inputs`。 |
| `model.py` | 文本/VL 配置、解码层、TP/EP 执行，以及 packed prefill 中的图像特征注入。计算算子从 `kernel.py` 导入。 |
| `vision_encoder.py` | PyTorch 视觉编码器，包含 2D RoPE、绝对位置编码及卷积下采样。 |
| `kernel.py` | Triton/CUDA 计算算子:稀疏注意力(DSA)索引器 + 解码/预填充、分块缩放 FP8 专家矩阵乘法、MoE 基础算子,以及融合的 QKNorm/RoPE。 |
| `test_vision.py` | 配置、权重加载和多模态推理回归。 |
| `requirements.txt` | 兼容版本范围：torch `>=2.10,<2.14`、transformers `>=4.57.6,<6`、safetensors `>=0.7,<1`、triton `>=3.6,<3.8`。 |

典型流程:`convert.py`(一次性,把模型权重分片)→ `generate.py`(运行)。
`generate.py` 加载由 `model.py`、`kernel.py` 和 `vision_encoder.py` 实现的模型。

专家权重格式由源配置决定：缺少或为空的 `quantization_config` 使用 BF16；
`quant_method="fp8"` 使用 FP8，并按 `modules_to_not_convert` 保留指定层的 BF16
专家。转换过程保留权重 dtype。

## 安装

使用与主机驱动匹配、启用了 CUDA 的 PyTorch。FP8 模型的 TP=8 推理需要 8 张支持
FP8 E4M3 的可见 GPU。已验证的视觉运行环境为 PyTorch 2.13.0+cu129、Triton 3.7.1、
Transformers 5.15.0 和 Safetensors 0.8.0；兼容版本范围见 `requirements.txt`。

创建虚拟环境并安装依赖：

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

如果主机尚未提供兼容的 CUDA 版 PyTorch，先从与驱动匹配的 CUDA 软件包地址安装，
再安装其余依赖：

```bash
python -m pip install \
  --index-url "<匹配的-pytorch-cuda-软件包地址>" \
  "torch>=2.10,<2.14"
python -m pip install -r requirements.txt
```

发布版直接读取本地 `tokenizer.json` 中保存的快速分词规则。Transformers 5.15
若只按分词器类别信息自动选择实现，会错误地把长文本压缩成很少的 token。
字节级 BPE 会先把文本表示成字节，再把常见的连续字节合并成文本片段；直接读取
`tokenizer.json` 可以同时保留 Transformers 4.57.6 下验证过的输入 token 编号和
正常的输出文本还原。

## 长输出稳定性

生成过程采用以下长输出计算约定：

- 多卡张量并行的部分结果按 rank 顺序逐个相加,相加时使用 FP32。
- 滑窗逐 token 解码使用 PyTorch 默认选择的 SDPA 注意力后端,也就是由当前
  PyTorch 和 CUDA 环境选择其支持的实现,不再强制使用较慢的通用数学实现。
- 请求生成 EOS（结束标记）后,会从后续解码批次中移除,对应缓存行也会同步整理。

这些检查覆盖同一活动批次内不同行位置的稳定性,但不承诺不同批大小、调度方式、
GPU 型号或软件版本之间逐位完全相同。

## 模型权重与启动方式

以下命令均在本目录执行。按源权重格式选择 FP8 或 BF16 小节，两种格式使用不同的
输出目录。转换只切分权重并保留 dtype，不会把 BF16 权重量化成 FP8。

以源模型目录中的 `config.json` 为准。`convert.py` 写出
`tpN/model-r{rank}.safetensors` 及对应的 `config-r{rank}.json`，包含
`gqa-provider-shared-tp-v2` 布局标记和 `expert_parallel_size=N`；分词器文件保存在
共享的 `tokenizer_files/` 下。`generate.py` 从 `--tp-dir` 读取配置，并自动发现
转换时复制的分词器。推理目录不附带模型配置；分片配置必须与同一次转换产生的
权重配套使用。配置省略 `expert_parallel_size` 时，运行时使用 `tp_size`。

<a id="fp8"></a>

## FP8：单节点 8 卡

FP8 路径已在 **8 × H200** 上验证，使用 **TP=EP=8**，每个 rank 放置 44 个路由
专家。源配置需声明 `quant_method="fp8"`；排除量化的专家层和视觉编码器保留 BF16
权重。

设置源权重和输出目录：

```bash
export STEP5_FP8_CHECKPOINT="<fp8-checkpoint-directory>"
export STEP5_FP8_OUT="<fp8-shard-output-directory>"
```

先检查权重名称与分片形状，再转换到新的输出目录，转换只需执行一次。
`--check-only` 只读取文件头，不加载权重数据、不写分片：

```bash
python3 convert.py \
  --checkpoint "$STEP5_FP8_CHECKPOINT" \
  --tp-size 8 --ep-size 8 --check-only

python3 convert.py \
  --checkpoint "$STEP5_FP8_CHECKPOINT" \
  --out-dir "$STEP5_FP8_OUT" \
  --tp-size 8 --ep-size 8
```

在可见 8 张 GPU 的节点上启动文本生成：

```bash
torchrun --standalone --nproc-per-node=8 generate.py \
  --tp-dir "$STEP5_FP8_OUT/tp8" --ep-size 8 \
  --prompt "请介绍一下张量并行。" \
  --max-new-tokens 128
```

图文生成先按[图像输入约定](#vision-inputs)，使用对应 checkpoint 的 processor
准备 prompt IDs 和图像张量，再运行：

```bash
torchrun --standalone --nproc-per-node=8 generate.py \
  --tp-dir "$STEP5_FP8_OUT/tp8" --ep-size 8 \
  --prompt-json prompt-ids.json --image-inputs image-inputs.safetensors \
  --max-new-tokens 128
```

<a id="bf16"></a>

## BF16：双节点共 16 卡

完整 92 层 BF16 图文模型在 TP/EP=8 下，仅参数就约需 **144.41 GiB/卡**，超过
已验证 H200 节点的 **140.40 GiB/卡**。采用 **TP=EP=16** 时，实测加载参数约为
**74.93 GiB/卡**，每个 rank 放置 22 个路由专家。参数占用包含每卡复制的视觉权重和
已切分的输出层，不包含 MTP；KV 缓存、RoPE、激活和通信还需要额外显存。

完整 BF16 解码器、视觉编码器与投影层已在**双节点 16 张 H200** 上通过文本与单图
贪心生成验证。所有 rank 输出 token 一致、正常 EOS，全程 logits 均为有限值。
batch size 为 1、图文 prompt 共 943 个 token（含 898 个视觉 token）时，
实测 PyTorch 显存分配峰值为 **76.37 GiB/卡**；此数值不包含 NCCL、CUDA context
等 PyTorch 之外的分配。通信使用 **NCCL TCP Socket**；尚未验证 RDMA、长上下文
负载或吞吐性能。

完整模型实测使用转换器的 TP 规则流式读取、切分原始权重，并执行发布版模型的
forward。下方完整 BF16 `convert.py` → `generate.py --tp-dir` 文件分片流程尚未
单独端到端执行；权重名称与形状检查、BF16 小模型转换/加载/生成测试已通过。

使用两台各有 8 张可见 H200 的节点。两台机器需要相同代码和兼容环境、可用的 NCCL
网络，以及在配置路径下访问同一套转换后权重和分词器文件的能力。
图文生成时，两台机器还需能够读取内容相同的图像输入文件。

在两台节点上设置以下路径。源权重应为 BF16，且没有量化配置或量化配置为空：

```bash
export STEP5_BF16_CHECKPOINT="<bf16-checkpoint-directory>"
export STEP5_BF16_OUT="<bf16-shard-output-directory>"
```

**只在一台节点上执行一次**检查与转换，生成完整的 16 份分片。启动前确保两台节点
都能访问生成的 `tp16/` 和 `tokenizer_files/` 目录：

```bash
python3 convert.py \
  --checkpoint "$STEP5_BF16_CHECKPOINT" \
  --tp-size 16 --ep-size 16 --check-only

python3 convert.py \
  --checkpoint "$STEP5_BF16_CHECKPOINT" \
  --out-dir "$STEP5_BF16_OUT" \
  --tp-size 16 --ep-size 16
```

在**两台节点上**设置相同、可访问的节点 0 地址，以及空闲的 rendezvous 端口：

```bash
export MASTER_ADDR="<node-0-reachable-IP-or-hostname>"
export MASTER_PORT=29500
```

在**节点 0**上设置：

```bash
export NODE_RANK=0
```

在**节点 1**上设置：

```bash
export NODE_RANK=1
```

在**两台节点上分别执行**下面的文本生成命令，使用各自的 `NODE_RANK` 加入同一次
启动。每台运行 8 个进程，总进程数为 16：

```bash
torchrun --nnodes=2 --nproc-per-node=8 \
  --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" --master-port="$MASTER_PORT" \
  generate.py \
  --tp-dir "$STEP5_BF16_OUT/tp16" --ep-size 16 \
  --prompt "请介绍一下张量并行。" \
  --max-new-tokens 128
```

图文生成则按[图像输入约定](#vision-inputs)准备数据，在**两台节点上分别执行**：

```bash
torchrun --nnodes=2 --nproc-per-node=8 \
  --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" --master-port="$MASTER_PORT" \
  generate.py \
  --tp-dir "$STEP5_BF16_OUT/tp16" --ep-size 16 \
  --prompt-json prompt-ids.json --image-inputs image-inputs.safetensors \
  --max-new-tokens 128
```

启动器设置 `WORLD_SIZE=2 × 8=16`，分片配置和 `--ep-size` 都必须为 16。
`--standalone` 仅用于上面的 FP8 单节点示例。

两种启动方式如需传入精确文本 token IDs，可将 `--prompt` 及其值替换为
`--prompt-json <prompt-json-file>`。文件接受 JSON 列表或
`{"prompt_ids": [...]}`；批量请求使用 `--prompt-json-batch`。

## 限制

- 完整模型生成已验证 FP8 单节点 8 × H200 和 BF16 双节点共 16 × H200，使用流式
  权重加载；完整 BF16 文件分片转换/加载流程尚未端到端验证。
- `--ep-size` 默认 8,且当前必须等于 TP / 进程总数;独立的 TP 与 EP 进程组(例如
  `TP=4, EP=2`)未实现。`generate.py` 从分片配置读取 TP(并对进程总数 `WORLD_SIZE` 做校验),
  刻意没有单独的 `--tp-size` 开关。
- 滑窗注意力使用 PyTorch SDPA。
- 只支持贪心生成。连续动态批处理、分页 KV 缓存、前缀缓存和 CUDA Graph
  均未提供。BF16 跨节点验证覆盖 NCCL TCP Socket 下的短文本与单图请求。
- MTP 层不加载,因此没有投机解码。
- 直接使用原始模型权重中的 FP8/BF16 专家布局;转换器与生成的 TP 分片和该权重布局绑定。

## 多模态 checkpoint（`step5_vl`）

`Step5ForConditionalGeneration` 使用 `Step5VLConfig`，顶层类型为
`model_type=step5_vl`，嵌套配置为 `text_config.model_type=step5` 和
`vision_config.model_type=perception_encoder`。纯文本 checkpoint 使用
`Step5Config` 和 `Step5ForCausalLM`。

Step-5 视觉编码器使用 PyTorch 算子，包含非因果 SDPA、二维 RoPE、绝对位置编码、
LayerScale 和两次卷积下采样。投影后的图像特征在 prefill 注入 packed 文本输入，
文本解码使用 DSA cache 和共置 TP/EP 执行。

已验证的 VL checkpoint 参数如下：

| 组件 | 配置 |
| --- | --- |
| 文本解码器 | 92 层、hidden size 4096；普通生成不加载 3 层 MTP |
| Vision Transformer | 47 层、width 1536、16 个注意力头、MLP size 8960 |
| Patch embedding | RGB，14×14 卷积核，stride 14 |
| 激活与归一化 | QuickGELU、pre-LN、无 post-LN、LayerScale 0.1 |
| 位置编码 | 绝对位置编码和二维 RoPE；无 CLS token |
| 下采样 | 两个 3×3 卷积，stride 2、padding 1；1536→3072→6144 |
| Projector | 6144→4096，无 bias |
| 图像占位符 | Token ID 128001 |
| 视觉权重 | 667 个 BF16 张量；每个 TP rank 约 3.96 GB |

Checkpoint 权重名为 `model.*`、`lm_head.*`、`vision_model.*` 和
`vit_large_projector.*`。Vision 与 projector 在每个 TP rank 上完整复制，
加载文件及 dtype 以 checkpoint 索引为准。转换器排除层编号
`>= text_config.num_hidden_layers` 的 MTP 权重。

VL checkpoint 同样使用上面的 [FP8](#fp8) 或 [BF16](#bf16) 检查与转换命令。
完整分片包含嵌套配置、`Step5ForConditionalGeneration` 架构名，以及文本、
vision 和 projector 权重。

断点恢复和正式加载都会先核对分片的完整 key、shape 以及 TP/EP/rank 元数据。
正式加载还会拒绝 Hugging Face 报告的缺失或异常 key，避免视觉权重缺失时
被默认初始化后继续推理。

<a id="vision-inputs"></a>

### 图像输入约定

图像接口如下：

| 参数 | 含义 |
| --- | --- |
| `pixel_values` | 预处理后的主图 `[图片数, 3, H, W]`，额外的前导 batch 维会被展平。 |
| `patch_pixel_values` | 可选裁剪图，按图片顺序排列。 |
| `num_patches` | 每张主图对应的非负整数裁剪数；省略时全部为 0。 |
| `image_embeds` | 已完成 projector 的 `[..., text_hidden_size]` 特征，与所有像素/裁剪参数互斥。 |

728×728 主图输出 169 个 token，504×504 裁剪图输出 81 个 token。
每张图片的顺序是**先全部裁剪图，再主图**；多请求按 packed prompt 顺序拼接。
`image_token_id` 的占位数量必须与特征 token 总数相同，`<im_start>` / `<im_end>`
仍使用文本 embedding。只在 prefill 编码图片，后续 decode 复用 cache。

缩放、归一化、裁剪和 prompt 构造使用对应 checkpoint 的 processor；这里接收
其预处理结果，没有另行定义 JPEG/PIL 预处理规则。可将结果保存为 safetensors：

```python
import torch
from safetensors.torch import save_file

save_file({
    "pixel_values": pixel_values.contiguous(),
    "patch_pixel_values": patch_pixel_values.contiguous(),
    "num_patches": torch.tensor(num_patches, dtype=torch.int64),
}, "image-inputs.safetensors")
```

准备好包含图像占位 token 的 `prompt-ids.json` 和 `image-inputs.safetensors` 后，
使用 [FP8](#fp8) 或 [BF16](#bf16) 小节中对应的图文启动命令。

`--prompt-json-batch` 可混合文本和图像请求，各 rank 读取相同的图像输入文件。
Python 的 `forward` / `generate_greedy` 也接受这些图像参数。

安装可选测试依赖并运行多模态集成回归：

```bash
python -m pip install pytest
python -m pytest -q test_vision.py
```

支持 `vision_select_layer=-1` 和 `lang` 模式的二维 RoPE，其他层选择或频率模式会显式报错。

### 验证结果

以下结果来自 H200，运行环境为 PyTorch 2.13.0+cu129、Triton 3.7.1、Transformers 5.15.0：

| 检查 | 结果 |
| --- | --- |
| 视觉集成、配置身份与 BF16 加载测试 | 20 passed |
| 配置、生成、服务、评测和缓存回归 | 203 passed，93 subtests passed |
| GPU 算子检查 | 10 项全部通过 |
| 批次与 NCCL TP 稳定性 | 通过 |
| FP8 checkpoint 结构，TP8 | 2653 个 runtime 张量通过，排除 51 个 MTP 张量 |
| BF16 checkpoint 结构，TP8 与 TP16 | 2398 个 runtime 张量通过，排除 51 个 MTP 张量 |
| BF16 小模型生成 | TP1/TP8 像素与投影后 embedding 输入生成相同 token IDs |
| 完整视觉数值验证 | 主图和裁剪图输出精确匹配，最大绝对误差 0 |
| TP8 混合精度测试模型 | 像素与投影后 embedding 输入生成相同 token IDs |
| HF 文件分片加载，完整真实 rank 0 | 85.4 GB 分片加载通过，真实图像特征 `[898,4096]` 精确匹配 |
| 完整真实 FP8 checkpoint TP8 图像生成，流式权重加载 | 正确描述草地上的白色萨摩耶犬；生成 27 个 token，正常 EOS，各 rank 输出相同 |
| 完整真实 BF16 checkpoint，双节点 TP16/EP16，流式权重加载 | 文本与单图生成通过；logits 均为有限值、正常 EOS、16 个 rank 的 token 一致；参数 74.93 GiB/卡，PyTorch 分配峰值 76.37 GiB/卡 |

单图用例包含一张 728×728 主图和九张 504×504 裁剪图，共 898 个视觉 token。
视觉编码使用 PyTorch 和融合 GPU 注意力。这些结果覆盖所测输入的功能和数值正确性，
不构成多模态基准或 OCR/视频质量评测。
