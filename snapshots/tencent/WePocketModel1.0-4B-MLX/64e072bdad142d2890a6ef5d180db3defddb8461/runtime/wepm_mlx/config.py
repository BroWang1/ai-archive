"""WePM configuration: the Qwen3.5 backbone config plus the task-slot contract."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from mlx_vlm.models.qwen3_5.config import ModelConfig

DEFAULT_MROPE_SECTION = (11, 11, 10)


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_config(raw: dict) -> dict:
    """Return a copy of the checkpoint config with an explicit text-side RoPE block.

    Older exports carry ``rope_theta`` / ``partial_rotary_factor`` at the top level
    instead of ``text_config.rope_parameters``. The MLX backbone reads the nested
    block, so fill it in without changing the values that produced the checkpoint.
    """
    config = copy.deepcopy(raw)
    text = config["text_config"]
    head_dim = text.get("head_dim") or text["hidden_size"] // text["num_attention_heads"]
    text["head_dim"] = int(head_dim)

    rope = text.get("rope_parameters")
    if not rope:
        rope = {
            "rope_type": "default",
            "mrope_section": list(DEFAULT_MROPE_SECTION),
            "partial_rotary_factor": float(
                text.get("partial_rotary_factor", config.get("partial_rotary_factor", 1.0))
            ),
            "rope_theta": float(config.get("rope_theta", text.get("rope_theta", 10000.0))),
        }
        text["rope_parameters"] = rope
    else:
        rope.setdefault("rope_type", rope.get("type", "default"))
        rope.setdefault(
            "partial_rotary_factor",
            float(text.get("partial_rotary_factor", config.get("partial_rotary_factor", 1.0))),
        )
        rope.setdefault("rope_theta", float(config.get("rope_theta", 10000.0)))
        rope.setdefault("mrope_section", list(DEFAULT_MROPE_SECTION))

    # The released checkpoints use interleaved M-RoPE; the MLX backbone is
    # hard-wired to that layout, so an explicit non-interleaved flag is refused.
    if rope.get("mrope_interleaved") is False:
        raise ValueError("non-interleaved M-RoPE checkpoints are not supported")

    text.setdefault("model_type", "qwen3_5_text")
    config.setdefault("model_type", "qwen3_5")
    return config


@dataclass(frozen=True)
class TaskSlotConfig:
    """Everything the WePM glue code needs from the checkpoint config."""

    embedding_dim: int
    embedding_mrl_dims: tuple[int, ...]
    mgvb_adapter_dim: int
    mgvb_token_budget: int
    mgvb_global_tokens: int
    mgvb_region_tokens: int
    mgvb_num_global_heads: int
    hidden_size: int
    decision_max_candidates: int
    decision_output_size: int
    eos_token_ids: tuple[int, ...]
    slot_token_id: int
    image_token_id: int
    video_token_id: int
    vision_start_token_id: int

    @property
    def mgvb_fine_tokens(self) -> int:
        return (
            self.mgvb_token_budget - self.mgvb_global_tokens - self.mgvb_region_tokens
        )


def build_task_slot_config(config: dict, *, slot_token_id: int) -> TaskSlotConfig:
    """Validate the task_slots_v1 contract and expose its values."""
    text = config["text_config"]
    if config.get("unimodel_architecture") != "task_slots_v1":
        raise ValueError(
            "this runtime requires a task_slots_v1 WePM export, got "
            f"{config.get('unimodel_architecture')!r}"
        )
    if config.get("unimodel_decision_head_type") != "direct":
        raise ValueError("the WePM runtime requires the trained direct decision head")
    if config.get("unimodel_decision_input_profile") != "systemone_visible_v1":
        raise ValueError("checkpoint decision input protocol is incompatible")
    if not config.get("unimodel_slot_enable") or not config.get("unimodel_mgvb_enable"):
        raise ValueError("the formal model requires E/J slots and MGVB")
    if config.get("unimodel_generation_slot_enable"):
        raise ValueError("task slots require slotless generation")
    if int(config.get("unimodel_slot_count", 1)) != 1 or int(
        config.get("unimodel_slot_readout_index", 0)
    ):
        raise ValueError("task slots require slot_count=1 and readout index 0")
    if config.get("unimodel_ds_lora_enable") or config.get("unimodel_mgve_enable"):
        raise ValueError("DS-LoRA/MGVE are not part of this architecture")

    max_candidates = int(config.get("unimodel_decision_max_candidates", 255))
    if max_candidates < 2:
        raise ValueError("unimodel_decision_max_candidates must be >= 2")
    # The trained direct head is padded to a multiple of 128; spare rows never
    # enter the candidate distribution.
    decision_output_size = ((max_candidates + 127) // 128) * 128

    eos_values = config.get("eos_token_id", text.get("eos_token_id"))
    eos_ids = tuple(int(v) for v in (eos_values if isinstance(eos_values, list) else [eos_values])
                    if v is not None)
    text_eos = text.get("eos_token_id")
    for value in (text_eos if isinstance(text_eos, list) else [text_eos]):
        if value is not None and int(value) not in eos_ids:
            eos_ids = eos_ids + (int(value),)

    return TaskSlotConfig(
        embedding_dim=int(config["unimodel_embedding_dim"]),
        embedding_mrl_dims=tuple(
            int(v) for v in config.get("unimodel_embedding_mrl_dims", [64, 128, 256, 512, 1024, 2048])
        ),
        mgvb_adapter_dim=int(config.get("unimodel_mgvb_adapter_dim", 512)),
        mgvb_token_budget=int(
            config.get("unimodel_mgvb_token_budget", config.get("unimodel_mgvb_total_budget", 256))
        ),
        mgvb_global_tokens=int(config.get("unimodel_mgvb_global_tokens", 8)),
        mgvb_region_tokens=int(config.get("unimodel_mgvb_region_tokens", 64)),
        mgvb_num_global_heads=int(config.get("unimodel_mgvb_num_global_heads", 8)),
        hidden_size=int(text["hidden_size"]),
        decision_max_candidates=max_candidates,
        decision_output_size=decision_output_size,
        eos_token_ids=eos_ids,
        slot_token_id=int(slot_token_id),
        image_token_id=int(config["image_token_id"]),
        video_token_id=int(config["video_token_id"]),
        vision_start_token_id=int(config["vision_start_token_id"]),
    )


def build_model_config(config: dict) -> ModelConfig:
    """Build the backbone config consumed by ``mlx_vlm``'s Qwen3.5 model."""
    return ModelConfig.from_dict(normalize_config(config))


def spatial_merge_size(config: dict) -> int:
    return int(config["vision_config"]["spatial_merge_size"])
