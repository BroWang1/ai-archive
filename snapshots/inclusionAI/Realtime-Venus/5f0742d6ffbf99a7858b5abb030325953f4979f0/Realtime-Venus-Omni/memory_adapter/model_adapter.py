# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Memory configuration and routing for Realtime-Venus-Omni Chat and Duplex.

Convert conversation inputs, manage memory sessions, and coordinate text
and speech generation through the model interfaces.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import logging
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np

from .omni_memory.config import MemoryConfig, load_memory_config
from .omni_memory.duplex.proactive_adapter import DuplexMemoryAdapter
from .omni_memory.duplex.runtime import MemoryDuplexRuntime
from .omni_memory.schema import MediaChunk, Question
from .omni_memory.session import MediaMemorySession


_CONTROLLER_ATTRIBUTE = "_realtime_venus_omni_memory_controller"
_DEFAULT_CHAT_QUERY = "Describe the video."
_MEMORY_MEDIA_SLOT_TYPE = "_realtime_venus_omni_memory_media"
_LOGGER = logging.getLogger(__name__)


def configure_memory(
    model: Any,
    *,
    memory_minutes: float | None = None,
) -> "RealtimeVenusOmniMemoryController":
    """Enable Memory with an optional Duplex archive duration in minutes."""
    overrides = None
    if memory_minutes is not None:
        if isinstance(memory_minutes, bool) or not isinstance(
            memory_minutes, (int, float)
        ):
            raise TypeError(
                "memory_minutes must be a positive finite number of minutes"
            )
        try:
            seconds = memory_minutes * 60.0
        except OverflowError as error:
            raise ValueError("memory_minutes must be positive and finite") from error
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("memory_minutes must be positive and finite")
        overrides = {"duplex": {"archive": {"retention_seconds": seconds}}}
    controller = RealtimeVenusOmniMemoryController(
        model=model,
        config=load_memory_config(overrides),
    )
    setattr(model, _CONTROLLER_ATTRIBUTE, controller)
    return controller


class RealtimeVenusOmniMemoryController:
    """Manage memory sessions for Chat and Duplex on a loaded model."""

    def __init__(
        self,
        *,
        model: Any,
        config: MemoryConfig,
    ) -> None:
        self.model = model
        self.config = config
        self.default_chat_query = _DEFAULT_CHAT_QUERY

    def chat(self, official_call: Mapping[str, Any]) -> Any:
        """Convert conversation media into one-second chunks and run Memory Chat."""
        call = _normalize_official_chat_call(official_call)
        _validate_memory_chat_options(call)
        media_chunks, query, prompt_context = _media_chunks_and_query(
            call.get("msgs"),
            default_query=self.default_chat_query,
            image=call.get("image"),
            call=call,
            normalize_content=_official_content_normalizer(self.model),
        )
        max_new_tokens = _positive_integer(
            call.get("max_new_tokens", self.config.chat.max_new_tokens),
            "max_new_tokens",
        )
        resolved_config = replace(
            self.config,
            chat=replace(self.config.chat, max_new_tokens=max_new_tokens),
        )
        processor = getattr(self.model, "processor", None)
        requested_processor = call.get("processor")
        requested_tokenizer = call.get("tokenizer")
        if (
            processor is None
            or requested_processor is not None
            or requested_tokenizer is not None
        ):
            prepare_processor = getattr(self.model, "prepare_processor", None)
            if not callable(prepare_processor):
                raise RuntimeError(
                    "Memory Chat requires model.processor or prepare_processor()"
                )
            prepare_processor(
                processor=requested_processor,
                tokenizer=requested_tokenizer,
            )
            processor = getattr(self.model, "processor", None)
        if processor is None:
            raise RuntimeError(
                "Realtime-Venus-Omni processor initialization returned no processor"
            )
        session = MediaMemorySession(
            model=self.model,
            processor=processor,
            use_memory=True,
            config=resolved_config,
            generate_audio=False,
            prompt_context=prompt_context,
        )
        rendered_prompt: str | None = None
        try:
            answer = session.run(
                media_chunks=media_chunks,
                questions=(Question(query_id="chat", text=query),),
                generation_options=_official_generation_options(call),
            )[0]
            rendered_prompt = session.last_rendered_prompt
        finally:
            session.close()
        if (
            bool(call.get("generate_audio", False))
            and bool(prompt_context["use_tts_template"])
            and call.get("output_audio_path")
        ):
            self._write_official_chat_audio(call, answer.text)
        if bool(call.get("return_prompt", False)):
            if not isinstance(rendered_prompt, str):
                raise RuntimeError(
                    "Memory Chat did not retain the prompt used for generation"
                )
            return answer.text, rendered_prompt
        return answer.text

    def _write_official_chat_audio(
        self,
        call: Mapping[str, Any],
        answer: str,
    ) -> None:
        """Generate speech from the answer text and write it to the requested path."""
        source_msgs = call.get("msgs")
        if not isinstance(source_msgs, Sequence):
            raise TypeError("msgs must be a sequence")
        tts_msgs = [
            deepcopy(message)
            for message in source_msgs
            if isinstance(message, Mapping) and message.get("role") == "system"
        ]
        tts_msgs.append({"role": "assistant", "content": f"<|tts_bos|>{answer}<|tts_eos|>"})
        if not hasattr(self.model, _CONTROLLER_ATTRIBUTE):
            raise RuntimeError("Memory controller state disappeared during Chat TTS")
        delattr(self.model, _CONTROLLER_ATTRIBUTE)
        try:
            self.model.chat(
                msgs=tts_msgs,
                max_new_tokens=1,
                do_sample=False,
                max_inp_length=call.get("max_inp_length", 8192),
                max_slice_nums=call.get("max_slice_nums"),
                use_image_id=call.get("use_image_id"),
                enable_thinking=False,
                use_tts_template=True,
                generate_audio=True,
                output_audio_path=call.get("output_audio_path"),
                output_tts_inputs_embeds_path=call.get("output_tts_inputs_embeds_path"),
                omni_mode=bool(call.get("omni_mode", False)),
                teacher_forcing=True,
                tts_proj_layer=call.get("tts_proj_layer", -1),
                tts_sampling_params=call.get("tts_sampling_params"),
                merge_audio_from_same_content=call.get(
                    "merge_audio_from_same_content", True
                ),
                tokenizer=call.get("tokenizer"),
                processor=call.get("processor"),
            )
        finally:
            setattr(self.model, _CONTROLLER_ATTRIBUTE, self)

    def duplex_factory_kwargs(self, kwargs: Mapping[str, Any]) -> dict[str, Any]:
        """Configure the decoder window mode required by Duplex Memory."""
        resolved = dict(kwargs)
        expected = "off"
        requested = resolved.get("sliding_window_mode", expected)
        if requested != expected:
            raise ValueError(
                f"Memory Duplex requires sliding_window_mode={expected!r}, "
                f"got {requested!r}"
            )
        resolved["sliding_window_mode"] = expected
        return resolved

    def wrap_duplex(self, official_duplex: Any) -> Any:
        """Attach long-term memory to an existing Duplex instance."""
        adapter = DuplexMemoryAdapter(official_duplex)
        runtime = MemoryDuplexRuntime(
            model=self.model,
            config=self.config.to_duplex_engine_config(),
            generate_audio=bool(getattr(official_duplex, "generate_audio", True)),
            adapter=adapter,
            auto_prepare=False,
        )
        return HuggingFaceMemoryDuplex(runtime=runtime, official=official_duplex)


class HuggingFaceMemoryDuplex:
    """Route Duplex calls through the memory runtime."""

    def __init__(self, *, runtime: MemoryDuplexRuntime, official: Any) -> None:
        self._memory_runtime = runtime
        self._official_duplex = official

    @property
    def memory_runtime(self) -> MemoryDuplexRuntime:
        """Return the underlying memory runtime."""
        return self._memory_runtime

    @property
    def official_duplex(self) -> Any:
        """Return the underlying Duplex instance."""
        return self._official_duplex

    def prepare(
        self,
        prefix_system_prompt: str | None = None,
        ref_audio: Any | None = None,
        prompt_wav_path: str | Path | None = None,
        context_previous_marker: str = "\n\nprevious: ",
        **kwargs: Any,
    ) -> Any:
        """Prepare a session and return the rendered system prompt."""
        return self._memory_runtime.prepare(
            prefix_system_prompt=prefix_system_prompt,
            ref_audio=ref_audio,
            prompt_wav_path=prompt_wav_path,
            context_previous_marker=context_previous_marker,
            **kwargs,
        )

    def streaming_prefill(
        self,
        audio_waveform: Any | None = None,
        frame_list: list[Any] | None = None,
        text_list: list[Any] | None = None,
        max_slice_nums: Any = 1,
        batch_vision_feed: bool = False,
    ) -> dict[str, Any]:
        """Prefill media and route non-empty text_list inputs to Memory."""
        return self._memory_runtime.streaming_prefill(
            audio_waveform=audio_waveform,
            frame_list=frame_list,
            text_list=text_list,
            max_slice_nums=max_slice_nums,
            batch_vision_feed=batch_vision_feed,
        )

    def streaming_generate(
        self,
        prompt_wav_path: str | Path | None = None,
        max_new_speak_tokens_per_chunk: int = 6,
        decode_mode: str = "sampling",
        temperature: float = 0.7,
        top_k: int = 100,
        top_p: float = 0.8,
        listen_prob_scale: float = 1.0,
        listen_top_k: int | None = None,
        text_repetition_penalty: float = 1.05,
        text_repetition_window_size: int = 512,
    ) -> dict[str, Any]:
        """Generate a chunk, including pending answers after the end of media."""
        return self._memory_runtime.streaming_generate(
            prompt_wav_path=(None if prompt_wav_path is None else str(prompt_wav_path)),
            max_new_speak_tokens_per_chunk=max_new_speak_tokens_per_chunk,
            decode_mode=decode_mode,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            listen_prob_scale=listen_prob_scale,
            listen_top_k=listen_top_k,
            text_repetition_penalty=text_repetition_penalty,
            text_repetition_window_size=text_repetition_window_size,
        )

    def as_simplex(
        self,
        reset_session: bool = True,
        reset_token2wav_cache: bool = False,
    ) -> Any:
        """Close both runtimes while preserving the original cleanup exception."""
        try:
            self._memory_runtime.close()
        except BaseException:
            try:
                self._official_duplex.as_simplex(
                    reset_session=reset_session,
                    reset_token2wav_cache=reset_token2wav_cache,
                )
            except BaseException:
                _LOGGER.exception(
                    "Official Duplex cleanup also failed after Memory close failed; "
                    "re-raising the original Memory error"
                )
            raise
        return self._official_duplex.as_simplex(
            reset_session=reset_session,
            reset_token2wav_cache=reset_token2wav_cache,
        )

    def __getattr__(self, name: str) -> Any:
        """Delegate attributes not defined here to the underlying Duplex instance."""
        official = object.__getattribute__(self, "_official_duplex")
        return getattr(official, name)


def _normalize_official_chat_call(official_call: Mapping[str, Any]) -> dict[str, Any]:
    """Expand nested keyword arguments and reject duplicate fields."""
    call = dict(official_call)
    call.pop("self", None)
    call.pop("memory_controller", None)
    extras = call.pop("kwargs", {})
    if not isinstance(extras, Mapping):
        raise TypeError("official chat kwargs must be a mapping")
    duplicates = sorted(set(call).intersection(extras))
    if duplicates:
        raise ValueError("duplicate Chat arguments: " + ", ".join(duplicates))
    call.update(extras)
    return call


def _validate_memory_chat_options(call: Mapping[str, Any]) -> None:
    """Reject options incompatible with embedding-based Memory Chat prefill."""
    if call.get("vision_hidden_states") is not None:
        raise ValueError("Memory Chat does not accept precomputed vision_hidden_states")
    for name in ("stream", "stream_input", "teacher_forcing"):
        if bool(call.get(name, False)):
            raise NotImplementedError(f"Memory Chat does not support {name}=True")
    max_slice_nums = call.get("max_slice_nums")
    if isinstance(max_slice_nums, bool) or max_slice_nums not in (None, 1):
        raise NotImplementedError(
            "Memory Chat currently supports max_slice_nums=None or 1; HD slicing "
            "requires a variable visual-token store and must not be silently "
            "treated as one slice"
        )
    _positive_integer(call.get("max_inp_length", 8192), "max_inp_length")


def _media_chunks_and_query(
    msgs: Any,
    *,
    default_query: str,
    image: Any | None = None,
    call: Mapping[str, Any] | None = None,
    normalize_content: Any | None = None,
) -> tuple[tuple[MediaChunk, ...], str, dict[str, Any]]:
    """Extract media chunks while preserving the conversation structure."""
    if not isinstance(msgs, Sequence) or isinstance(msgs, (str, bytes)) or not msgs:
        raise ValueError("Memory Chat requires a non-empty msgs sequence")
    if isinstance(msgs[0], Sequence) and not isinstance(msgs[0], Mapping):
        raise NotImplementedError("Memory Chat does not support batched msgs")
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Memory Chat requires Pillow") from error

    source_messages = []
    for message in msgs:
        if not isinstance(message, Mapping):
            raise TypeError("each Chat message must be a mapping")
        copied = dict(message)
        content = copied.get("content")
        if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
            copied["content"] = list(content)
        source_messages.append(copied)
    if image is not None and source_messages:
        first = source_messages[0]
        if not isinstance(first, Mapping):
            raise TypeError("each Chat message must be a mapping")
        if isinstance(first.get("content"), str):
            first["content"] = [image, first["content"]]

    prompt_messages: list[dict[str, Any]] = []
    chunks: list[MediaChunk] = []
    latest_user_text = ""
    inserted_memory_slot = False
    memory_message_index: int | None = None
    saw_audio = False
    for message_index, message in enumerate(source_messages):
        if not isinstance(message, Mapping):
            raise TypeError("each Chat message must be a mapping")
        role = message.get("role")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"unsupported Chat role: {role!r}")
        if message_index == 0 and role not in {"system", "user"}:
            raise ValueError("the first Chat message must be system or user")
        content = message.get("content")
        content_was_text = isinstance(content, str)
        if callable(normalize_content):
            items = list(normalize_content(content))
        elif content_was_text:
            items = [content]
        elif isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
            items = list(_normalize_content_items(content))
        else:
            raise TypeError("message content must be text or a content sequence")

        if role == "user":
            text_parts = [
                item.strip() for item in items if isinstance(item, str) and item.strip()
            ]
            if text_parts:
                latest_user_text = "\n".join(text_parts)

        preserved: list[Any] = []
        cursor = 0
        video_region_started = False
        video_region_closed = False
        while cursor < len(items):
            item = items[cursor]
            if isinstance(item, np.ndarray):
                saw_audio = True
            is_video_unit = (
                role == "user"
                and isinstance(item, Image.Image)
                and cursor + 1 < len(items)
                and isinstance(items[cursor + 1], np.ndarray)
            )
            if not is_video_unit:
                if video_region_started:
                    video_region_closed = True
                preserved.append(item)
                cursor += 1
                continue

            if video_region_closed:
                raise NotImplementedError(
                    "Memory Chat requires video frame/audio units to form one "
                    "contiguous region inside their user message"
                )
            video_region_started = True

            main_frame = item
            audio = items[cursor + 1]
            if memory_message_index is None:
                memory_message_index = message_index
            elif memory_message_index != message_index:
                raise NotImplementedError(
                    "Memory Chat requires all video frame/audio units to remain "
                    "inside one user message so their original conversation turn "
                    "is unambiguous"
                )
            saw_audio = True
            cursor += 2
            frames = [main_frame]
            if cursor < len(items) and isinstance(items[cursor], Image.Image):
                next_is_stacked = cursor + 1 == len(items) or not isinstance(
                    items[cursor + 1], np.ndarray
                )
                if next_is_stacked:
                    frames.append(items[cursor])
                    cursor += 1
            index = len(chunks)
            frame_times = tuple(
                float(index) + offset / len(frames) for offset in range(len(frames))
            )
            chunks.append(
                MediaChunk(
                    sequence_number=index,
                    start_seconds=float(index),
                    end_seconds=float(index + 1),
                    frames=tuple(frames),
                    frame_timestamps_seconds=frame_times,
                    audio_waveform=audio,
                    is_final=False,
                )
            )
            if not inserted_memory_slot:
                preserved.append({"type": _MEMORY_MEDIA_SLOT_TYPE})
                inserted_memory_slot = True

        prompt_messages.append(
            {
                "role": role,
                "content": (
                    preserved[0]
                    if content_was_text
                    and len(preserved) == 1
                    and isinstance(preserved[0], str)
                    else preserved
                ),
            }
        )

    if not chunks:
        raise ValueError(
            "Memory Chat found no [PIL frame, numpy audio] pairs in user msgs"
        )
    chunks[-1] = replace(chunks[-1], is_final=True)
    query = latest_user_text.strip() or default_query
    options = {} if call is None else dict(call)
    prompt_context = {
        "msgs": tuple(prompt_messages),
        "memory_media_slot_type": _MEMORY_MEDIA_SLOT_TYPE,
        "omni_mode": bool(options.get("omni_mode", False)),
        "use_tts_template": bool(options.get("use_tts_template", False)) or saw_audio,
        "enable_thinking": bool(options.get("enable_thinking", False)),
        "max_slice_nums": 1,
        "use_image_id": options.get("use_image_id"),
        "max_input_length": options.get("max_inp_length", 8192),
        "merge_audio_from_same_content": bool(
            options.get("merge_audio_from_same_content", True)
        ),
    }
    return tuple(chunks), query, prompt_context


def _official_content_normalizer(model: Any) -> Any | None:
    """Get the content normalizer from the loaded model module."""
    module = sys.modules.get(type(model).__module__)
    normalizer = None if module is None else getattr(module, "normalize_content", None)
    return normalizer if callable(normalizer) else None


def _normalize_content_items(content: Sequence[Any]) -> tuple[Any, ...]:
    """Normalize supported content formats into model input items."""
    normalized: list[Any] = []
    for item in content:
        if not isinstance(item, Mapping):
            normalized.append(item)
            continue
        item_type = item.get("type")
        if item_type in {"text", "input_text"}:
            normalized.append(item.get("text", ""))
        elif item_type in {"image", "image_url", "input_image"}:
            normalized.append(item.get("image", item.get("image_url")))
        elif item_type in {"audio", "input_audio"}:
            normalized.append(item.get("audio", item.get("input_audio")))
        else:
            raise ValueError(f"unsupported structured content type: {item_type!r}")
    return tuple(normalized)


def _official_generation_options(call: Mapping[str, Any]) -> dict[str, Any]:
    """Extract text generation options, excluding media and TTS controls."""
    controls = {
        "image",
        "msgs",
        "vision_hidden_states",
        "max_new_tokens",
        "max_inp_length",
        "max_slice_nums",
        "use_image_id",
        "enable_thinking",
        "use_tts_template",
        "generate_audio",
        "output_audio_path",
        "output_tts_inputs_embeds_path",
        "omni_mode",
        "teacher_forcing",
        "return_prompt",
        "tts_proj_layer",
        "tts_sampling_params",
        "merge_audio_from_same_content",
        "stream",
        "stream_input",
        "tokenizer",
        "processor",
    }
    return {key: value for key, value in call.items() if key not in controls}


def _positive_integer(value: Any, name: str) -> int:
    """Validate a positive integer parameter, excluding boolean values."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


__all__ = [
    "HuggingFaceMemoryDuplex",
    "RealtimeVenusOmniMemoryController",
    "configure_memory",
]
