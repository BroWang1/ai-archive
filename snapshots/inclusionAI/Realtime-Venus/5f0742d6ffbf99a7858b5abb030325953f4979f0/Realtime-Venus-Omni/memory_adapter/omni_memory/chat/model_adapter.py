# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Media selection and input assembly for Memory Chat."""

from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence
import numpy as np
import torch
from .engine.adapters.realtime_venus_omni import RealtimeVenusOmniAdapter
from .engine.adapters.selected_sequence import assemble_savemem_question
from .engine.data.sampling import SampledFrame
from .engine.memory.semantic import embed_pseudo_questions
from .engine.memory.types import FrameTokenStore


@dataclass(frozen=True)
class ChatGenerationOutput:
    """Return generated text together with exact assembled-input accounting."""

    text: str
    context_budget: Any
    rendered_prompt: str


@dataclass(frozen=True)
class PreparedChatGeneration:
    """Hold the assembled LLM input and its rendered prompt."""

    assembled: Any
    rendered_prompt: str


class OfficialChatMemoryAdapter:
    """Expose only the model operations required by ``MemoryChatRuntime``."""

    def __init__(self, model: Any, processor: Any) -> None:
        if processor is None:
            raise RuntimeError(
                "Memory Chat requires the matching AutoProcessor; load it from the same model directory and pass it as this adapter's processor argument, or use model.chat(processor=...) through the HF Memory route"
            )
        config = getattr(model, "config", None)
        if config is None:
            raise RuntimeError("Realtime-Venus-Omni model must expose config")
        tokenizer = getattr(processor, "tokenizer", None)
        if tokenizer is None:
            raise RuntimeError("Realtime-Venus-Omni processor must expose tokenizer")
        device = getattr(model, "device", None)
        if device is None:
            parameter = next(model.parameters(), None)
            device = "cpu" if parameter is None else parameter.device
        self.engine = RealtimeVenusOmniAdapter(
            model=model,
            processor=processor,
            tokenizer=tokenizer,
            device=torch.device(device),
        )

    @property
    def device(self) -> torch.device:
        return self.engine.device

    def encode_visual(
        self, images: Sequence[Any], sampled_frames: Sequence[SampledFrame]
    ) -> FrameTokenStore:
        prepared = self.engine.prepare_visual_chunk(images, sampled_frames)
        return self.engine.encode_visual(prepared)

    def encode_audio(
        self, waveform: np.ndarray, original_frames: Sequence[SampledFrame]
    ) -> tuple[tuple[torch.Tensor, ...], Any]:
        prepared = self.engine.prepare_audio_prefix(waveform, original_frames)
        return (tuple(self.engine.encode_audio(prepared)), prepared.audio_metadata)

    def embed_query(self, text: str) -> torch.Tensor:
        return embed_pseudo_questions(
            [text],
            self.engine.tokenizer,
            self.engine.text_embedding_layer(),
            exclude_added_special_tokens=True,
        )

    @torch.inference_mode()
    def prepare_answer(
        self,
        *,
        visual_memory: Any,
        selected_visual_ids: tuple[int, ...],
        audio_embeddings: tuple[torch.Tensor, ...],
        audio_start_seconds: tuple[float, ...],
        audio_end_seconds: tuple[float, ...],
        selected_audio_ids: tuple[int, ...],
        prompt: str,
        max_new_tokens: int,
        generate_audio: bool,
        prompt_context: Mapping[str, Any] | None = None,
    ) -> PreparedChatGeneration:
        """Copy selected media into one self-contained final LLM input."""
        if generate_audio:
            raise NotImplementedError(
                "This Memory Chat embedding-generation stage produces text only; the HF Chat controller synthesizes that text through its separate teacher-forcing TTS step"
            )
        selected = assemble_savemem_question(
            adapter=self.engine,
            visual_memory=visual_memory,
            selected_visual_frame_ids=selected_visual_ids,
            audio_embeddings=audio_embeddings,
            audio_start_seconds=audio_start_seconds,
            audio_end_seconds=audio_end_seconds,
            selected_audio_indices=selected_audio_ids,
            prompt=prompt,
            reserved_generation_tokens=max_new_tokens,
            prompt_context=prompt_context,
        )
        return PreparedChatGeneration(
            assembled=selected.assembled, rendered_prompt=selected.rendered_prompt
        )

    def generate_prepared_answer(
        self,
        prepared: PreparedChatGeneration,
        *,
        max_new_tokens: int,
        generation_options: Mapping[str, Any] | None = None,
    ) -> ChatGenerationOutput:
        """Decode one prepared input after source media banks may be released."""
        generation = {
            "do_sample": True,
            "max_new_tokens": max_new_tokens,
            "generate_audio": False,
        }
        if generation_options is not None:
            generation.update(generation_options)
        generation["max_new_tokens"] = max_new_tokens
        generation["generate_audio"] = False
        text = self.engine.generate(prepared.assembled, generation)
        return ChatGenerationOutput(
            text=str(text),
            context_budget=prepared.assembled.context_budget,
            rendered_prompt=prepared.rendered_prompt,
        )


def dense_sampled_frames(decisions: Sequence[Any]) -> tuple[SampledFrame, ...]:
    """Renumber kept candidates without changing their source provenance."""
    return tuple(
        (
            replace(item.sampled_frame, ordinal=index)
            for (index, item) in enumerate((item for item in decisions if item.keep))
        )
    )
