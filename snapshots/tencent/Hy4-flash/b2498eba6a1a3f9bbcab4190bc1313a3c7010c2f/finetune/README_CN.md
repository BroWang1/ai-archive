<p align="left">
   <a href="README.md">English</a> ｜ 中文
</p>

# 模型微调

Hy4 flash 提供了模型微调相关流程，您可以在此章节对训练数据格式进行处理以供模型微调使用。

## 训练数据格式及处理

**Hy4 flash 支持两种思考模式，可通过 `reasoning_effort` 参数控制（仅支持 `no_think` 与 `high`，传入其他值会报错）**：

| `reasoning_effort` | 模式 | 说明 |
|---|---|---|
| `no_think` | 快思考 | 不进行推理过程，模型直接输出答案。 |
| `high` | 深度思考 | 充分推理，思考过程详细。 |

训练数据按照以下形式处理为 messages 格式，训练和推理的默认 system prompt 为空，可以根据自己的需求进行设定。

对于 `high` 模式，assistant 的推理过程可放在 `reasoning_content` 字段中（`chat_template` 也支持 `reasoning` 字段且优先级更高）；`no_think` 模式下模板始终输出空的 `<think></think>`，无需提供推理字段。

```jsonl
# 快思考模式 (no_think) — 无推理字段
{"reasoning_effort": "no_think", "messages": [{"content": "你是一个有用的人工智能助手。\n现在的时间是2026-01-01 13:26:12 周四", "role": "system"}, {"content": "1+1=?", "role": "user"}, {"role": "assistant", "content": "1+1=2"}]}

# 深度思考模式 (high) — 包含推理过程
{"reasoning_effort": "high", "messages": [{"content": "你是一个有用的人工智能助手。\n现在的时间是2026-01-01 13:26:12 周四", "role": "system"}, {"content": "1+1=?", "role": "user"}, {"role": "assistant", "content": "1+1=2", "reasoning_content": "用户问的是1+1等于多少。在基本的十进制算术中，1+1等于2。"}]}
```

> **`reasoning_effort` 默认值说明：**
> - **训练时**：如果训练数据中未指定 `reasoning_effort`，训练脚本默认使用 `no_think`（快思考）。这是因为训练脚本会将不含推理字段的样本视为非思考模式数据。
> - **推理时**：如果调用 `apply_chat_template` 时未传入 `reasoning_effort` 参数，`chat_template` 默认使用 `high`（深度思考）。

使用 `apply_chat_template` 进行 tokenize 的示例：

```python
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("./models", use_fast=False, trust_remote_code=True)

messages = [
    {"content": "你是一个有用的人工智能助手。", "role": "system"},
    {"content": "1+1=?", "role": "user"},
    {"role": "assistant", "content": "1+1=2"}
]
ids = tokenizer.apply_chat_template(messages, tokenize=True, reasoning_effort="no_think")
```

### 多模态数据格式（图片 / 视频）

Hy4 flash 支持图片、视频和纯文本的混合训练。数据格式为 JSONL，每行一个样本。

#### 图片数据

在 user 消息中使用 `<image>` 标签标记图片位置，并在 `images` 字段中提供图片路径列表：

```json
{"messages": [{"role": "system", "content": "你是一个有用的人工智能助手。"}, {"role": "user", "content": "<image>请详细描述这张图片。"}, {"role": "assistant", "content": "图片展示了一幅美丽的海上日落景象。"}], "images": ["test_images/sunset.jpg"]}
```

支持多张图片 —— 使用多个 `<image>` 标签，并在 `images` 列表中按顺序提供对应的路径：

```json
{"messages": [{"role": "user", "content": "<image>请比较第一张图片和第二张图片。<image>"}], "images": ["img1.jpg", "img2.jpg"]}
```

#### 视频数据

在 user 消息中使用 `<video>` 标签标记视频位置，并在 `videos` 字段中提供视频路径列表：

```json
{"messages": [{"role": "system", "content": "你是一个有用的人工智能助手。"}, {"role": "user", "content": "<video>请描述这个视频中发生了什么。"}, {"role": "assistant", "content": "视频展示了一只猫在硬木地板上玩毛线球。"}], "videos": ["test_videos/cat.mp4"]}
```

#### 纯文本数据（混合训练）

不包含 `<image>` 或 `<video>` 标签的样本会被当作纯文本处理，可以与多模态数据混合在同一个 JSONL 文件中：

```json
{"messages": [{"role": "system", "content": "你是一个有用的人工智能助手。"}, {"role": "user", "content": "法国的首都是哪里？"}, {"role": "assistant", "content": "法国的首都是巴黎。"}]}
```

#### 注意事项

- 图片/视频路径可以是**绝对路径**或**相对路径**（相对于 JSONL 文件所在目录或工作目录，具体取决于训练框架）。
- 消息中的 `<image>` / `<video>` 标签数量必须与 `images` / `videos` 列表中的路径数量一致。
- 单个样本可以同时包含 `images` 和 `videos` 字段。
- 支持的图片格式取决于 [Pillow](https://pillow.readthedocs.io/) 库（常见格式如 JPEG、PNG 等均支持）。支持的视频格式取决于视频解码后端（默认为 [PyAV](https://pyav.org/)，基于 FFmpeg，常见格式如 MP4 等均支持）。
- 纯文本示例数据位于 `data/example_data.jsonl`，多模态示例数据位于 `data/example_vl_data.jsonl`。

## 微调流程

### 硬件需求

经过测试，最小的资源配置如下：

- **LoRA 微调**：最少需要 4 机 32 卡，每卡显存至少 96GB，每机 CPU 内存至少 2TB。
- **全量微调**：最少需要 4 机 32 卡，每卡显存至少 96GB，每机 CPU 内存至少 2TB。

> 注：以上为最小资源配置，实际所需资源会随 max_seq_length、batch size、图片分辨率、视频帧数等因素相应增加。多模态数据（尤其是高分辨率图片和视频）的显存消耗显著高于纯文本。

### 配置机器间免密 ssh 登录（多机训练）

> 如果只使用单机训练，可跳过本节。

以下操作以两个机器为例，两台机器的 ip 分别以`${ip1}`和`${ip2}`标识，以下操作均在 docker container 内执行。

首先，配置多机container免密，在每台机器上执行。

```sh
ssh-keygen			# 生成id_rsa和id_rsa.pub，用于免密登录
ssh-keygen -t rsa -A    # 生成/etc/ssh/ssh_host_rsa_key和ssh_host_ecdsa_key， 用于后面启动ssh listen
/usr/sbin/sshd -p 36005 -o ListenAddress=0.0.0.0        # 启动 SSH 监听
echo "Port 36005" > ~/.ssh/config   # ssh 连接端口修改为 36005
passwd root    # 需要配置root密码，否则监测平台会报警
```

注意：这里的`36005`是一个示例端口，可以选用任意端口，但需要保证使用的端口**开放**且**不被其他的进程占用**。

接下来，在每台机器的 container 内，执行：

```sh
cat ~/.ssh/id_rsa.pub
```

**将输出的 ssh 公钥复制并粘贴到`~/.ssh/authorized_keys`文件中，每行一个公钥，每台机器上都要做这个操作**。最终每台机器上的`~/.ssh/authorized_keys`文件内容应当是一致的，并且包含了所有机器的公钥。

需要注意，多节点训练时，每个节点上执行的代码都得一致，建议挂载一个共享的网络盘，如果无法挂载共享网盘，则需要手动将数据集、脚本、代码复制在多台机器的相同目录下。

### 启动方式

本项目提供三种微调方式，您可以根据需求选择：

- **DeepSpeed 原生微调**（基于 HuggingFace Transformers Trainer）：位于 `deepspeed_support` 目录下
- **LLaMA-Factory 微调**：位于 `llama_factory_support` 目录下
- **ms-swift 微调**：位于 `ms_swift_support` 目录下

#### DeepSpeed 原生微调

参考：[HuggingFace Transformers Trainer](https://huggingface.co/docs/transformers/main/en/main_classes/trainer)

`deepspeed_support` 目录下提供了以下启动脚本：

| 场景 | 启动脚本 | 训练脚本 | 说明 |
|---|---|---|---|
| VL 微调（图片/视频/文本） | `bash train_vl.sh` | `train_vl.py` | 多模态微调（冻结 ViT） |
| 纯文本微调 | `bash train_llm.sh` | `train_vl.py` | 使用 VL checkpoint 进行纯文本训练（冻结 ViT） |

##### 单机启动微调

首先安装依赖（`requirements.txt` 位于 `finetune` 根目录下）：

```sh
pip install -r ../requirements.txt
```

然后安装包含 Hy4 flash 模型定义的 transformers 开发版本（从 GitHub PR 安装）：

```sh
pip install "transformers @ git+https://github.com/huggingface/transformers.git@refs/pull/50903/head"
```

> **注意：** 此 transformers 版本包含 Hy4 flash 模型的完整支持，是运行微调的必要依赖。待该 PR 合入正式版本后，可改用 `pip install transformers>=X.Y.Z` 安装。

然后在 `deepspeed_support` 目录下，执行：

```sh
# 纯文本微调
bash train_llm.sh

# VL 多模态微调
bash train_vl.sh
```

##### 多机启动微调

如果要用多台机器启动微调，请先完成 [配置机器间免密 ssh 登录](#配置机器间免密-ssh-登录多机训练) 中的配置，并保证多台机器在一个集群内。

确认依赖已经安装完成，然后修改对应启动脚本（如 `train_llm.sh` 或 `train_vl.sh`）中开头的以下配置：

```sh
export HOST_GPU_NUM=8
# IP list, comma separated. e.g. "192.168.1.1,192.168.1.2" or single node "192.168.1.1"
IP_LIST=${IP_LIST:-"127.0.0.1"}
```

注意：如果`IP_LIST`环境变量未设置，则将`IP_LIST`替换为IP列表！格式为：
```text
如果只有一个IP：
IP_LIST=${ip_1}

如果有多个IP：
IP_LIST=${ip_1},${ip_2}

```

请将`${ip_1}`和`${ip_2}`替换为真实的IP地址。

然后，在`${ip1}`的机器上，在`deepspeed_support/`目录下，执行对应的启动脚本即可（如 `bash train_llm.sh` 或 `bash train_vl.sh`）。注意第一次启动时可能会看见以下的输出：

```text
The authenticity of host '[ip]:36005 ([ip]:36005)' can't be established.
ECDSA key fingerprint is xxxxxx.
ECDSA key fingerprint is MD5:xxxxxx.
Are you sure you want to continue connecting (yes/no)?
```

此时输入`yes`即可继续。

##### 关键参数

脚本中的关键参数如下：

- `--deepspeed`: 此参数应当指向一个 deepspeed 的配置文件，`deepspeed_support`文件夹下提供了四种 DeepSpeed 的默认配置文件：`ds_zero2_no_offload.json`, `ds_zero2_offload.json`, `ds_zero3_no_offload.json`, `ds_zero3_offload.json`，可根据显存与通信情况选择不同的 ZeRO 阶段（ZeRO-2 / ZeRO-3）与 offload 策略
- `--model_name_or_path`: 要加载的 Hy4 flash 的 HF 预训练模型权重路径，否则无法加载
- `--tokenizer_name_or_path`: tokenizer 文件夹路径，否则无法加载
- `--train_data_file`: 训练文件路径，应该为一个 jsonl 文件
- `--output_dir`: 输出文件夹，log、tensorboard 和权重都会存储在这个路径下
- `--per_device_train_batch_size`: 每张卡上的 batch size
- `--gradient_accumulation_steps`: 梯度累计次数，`per_device_train_batch_size * gradient_accumulation_steps * dp_size`为 global_batch_size
- `--max_steps`: 训练的总步数
- `--save_steps`: 每多少个 step 存储一个 checkpoint
- `--gradient_checkpointing`: 开启梯度检查点
- `--learning_rate`: 训练时的最大学习率
- `--min_lr`: 训练时的最小学习率（绝对值，如 `1e-6`；不传时默认 `0.01`，此时按 `learning_rate * min_lr` 比例计算）
- `--use_flash_attn`: 开启 flash-attention 进行训练加速

##### 显存不足怎么办？

参考：[DeepSpeed Configuration](https://www.deepspeed.ai/docs/config-json/)

可以尝试修改 ds config，去掉这几个参数的 auto 属性，改小试试看：

- `stage3_param_persistence_threshold`
- `stage3_prefetch_bucket_size`
- `stage3_max_reuse_distance`

##### 多模态（VL）微调

`train_vl.sh` 同时支持三种数据：图片+文本、视频+文本、纯文本。数据格式详见 [多模态数据格式](#多模态数据格式图片--视频)。

VL 特有参数（除上述参数外）：

- `--freeze_vit`: 冻结 ViT 视觉编码器（默认开启，即 `default=True`）。冻结后视觉编码器权重不会被更新，训练集中在 LLM 和投影层上。如需训练视觉编码器，请显式设置 `--freeze_vit false`。
- `--train_data_file`: 包含多模态数据的 JSONL 训练文件路径（含 `images` / `videos` 字段）。
- `--image_base_dir`: 用于解析数据文件中相对图片/视频路径的基础目录。如未指定，路径相对于工作目录解析。

**图片处理参数**（对齐 HuggingFace processor 的 `images_kwargs` API）：

- `--image_min_pixels`: 图片缩放的最小像素数。对应 HF image processor 中 `size["shortest_edge"]`。默认值 `None`（使用 `preprocessor_config.json` 中的配置，默认 4096）。
- `--image_max_pixels`: 图片缩放的最大像素数。对应 HF image processor 中 `size["longest_edge"]`。默认值 `None`（使用 `preprocessor_config.json` 中的配置，默认 4194304）。

**视频处理参数**（对齐 HuggingFace processor 的 `videos_kwargs` API）：

- `--video_max_pixels`: 视频所有帧的总像素预算。对应 HF video processor 中 `size["longest_edge"]`。默认值 `None`（使用 `video_preprocessor_config.json` 中的配置）。设置此参数后，每帧的像素预算为 `video_max_pixels / num_frames`，从而控制视频产生的 token 数量。
- `--video_max_frames`: 从视频中采样的最大帧数。对应 HF video processor 中 `max_frames`。默认值 `None`。
- `--video_fps`: 视频采样的目标帧率（每秒采样帧数）。对应 HF video processor 中 `fps`。默认值 `None`。

> **视频参数说明：** 视频产生的 token 数量远大于图片。应根据 `--max_seq_length` 合理设置视频参数，确保视频 token 不超出序列长度限制。

#### LLaMA-Factory 微调

如果对 LLaMA-Factory 较为熟悉，可使用 LLaMA-Factory 进行微调。脚本、代码以及配置文件都归档在 `llama_factory_support` 目录下。如果没有特别说明，接下来我们提到的文件都是该目录下的文件。

##### 安装

可以通过下载源码 https://github.com/hiyouga/LLaMA-Factory/tree/main ，根据网站的指引进行安装。

##### 配置文件

我们提供了 llama-factory 的微调示例配置文件，分别对应不同的微调场景：

| 配置文件 | 场景 |
|---|---|
| `hy_v4_flash_full_sft.yaml` | LLM 全量微调 |
| `hy_v4_flash_lora_sft.yaml` | LLM LoRA 微调 |
| `hy_v4_flash_vl_full_sft.yaml` | VL 全量微调 |
| `hy_v4_flash_vl_lora_sft.yaml` | VL LoRA 微调 |

脚本中的关键参数如下：

**模型相关：**

- `model_name_or_path`: Hy4 flash HF 格式预训练模型权重路径
- `trust_remote_code`: 是否信任远程代码，Hy4 flash 需要设置为 `true`

**训练方法：**

- `stage`: 训练阶段，当前为 `sft`（监督微调）
- `finetuning_type`: 微调类型，可选 `full`（全量微调）或 `lora`（LoRA 微调）
- `deepspeed`: DeepSpeed 配置文件路径，全量微调推荐 `../deepspeed_support/ds_zero3_offload.json`
- `fsdp` + `fsdp_config`: FSDP 分布式策略，LoRA 微调推荐使用 FSDP（配置已内置在 `hy_v4_flash_lora_sft.yaml` 中）；与 DeepSpeed 二选一

> **分布式策略选择建议：**
> - **FSDP**：推荐用于 LoRA 微调，兼容性好，配置简单
> - **DeepSpeed ZeRO-3 + Offload**：推荐用于全量微调或显存紧张的场景

**LoRA 参数（仅 LoRA 微调时生效）：**

- `lora_rank`: LoRA 秩，默认 `64`
- `lora_alpha`: LoRA alpha 系数，默认 `128`
- `lora_dropout`: LoRA dropout 比率，默认 `0.05`
- `lora_target`: LoRA 应用的目标模块，默认为 `q_a_proj,q_b_proj,kv_a_proj_with_mqa,kv_b_proj,o_proj`

**数据集：**

- `dataset_dir`: 数据集目录路径
- `dataset`: 数据集名称，需要在 `dataset_dir` 下的 `dataset_info.json` 中注册
- `template`: 对话模板，Hy4 flash 使用 `hy_v4_flash`
- `cutoff_len`: 最大序列长度，超出部分会被截断；LoRA 微调建议适当减小以节省显存
- `max_samples`: 每个数据集最多使用的样本数
- `overwrite_cache`: 是否覆盖已缓存的预处理数据集

**输出：**

- `output_dir`: 输出目录，日志、TensorBoard 和权重都会存储在此路径下
- `logging_steps`: 每多少步记录一次日志
- `save_steps`: 每多少步保存一次 checkpoint
- `plot_loss`: 是否绘制训练 loss 曲线
- `overwrite_output_dir`: 是否覆盖已有的输出目录
- `save_only_model`: 是否只保存模型权重（不保存优化器状态等）
- `report_to`: 日志上报工具，可选 `none`、`wandb`、`tensorboard`、`swanlab`、`mlflow`

**训练超参数：**

- `per_device_train_batch_size`: 每张卡上的 batch size
- `gradient_accumulation_steps`: 梯度累积步数，`per_device_train_batch_size * gradient_accumulation_steps * dp_size` 为 global batch size
- `learning_rate`: 最大学习率，全量微调推荐 `1.0e-5`，LoRA 微调推荐 `2.0e-4`
- `num_train_epochs`: 训练轮数
- `lr_scheduler_type`: 学习率调度器类型，推荐使用 `cosine_with_min_lr`
- `lr_scheduler_kwargs.min_lr_rate`: 最小学习率与最大学习率的比值，例如 `0.1` 表示最小学习率为最大学习率的 10%
- `warmup_steps`: 预热步数
- `bf16`: 是否使用 BFloat16 混合精度训练
- `gradient_checkpointing`: 是否开启梯度重计算以节省显存
- `ddp_timeout`: 分布式训练超时时间（毫秒）
- `flash_attn`: 注意力实现方式，可选 `auto`（自动选择）、`sdpa`、`disabled`（禁用）等。具体默认值视配置文件而定（如 LLM 全量微调为 `disabled`，LLM LoRA 为 `auto`，VL 全量微调为 `auto`，VL LoRA 为 `disabled`）
- `resume_from_checkpoint`: 从指定 checkpoint 路径恢复训练，设为 `null` 表示从头开始训练

**图片/视频处理参数（VL 微调时生效）：**

以下参数由模型自带的 processor 配置决定（见 `hy_v4_template.py`），默认值如下。如需调整，可在 YAML 配置文件中覆盖（需确认 LLaMA-Factory 版本支持）或修改 processor 配置：

- `image_max_pixels`: 图片缩放的最大像素数，默认 `4194304`（2048×2048）
- `image_min_pixels`: 图片缩放的最小像素数，默认 `4096`（64×64）
- `video_max_pixels`: 视频每帧的最大像素数，默认 `65536`（256×256）
- `video_min_pixels`: 视频每帧的最小像素数，默认 `256`（16×16）
- `video_fps`: 视频采样帧率，默认 `2.0`
- `video_maxlen`: 视频最大采样帧数，默认 `128`

> **视频参数说明：** 视频产生的 token 数量远大于图片。应根据 `cutoff_len` 合理设置视频参数，确保视频 token 不超出序列长度限制。降低 `video_max_pixels` 或 `video_maxlen` 可显著减少显存占用。

##### 启动脚本

我们为不同场景提供了对应的启动脚本：

| 场景 | 启动脚本 | 默认配置文件 |
|---|---|---|
| VL 全量微调 | `bash train_lf.sh` | `hy_v4_flash_vl_full_sft.yaml` |
| VL LoRA 微调 | `bash train_lf_lora.sh` | `hy_v4_flash_vl_lora_sft.yaml` |
| LLM 全量微调 | `bash train_lf_llm.sh` | `hy_v4_flash_full_sft.yaml` |
| LLM LoRA 微调 | `bash train_lf_lora_llm.sh` | `hy_v4_flash_lora_sft.yaml` |

每个脚本均支持通过 `YAML_FILE` 环境变量覆盖默认配置文件。

##### 启动微调

如需多机训练，请先完成 [配置机器间免密 ssh 登录](#配置机器间免密-ssh-登录多机训练) 中的配置（单机训练可跳过此步骤）。

修改对应启动脚本中开头的以下配置：

```sh
export HOST_GPU_NUM=8
# IP list, comma separated. e.g. "192.168.1.1,192.168.1.2" or single node "192.168.1.1"
export IP_LIST=${IP_LIST:-"127.0.0.1"}
```

注意：
1. 如果 `IP_LIST` 环境变量未设置，则将 `IP_LIST` 替换为 IP 列表！格式为：
```text
如果只有一个IP：
IP_LIST=${ip_1}

如果有多个IP：
IP_LIST=${ip_1},${ip_2}

```
请将 `${ip_1}` 和 `${ip_2}` 替换为真实的 IP 地址。

2. 如需指定微调配置文件，可通过 `YAML_FILE` 环境变量设置（建议使用绝对路径，或先 `cd` 到 `llama_factory_support/` 目录后再执行）。例如：
```sh
export YAML_FILE=/path/to/llama_factory_support/hy_v4_flash_lora_sft.yaml
```

多机训练时，每台机器上都需要启动 `torchrun` 进程。启动脚本中内置了 `pdsh` 一键分发功能，只需在一台机器上执行即可自动分发到所有节点：

```sh
# VL 全量微调
bash train_lf.sh

# LLM 全量微调
bash train_lf_llm.sh
```

> **注意：** 如果您的环境不支持 `pdsh`，或需要自定义启动方式，请在每台机器上分别手动执行启动脚本。手动执行时必须设置 `_WORKER_MODE=1` 以跳过 pdsh 分发分支，例如：
> ```bash
> # 在每台机器上分别执行：
> export IP_LIST="10.0.0.1,10.0.0.2"
> export _WORKER_MODE=1
> bash train_lf.sh
> ```

##### 多模态（VL）微调

VL 微调与纯文本配置的主要区别：

- `template`: 设为 `hy_v4_flash_vl`（而非 `hy_v4_flash`）
- `dataset`: 使用在 `dataset_info.json` 中注册的 VL 数据集，需包含 `images` 列；如需同时支持视频，还需包含 `videos` 列
- `freeze_vision_tower`: 设为 `true` 以冻结 ViT 视觉编码器（推荐）

如需注册自定义 VL 数据集，在 `dataset_info.json` 中添加条目：

```json
{
  "my_vl_dataset": {
    "file_name": "/path/to/my_vl_data.jsonl",
    "formatting": "sharegpt",
    "columns": {
      "messages": "messages",
      "images": "images",
      "videos": "videos"
    },
    "tags": {
      "role_tag": "role",
      "content_tag": "content",
      "user_tag": "user",
      "assistant_tag": "assistant",
      "system_tag": "system"
    }
  }
}
```

#### ms-swift 微调

如果对 ms-swift 较为熟悉，可使用 ms-swift 进行微调。脚本和代码都归档在 `ms_swift_support` 目录下。如果没有特别说明，接下来我们提到的文件都是该目录下的文件。

##### 安装

可以通过 pip 安装 ms-swift：

```sh
pip install ms-swift
```

或从源码安装：https://github.com/modelscope/ms-swift

##### 微调脚本

| 场景 | 微调方式 | 启动脚本 |
|---|---|---|
| 纯文本（LLM） | 全量微调 | `bash sft_train.sh` |
| 纯文本（LLM） | LoRA 微调 | `bash sft_train_lora.sh` |
| 多模态（VL） | 全量微调 | `bash sft_train_vl.sh` |
| 多模态（VL） | LoRA 微调 | `bash sft_train_vl_lora.sh` |

> **注意：** ms-swift 的训练参数直接在启动脚本中以 CLI 参数形式配置，如需修改请直接编辑对应的启动脚本。

##### 关键参数

启动脚本中的关键参数如下：

**模型相关：**

- `model`: 模型路径，可以是 HuggingFace Hub ID 或本地路径
- `model_type`: 模型类型，设为 `hy_v4_flash_vl`
- `template`: 对话模板，设为 `hy_v4_flash_vl`
- `torch_dtype`: 数据类型，推荐 `bfloat16`
- `attn_impl`: 注意力实现，默认 `eager`

**训练方法：**

- `tuner_type`: 微调类型，全量微调设为 `full`，LoRA 微调设为 `lora`
- `lora_rank`: LoRA 秩，默认 `64`
- `lora_alpha`: LoRA alpha 系数，默认 `128`
- `lora_dropout`: LoRA dropout 比率，默认 `0.05`
- `target_modules`: LoRA 应用的目标模块，默认为 MLA 投影层：`q_a_proj`, `q_b_proj`, `kv_a_proj_with_mqa`, `kv_b_proj`, `o_proj`

**数据集：**

- `dataset`: 数据集路径，支持本地 jsonl 文件（sharegpt 格式）
- `max_length`: 最大序列长度，超出部分会被截断
- `lazy_tokenize`: 是否延迟 tokenize，推荐 `true`

**输出：**

- `output_dir`: 输出目录
- `save_steps`: 每多少步保存一次 checkpoint
- `save_total_limit`: 最多保留的 checkpoint 数量
- `logging_steps`: 每多少步记录一次日志
- `report_to`: 日志上报工具，可选 `none`, `wandb`, `tensorboard`, `swanlab`, `mlflow`

**训练超参数：**

- `per_device_train_batch_size`: 每张卡上的 batch size
- `gradient_accumulation_steps`: 梯度累积步数
- `learning_rate`: 最大学习率，全量微调推荐 `1.0e-5`，LoRA 微调推荐 `2.0e-4`
- `num_train_epochs`: 训练轮数
- `lr_scheduler_type`: 学习率调度器类型，推荐 `cosine`
- `warmup_steps`: 预热步数
- `bf16`: 是否使用 BFloat16 混合精度训练

**分布式策略 / 优化：**

- `deepspeed`: DeepSpeed 配置文件路径，脚本中默认使用 `../deepspeed_support/ds_zero3_offload.json`；全量微调推荐 ZeRO-3 + Offload
- `fsdp`: FSDP 配置文件路径（JSON），LoRA 微调推荐使用 FSDP；与 DeepSpeed 二选一
- `gradient_checkpointing`: 是否开启梯度重计算
- `max_grad_norm`: 梯度裁剪阈值

> **分布式策略选择建议：**
> - **FSDP**：推荐用于 LoRA 微调，兼容性好，配置简单
> - **DeepSpeed ZeRO-3 + Offload**：推荐用于全量微调或显存紧张的场景

**其他：**

- `ddp_timeout`: 分布式训练超时时间（毫秒）
- `seed`: 随机种子
- `resume_from_checkpoint`: 从指定 checkpoint 路径恢复训练

**图片/视频处理参数（VL 微调时生效）：**

ms-swift 的图片/视频处理由模型自带的 image processor 和 video processor 控制，参数默认值来自模型目录下的 `preprocessor_config.json` 和 `video_preprocessor_config.json`（以实际 ckpt 内的 JSON 配置为准）。如需调整，可直接修改模型目录下对应的 JSON 配置文件。

图片处理参数（`preprocessor_config.json`）：

- `min_pixels`: 图片缩放的最小像素数，默认 `4096`
- `max_pixels`: 图片缩放的最大像素数，默认 `4194304`（2048×2048）

视频处理参数（`video_preprocessor_config.json`）：

- `size.longest_edge`: 视频所有帧的总像素预算，默认 `1572864`
- `max_image_size.longest_edge`: 单帧视频的最大像素数，默认 `262144`
- `max_frames`: 视频最大采样帧数，默认 `2`
- `fps`: 视频采样的目标帧率（每秒采样帧数），默认 `2`
- `do_sample_frames`: 是否启用帧采样，默认 `true`

> **视频参数说明：** 视频产生的 token 数量远大于图片。应根据 `max_length` 合理设置视频参数，确保视频 token 不超出序列长度限制。降低 `size.longest_edge`、`max_image_size.longest_edge` 或 `max_frames` 可显著减少显存占用。

##### 启动微调

如需多机训练，请先完成 [配置机器间免密 ssh 登录](#配置机器间免密-ssh-登录多机训练) 中的配置（单机训练可跳过此步骤）。

修改对应启动脚本中开头的以下配置：

```sh
export HOST_GPU_NUM=8
# IP list, comma separated. e.g. "10.0.0.1,10.0.0.2" or single node "127.0.0.1"
export IP_LIST=${IP_LIST:-"127.0.0.1"}
```

多机训练时，每台机器上都需要启动 `torchrun` 进程。启动脚本中内置了 `pdsh` 一键分发功能，只需在一台机器上执行即可自动分发到所有节点：

```sh
# 纯文本全量微调
bash sft_train.sh

# 纯文本 LoRA 微调
bash sft_train_lora.sh

# VL 全量微调 + DeepSpeed ZeRO-3
bash sft_train_vl.sh

# VL LoRA 微调 + FSDP
bash sft_train_vl_lora.sh

# 多机训练（使用 pdsh 一键分发，只需在一台机器上执行）
IP_LIST="10.0.0.1,10.0.0.2" bash sft_train.sh
```

> **注意：** 如果您的环境不支持 `pdsh`，或需要自定义启动方式，请在每台机器上分别手动执行启动脚本。手动执行时必须设置 `_WORKER_MODE=1` 以跳过 pdsh 分发分支，例如：
> ```bash
> # 在每台机器上分别执行：
> export IP_LIST="10.0.0.1,10.0.0.2"
> export _WORKER_MODE=1
> bash sft_train.sh
> ```

##### 多模态（VL）微调

VL 微调与纯文本脚本的主要区别如下：

- `model_type`: 设为 `hy_v4_flash_vl`（而非 `hy_v4_flash`）
- `template`: 设为 `hy_v4_flash_vl`（而非 `hy_v4_flash`）
- `dataset`: 指向包含多模态数据的 JSONL 文件（含 `images` / `videos` 字段）
