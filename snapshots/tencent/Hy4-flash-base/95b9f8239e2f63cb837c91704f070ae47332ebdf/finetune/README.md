<p align="left">
    <a href="README_CN.md">中文</a> ｜ English
</p>

# Model Fine-tuning

Hy4 flash provides processes related to model fine-tuning. This section details how to process training data for model fine-tuning purposes.

## Training Data Format and Processing

**Hy4 flash supports two thinking modes, controlled by the `reasoning_effort` parameter (only `no_think` and `high` are accepted; any other value raises an error). The available options are**:

| `reasoning_effort` | Mode | Description |
|---|---|---|
| `no_think` | Fast thinking | No reasoning process; the model directly outputs the answer. |
| `high` | Deep thinking | Thorough reasoning with a detailed thinking process. |

The training data should be formatted as a list of messages shown below. By default, the system prompt for both training and inference is empty; customize it as needed.

For `high` mode, the assistant's reasoning process can be provided in the `reasoning_content` field (the `chat_template` also accepts a `reasoning` field, which takes precedence); in `no_think` mode the template always emits empty `<think></think>` tags, so no reasoning field is needed.

```jsonl
# Fast thinking pattern (no_think) — no reasoning field
{"reasoning_effort": "no_think", "messages": [{"content": "You are a helpful assistant.\nThe current time is 2026-01-01 13:26:12 Thursday", "role": "system"}, {"content": "1+1=?", "role": "user"}, {"role": "assistant", "content": "1+1=2"}]}

# Deep thinking pattern (high) — with reasoning content
{"reasoning_effort": "high", "messages": [{"content": "You are a helpful assistant.\nThe current time is 2026-01-01 13:26:12 Thursday", "role": "system"}, {"content": "1+1=?", "role": "user"}, {"role": "assistant", "content": "1+1=2", "reasoning_content": "The user is asking for the result of 1 + 1. In basic decimal arithmetic, 1 + 1 equals 2."}]}
```

> **`reasoning_effort` default values:**
> - **During training**: If `reasoning_effort` is not specified in the training data, the training script defaults to `no_think` (fast thinking). This is because samples without a reasoning field are treated as non-thinking-mode data by the training script.
> - **During inference**: If `reasoning_effort` is not passed when calling `apply_chat_template`, the `chat_template` defaults to `high` (deep thinking).

Example of using `apply_chat_template` to tokenize:

```python
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("./models", use_fast=False, trust_remote_code=True)

messages = [
    {"content": "You are a helpful assistant.", "role": "system"},
    {"content": "1+1=?", "role": "user"},
    {"role": "assistant", "content": "1+1=2"}
]
ids = tokenizer.apply_chat_template(messages, tokenize=True, reasoning_effort="no_think")
```

### Multimodal Data Format (Image / Video)

Hy4 flash supports mixed training with images, videos, and pure text. The data format is JSONL, with one sample per line.

#### Image Data

Use the `<image>` tag in the user message to mark the image position, and provide the image path list in the `images` field:

```json
{"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "<image>Please describe this image in detail."}, {"role": "assistant", "content": "The image shows a beautiful sunset over the ocean."}], "images": ["test_images/sunset.jpg"]}
```

Multiple images are supported — use multiple `<image>` tags and provide the corresponding paths in the `images` list (in order):

```json
{"messages": [{"role": "user", "content": "<image>Compare the first image with the second one.<image>"}], "images": ["img1.jpg", "img2.jpg"]}
```

#### Video Data

Use the `<video>` tag in the user message to mark the video position, and provide the video path list in the `videos` field:

```json
{"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "<video>Please describe what is happening in this video."}, {"role": "assistant", "content": "The video shows a cat playing with a ball of yarn on a hardwood floor."}], "videos": ["test_videos/cat.mp4"]}
```

#### Pure Text Data (Mixed Training)

Samples without `<image>` or `<video>` tags are treated as pure text and can be mixed in the same JSONL file:

```json
{"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "What is the capital of France?"}, {"role": "assistant", "content": "The capital of France is Paris."}]}
```

#### Notes

- Image/video paths can be **absolute paths** or **relative paths** (relative to the JSONL file location or the working directory, depending on the training framework).
- The number of `<image>` / `<video>` tags in the message must match the number of paths in the `images` / `videos` list.
- A single sample can contain both `images` and `videos` fields simultaneously.
- Supported image formats depend on the [Pillow](https://pillow.readthedocs.io/) library (common formats such as JPEG, PNG, etc. are supported). Supported video formats depend on the video decoding backend (default is [PyAV](https://pyav.org/), which is based on FFmpeg; common formats such as MP4 are supported).
- Pure text example data is provided in `data/example_data.jsonl`, and multimodal example data in `data/example_vl_data.jsonl`.

## Fine-tuning Process

### Hardware Requirements

Based on testing, the minimum resource configuration is as follows:

- **LoRA Fine-tuning**: At least 4 machines with 32 GPUs (at least 96GB GPU memory per GPU, at least 2TB CPU memory per machine).
- **Full Fine-tuning**: At least 4 machines with 32 GPUs (at least 96GB GPU memory per GPU, at least 2TB CPU memory per machine).

> Note: The above are minimum resource configurations; actual requirements increase with `max_seq_length`, batch size, image resolution, number of video frames, etc. Multimodal data (especially high-resolution images and videos) consumes significantly more memory than pure text.

### Configure Passwordless SSH Login Between Machines (Multi-Machine Training)

> If you only use single-machine training, you can skip this section.

The following instructions use two machines as an example, with their IPs denoted as `${ip1}` and `${ip2}`. All steps should be performed inside the Docker container.

First, configure passwordless SSH for each container on every machine:

```sh
ssh-keygen			# Generate id_rsa and id_rsa.pub for passwordless login
ssh-keygen -t rsa -A    # Generate /etc/ssh/ssh_host_rsa_key and ssh_host_ecdsa_key for SSH listening
/usr/sbin/sshd -p 36005 -o ListenAddress=0.0.0.0        # Start SSH listening
echo "Port 36005" > ~/.ssh/config   # Set SSH connection port to 36005
passwd root    # Set the root password to avoid monitoring platform alerts
```

Note: `36005` is an example port. You may use any available port, but ensure it is **open** and **not occupied by other processes**.

Next, in each machine's container, execute:

```sh
cat ~/.ssh/id_rsa.pub
```

**Copy the output SSH public key and paste it into the `~/.ssh/authorized_keys` file, one key per line. This must be done on every machine.** In the end, the `~/.ssh/authorized_keys` file on each machine should be identical and contain the public keys of all machines.

Please note that for multi-node training, the code executed on each node must be identical. It is recommended to mount a shared network drive. If this is not possible, you must manually copy the dataset, scripts, and code to the same directory on each machine.

### Launch Methods

This repository provides three fine-tuning approaches:

- **DeepSpeed Native Fine-tuning** (based on HuggingFace Transformers Trainer): Located in the `deepspeed_support` directory
- **LLaMA-Factory Fine-tuning**: Located in the `llama_factory_support` directory
- **ms-swift Fine-tuning**: Located in the `ms_swift_support` directory

#### DeepSpeed Native Fine-tuning

Reference: [HuggingFace Transformers Trainer](https://huggingface.co/docs/transformers/main/en/main_classes/trainer)

The `deepspeed_support` directory provides the following launch scripts:

| Scenario | Launch Script | Training Script | Description |
|---|---|---|---|
| VL Fine-tuning (image/video/text) | `bash train_vl.sh` | `train_vl.py` | Multimodal fine-tuning (ViT frozen) |
| Pure Text Fine-tuning | `bash train_llm.sh` | `train_vl.py` | Pure text training using VL checkpoint (ViT frozen) |

##### Single-Machine Fine-tuning

First, install dependencies (`requirements.txt` is located in the `finetune` root directory):

```sh
pip install -r ../requirements.txt
```

Then install the dev version of transformers that includes Hy4 flash model support (installed from a GitHub PR):

```sh
pip install "transformers @ git+https://github.com/huggingface/transformers.git@refs/pull/50903/head"
```

> **Note:** This transformers version includes full support for the Hy4 flash model and is a required dependency for fine-tuning. Once this PR is merged into an official release, you can switch to `pip install transformers>=X.Y.Z`.

Then, in the `deepspeed_support` directory, execute:

```sh
# Pure text fine-tuning
bash train_llm.sh

# VL multimodal fine-tuning
bash train_vl.sh
```

##### Multi-Machine Fine-tuning

To launch fine-tuning across multiple machines, please first complete the configuration in [Configure Passwordless SSH Login Between Machines](#configure-passwordless-ssh-login-between-machines-multi-machine-training), and ensure all machines are within the same cluster.

Confirm that dependencies are installed, then modify the following configuration at the beginning of the corresponding launch script (e.g., `train_llm.sh` or `train_vl.sh`):

```sh
export HOST_GPU_NUM=8
# IP list, comma separated. e.g. "192.168.1.1,192.168.1.2" or single node "192.168.1.1"
IP_LIST=${IP_LIST:-"127.0.0.1"}
```

Note: If the `IP_LIST` environment variable is not set, replace `IP_LIST` with the IP list! The format is:
```text
For a single IP:
IP_LIST=${ip_1}

For multiple IPs:
IP_LIST=${ip_1},${ip_2}

```

Replace `${ip_1}` and `${ip_2}` with the actual IP addresses.

Then, on the machine with `${ip1}`, execute the corresponding launch script in the `deepspeed_support/` directory (e.g., `bash train_llm.sh` or `bash train_vl.sh`). On first launch, you may see the following output:

```text
The authenticity of host '[ip]:36005 ([ip]:36005)' can't be established.
ECDSA key fingerprint is xxxxxx.
ECDSA key fingerprint is MD5:xxxxxx.
Are you sure you want to continue connecting (yes/no)?
```

Type `yes` to continue.

##### Key Parameters

The key parameters in the script are as follows:

- `--deepspeed`: Path to the DeepSpeed configuration file. Four default DeepSpeed configuration files are provided in the `deepspeed_support` folder: `ds_zero2_no_offload.json`, `ds_zero2_offload.json`, `ds_zero3_no_offload.json`, and `ds_zero3_offload.json`, with different ZeRO stages (ZeRO-2 / ZeRO-3) and offload strategies selectable based on available GPU memory and communication constraints.
- `--model_name_or_path`: Path to the Hy4 flash HF pre-trained model weights to load, otherwise loading will fail.
- `--tokenizer_name_or_path`: Path to the tokenizer folder, otherwise loading will fail.
- `--train_data_file`: Path to the training file, which should be a jsonl file.
- `--output_dir`: Output directory where logs, tensorboard files, and model weights will be stored.
- `--per_device_train_batch_size`: Batch size per GPU.
- `--gradient_accumulation_steps`: Number of gradient accumulation steps. The global batch size is `per_device_train_batch_size * gradient_accumulation_steps * dp_size`.
- `--max_steps`: Total number of training steps.
- `--save_steps`: Number of steps between saving checkpoints.
- `--gradient_checkpointing`: Enable gradient checkpointing.
- `--learning_rate`: Maximum learning rate during training.
- `--min_lr`: Minimum learning rate during training (absolute value, e.g. `1e-6`; if not specified, defaults to `0.01` and is computed as `learning_rate * min_lr` ratio).
- `--use_flash_attn`: Enable flash-attention for accelerated training.

##### What if GPU Memory is Insufficient?

Reference: [DeepSpeed Configuration](https://www.deepspeed.ai/docs/config-json/)

You can try modifying the DeepSpeed configuration by removing the `auto` attribute from the following parameters and reducing their values:

- `stage3_param_persistence_threshold`
- `stage3_prefetch_bucket_size`
- `stage3_max_reuse_distance`

##### Multimodal (VL) Fine-tuning

`train_vl.sh` supports three types of data simultaneously: image + text, video + text, and pure text. The data format is described in [Multimodal Data Format](#multimodal-data-format-image--video).

VL-specific parameters (in addition to the parameters listed above):

- `--freeze_vit`: Freeze the ViT vision encoder during training (enabled by default, i.e. `default=True`). This prevents the vision encoder weights from being updated, focusing training on the LLM and projector. To train the vision encoder, explicitly set `--freeze_vit false`.
- `--train_data_file`: Path to the JSONL training file containing multimodal data (with `images` / `videos` fields).
- `--image_base_dir`: Base directory for resolving relative image/video paths in the data file. If not specified, paths are resolved relative to the working directory.

**Image processing parameters** (aligned with HuggingFace processor's `images_kwargs` API):

- `--image_min_pixels`: Minimum pixel count for image resizing. Maps to `size["shortest_edge"]` in the HF image processor. Default `None` (uses the value from `preprocessor_config.json`, default 4096).
- `--image_max_pixels`: Maximum pixel count for image resizing. Maps to `size["longest_edge"]` in the HF image processor. Default `None` (uses the value from `preprocessor_config.json`, default 4194304).

**Video processing parameters** (aligned with HuggingFace processor's `videos_kwargs` API):

- `--video_max_pixels`: Total pixel budget for all video frames. Maps to `size["longest_edge"]` in the HF video processor. Default `None` (uses the value from `video_preprocessor_config.json`). When set, the per-frame pixel budget is `video_max_pixels / num_frames`, which controls the number of tokens generated by the video.
- `--video_max_frames`: Maximum number of frames to sample from a video. Maps to `max_frames` in the HF video processor. Default `None`.
- `--video_fps`: Target frame rate for video sampling (frames per second). Maps to `fps` in the HF video processor. Default `None`.

> **Video parameters:** Videos generate significantly more tokens than images. You should set video parameters appropriately based on `--max_seq_length` to ensure video tokens do not exceed the sequence length limit.

#### LLaMA-Factory Fine-tuning

If you are familiar with LLaMA-Factory, you can use it for fine-tuning. All scripts, code, and configuration files are located in the `llama_factory_support` directory. Unless otherwise specified, all files mentioned below are located in this directory.

##### Installation

You can install LLaMA-Factory by downloading the source code from https://github.com/hiyouga/LLaMA-Factory/tree/main and following the instructions on the website.

##### Configuration Files

We provide sample LLaMA-Factory fine-tuning configuration files for different scenarios:

| Configuration File | Scenario |
|---|---|
| `hy_v4_flash_full_sft.yaml` | LLM Full Fine-tuning |
| `hy_v4_flash_lora_sft.yaml` | LLM LoRA Fine-tuning |
| `hy_v4_flash_vl_full_sft.yaml` | VL Full Fine-tuning |
| `hy_v4_flash_vl_lora_sft.yaml` | VL LoRA Fine-tuning |

Key parameters in the configuration files are as follows:

**Model:**

- `model_name_or_path`: Path to the Hy4 flash HF format pre-trained model weights
- `trust_remote_code`: Whether to trust remote code; Hy4 flash requires this to be set to `true`

**Training Method:**

- `stage`: Training stage, currently `sft` (supervised fine-tuning)
- `finetuning_type`: Fine-tuning type, either `full` (full fine-tuning) or `lora` (LoRA fine-tuning)
- `deepspeed`: DeepSpeed configuration file path; `../deepspeed_support/ds_zero3_offload.json` is recommended for full fine-tuning
- `fsdp` + `fsdp_config`: FSDP distributed strategy; recommended for LoRA fine-tuning (configuration is built into `hy_v4_flash_lora_sft.yaml`); mutually exclusive with DeepSpeed

> **Distributed Strategy Recommendations:**
> - **FSDP**: Recommended for LoRA fine-tuning, good compatibility and simple configuration
> - **DeepSpeed ZeRO-3 + Offload**: Recommended for full fine-tuning or memory-constrained scenarios

**LoRA Parameters (only effective during LoRA fine-tuning):**

- `lora_rank`: LoRA rank, default `64`
- `lora_alpha`: LoRA alpha coefficient, default `128`
- `lora_dropout`: LoRA dropout ratio, default `0.05`
- `lora_target`: Target modules for LoRA, default `q_a_proj,q_b_proj,kv_a_proj_with_mqa,kv_b_proj,o_proj`

**Dataset:**

- `dataset_dir`: Dataset directory path
- `dataset`: Dataset name, must be registered in `dataset_info.json` under `dataset_dir`
- `template`: Chat template; Hy4 flash uses `hy_v4_flash`
- `cutoff_len`: Maximum sequence length; sequences exceeding this will be truncated. For LoRA fine-tuning, a smaller value is recommended to save memory
- `max_samples`: Maximum number of samples per dataset
- `overwrite_cache`: Whether to overwrite cached preprocessed datasets

**Output:**

- `output_dir`: Output directory where logs, TensorBoard files, and weights will be stored
- `logging_steps`: Number of steps between logging
- `save_steps`: Number of steps between saving checkpoints
- `plot_loss`: Whether to plot the training loss curve
- `overwrite_output_dir`: Whether to overwrite the existing output directory
- `save_only_model`: Whether to save only model weights (excluding optimizer states, etc.)
- `report_to`: Logging tool, options: `none`, `wandb`, `tensorboard`, `swanlab`, `mlflow`

**Training Hyperparameters:**

- `per_device_train_batch_size`: Batch size per GPU
- `gradient_accumulation_steps`: Gradient accumulation steps; `per_device_train_batch_size * gradient_accumulation_steps * dp_size` equals the global batch size
- `learning_rate`: Maximum learning rate; `1.0e-5` recommended for full fine-tuning, `2.0e-4` for LoRA fine-tuning
- `num_train_epochs`: Number of training epochs
- `lr_scheduler_type`: Learning rate scheduler type; `cosine_with_min_lr` is recommended
- `lr_scheduler_kwargs.min_lr_rate`: Ratio of minimum to maximum learning rate; e.g., `0.1` means the minimum learning rate is 10% of the maximum
- `warmup_steps`: Number of warmup steps
- `bf16`: Whether to use BFloat16 mixed precision training
- `gradient_checkpointing`: Whether to enable gradient checkpointing to save memory
- `ddp_timeout`: Distributed training timeout (milliseconds)
- `flash_attn`: Attention implementation; options include `auto` (automatic selection), `sdpa`, `disabled`, etc. The actual default depends on the configuration file (e.g. LLM full fine-tuning uses `disabled`, LLM LoRA uses `auto`, VL full fine-tuning uses `auto`, VL LoRA uses `disabled`)
- `resume_from_checkpoint`: Resume training from a specified checkpoint path; set to `null` to start from scratch

**Image/Video Processing Parameters (effective for VL fine-tuning):**

The following parameters are determined by the model's built-in processor configuration (see `hy_v4_template.py`), with defaults listed below. To adjust, you may override them in the YAML configuration file (if supported by your LLaMA-Factory version) or modify the processor configuration:

- `image_max_pixels`: Maximum pixel count for image resizing, default `4194304` (2048×2048)
- `image_min_pixels`: Minimum pixel count for image resizing, default `4096` (64×64)
- `video_max_pixels`: Maximum pixel count per video frame, default `65536` (256×256)
- `video_min_pixels`: Minimum pixel count per video frame, default `256` (16×16)
- `video_fps`: Video sampling frame rate, default `2.0`
- `video_maxlen`: Maximum number of sampled video frames, default `128`

> **Video parameter note:** Videos produce significantly more tokens than images. Set video parameters appropriately based on `cutoff_len` to ensure video tokens do not exceed the sequence length limit. Lowering `video_max_pixels` or `video_maxlen` can significantly reduce GPU memory usage.

##### Launch Scripts

We provide dedicated launch scripts for different scenarios:

| Scenario | Launch Script | Default Configuration |
|---|---|---|
| VL Full Fine-tuning | `bash train_lf.sh` | `hy_v4_flash_vl_full_sft.yaml` |
| VL LoRA Fine-tuning | `bash train_lf_lora.sh` | `hy_v4_flash_vl_lora_sft.yaml` |
| LLM Full Fine-tuning | `bash train_lf_llm.sh` | `hy_v4_flash_full_sft.yaml` |
| LLM LoRA Fine-tuning | `bash train_lf_lora_llm.sh` | `hy_v4_flash_lora_sft.yaml` |

Each script supports overriding the default configuration file via the `YAML_FILE` environment variable.

##### Launch Fine-tuning

For multi-machine fine-tuning, please first complete the configuration in [Configure Passwordless SSH Login Between Machines](#configure-passwordless-ssh-login-between-machines-multi-machine-training) (single-machine fine-tuning can skip this step).

Modify the following configuration at the beginning of the corresponding launch script:

```sh
export HOST_GPU_NUM=8
# IP list, comma separated. e.g. "192.168.1.1,192.168.1.2" or single node "192.168.1.1"
export IP_LIST=${IP_LIST:-"127.0.0.1"}
```

Note:
1. If the `IP_LIST` environment variable is not set, replace `IP_LIST` with the IP list! The format is:
```text
For a single IP:
IP_LIST=${ip_1}

For multiple IPs:
IP_LIST=${ip_1},${ip_2}

```
Replace `${ip_1}` and `${ip_2}` with the actual IP addresses.

2. To specify a fine-tuning configuration file, set the `YAML_FILE` environment variable (absolute paths are recommended, or `cd` into the `llama_factory_support/` directory before running). For example:
```sh
export YAML_FILE=/path/to/llama_factory_support/hy_v4_flash_lora_sft.yaml
```

For multi-machine training, each machine needs to run a `torchrun` process. The launch script has built-in `pdsh` support for one-click distribution — you only need to execute it on one machine and it will automatically distribute to all nodes:

```sh
# VL full fine-tuning
bash train_lf.sh

# LLM full fine-tuning
bash train_lf_llm.sh
```

> **Note:** If your environment does not support `pdsh`, or you need a custom launch method, please manually execute the launch script on each machine separately. When doing so, you must set `_WORKER_MODE=1` to skip the pdsh distribution branch, for example:
> ```bash
> # On each machine:
> export IP_LIST="10.0.0.1,10.0.0.2"
> export _WORKER_MODE=1
> bash train_lf.sh
> ```

##### Multimodal (VL) Fine-tuning

Key differences between VL and pure text configuration:

- `template`: Set to `hy_v4_flash_vl` (instead of `hy_v4_flash`)
- `dataset`: Use a VL dataset registered in `dataset_info.json`, which must include an `images` column; to also support video, include a `videos` column
- `freeze_vision_tower`: Set to `true` to freeze the ViT vision encoder during training (recommended)

To register a custom VL dataset, add an entry to `dataset_info.json`:

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

#### ms-swift Fine-tuning

If you are familiar with ms-swift, you can use it for fine-tuning. All scripts and code are located in the `ms_swift_support` directory. Unless otherwise specified, all files mentioned below are located in this directory.

##### Installation

You can install ms-swift via pip:

```sh
pip install ms-swift
```

Or install from source: https://github.com/modelscope/ms-swift

##### Fine-tuning Scripts

| Scenario | Fine-tuning Method | Launch Script |
|---|---|---|
| Pure Text (LLM) | Full Fine-tuning | `bash sft_train.sh` |
| Pure Text (LLM) | LoRA Fine-tuning | `bash sft_train_lora.sh` |
| Multimodal (VL) | Full Fine-tuning | `bash sft_train_vl.sh` |
| Multimodal (VL) | LoRA Fine-tuning | `bash sft_train_vl_lora.sh` |

> **Note:** Training parameters for ms-swift are configured directly as CLI arguments in the launch scripts. To modify parameters, edit the corresponding launch script directly.

##### Key Parameters

Key parameters in the launch scripts are as follows:

**Model:**

- `model`: Model path, can be a HuggingFace Hub ID or a local path
- `model_type`: Model type, set to `hy_v4_flash_vl`
- `template`: Chat template, set to `hy_v4_flash_vl`
- `torch_dtype`: Data type, `bfloat16` is recommended
- `attn_impl`: Attention implementation, default `eager`

**Training Method:**

- `tuner_type`: Fine-tuning type; set to `full` for full fine-tuning, `lora` for LoRA fine-tuning
- `lora_rank`: LoRA rank, default `64`
- `lora_alpha`: LoRA alpha coefficient, default `128`
- `lora_dropout`: LoRA dropout ratio, default `0.05`
- `target_modules`: Target modules for LoRA, default MLA projection layers: `q_a_proj`, `q_b_proj`, `kv_a_proj_with_mqa`, `kv_b_proj`, `o_proj`

**Dataset:**

- `dataset`: Dataset path, supports local jsonl files (sharegpt format)
- `max_length`: Maximum sequence length; sequences exceeding this will be truncated
- `lazy_tokenize`: Whether to use lazy tokenization, `true` is recommended

**Output:**

- `output_dir`: Output directory
- `save_steps`: Number of steps between saving checkpoints
- `save_total_limit`: Maximum number of checkpoints to keep
- `logging_steps`: Number of steps between logging
- `report_to`: Logging tool, options: `none`, `wandb`, `tensorboard`, `swanlab`, `mlflow`

**Training Hyperparameters:**

- `per_device_train_batch_size`: Batch size per GPU
- `gradient_accumulation_steps`: Gradient accumulation steps
- `learning_rate`: Maximum learning rate; `1.0e-5` recommended for full fine-tuning, `2.0e-4` for LoRA fine-tuning
- `num_train_epochs`: Number of training epochs
- `lr_scheduler_type`: Learning rate scheduler type, `cosine` is recommended
- `warmup_steps`: Number of warmup steps
- `bf16`: Whether to use BFloat16 mixed precision training

**Distributed Strategy / Optimization:**

- `deepspeed`: DeepSpeed configuration file path; the scripts default to `../deepspeed_support/ds_zero3_offload.json`; ZeRO-3 + Offload is recommended for full fine-tuning
- `fsdp`: FSDP configuration file path (JSON); recommended for LoRA fine-tuning; mutually exclusive with DeepSpeed
- `gradient_checkpointing`: Whether to enable gradient checkpointing
- `max_grad_norm`: Gradient clipping threshold

> **Distributed Strategy Recommendations:**
> - **FSDP**: Recommended for LoRA fine-tuning, good compatibility and simple configuration
> - **DeepSpeed ZeRO-3 + Offload**: Recommended for full fine-tuning or memory-constrained scenarios

**Other:**

- `ddp_timeout`: Distributed training timeout (milliseconds)
- `seed`: Random seed
- `resume_from_checkpoint`: Resume training from a specified checkpoint path

**Image/Video Processing Parameters (effective for VL fine-tuning):**

Image/video processing in ms-swift is controlled by the model's built-in image processor and video processor. Parameter defaults come from `preprocessor_config.json` and `video_preprocessor_config.json` in the model directory (the actual values depend on the specific checkpoint). To adjust these values, directly modify the corresponding JSON configuration files in the model directory.

Image processing parameters (`preprocessor_config.json`):

- `min_pixels`: Minimum pixel count for image resizing, default `4096`
- `max_pixels`: Maximum pixel count for image resizing, default `4194304` (2048×2048)

Video processing parameters (`video_preprocessor_config.json`):

- `size.longest_edge`: Total pixel budget for all video frames, default `1572864`
- `max_image_size.longest_edge`: Maximum pixel count per single video frame, default `262144`
- `max_frames`: Maximum number of sampled video frames, default `2`
- `fps`: Target frame rate for video sampling (frames per second), default `2`
- `do_sample_frames`: Whether to enable frame sampling, default `true`

> **Video parameter note:** Videos produce significantly more tokens than images. Set video parameters appropriately based on `max_length` to ensure video tokens do not exceed the sequence length limit. Lowering `size.longest_edge`, `max_image_size.longest_edge`, or `max_frames` can significantly reduce GPU memory usage.

##### Launch Fine-tuning

For multi-machine fine-tuning, please first complete the configuration in [Configure Passwordless SSH Login Between Machines](#configure-passwordless-ssh-login-between-machines-multi-machine-training) (single-machine fine-tuning can skip this step).

Modify the following configuration at the beginning of the corresponding launch script:

```sh
export HOST_GPU_NUM=8
# IP list, comma separated. e.g. "10.0.0.1,10.0.0.2" or single node "127.0.0.1"
export IP_LIST=${IP_LIST:-"127.0.0.1"}
```

For multi-machine training, each machine needs to run a `torchrun` process. The launch script has built-in `pdsh` support for one-click distribution — you only need to execute it on one machine and it will automatically distribute to all nodes:

```sh
# Pure text full fine-tuning
bash sft_train.sh

# Pure text LoRA fine-tuning
bash sft_train_lora.sh

# VL full fine-tuning with DeepSpeed ZeRO-3
bash sft_train_vl.sh

# VL LoRA fine-tuning with FSDP
bash sft_train_vl_lora.sh

# Multi-machine training (one-click distribution via pdsh, execute on one machine only)
IP_LIST="10.0.0.1,10.0.0.2" bash sft_train.sh
```

> **Note:** If your environment does not support `pdsh`, or you need a custom launch method, please manually execute the launch script on each machine separately. When doing so, you must set `_WORKER_MODE=1` to skip the pdsh distribution branch, for example:
> ```bash
> # On each machine:
> export IP_LIST="10.0.0.1,10.0.0.2"
> export _WORKER_MODE=1
> bash sft_train.sh
> ```

##### Multimodal (VL) Fine-tuning

The key differences between VL and pure text scripts are:

- `model_type`: Set to `hy_v4_flash_vl` (instead of `hy_v4_flash`)
- `template`: Set to `hy_v4_flash_vl` (instead of `hy_v4_flash`)
- `dataset`: Point to a JSONL file containing multimodal data (with `images` / `videos` fields)
