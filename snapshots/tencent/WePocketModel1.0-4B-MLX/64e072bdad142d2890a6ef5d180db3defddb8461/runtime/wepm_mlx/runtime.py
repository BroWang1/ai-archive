"""WePM runtime on MLX: generation, multimodal embedding and JEV decision."""

from __future__ import annotations

import time
from pathlib import Path

import mlx.core as mx
import numpy as np

from . import decision_protocol
from .config import build_task_slot_config, read_json, spatial_merge_size
from .image import prepare_images
from .mgvb import MultiGranularityVisualBottleneck
from .positions import get_rope_index
from .weights import (
    load_backbone,
    load_task_weights,
    quantize_backbone,
    resolve_model_dir,
    split_task_weights,
)

TASKS = ("generate", "embedding", "decision")


class WePMRuntime:
    """One shared backbone plus the trained E/J slots and MGVB.

    Each call accepts one ordered text/image request. Generation decodes
    autoregressively with no slot. E reads the embedding slot and applies the
    normalized projection; J reads its own slot and applies the direct candidate
    head.
    """

    def __init__(
        self,
        model: str | Path,
        *,
        revision: str | None = None,
        dtype: mx.Dtype = mx.bfloat16,
        quantize_bits: int | None = None,
        quantize_group_size: int = 64,
    ):
        self.model_dir = resolve_model_dir(model, revision=revision)
        self.config = read_json(self.model_dir / "config.json")
        self.tokenizer = self._load_tokenizer()
        slot_token_id = self.tokenizer.pad_token_id
        if slot_token_id is None:
            slot_token_id = self.tokenizer.eos_token_id
        self.task = build_task_slot_config(self.config, slot_token_id=slot_token_id)
        self.merge_size = spatial_merge_size(self.config)
        self.dtype = dtype

        self.model = load_backbone(self.model_dir, self.config, dtype=dtype)
        if quantize_bits is not None:
            quantize_backbone(
                self.model, bits=quantize_bits, group_size=quantize_group_size
            )
            mx.eval(self.model.parameters())
        self.language_model = self.model.language_model
        self.vision_tower = self.model.vision_tower
        self.embed_tokens = self.language_model.model.embed_tokens

        slots, heads, mgvb_weights = split_task_weights(
            load_task_weights(self.model_dir, dtype=dtype)
        )
        self.slots = slots
        self.embedding_head = heads["embedding"]
        self.decision_head = heads["decision"]
        self._check_task_shapes()

        self.mgvb = MultiGranularityVisualBottleneck(
            self.task.hidden_size,
            adapter_dim=self.task.mgvb_adapter_dim,
            token_budget=self.task.mgvb_token_budget,
            global_tokens=self.task.mgvb_global_tokens,
            region_tokens=self.task.mgvb_region_tokens,
            num_global_heads=self.task.mgvb_num_global_heads,
        )
        self.mgvb.load_weights(list(mgvb_weights.items()))
        self.mgvb.eval()
        mx.eval(self.mgvb.parameters())

    # ------------------------------------------------------------------ setup
    def _load_tokenizer(self):
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            self.model_dir, local_files_only=True, trust_remote_code=False
        )
        template_path = self.model_dir / "chat_template.jinja"
        if template_path.is_file():
            tokenizer.chat_template = template_path.read_text(encoding="utf-8")
        if not tokenizer.chat_template:
            raise ValueError("missing saved training chat template")
        return tokenizer

    def _check_task_shapes(self) -> None:
        hidden = self.task.hidden_size
        for role, slot in self.slots.items():
            if tuple(slot.shape) != (hidden,):
                raise ValueError(f"{role} slot shape mismatch: {tuple(slot.shape)}")
        if tuple(self.embedding_head.shape) != (self.task.embedding_dim, hidden):
            raise ValueError(f"embedding head shape mismatch: {tuple(self.embedding_head.shape)}")
        if tuple(self.decision_head.shape) != (self.task.decision_output_size, hidden):
            raise ValueError(f"decision head shape mismatch: {tuple(self.decision_head.shape)}")

    @property
    def eos_token_ids(self) -> set[int]:
        return set(self.task.eos_token_ids)

    # ------------------------------------------------------------- tokenizing
    def _render_prompt(self, content, *, generation: bool) -> str:
        messages = [{"role": "user", "content": content}]
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=generation,
            enable_thinking=False,
        )

    def _content_and_images(self, content):
        """Split request content into template content and image descriptors."""
        template_content = []
        images = []
        content_types = []
        for item in content:
            item_type = item.get("type") if isinstance(item, dict) else None
            if item_type == "text":
                text = item.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("text content must be nonempty")
                template_content.append({"type": "text", "text": text})
            elif item_type == "image":
                template_content.append({"type": "image"})
                images.append(item)
            else:
                raise ValueError("content items must have type text or image")
            content_types.append(item_type)
        if not template_content:
            raise ValueError("content must not be empty")
        return template_content, images, content_types

    def _encode_ids(self, rendered: str, image_counts: list[int]) -> np.ndarray:
        """Tokenize the rendered prompt and expand every image placeholder."""
        ids = self.tokenizer(rendered, add_special_tokens=False)["input_ids"]
        image_id = self.task.image_token_id
        output: list[int] = []
        image_index = 0
        for token in ids:
            if token != image_id:
                output.append(token)
                continue
            if image_index >= len(image_counts):
                raise ValueError("prompt has more image placeholders than images")
            output.extend([image_id] * image_counts[image_index])
            image_index += 1
        if image_index != len(image_counts):
            raise ValueError(
                f"prompt has {image_index} image placeholders for {len(image_counts)} images"
            )
        return np.asarray(output, dtype=np.int64)

    # -------------------------------------------------------------- encoding
    def _text_query(self, ids: np.ndarray, embeddings: mx.array, slot_role: str | None):
        """Mean+last prompt-token query, built exactly as in training."""
        mask = np.ones(ids.shape[0], dtype=bool)
        for token_id in self.tokenizer.all_special_ids:
            mask &= ids != token_id
        if slot_role is not None and mask.size:
            mask[-1] = False
        if not mask.any():
            return None
        rows = embeddings[0]
        index = np.nonzero(mask)[0]
        mean = rows[mx.array(index)].mean(axis=0)
        last = rows[int(index[-1])]
        return mx.concatenate([mean, last], axis=0)

    def _vision_features(self, pixels: mx.array, grid: np.ndarray) -> mx.array:
        merged, _ = self.vision_tower(pixels, mx.array(grid.reshape(1, 3)))
        return merged

    def _prepare_inputs(self, content, *, task: str):
        if task not in TASKS:
            raise ValueError(f"unknown task: {task}")
        generation = task == "generate"
        slot_role = None if generation else task
        template_content, image_items, content_types = self._content_and_images(content)

        merged_counts: list[int] = []
        grids = None
        pixel_values = None
        if image_items:
            pixel_values_np, grids = prepare_images(image_items, self.merge_size)
            native = grids.prod(-1) // (self.merge_size**2)
            merged_counts = [
                int(min(int(n), self.task.mgvb_token_budget)) for n in native
            ]
            pixel_values = mx.array(pixel_values_np)

        ids = self._encode_ids(self._render_prompt(template_content, generation=generation), merged_counts)
        if slot_role is not None:
            ids = np.concatenate([ids, np.asarray([self.task.slot_token_id], dtype=np.int64)])

        embeddings = self.embed_tokens(mx.array(ids)[None])
        # Only the appended position is a soft slot. Literal pad tokens in the
        # prompt and generated tokens always retain native embeddings.
        if slot_role is not None:
            slots = self.slots[slot_role]
            embeddings = mx.concatenate(
                [embeddings[:, :-1], slots.astype(embeddings.dtype)[None, None]], axis=1
            )

        positions = None
        if grids is not None:
            # The reference reports visual lengths after the 2x2 spatial merge.
            native_lengths = [
                int(n) // (self.merge_size**2) for n in grids.prod(-1)
            ]
            query = self._text_query(ids, embeddings, slot_role)
            features = []
            coords = []
            offset = 0
            for index, grid in enumerate(grids):
                count = int(grid.prod())
                patch = pixel_values[offset : offset + count].astype(self.dtype)
                offset += count
                native_features = self._vision_features(patch, grid)
                del patch
                compact, image_positions = self.mgvb.compress_one(
                    native_features, grid, query, self.merge_size
                )
                features.append(compact)
                coords.append(image_positions)
                mx.eval(compact)
            packed = mx.concatenate(features, axis=0)
            mask = ids == self.task.image_token_id
            if int(mask.sum()) != packed.shape[0]:
                raise ValueError("MGVB image-feature/placeholder mismatch")
            # Scatter compact visual tokens into the placeholder rows.
            flat = embeddings[0]
            flat[mx.array(np.nonzero(mask)[0]), :] = packed.astype(embeddings.dtype)
            embeddings = flat[None]
            positions, delta = get_rope_index(
                spatial_merge_size=self.merge_size,
                image_token_id=self.task.image_token_id,
                video_token_id=self.task.video_token_id,
                vision_start_token_id=self.task.vision_start_token_id,
                input_ids=ids,
                image_grid_thw=grids,
                image_position_ids=coords,
            )
            metadata_visual = {
                "native_visual_tokens": native_lengths,
                "compact_visual_tokens": merged_counts,
                "mrope_delta": delta,
            }
        else:
            positions, delta = get_rope_index(
                spatial_merge_size=self.merge_size,
                image_token_id=self.task.image_token_id,
                video_token_id=self.task.video_token_id,
                vision_start_token_id=self.task.vision_start_token_id,
                input_ids=ids,
            )
            metadata_visual = {
                "native_visual_tokens": [],
                "compact_visual_tokens": [],
                "mrope_delta": delta,
            }

        metadata = {
            "input_tokens": int(ids.shape[0]),
            **metadata_visual,
            "slot_positions": [int(ids.shape[0] - 1)] if slot_role is not None else [],
            "slot_role": slot_role,
            "generation_prompt": generation,
            "content_types": content_types,
        }
        return ids, embeddings, positions, metadata

    # ------------------------------------------------------------- inference
    def _forward(self, ids, embeddings, positions, cache=None):
        position_ids = mx.array(positions.astype(np.int32))[:, None, :]
        return self.language_model.model(
            mx.array(ids)[None],
            inputs_embeds=embeddings,
            cache=cache,
            position_ids=position_ids,
        )

    def last_hidden(self, content, *, task: str) -> tuple[mx.array, dict]:
        ids, embeddings, positions, metadata = self._prepare_inputs(content, task=task)
        hidden = self._forward(ids, embeddings, positions)
        return hidden[:, -1, :], metadata

    def embed(self, content, *, dims: list[int] | None = None) -> dict:
        """Return L2-normalized embedding vectors at the requested MRL dimensions."""
        start = time.monotonic()
        hidden, metadata = self.last_hidden(content, task="embedding")
        # The training head projects in the model dtype before fp32 L2 normalization.
        projected = mx.matmul(hidden, self.embedding_head.T).astype(mx.float32)
        if not bool(mx.all(mx.isfinite(projected))) or float(mx.linalg.norm(projected)) == 0:
            raise ValueError("nonfinite or zero embedding")
        dims = list(dims or self.task.embedding_mrl_dims)
        allowed = set(self.task.embedding_mrl_dims)
        if any(d not in allowed for d in dims):
            raise ValueError(f"dimensions must be chosen from {sorted(allowed)}")
        vector = projected[0]
        vectors = {}
        for dim in dims:
            truncated = vector[:dim]
            norm = mx.sqrt(mx.sum(truncated * truncated))
            vectors[str(dim)] = (truncated / mx.maximum(norm, mx.array(1e-12))).tolist()
        return {
            "embeddings": vectors,
            "seconds": time.monotonic() - start,
            "input": metadata,
        }

    def decide(self, request, images=()) -> dict:
        """Evaluate one SystemOne choice/score/noul request using the J slot."""
        start = time.monotonic()
        value = decision_protocol.request_input(request)
        count = len(value.ids)
        if count > self.task.decision_max_candidates:
            raise ValueError("candidate count exceeds the trained direct head capacity")
        wire_images = decision_protocol.request_images(request)
        if images and wire_images:
            raise ValueError("use either local image inputs or JSON image data URLs")
        if len(images) > 8 or sum(map(len, wire_images)) > 64 * 1024 * 1024:
            raise ValueError(
                "decision supports at most eight images and 64 MiB of image bytes"
            )
        decision_content = [
            {"type": "image", "path" if not isinstance(image, (bytes, bytearray)) else "bytes": image}
            for image in (images or wire_images)
        ]
        decision_content.append(
            {"type": "text", "text": decision_protocol.render_input(value)[0]}
        )
        hidden, metadata = self.last_hidden(decision_content, task="decision")
        # The direct head maps h_J to option indices. E normalization and
        # physical padding rows never enter the candidate distribution.
        logits = mx.matmul(hidden, self.decision_head.T).astype(mx.float32)[0, :count]
        if not bool(mx.all(mx.isfinite(logits))):
            raise ValueError("nonfinite decision logits")
        probabilities = mx.softmax(logits, axis=-1).tolist()
        return {
            **decision_protocol.response_from_probabilities(value, probabilities),
            "candidate_count": count,
            "seconds": time.monotonic() - start,
            "input": metadata,
        }

    def generate(self, content, max_new_tokens: int = 64) -> dict:
        """Greedy generation using the backbone's hybrid KV/recurrent cache."""
        if not 0 < max_new_tokens <= 512:
            raise ValueError("max_new_tokens must be in [1, 512]")
        start = time.monotonic()
        ids, embeddings, positions, metadata = self._prepare_inputs(content, task="generate")
        cache = self.language_model.make_cache()
        hidden = self._forward(ids, embeddings, positions, cache=cache)
        rope_start = int(positions.max()) + 1
        prompt_length = int(ids.shape[0])
        stop_ids = self.eos_token_ids
        generated: list[int] = []
        finish = "length"
        for index in range(max_new_tokens):
            logits = self.embed_tokens.as_linear(hidden[:, -1:, :]).astype(mx.float32)
            if not bool(mx.all(mx.isfinite(logits))):
                raise ValueError("nonfinite generation logits")
            token = mx.argmax(logits[:, -1, :], axis=-1)
            token_id = int(token.item())
            generated.append(token_id)
            if token_id in stop_ids:
                finish = "eos"
                break
            if index + 1 == max_new_tokens:
                break
            step = rope_start + index
            step_positions = np.full((3, 1, 1), step, dtype=np.int32)
            hidden = self._forward_step(
                np.asarray([[token_id]], dtype=np.int64), step_positions, cache
            )
        return {
            "text": self.tokenizer.decode(generated, skip_special_tokens=True),
            "token_ids": generated,
            "finish_reason": finish,
            "seconds": time.monotonic() - start,
            "input": metadata,
        }

    def _forward_step(self, token_ids: np.ndarray, positions: np.ndarray, cache) -> mx.array:
        position_ids = mx.array(positions)
        return self.language_model.model(
            mx.array(token_ids),
            cache=cache,
            position_ids=position_ids,
        )

    def close(self) -> None:
        self.model = None
        self.mgvb = None
        self.language_model = None
        self.vision_tower = None
        self.embed_tokens = None
        self.slots = {}
        self.embedding_head = None
        self.decision_head = None
        mx.clear_cache()


def load_runtime(model: str | Path, **kwargs) -> WePMRuntime:
    return WePMRuntime(model, **kwargs)
