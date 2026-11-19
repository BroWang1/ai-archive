# Copyright 2024 Tencent Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
HY4-VL SFT training script with DeepSpeed.

Supports:
- Image + text multimodal SFT
- Video + text multimodal SFT
- Pure text SFT (backward compatible)
- LoRA and full fine-tuning
- DeepSpeed ZeRO-2/3 with optional CPU offload

Data format (jsonl):
    # Image example
    {"messages": [...], "images": ["/path/to/img.jpg"]}
    # Video example
    {"messages": [...], "videos": ["/path/to/video.mp4"]}
    # Pure text example
    {"messages": [...]}
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import torch
import shutil
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

import transformers
from torch.utils.data import Dataset
from transformers import Trainer, TrainerCallback
from peft import LoraConfig, get_peft_model
from transformers.trainer_utils import PREFIX_CHECKPOINT_DIR
from PIL import Image

logger = logging.getLogger(__name__)


def print_args(args, name='arguments'):
    """Print arguments."""
    if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
        print(f'------------------------ {name} ------------------------', flush=True)
        str_list = []
        for arg in vars(args):
            dots = '.' * (48 - len(arg))
            str_list.append('  {} {} {}'.format(arg, dots, getattr(args, arg)))
        for arg in sorted(str_list, key=lambda x: x.lower()):
            print(arg, flush=True)
        print(f'-------------------- end of {name} ---------------------', flush=True)


@dataclass
class ModelArguments:
    use_flash_attn: bool = field(
        default=False,
        metadata={"help": "Enable FlashAttention-2 for faster training."}
    )
    use_lora: bool = field(default=False, metadata={"help": "Enable LoRA for efficient training."})
    lora_rank: int = field(default=64, metadata={"help": "The rank of LoRA."})
    lora_alpha: int = field(default=8, metadata={"help": "LoRA alpha"})
    lora_dropout: float = field(default=0.0, metadata={"help": "LoRA dropout"})
    freeze_vit: bool = field(
        default=True,
        metadata={"help": "Freeze the Vision Transformer (ViT) encoder during training."}
    )


@dataclass
class DataArguments:
    train_data_file: str = field(default=None, metadata={"help": "Path to the training data (jsonl)."})
    max_seq_length: int = field(
        default=2048,
        metadata={"help": "The max sequence length of the model inputs after tokenization."}
    )
    image_base_dir: Optional[str] = field(
        default=None,
        metadata={"help": "Base directory for resolving relative image/video paths in the data."}
    )
    use_dummy_data: bool = field(default=False, metadata={"help": "Use dummy data for testing."})
    # Image processing overrides (align with HF processor's images_kwargs API)
    image_min_pixels: Optional[int] = field(
        default=None,
        metadata={"help": "Min pixels for image resizing. Maps to size['shortest_edge'] in HF image processor."}
    )
    image_max_pixels: Optional[int] = field(
        default=None,
        metadata={"help": "Max pixels for image resizing. Maps to size['longest_edge'] in HF image processor."}
    )
    # Video processing overrides (align with HF processor's videos_kwargs API)
    video_max_pixels: Optional[int] = field(
        default=None,
        metadata={"help": "Max total pixels for video frames. Maps to size['longest_edge'] in HF video processor."}
    )
    video_max_frames: Optional[int] = field(
        default=None,
        metadata={"help": "Max number of frames to sample from video. Maps to max_frames in HF video processor."}
    )
    video_fps: Optional[int] = field(
        default=None,
        metadata={"help": "Target frames per second for video sampling. Maps to fps in HF video processor."}
    )


@dataclass
class TrainingArguments(transformers.TrainingArguments):
    cache_dir: Optional[str] = field(default=None)
    optim: str = field(default="adamw_torch")
    tokenizer_name_or_path: Optional[str] = field(default=None)
    model_name_or_path: Optional[str] = field(default=None)
    min_lr: float = field(
        default=0.01,
        metadata={"help": "The final learning rate at the end of the decay will be learning_rate * min_lr"}
    )


IGNORE_INDEX = -100

HY_START_ID = 120000
HY_MIDDLE_ID = 120001
HY_END_ID = 120025


# ============================================================================
# Dummy Dataset (for testing without real data)
# ============================================================================

class VLDummyDataset(Dataset):
    """Dummy dataset that generates random tokens for VL pipeline testing."""

    def __init__(self, processor, max_seq_length=512, length=100):
        self.processor = processor
        self.tokenizer = processor.tokenizer
        self.max_seq_length = max_seq_length
        self.length = length

    def __len__(self):
        return self.length

    def __getitem__(self, index):
        tokens = torch.randint(0, self.tokenizer.vocab_size, (self.max_seq_length,))
        # For dummy data, use 1D position_ids (no MRoPE)
        position_ids = torch.arange(self.max_seq_length).unsqueeze(0).expand(3, -1)
        return {
            'input_ids': tokens,
            'labels': tokens,
            'attention_mask': torch.ones(self.max_seq_length, dtype=torch.bool),
            'position_ids': position_ids,
            'mm_token_type_ids': torch.zeros(self.max_seq_length, dtype=torch.long),
        }


# ============================================================================
# VL SFT Dataset
# ============================================================================

class VLSFTDataset(Dataset):
    """
    Vision-Language SFT dataset.

    Supports three data types:
    - Image + text: {"messages": [...], "images": ["path/to/img.jpg"]}
    - Video + text: {"messages": [...], "videos": ["path/to/video.mp4"]}
    - Pure text:    {"messages": [...]}

    The processor handles:
    - Image/video loading and preprocessing (pixel_values, grid_thw)
    - Token expansion (replacing <image>/<video> with correct number of tokens)
    - 3D MRoPE position_ids construction [t, h, w]
    """

    def __init__(self, data_file, processor, max_seq_length=2048, image_base_dir=None,
                 image_min_pixels=None, image_max_pixels=None,
                 video_max_pixels=None, video_max_frames=None, video_fps=None):
        self.processor = processor
        self.tokenizer = processor.tokenizer
        self.max_seq_length = max_seq_length
        self.image_base_dir = image_base_dir
        # Image/video processing overrides
        self.image_min_pixels = image_min_pixels
        self.image_max_pixels = image_max_pixels
        self.video_max_pixels = video_max_pixels
        self.video_max_frames = video_max_frames
        self.video_fps = video_fps

        # Pre-compute special token IDs for loss masking
        self.hy_start_id = HY_START_ID
        self.hy_middle_id = HY_MIDDLE_ID
        self.hy_end_id = HY_END_ID
        self.assistant_bpe_ids = self.tokenizer.encode('assistant', add_special_tokens=False)
        self.pad_token_id = self.tokenizer.pad_token_id

        self.data_list = self._load_data(data_file)

    def __len__(self):
        return len(self.data_list)

    def _load_data(self, data_file):
        logger.info(f'Loading data: {data_file}')
        with open(data_file, 'r', encoding='utf8') as f:
            data_list = f.readlines()
        logger.info(f"Loaded {len(data_list)} samples")
        return data_list

    def _resolve_path(self, path):
        """Resolve relative paths using image_base_dir."""
        if os.path.isabs(path):
            return path
        if self.image_base_dir:
            return os.path.join(self.image_base_dir, path)
        return path

    def _load_images(self, image_paths):
        """Load images from paths, return list of PIL Images."""
        images = []
        for p in image_paths:
            full_path = self._resolve_path(p)
            try:
                img = Image.open(full_path).convert("RGB")
                images.append(img)
            except Exception as e:
                logger.warning(f"Failed to load image {full_path}: {e}")
                # Create a small placeholder image
                images.append(Image.new("RGB", (224, 224), color=(128, 128, 128)))
        return images

    def _find_assistant_turn_boundaries(self, token_ids):
        """Find assistant turn boundaries for loss masking.

        Locates assistant turns by finding <hy_start> + "assistant" BPE tokens pattern,
        then marks loss from the <hy_middle> token (exclusive) to <hy_end> (inclusive).
        """
        boundaries = []
        assistant_len = len(self.assistant_bpe_ids)
        ids_list = token_ids.tolist() if isinstance(token_ids, torch.Tensor) else token_ids
        n = len(ids_list)

        i = 0
        while i < n:
            if ids_list[i] == self.hy_start_id:
                role_start = i + 1
                role_end = role_start + assistant_len
                if role_end <= n and ids_list[role_start:role_end] == self.assistant_bpe_ids:
                    if role_end < n and ids_list[role_end] == self.hy_middle_id:
                        middle_pos = role_end
                        end_pos = None
                        for j in range(middle_pos + 1, n):
                            if ids_list[j] == self.hy_end_id:
                                end_pos = j
                                break
                        if end_pos is not None:
                            boundaries.append((middle_pos, end_pos))
                            i = end_pos + 1
                            continue
            i += 1

        return boundaries

    @staticmethod
    def _normalize_messages(messages):
        """Convert legacy <image>/<video> string placeholders to multimodal content list format.

        Legacy format:  {"role": "user", "content": "<image>Describe this image."}
        Normalized:     {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": "Describe this image."}]}

        This ensures chat_template's render_content() correctly emits image/video pad tokens.
        Messages already using list-of-dict content are left unchanged.
        """
        IMAGE_PLACEHOLDER = "<image>"
        VIDEO_PLACEHOLDER = "<video>"
        normalized = []
        for msg in messages:
            content = msg.get("content", "")
            # Only transform string content that contains placeholders
            if isinstance(content, str) and (IMAGE_PLACEHOLDER in content or VIDEO_PLACEHOLDER in content):
                parts = []
                remaining = content
                while remaining:
                    img_idx = remaining.find(IMAGE_PLACEHOLDER)
                    vid_idx = remaining.find(VIDEO_PLACEHOLDER)
                    # Find the earliest placeholder
                    candidates = []
                    if img_idx != -1:
                        candidates.append((img_idx, IMAGE_PLACEHOLDER, "image"))
                    if vid_idx != -1:
                        candidates.append((vid_idx, VIDEO_PLACEHOLDER, "video"))
                    if not candidates:
                        # No more placeholders, add remaining text
                        text_part = remaining.strip()
                        if text_part:
                            parts.append({"type": "text", "text": text_part})
                        break
                    # Pick the earliest one
                    candidates.sort(key=lambda x: x[0])
                    idx, placeholder, media_type = candidates[0]
                    # Add text before the placeholder
                    before = remaining[:idx].strip()
                    if before:
                        parts.append({"type": "text", "text": before})
                    parts.append({"type": media_type})
                    remaining = remaining[idx + len(placeholder):]
                normalized.append({**msg, "content": parts})
            else:
                normalized.append(msg)
        return normalized

    def _build_text_from_messages(self, messages, reasoning_effort='no_think'):
        """Build text string from messages, applying chat template."""
        try:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False,
                reasoning_effort=reasoning_effort
            )
        except Exception as e:
            logger.warning(f"apply_chat_template failed: {e}, messages: {messages}")
            text = ""
        return text

    def __getitem__(self, index):
        data = json.loads(self.data_list[index])
        messages = data.get('messages', [])
        image_paths = data.get('images', [])
        video_paths = data.get('videos', [])

        # Read reasoning_effort from data; default to 'no_think' for data without reasoning_content
        reasoning_effort = data.get('reasoning_effort', 'no_think')

        # Normalize legacy <image>/<video> string placeholders to multimodal content format
        # so that chat_template correctly emits image/video pad tokens
        messages = self._normalize_messages(messages)

        # Build the text with chat template (not tokenized yet)
        text = self._build_text_from_messages(messages, reasoning_effort=reasoning_effort)

        if not text:
            return self._make_placeholder()

        # Determine modality and call processor
        try:
            processor_kwargs = {"text": text, "return_tensors": "pt"}

            if image_paths:
                images = self._load_images(image_paths)
                processor_kwargs["images"] = images
                # Override image processor defaults via HF's images_kwargs API
                ik = {}
                if self.image_min_pixels is not None or self.image_max_pixels is not None:
                    ik["size"] = dict(self.processor.image_processor.size)
                    if self.image_min_pixels is not None:
                        ik["size"]["shortest_edge"] = self.image_min_pixels
                    if self.image_max_pixels is not None:
                        ik["size"]["longest_edge"] = self.image_max_pixels
                if ik:
                    processor_kwargs["images_kwargs"] = ik
            if video_paths:
                # Video loading is handled by the processor's video_processor
                resolved_videos = [self._resolve_path(p) for p in video_paths]
                processor_kwargs["videos"] = resolved_videos
                # Override video processor defaults via HF's videos_kwargs API
                vk = {}
                if self.video_max_pixels is not None:
                    vk["size"] = {"shortest_edge": 4096, "longest_edge": self.video_max_pixels}
                if self.video_max_frames is not None:
                    vk["max_frames"] = self.video_max_frames
                if self.video_fps is not None:
                    vk["fps"] = self.video_fps
                # Enable frame sampling so that max_frames/fps take effect
                if self.video_max_frames is not None or self.video_fps is not None:
                    vk["do_sample_frames"] = True
                if vk:
                    processor_kwargs["videos_kwargs"] = vk

            inputs = self.processor(**processor_kwargs)
        except Exception as e:
            logger.warning(f"Processor failed for sample {index}: {e}")
            return self._make_placeholder()

        # Extract tensors (processor returns batch dim, squeeze it)
        input_ids = inputs["input_ids"].squeeze(0)  # [seq_len]
        attention_mask = inputs["attention_mask"].squeeze(0)  # [seq_len]
        # position_ids: optional — old processor (transformers-dev) returns it,
        # new processor (transformers-hy4vl) does not (model computes it internally)
        position_ids = inputs["position_ids"].squeeze(0) if "position_ids" in inputs else None

        # Truncate to max_seq_length
        seq_len = min(input_ids.shape[0], self.max_seq_length)
        input_ids = input_ids[:seq_len]
        attention_mask = attention_mask[:seq_len]
        if position_ids is not None:
            position_ids = position_ids[:, :seq_len]

        # Build labels with loss masking (only compute loss on assistant turns)
        labels = torch.full_like(input_ids, IGNORE_INDEX)
        boundaries = self._find_assistant_turn_boundaries(input_ids)
        for middle_pos, end_pos in boundaries:
            end_pos = min(end_pos, seq_len - 1)
            if middle_pos + 1 < seq_len:
                labels[middle_pos + 1:end_pos + 1] = input_ids[middle_pos + 1:end_pos + 1]

        result = {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": attention_mask,
        }
        if position_ids is not None:
            result["position_ids"] = position_ids

        # Add pixel_values and grid_thw if present (for vision inputs)
        if "pixel_values" in inputs:
            result["pixel_values"] = inputs["pixel_values"]
            # pixel_values: [num_patches, C, H, W] or similar - keep as-is
        if "image_grid_thw" in inputs:
            result["image_grid_thw"] = inputs["image_grid_thw"]
        if "pixel_values_videos" in inputs:
            result["pixel_values_videos"] = inputs["pixel_values_videos"]
        if "video_grid_thw" in inputs:
            result["video_grid_thw"] = inputs["video_grid_thw"]

        # mm_token_type_ids: per-token modality indicator (0=text, 1=image, 2=video)
        # Required by the opensource model's get_rope_index() for 3D MRoPE position_ids
        if "mm_token_type_ids" in inputs:
            mm_token_type_ids = inputs["mm_token_type_ids"].squeeze(0)[:seq_len]
            result["mm_token_type_ids"] = mm_token_type_ids

        return result

    def _make_placeholder(self):
        """Return a minimal valid sample when data processing fails."""
        seq_len = min(2, self.max_seq_length)
        input_ids = torch.tensor([self.hy_start_id, self.hy_end_id], dtype=torch.long)[:seq_len]
        labels = torch.full((seq_len,), IGNORE_INDEX, dtype=torch.long)
        attention_mask = torch.ones(seq_len, dtype=torch.bool)
        return {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": attention_mask,
            "mm_token_type_ids": torch.zeros(seq_len, dtype=torch.long),
        }


# ============================================================================
# VL Data Collator
# ============================================================================

@dataclass
class VLDataCollator:
    """Collate examples for VL supervised fine-tuning.

    Handles:
    - Padding input_ids, labels, attention_mask to the same length
    - Padding 3D position_ids [3, seq_len] to the same length (if present)
    - Concatenating pixel_values and grid_thw across the batch
    """

    pad_token_id: int
    max_seq_length: int = 2048

    def __call__(self, instances: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Pad text tensors
        input_ids = [inst['input_ids'] for inst in instances]
        labels = [inst['labels'] for inst in instances]
        attention_mask = [inst['attention_mask'] for inst in instances]

        # Pad input_ids and labels
        input_ids = torch.nn.utils.rnn.pad_sequence(
            input_ids, batch_first=True, padding_value=self.pad_token_id
        )
        labels = torch.nn.utils.rnn.pad_sequence(
            labels, batch_first=True, padding_value=IGNORE_INDEX
        )
        attention_mask = input_ids.ne(self.pad_token_id)

        batch = {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": attention_mask,
        }

        # Pad position_ids if present (old processor provides them;
        # new processor omits them and the model computes internally)
        position_ids_list = [inst.get('position_ids') for inst in instances]
        if any(p is not None for p in position_ids_list):
            max_len = input_ids.shape[1]
            padded_position_ids = []
            for pos_ids in position_ids_list:
                if pos_ids is None:
                    # Fallback: simple incremental position ids
                    pos_ids = torch.arange(max_len).unsqueeze(0).expand(3, -1)
                # pos_ids shape: [3, seq_len_i]
                seq_len_i = pos_ids.shape[1]
                if seq_len_i < max_len:
                    pad = torch.zeros(3, max_len - seq_len_i, dtype=pos_ids.dtype)
                    pos_ids = torch.cat([pos_ids, pad], dim=1)
                padded_position_ids.append(pos_ids)
            batch["position_ids"] = torch.stack(padded_position_ids, dim=0)  # [B, 3, max_len]

        # Concatenate pixel_values across the batch (variable number of patches per sample)
        all_pixel_values = [inst["pixel_values"] for inst in instances if "pixel_values" in inst]
        if all_pixel_values:
            # Each pixel_values may have different number of patches, concat along dim 0
            batch["pixel_values"] = torch.cat(all_pixel_values, dim=0)

        all_image_grid_thw = [inst["image_grid_thw"] for inst in instances if "image_grid_thw" in inst]
        if all_image_grid_thw:
            batch["image_grid_thw"] = torch.cat(all_image_grid_thw, dim=0)

        all_pixel_values_videos = [inst["pixel_values_videos"] for inst in instances if "pixel_values_videos" in inst]
        if all_pixel_values_videos:
            batch["pixel_values_videos"] = torch.cat(all_pixel_values_videos, dim=0)

        all_video_grid_thw = [inst["video_grid_thw"] for inst in instances if "video_grid_thw" in inst]
        if all_video_grid_thw:
            batch["video_grid_thw"] = torch.cat(all_video_grid_thw, dim=0)

        # mm_token_type_ids: per-token modality indicator for 3D MRoPE
        # Pad with 0 (text type) to match the padded sequence length
        all_mm_token_type_ids = [inst.get("mm_token_type_ids") for inst in instances]
        if any(v is not None for v in all_mm_token_type_ids):
            mm_list = []
            for i, mm_ids in enumerate(all_mm_token_type_ids):
                if mm_ids is None:
                    # Fallback: all-text for samples without mm_token_type_ids
                    mm_ids = torch.zeros(instances[i]["input_ids"].shape[0], dtype=torch.long)
                mm_list.append(mm_ids)
            batch["mm_token_type_ids"] = torch.nn.utils.rnn.pad_sequence(
                mm_list, batch_first=True, padding_value=0
            )

        return batch


# ============================================================================
# Data Module
# ============================================================================

def make_vl_data_module(processor, data_args) -> Dict:
    """Make dataset and collator for VL supervised fine-tuning."""
    if data_args.use_dummy_data:
        train_dataset = VLDummyDataset(processor, data_args.max_seq_length)
    else:
        train_dataset = VLSFTDataset(
            data_file=data_args.train_data_file,
            processor=processor,
            max_seq_length=data_args.max_seq_length,
            image_base_dir=data_args.image_base_dir,
            image_min_pixels=data_args.image_min_pixels,
            image_max_pixels=data_args.image_max_pixels,
            video_max_pixels=data_args.video_max_pixels,
            video_max_frames=data_args.video_max_frames,
            video_fps=data_args.video_fps,
        )
    data_collator = VLDataCollator(
        pad_token_id=processor.tokenizer.pad_token_id,
        max_seq_length=data_args.max_seq_length,
    )
    return dict(train_dataset=train_dataset, eval_dataset=None, data_collator=data_collator)


# ============================================================================
# Checkpoint Save Callback
# ============================================================================

# Files to copy to each checkpoint directory
_CHECKPOINT_FILES = [
    'config.json',
    'generation_config.json',
    'tokenizer_config.json',
    'tokenizer.json',
    'chat_template.jinja',
    'preprocessor_config.json',
    'video_preprocessor_config.json',
    'hy.tiktoken',
    'tokenization_hy.py',
    'special_tokens_map.json',
]


class CustomSaveCallback(TrainerCallback):
    """Copy tokenizer and config files when saving checkpoints."""

    def on_save(self, args, state, control, **kwargs):
        if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
            output_dir = os.path.join(
                args.output_dir, f"{PREFIX_CHECKPOINT_DIR}-{state.global_step}"
            )
            for fname in _CHECKPOINT_FILES:
                src = os.path.join(args.tokenizer_name_or_path, fname)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(output_dir, fname))
        return control


# ============================================================================
# Main Training Function
# ============================================================================

def train():
    parser = transformers.HfArgumentParser((ModelArguments, DataArguments, TrainingArguments))
    model_args, data_args, training_args = parser.parse_args_into_dataclasses()
    print_args(model_args, 'model arguments')
    print_args(data_args, 'data arguments')
    print_args(training_args, 'training arguments')

    # -----------------------------------------------------------------------
    # Load processor (tokenizer + image_processor + video_processor)
    # -----------------------------------------------------------------------
    processor = transformers.AutoProcessor.from_pretrained(
        training_args.tokenizer_name_or_path or training_args.model_name_or_path,
        trust_remote_code=True,
    )
    # Compatible with both old (4.x) and new (5.x+) transformers:
    # In older versions, processor.tokenizer is always available.
    # In newer versions, the attribute may not exist or may return a different type.
    if hasattr(processor, 'tokenizer') and hasattr(processor.tokenizer, 'pad_token_id'):
        tokenizer = processor.tokenizer
    else:
        tokenizer = transformers.AutoTokenizer.from_pretrained(
            training_args.tokenizer_name_or_path or training_args.model_name_or_path,
            trust_remote_code=True,
        )
        # Attach tokenizer to processor so downstream code (Dataset, DataCollator)
        # can access it via processor.tokenizer
        processor.tokenizer = tokenizer

    init_kwargs = {}
    if model_args.use_flash_attn:
        init_kwargs["attn_implementation"] = "flash_attention_2"
        try:
            from transformers.modeling_flash_attention_utils import FLASH_ATTENTION_COMPATIBILITY_MATRIX
            FLASH_ATTENTION_COMPATIBILITY_MATRIX[2]["pkg_availability_check"] = lambda *a, **kw: True
            print("[Patch] Bypassed flash_attn package distribution name check for FA2.")
        except Exception as e:
            print(f"[Patch] Could not patch FA2 pkg check (non-fatal): {e}")

    # Determine torch dtype
    if training_args.bf16:
        torch_dtype = torch.bfloat16
    elif training_args.fp16:
        torch_dtype = torch.float16
    else:
        torch_dtype = torch.float32

    # -----------------------------------------------------------------------
    # DeepSpeed ZeRO-3 setup
    # -----------------------------------------------------------------------
    if training_args.deepspeed:
        from transformers.integrations import HfDeepSpeedConfig

        ds_config = training_args.deepspeed
        if isinstance(ds_config, str):
            with open(ds_config, 'r') as f:
                ds_config = json.load(f)

        if ds_config.get("train_micro_batch_size_per_gpu", "auto") == "auto":
            ds_config["train_micro_batch_size_per_gpu"] = training_args.per_device_train_batch_size
        if ds_config.get("gradient_accumulation_steps", "auto") == "auto":
            ds_config["gradient_accumulation_steps"] = training_args.gradient_accumulation_steps
        if ds_config.get("train_batch_size", "auto") == "auto":
            ds_config["train_batch_size"] = (
                training_args.per_device_train_batch_size
                * training_args.gradient_accumulation_steps
                * (torch.distributed.get_world_size() if torch.distributed.is_initialized() else 1)
            )

        # NOTE: VLM has mixed-dtype persistent_parameters (ViT fp32 params vs
        # LLM bf16 params) which causes TypeError in ZeRO-3 all_gather.
        # This is fixed by setting stage3_param_persistence_threshold=0 in the
        # DeepSpeed config JSON file (ds_zero3_offload.json).

        dschf = HfDeepSpeedConfig(ds_config)  # noqa: F841

    # -----------------------------------------------------------------------
    # Load model (VL model: ViT + LLM)
    # -----------------------------------------------------------------------
    _has_weights = (
        training_args.model_name_or_path is not None
        and os.path.isdir(training_args.model_name_or_path)
        and any(
            os.path.isfile(os.path.join(training_args.model_name_or_path, f))
            for f in ("model.safetensors", "pytorch_model.bin",
                      "model.safetensors.index.json", "pytorch_model.bin.index.json")
        )
    )

    if _has_weights:
        print(f"Loading VL model from: {training_args.model_name_or_path}")
        # Disable Engram during training to avoid ~59 GiB Embedding OOM.
        # The config.json is kept intact so inference can still use Engram.
        _config = transformers.AutoConfig.from_pretrained(
            training_args.model_name_or_path, trust_remote_code=True
        )
        if hasattr(_config, 'text_config') and hasattr(_config.text_config, 'engram_layer_ids'):
            _config.text_config.engram_layer_ids = None
            print("[HY4-VL] Disabled Engram (set text_config.engram_layer_ids=None) for training.")

        model = transformers.AutoModelForImageTextToText.from_pretrained(
            training_args.model_name_or_path,
            config=_config,
            trust_remote_code=True,
            dtype=torch_dtype,
            attn_implementation=init_kwargs.get("attn_implementation", None),
        )
        print(f"[HY4-VL] Model loaded successfully via from_pretrained.")
    else:
        if training_args.model_name_or_path is None:
            raise ValueError("--model_name_or_path must be specified.")
        print(f"Model weights not found at: {training_args.model_name_or_path}, "
              f"using random initialized model instead.")
        config = transformers.AutoConfig.from_pretrained(
            training_args.model_name_or_path, trust_remote_code=True
        )
        model = transformers.AutoModelForImageTextToText.from_config(
            config, trust_remote_code=True, dtype=torch_dtype,
            attn_implementation=init_kwargs.get("attn_implementation", None),
        )

    # -----------------------------------------------------------------------
    # Freeze ViT encoder (default: freeze during SFT)
    # Compatible with both `model.vit` (internal) and `model.vision_tower` (opensource)
    # -----------------------------------------------------------------------
    if model_args.freeze_vit:
        vit_module = (getattr(model, 'vit', None)
                      or getattr(model, 'vision_tower', None)
                      or getattr(getattr(model, 'model', None), 'vision_tower', None))
        if vit_module is not None:
            vit_module.requires_grad_(False)
            vit_params = sum(getattr(p, 'ds_numel', p.numel()) for p in vit_module.parameters())
            print(f"[HY4-VL] Froze ViT encoder ({vit_params / 1e6:.1f}M parameters)")
        else:
            print("[HY4-VL] WARNING: freeze_vit=True but no ViT encoder found (checked 'vit', 'vision_tower', 'model.vision_tower').")

    # -----------------------------------------------------------------------
    # LoRA setup
    # -----------------------------------------------------------------------
    if model_args.use_lora:
        lora_config = LoraConfig(
            r=model_args.lora_rank,
            lora_alpha=model_args.lora_alpha,
            lora_dropout=model_args.lora_dropout,
            target_modules=["q_a_proj", "q_b_proj", "kv_a_proj_with_mqa", "kv_b_proj", "o_proj"],
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)

        # Mark PEFT LoRA wrapper modules as ZeRO-3 leaf modules
        try:
            from deepspeed.utils import set_z3_leaf_module
            from peft.tuners.lora import Linear as LoraLinear
            z3_leaf_count = 0
            for module in model.modules():
                if isinstance(module, LoraLinear):
                    set_z3_leaf_module(module, True)
                    z3_leaf_count += 1
            print(f"[z3_leaf] Marked {z3_leaf_count} LoraLinear modules with _z3_leaf=True", flush=True)
        except ImportError:
            print("[z3_leaf] DeepSpeed or PEFT not available, skipping z3_leaf patch.")

    # -----------------------------------------------------------------------
    # Data module
    # -----------------------------------------------------------------------
    data_module = make_vl_data_module(processor=processor, data_args=data_args)

    model.is_parallelizable = True
    model.model_parallel = True

    training_args.lr_scheduler_kwargs = {
        'min_lr_rate': training_args.min_lr / training_args.learning_rate,
    }

    # Fix: DeepSpeed ZeRO-3 + gradient checkpointing compatibility
    if training_args.gradient_checkpointing and training_args.deepspeed:
        training_args.gradient_checkpointing_kwargs = {"use_reentrant": True}

    # -----------------------------------------------------------------------
    # Create Trainer
    # -----------------------------------------------------------------------
    trainer = Trainer(
        model=model,
        processing_class=tokenizer,
        args=training_args,
        callbacks=[CustomSaveCallback],
        **data_module
    )
    model.config.use_cache = False

    # -----------------------------------------------------------------------
    # Post-init patches
    # -----------------------------------------------------------------------

    # Fix dtype mismatch in DeepSpeed ZeRO-3 linear wrapper
    import torch.nn.functional as _F
    _orig_F_linear = _F.linear

    def _dtype_safe_linear(input, weight, bias=None):
        if input.dtype != weight.dtype:
            input = input.to(weight.dtype)
        return _orig_F_linear(input, weight, bias)

    _F.linear = _dtype_safe_linear

    # Skip grad norm calculation when max_grad_norm == 0
    if getattr(training_args, "max_grad_norm", None) == 0:
        from deepspeed.runtime.zero.stage3 import DeepSpeedZeroOptimizer_Stage3

        def _skip_get_norm_groups(self):
            return [torch.tensor(0.0)]

        DeepSpeedZeroOptimizer_Stage3._get_norm_groups = _skip_get_norm_groups
        logger.info("[grad_norm] max_grad_norm=0: patched to skip grad norm computation")

    # -----------------------------------------------------------------------
    # Train
    # -----------------------------------------------------------------------
    trainer.train(resume_from_checkpoint=training_args.resume_from_checkpoint)

    if torch.distributed.is_initialized():
        torch.distributed.barrier()


def _apply_safe_pin_memory_patch():
    """Make CUDA pin_memory fault-tolerant for DeepSpeed ZeRO-3.

    DeepSpeed ZeRO-3 calls get_accelerator().pin_memory(tensor) during
    _create_param_groups_fp16_flat_cpu_memory to create pinned (page-locked)
    CPU buffers for parameter offloading.  This call is hard-coded and NOT
    controlled by the config's ``pin_memory: false`` setting.

    On some nodes, pin_memory() can sporadically fail with
    ``CUDA error: invalid argument`` due to transient driver/cgroup issues.
    This patch wraps the CUDA accelerator's pin_memory method so that if
    the call fails, it falls back to returning the original (unpinned)
    tensor instead of crashing the entire training job.
    """
    try:
        from deepspeed.accelerator.cuda_accelerator import CUDA_Accelerator

        _orig_pin_memory = CUDA_Accelerator.pin_memory

        def _safe_pin_memory(self, tensor):
            try:
                return _orig_pin_memory(self, tensor)
            except Exception as e:
                rank = torch.distributed.get_rank() if torch.distributed.is_initialized() else 0
                print(f"[HYV4 Patch] WARNING: pin_memory() failed on rank {rank}: {e}. "
                      f"Falling back to unpinned CPU tensor.", flush=True)
                return tensor

        CUDA_Accelerator.pin_memory = _safe_pin_memory
        print("[HYV4 Patch] Patched CUDA_Accelerator.pin_memory with "
              "fault-tolerant fallback.", flush=True)
    except ImportError:
        pass


if __name__ == "__main__":
    _apply_safe_pin_memory_patch()
    train()
