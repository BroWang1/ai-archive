# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""External Realtime-Venus-Omni adapter without modifying checkpoint remote code."""

from __future__ import annotations
import math
import warnings
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
import numpy as np
import torch
from ..data.sampling import SampledFrame
from ..memory.types import FrameTokenStore
from .sequence_assembler import AssembledInput, CanonicalOmniInput


@dataclass(frozen=True)
class DecodedMedia:
    """Decoded sampled RGB frames plus the complete visible audio prefix."""

    frames: tuple[object, ...]
    audio_waveform: np.ndarray
    audio_sample_rate: int


@dataclass(frozen=True)
class AudioMetadata:
    """Coverage record proving that all decoded audio reached the processor."""

    source_sample_rate: int
    source_sample_count: int
    source_duration_seconds: float
    segment_sample_counts: tuple[int, ...]
    segment_start_seconds: tuple[float, ...] = ()
    segment_end_seconds: tuple[float, ...] = ()
    segment_frame_indices: tuple[int, ...] = ()
    segment_token_counts: tuple[int, ...] = ()
    placeholder_layout_repaired: bool = False
    source_segment_sample_counts: tuple[int, ...] = ()
    processor_segment_sample_counts: tuple[int, ...] = ()
    processor_padding_sample_count: int = 0
    zero_token_segment_indices: tuple[int, ...] = ()
    zero_token_segment_sample_count: int = 0

    @property
    def segment_count(self) -> int:
        return len(self.segment_sample_counts)


@dataclass(frozen=True)
class AudioSegment:
    """One waveform block bounded by manifest target timestamps."""

    waveform: np.ndarray
    start_sample: int
    end_sample: int
    frame_index: int


@dataclass(frozen=True)
class PreparedExample:
    """Processor output and the canonical sequence contract."""

    data: MutableMapping[str, object]
    canonical: CanonicalOmniInput
    sampled_frames: tuple[SampledFrame, ...]
    rendered_prompt: str
    audio_metadata: AudioMetadata


@dataclass(frozen=True)
class PreparedVisualChunk:
    """Processor tensors for one bounded image-only chunk."""

    data: MutableMapping[str, object]
    sampled_frames: tuple[SampledFrame, ...]


@dataclass(frozen=True)
class PreparedSelectedConversation:
    """Conversation inputs assembled from message templates and memory embeddings."""

    canonical: CanonicalOmniInput
    visual_frames: tuple[tuple[tuple[int, ...], torch.Tensor], ...]
    audio_embeddings: tuple[torch.Tensor, ...]
    rendered_prompt: str


class _ScaledEmbedding(torch.nn.Module):
    """Match Realtime-Venus-Omni's optional ``llm.config.scale_emb`` exactly."""

    def __init__(self, embedding: torch.nn.Module, scale: object) -> None:
        super().__init__()
        self.embedding = embedding
        self.scale = scale

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        return self.embedding(input_ids) * self.scale


MediaDecoder = Callable[[Path, tuple[SampledFrame, ...], float], DecodedMedia]


def _get_decord_batch(
    decord: object, video_path: Path, source_indices: Sequence[int]
) -> object:
    """Decode exact frame indices, retrying known Decord thread failures serially."""
    if not source_indices:
        raise ValueError("source_indices cannot be empty")

    def open_reader(*, num_threads: int | None = None) -> object:
        kwargs: dict[str, object] = {"ctx": decord.cpu(0)}
        if num_threads is not None:
            kwargs["num_threads"] = num_threads
        reader = decord.VideoReader(str(video_path), **kwargs)
        maximum_index = max(source_indices)
        if maximum_index >= len(reader):
            raise RuntimeError(
                f"manifest frame {maximum_index} exceeds decoded frame count {len(reader)}"
            )
        return reader

    reader = open_reader()
    try:
        return reader.get_batch(source_indices)
    except Exception as threaded_error:
        warnings.warn(
            f"Decord automatic-thread frame decoding failed; retrying the same {len(source_indices)} frame indices with num_threads=1 for {video_path}: {type(threaded_error).__name__}: {threaded_error}",
            RuntimeWarning,
            stacklevel=2,
        )
        del reader
    retry_reader = open_reader(num_threads=1)
    try:
        return retry_reader.get_batch(source_indices)
    except Exception as single_thread_error:
        raise RuntimeError(
            f"failed to decode video frames with both Decord automatic threads and num_threads=1: {video_path}"
        ) from single_thread_error


def _decode_complete_media(
    video_path: Path,
    sampled_frames: tuple[SampledFrame, ...],
    effective_duration_seconds: float,
) -> DecodedMedia:
    """Decode manifest frames and the complete visible 16 kHz mono audio prefix."""
    if not video_path.is_file():
        raise FileNotFoundError(f"video file does not exist: {video_path}")
    try:
        import decord
        import librosa
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "media decoding requires decord, librosa, and Pillow from requirements.txt"
        ) from error
    try:
        source_indices = [frame.source_frame_index for frame in sampled_frames]
        batch = _get_decord_batch(decord, video_path, source_indices)
        arrays = batch.asnumpy() if hasattr(batch, "asnumpy") else np.asarray(batch)
        frames = tuple((Image.fromarray(array).convert("RGB") for array in arrays))
    except Exception as error:
        if isinstance(error, (ValueError, RuntimeError)):
            raise
        raise RuntimeError(f"failed to decode video frames: {video_path}") from error
    try:
        (waveform, sample_rate) = librosa.load(
            str(video_path), sr=16000, mono=True, duration=effective_duration_seconds
        )
    except Exception as error:
        raise RuntimeError(f"failed to decode source audio: {video_path}") from error
    waveform = np.asarray(waveform, dtype=np.float32)
    maximum_samples = int(effective_duration_seconds * 16000)
    waveform = np.ascontiguousarray(waveform[:maximum_samples], dtype=np.float32)
    if sample_rate != 16000:
        raise RuntimeError(f"expected decoded audio at 16000 Hz, got {sample_rate}")
    if waveform.ndim != 1 or waveform.size == 0:
        raise RuntimeError(f"source audio is missing or empty: {video_path}")
    if not np.isfinite(waveform).all():
        raise RuntimeError(f"source audio contains non-finite samples: {video_path}")
    if len(frames) != len(sampled_frames):
        raise RuntimeError(
            f"decoded {len(frames)} frames for {len(sampled_frames)} manifest entries"
        )
    return DecodedMedia(frames, waveform, int(sample_rate))


def _as_batch_tensor(value: object, name: str) -> torch.Tensor:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 1
    ):
        raise RuntimeError(f"{name} must contain exactly one batch item")
    tensor = value[0]
    if not isinstance(tensor, torch.Tensor):
        raise RuntimeError(f"{name}[0] must be a tensor")
    return tensor


class RealtimeVenusOmniAdapter:
    """Realtime-Venus-Omni media encoding and generation for single-item batches."""

    def __init__(
        self,
        model: object,
        processor: object,
        tokenizer: object,
        device: torch.device,
        media_decoder: MediaDecoder | None = None,
    ) -> None:
        self.model = model
        self.processor = processor
        self.tokenizer = tokenizer
        self.device = torch.device(device)
        self._media_decoder = media_decoder or _decode_complete_media
        self.validate_contract()

    def validate_contract(self) -> None:
        """Fail early when the external checkpoint is not Realtime-Venus-Omni-compatible."""
        required_model_methods = (
            "get_vision_embedding",
            "get_audio_embedding",
            "get_vllm_embedding",
            "get_omni_embedding",
            "_decode",
            "_decode_text",
            "prepare_generation_config",
        )
        for name in required_model_methods:
            if not callable(getattr(self.model, name, None)):
                raise RuntimeError(f"Realtime-Venus-Omni remote code is missing {name}()")
        llm = getattr(self.model, "llm", None)
        if llm is None or not callable(getattr(llm, "generate", None)):
            raise RuntimeError("Realtime-Venus-Omni remote code is missing llm.generate()")
        embedding = getattr(getattr(llm, "model", None), "embed_tokens", None)
        if not isinstance(embedding, torch.nn.Module):
            raise RuntimeError(
                "Realtime-Venus-Omni remote code is missing llm.model.embed_tokens"
            )
        for name in ("vpm", "resampler", "apm"):
            if not isinstance(getattr(self.model, name, None), torch.nn.Module):
                raise RuntimeError(f"Realtime-Venus-Omni remote code is missing {name} module")
        embedding_weight = getattr(embedding, "weight", None)
        if not isinstance(embedding_weight, torch.Tensor) or embedding_weight.ndim != 2:
            raise RuntimeError("llm.model.embed_tokens.weight must have shape [V,D]")
        embedding_dim = int(embedding_weight.shape[1])
        llm_hidden_size = getattr(getattr(llm, "config", None), "hidden_size", None)
        model_embed_dim = getattr(self.model, "embed_dim", None)
        if llm_hidden_size != embedding_dim or model_embed_dim != embedding_dim:
            raise RuntimeError(
                f"Realtime-Venus-Omni hidden dimension mismatch: embed_tokens={embedding_dim}, llm.config.hidden_size={llm_hidden_size}, model.embed_dim={model_embed_dim}"
            )
        query_num = getattr(getattr(self.model, "config", None), "query_num", None)
        if query_num != 64:
            raise RuntimeError(f"expected model.config.query_num=64, got {query_num!r}")
        context = getattr(getattr(llm, "config", None), "max_position_embeddings", None)
        if isinstance(context, bool) or not isinstance(context, int) or context <= 0:
            raise RuntimeError("llm.config.max_position_embeddings must be positive")
        if not callable(self.processor):
            raise RuntimeError("Realtime-Venus-Omni processor must be callable")
        if not callable(getattr(self.tokenizer, "apply_chat_template", None)):
            raise RuntimeError("Realtime-Venus-Omni tokenizer is missing apply_chat_template()")
        if not callable(getattr(self.tokenizer, "convert_tokens_to_ids", None)):
            raise RuntimeError("Realtime-Venus-Omni tokenizer is missing convert_tokens_to_ids()")
        terminators = getattr(self.model, "terminators", None)
        if not isinstance(terminators, Sequence) or not terminators:
            raise RuntimeError("Realtime-Venus-Omni model.terminators must be non-empty")

    @property
    def max_input_length(self) -> int:
        return int(self.model.llm.config.max_position_embeddings)

    def text_embedding_layer(self) -> torch.nn.Module:
        embedding = self.model.llm.model.embed_tokens
        scale = getattr(self.model.llm.config, "scale_emb", 1.0)
        return _ScaledEmbedding(embedding, scale)

    @staticmethod
    def _validate_manifest_frames(sampled_frames: tuple[SampledFrame, ...]) -> None:
        if not sampled_frames:
            raise ValueError("sampled_frames cannot be empty")
        if tuple((frame.ordinal for frame in sampled_frames)) != tuple(
            range(len(sampled_frames))
        ):
            raise ValueError("sampled frame ordinals must be contiguous from zero")
        source_indices = tuple((frame.source_frame_index for frame in sampled_frames))
        if any(
            (right <= left for (left, right) in zip(source_indices, source_indices[1:]))
        ):
            raise ValueError("sampled source frame indices must be strictly increasing")
        for name, timestamps in (
            (
                "target",
                tuple((frame.target_timestamp_seconds for frame in sampled_frames)),
            ),
            (
                "decoded",
                tuple((frame.decoded_timestamp_seconds for frame in sampled_frames)),
            ),
        ):
            if any((not math.isfinite(value) or value < 0 for value in timestamps)):
                raise ValueError(
                    f"sampled frame {name} timestamps must be finite and nonnegative"
                )
            if any((right < left for (left, right) in zip(timestamps, timestamps[1:]))):
                raise ValueError(
                    f"sampled frame {name} timestamps must be nondecreasing"
                )

    @staticmethod
    def _validate_manifest_frame_chunk(
        sampled_frames: tuple[SampledFrame, ...],
    ) -> None:
        """Validate one contiguous slice whose ordinal may start after zero."""
        if not sampled_frames:
            raise ValueError("sampled_frames cannot be empty")
        ordinals = tuple((frame.ordinal for frame in sampled_frames))
        if ordinals != tuple(range(ordinals[0], ordinals[0] + len(ordinals))):
            raise ValueError("sampled frame chunk ordinals must be contiguous")
        source_indices = tuple((frame.source_frame_index for frame in sampled_frames))
        if any(
            (right <= left for (left, right) in zip(source_indices, source_indices[1:]))
        ):
            raise ValueError("sampled source frame indices must be strictly increasing")
        for name, timestamps in (
            (
                "target",
                tuple((frame.target_timestamp_seconds for frame in sampled_frames)),
            ),
            (
                "decoded",
                tuple((frame.decoded_timestamp_seconds for frame in sampled_frames)),
            ),
        ):
            if any((not math.isfinite(value) or value < 0 for value in timestamps)):
                raise ValueError(
                    f"sampled frame {name} timestamps must be finite and nonnegative"
                )
            if any((right < left for (left, right) in zip(timestamps, timestamps[1:]))):
                raise ValueError(
                    f"sampled frame {name} timestamps must be nondecreasing"
                )

    @staticmethod
    def _split_audio_by_target_timestamps(
        waveform: np.ndarray, sampled_frames: Sequence[SampledFrame]
    ) -> tuple[AudioSegment, ...]:
        """Mirror minicpmo-utils audio slicing for the manifest target timestamps.

        ``minicpmo-utils==1.0.6``
        ``get_audio_segments(..., adjust_length=False)`` slices at
        ``int(timestamp * 16000)`` and pads only a final segment shorter than
        0.1 seconds. Visual decoder PTS must not redefine these audio bounds.
        """
        if waveform.ndim != 1 or waveform.size == 0:
            raise RuntimeError("decoded source audio must be a non-empty mono waveform")
        frames = tuple(sampled_frames)
        if not frames:
            raise ValueError("sampled_frames cannot be empty")
        sample_rate = 16000
        blocks: list[AudioSegment] = []
        for frame_index, frame in enumerate(frames):
            start = int(frame.target_timestamp_seconds * sample_rate)
            end = (
                int(frames[frame_index + 1].target_timestamp_seconds * sample_rate)
                if frame_index + 1 < len(frames)
                else int(waveform.size)
            )
            start = min(max(0, start), int(waveform.size))
            end = min(max(start, end), int(waveform.size))
            segment = np.ascontiguousarray(waveform[start:end], dtype=np.float32)
            if frame_index == len(frames) - 1 and segment.size < 1600:
                segment = np.concatenate(
                    (segment, np.zeros(1600 - segment.size, dtype=segment.dtype))
                )
            if segment.size <= 0:
                raise RuntimeError(
                    f"official audio segment {frame_index} is empty: start={start}, end={end}"
                )
            blocks.append(
                AudioSegment(
                    waveform=np.ascontiguousarray(segment, dtype=np.float32),
                    start_sample=start,
                    end_sample=end,
                    frame_index=frame_index,
                )
            )
        return tuple(blocks)

    @staticmethod
    def _merged_audio_token_counts(
        processor: object, segment_sample_counts: Sequence[int], sample_rate: int
    ) -> tuple[int, ...]:
        """Map raw logical blocks to the unchanged merged APM token stream."""
        if (
            isinstance(sample_rate, bool)
            or not isinstance(sample_rate, int)
            or sample_rate <= 0
        ):
            raise ValueError("sample_rate must be a positive integer")
        get_placeholder = getattr(processor, "get_audio_placeholder", None)
        if not callable(get_placeholder):
            raise RuntimeError("Realtime-Venus-Omni processor is missing get_audio_placeholder()")
        max_chunk_samples = 30 * sample_rate
        cache: dict[int, int] = {0: 0}

        def projected_count(sample_count: int) -> int:
            if sample_count not in cache:
                placeholder = get_placeholder(
                    sample_count, chunk_input=False, chunk_length=1
                )
                if not isinstance(placeholder, str):
                    raise RuntimeError(
                        "processor.get_audio_placeholder() must return a string"
                    )
                cache[sample_count] = placeholder.count("<unk>")
            return cache[sample_count]

        tokens_per_full_chunk = projected_count(max_chunk_samples)

        def projected_prefix(sample_count: int) -> int:
            (full_chunks, remainder) = divmod(sample_count, max_chunk_samples)
            return full_chunks * tokens_per_full_chunk + projected_count(remainder)

        result: list[int] = []
        cumulative_samples = 0
        previous_tokens = 0
        for index, count in enumerate(segment_sample_counts):
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError(f"audio segment {index} sample count must be positive")
            cumulative_samples += count
            cumulative_tokens = projected_prefix(cumulative_samples)
            block_tokens = cumulative_tokens - previous_tokens
            if block_tokens < 0:
                raise RuntimeError(
                    f"cumulative audio projection token count decreased; block={index}, samples={count}"
                )
            result.append(block_tokens)
            previous_tokens = cumulative_tokens
        return tuple(result)

    def _repair_audio_placeholder_layout(
        self, data: MutableMapping[str, object], expected_audio_lengths: Sequence[int]
    ) -> bool:
        """Repair old remote-code bounds while retaining merged audio features."""
        input_ids = data.get("input_ids")
        attention_mask = data.get("attention_mask")
        if (
            not isinstance(input_ids, torch.Tensor)
            or input_ids.ndim != 2
            or input_ids.shape[0] != 1
        ):
            raise RuntimeError("processor input_ids must have shape [1,L]")
        if (
            not isinstance(attention_mask, torch.Tensor)
            or attention_mask.shape != input_ids.shape
        ):
            raise RuntimeError("processor attention_mask must match input_ids")
        audio_bounds = _as_batch_tensor(data.get("audio_bounds"), "audio_bounds")
        if audio_bounds.ndim != 2 or audio_bounds.shape[1:] != (2,):
            raise RuntimeError("processor audio_bounds must have shape [A,2]")
        expected = tuple((int(value) for value in expected_audio_lengths))
        if len(expected) != audio_bounds.shape[0] or any(
            (value < 0 for value in expected)
        ):
            raise RuntimeError(
                "expected audio token lengths must be nonnegative and align with bounds"
            )
        old_pairs = tuple(
            (
                (int(start), int(end))
                for (start, end) in audio_bounds.detach().cpu().tolist()
            )
        )
        old_lengths = tuple((end - start for (start, end) in old_pairs))
        if old_lengths == expected and all((value > 0 for value in expected)):
            return False
        sequence_length = int(input_ids.shape[1])
        if any(
            (
                start <= 0 or end >= sequence_length or end < start
                for (start, end) in old_pairs
            )
        ):
            raise RuntimeError("cannot repair invalid processor audio bounds")
        placeholder_id = next(
            (input_ids[0, start] for (start, end) in old_pairs if end > start), None
        )
        if placeholder_id is None:
            unk_token_id = getattr(self.tokenizer, "unk_token_id", None)
            if not isinstance(unk_token_id, int):
                convert = getattr(self.tokenizer, "convert_tokens_to_ids", None)
                unk_token_id = convert("<unk>") if callable(convert) else None
            if not isinstance(unk_token_id, int) or unk_token_id < 0:
                raise RuntimeError("cannot recover the <unk> placeholder token id")
            placeholder_id = input_ids.new_tensor(unk_token_id)
        pieces: list[torch.Tensor] = []
        new_audio_bounds: list[tuple[int, int]] = []
        cursor = 0
        new_cursor = 0
        for (start, end), new_length in zip(old_pairs, expected):
            if int(input_ids[0, start - 1]) != int(self.tokenizer.audio_start_id):
                raise RuntimeError("audio block is missing its start marker")
            if int(input_ids[0, end]) != int(self.tokenizer.audio_end_id):
                raise RuntimeError("audio block is missing its end marker")
            if new_length == 0:
                prefix = input_ids[0, cursor : start - 1]
                pieces.append(prefix)
                new_cursor += int(prefix.numel())
                cursor = end + 1
                continue
            prefix = input_ids[0, cursor:start]
            pieces.append(prefix)
            new_cursor += int(prefix.numel())
            new_start = new_cursor
            pieces.append(placeholder_id.expand(new_length))
            new_cursor += new_length
            new_audio_bounds.append((new_start, new_cursor))
            end_marker = input_ids[0, end : end + 1]
            pieces.append(end_marker)
            new_cursor += 1
            cursor = end + 1
        suffix = input_ids[0, cursor:]
        pieces.append(suffix)
        repaired_ids = torch.cat(pieces, dim=0).unsqueeze(0)
        deltas = tuple(
            (
                -(old_length + 2) if new_length == 0 else new_length - old_length
                for (new_length, old_length) in zip(expected, old_lengths)
            )
        )

        def remap_position(position: int) -> int:
            return position + sum(
                (
                    delta
                    for ((_, old_end), delta) in zip(old_pairs, deltas)
                    if position > old_end
                )
            )

        def remap_bound_key(key: str) -> None:
            if key not in data:
                return
            bounds = _as_batch_tensor(data.get(key), key)
            if bounds.ndim != 2 or bounds.shape[1:] != (2,):
                raise RuntimeError(f"processor {key} must have shape [N,2]")
            remapped = torch.tensor(
                [
                    (remap_position(int(start)), remap_position(int(end)))
                    for (start, end) in bounds.detach().cpu().tolist()
                ],
                dtype=bounds.dtype,
                device=bounds.device,
            ).reshape(-1, 2)
            data[key] = [remapped]

        data["input_ids"] = repaired_ids
        data["attention_mask"] = torch.ones_like(
            repaired_ids, dtype=attention_mask.dtype
        )
        remap_bound_key("image_bound")
        remap_bound_key("spk_bounds")
        data["audio_bounds"] = [
            torch.tensor(
                new_audio_bounds, dtype=audio_bounds.dtype, device=audio_bounds.device
            ).reshape(-1, 2)
        ]
        return True

    def prepare_canonical_input(
        self,
        video_path: Path,
        sampled_frames: Sequence[SampledFrame],
        prompt: str,
        effective_duration_seconds: float,
    ) -> PreparedExample:
        """Decode and prepare one complete video input."""
        frames_tuple = tuple(sampled_frames)
        self._validate_manifest_frames(frames_tuple)
        decoded = self.decode_media(
            video_path, frames_tuple, effective_duration_seconds
        )
        return self.prepare_decoded_input(decoded, frames_tuple, prompt)

    def decode_media(
        self,
        video_path: Path,
        sampled_frames: Sequence[SampledFrame],
        effective_duration_seconds: float,
    ) -> DecodedMedia:
        """Decode one question's sampled frames and visible audio prefix."""
        frames_tuple = tuple(sampled_frames)
        self._validate_manifest_frames(frames_tuple)
        if (
            not isinstance(effective_duration_seconds, (int, float))
            or not math.isfinite(effective_duration_seconds)
            or effective_duration_seconds <= 0
        ):
            raise ValueError("effective duration must be finite and positive")
        if any(
            (
                frame.decoded_timestamp_seconds >= effective_duration_seconds
                for frame in frames_tuple
            )
        ):
            raise ValueError("sampled frame crosses the effective duration")
        decoded = self._media_decoder(
            video_path, frames_tuple, float(effective_duration_seconds)
        )
        if decoded.audio_sample_rate != 16000:
            raise RuntimeError(
                f"media decoder must return 16000 Hz audio, got {decoded.audio_sample_rate}"
            )
        maximum_samples = int(float(effective_duration_seconds) * 16000)
        if decoded.audio_waveform.size > maximum_samples:
            raise RuntimeError(
                f"decoded audio exceeds effective duration: samples={decoded.audio_waveform.size}, maximum={maximum_samples}"
            )
        if decoded.audio_waveform.size <= 0:
            raise RuntimeError("decoded visible audio prefix is empty")
        return decoded

    def decode_audio_prefix(
        self, video_path: Path, effective_duration_seconds: float
    ) -> np.ndarray:
        """Decode one complete visible mono 16 kHz waveform without video frames."""
        if not video_path.is_file():
            raise FileNotFoundError(f"video file does not exist: {video_path}")
        if (
            isinstance(effective_duration_seconds, bool)
            or not isinstance(effective_duration_seconds, (int, float))
            or (not math.isfinite(effective_duration_seconds))
            or (effective_duration_seconds <= 0)
        ):
            raise ValueError("effective duration must be finite and positive")
        try:
            import librosa
        except ImportError as error:
            raise RuntimeError("audio decoding requires librosa") from error
        (waveform, sample_rate) = librosa.load(
            str(video_path),
            sr=16000,
            mono=True,
            duration=float(effective_duration_seconds),
        )
        if sample_rate != 16000:
            raise RuntimeError(f"expected decoded audio at 16000 Hz, got {sample_rate}")
        maximum_samples = int(float(effective_duration_seconds) * 16000)
        result = np.ascontiguousarray(
            np.asarray(waveform, dtype=np.float32)[:maximum_samples], dtype=np.float32
        )
        if result.ndim != 1 or result.size <= 0:
            raise RuntimeError(f"source audio is missing or empty: {video_path}")
        if not np.isfinite(result).all():
            raise RuntimeError(
                f"source audio contains non-finite samples: {video_path}"
            )
        return result

    def _move_processor_data(self, data: object) -> MutableMapping[str, object]:
        if not isinstance(data, MutableMapping):
            raise RuntimeError("Realtime-Venus-Omni processor output must be a mutable mapping")
        if hasattr(data, "to"):
            moved = data.to(self.device)
            if moved is not None:
                data = moved
        return data

    def prepare_visual_chunk(
        self, images: Sequence[object], sampled_frames: Sequence[SampledFrame]
    ) -> PreparedVisualChunk:
        """Run image preprocessing for one bounded frame chunk."""
        frames_tuple = tuple(sampled_frames)
        images_tuple = tuple(images)
        self._validate_manifest_frame_chunk(frames_tuple)
        if len(images_tuple) != len(frames_tuple):
            raise ValueError("images must align with sampled_frames")
        content = "".join(("<image>./</image>" for _ in images_tuple))
        content += "Encode the provided visual frames."
        rendered = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": content}],
            tokenize=False,
            add_generation_prompt=True,
            use_tts_template=True,
            enable_thinking=False,
        )
        data = self.processor(
            [rendered],
            [list(images_tuple)],
            [[]],
            [[]],
            max_slice_nums=1,
            use_image_id=False,
            stream_input=False,
            return_tensors="pt",
            sampling_rate=16000,
            max_length=None,
        )
        return PreparedVisualChunk(
            data=self._move_processor_data(data), sampled_frames=frames_tuple
        )

    def prepare_audio_prefix(
        self, waveform: np.ndarray, sampled_frames: Sequence[SampledFrame]
    ) -> PreparedExample:
        """Run audio preprocessing once without materializing video images."""
        frames_tuple = tuple(sampled_frames)
        self._validate_manifest_frames(frames_tuple)
        audio = np.ascontiguousarray(np.asarray(waveform, dtype=np.float32))
        if audio.ndim != 1 or audio.size <= 0 or (not np.isfinite(audio).all()):
            raise ValueError("waveform must be finite non-empty mono float audio")
        audio_segments = self._split_audio_by_target_timestamps(audio, frames_tuple)
        audios = [segment.waveform for segment in audio_segments]
        content = "".join(("<audio>./</audio>" for _ in audios))
        content += "Encode the provided audio."
        rendered = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": content}],
            tokenize=False,
            add_generation_prompt=True,
            use_tts_template=True,
            enable_thinking=False,
        )
        data = self.processor(
            [rendered],
            [[]],
            [audios],
            [[0] * len(audios)],
            max_slice_nums=1,
            use_image_id=False,
            stream_input=False,
            return_tensors="pt",
            sampling_rate=16000,
            max_length=None,
        )
        data = self._move_processor_data(data)
        source_segment_sample_counts = tuple(
            (
                int(segment.end_sample - segment.start_sample)
                for segment in audio_segments
            )
        )
        processor_segment_sample_counts = tuple(
            (int(segment.waveform.size) for segment in audio_segments)
        )
        segment_token_counts = self._merged_audio_token_counts(
            self.processor, processor_segment_sample_counts, sample_rate=16000
        )
        repaired = self._repair_audio_placeholder_layout(data, segment_token_counts)
        projected = tuple(
            (index for (index, count) in enumerate(segment_token_counts) if count > 0)
        )
        zeros = tuple(
            (index for (index, count) in enumerate(segment_token_counts) if count == 0)
        )
        canonical = self._canonical_from_processor(
            data, expected_images=0, expected_audio_segments=len(projected)
        )
        metadata = AudioMetadata(
            source_sample_rate=16000,
            source_sample_count=int(audio.size),
            source_duration_seconds=float(audio.size / 16000),
            segment_sample_counts=tuple(
                (processor_segment_sample_counts[index] for index in projected)
            ),
            segment_start_seconds=tuple(
                (audio_segments[index].start_sample / 16000 for index in projected)
            ),
            segment_end_seconds=tuple(
                (audio_segments[index].end_sample / 16000 for index in projected)
            ),
            segment_frame_indices=tuple(
                (audio_segments[index].frame_index for index in projected)
            ),
            segment_token_counts=tuple(
                (segment_token_counts[index] for index in projected)
            ),
            placeholder_layout_repaired=repaired,
            source_segment_sample_counts=source_segment_sample_counts,
            processor_segment_sample_counts=processor_segment_sample_counts,
            processor_padding_sample_count=sum(processor_segment_sample_counts)
            - sum(source_segment_sample_counts),
            zero_token_segment_indices=zeros,
            zero_token_segment_sample_count=sum(
                (source_segment_sample_counts[index] for index in zeros)
            ),
        )
        return PreparedExample(
            data=data,
            canonical=canonical,
            sampled_frames=frames_tuple,
            rendered_prompt=str(rendered),
            audio_metadata=metadata,
        )

    def prepare_selected_canonical(
        self,
        *,
        modalities: Sequence[str],
        audio_token_counts: Sequence[int],
        prompt: str,
    ) -> CanonicalOmniInput:
        """Build a bounded placeholder layout without re-encoding media.

        Dummy media is used only to make the remote processor emit its exact chat
        control and boundary tokens. Audio placeholder lengths are then repaired
        to the already encoded blocks' projected-token counts. Pixel/audio
        features from this call are never moved to CUDA or passed to VPM/APM.
        """
        modality_tuple = tuple(modalities)
        if any((value not in {"visual", "audio"} for value in modality_tuple)):
            raise ValueError("modalities must contain only visual or audio")
        expected_audio = tuple((int(value) for value in audio_token_counts))
        if len(expected_audio) != modality_tuple.count("audio") or any(
            (value <= 0 for value in expected_audio)
        ):
            raise ValueError("audio_token_counts must align with audio modalities")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt must be a non-empty string")
        try:
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "selected canonical preparation requires Pillow"
            ) from error
        dummy_image = Image.new("RGB", (16, 16), color=(0, 0, 0))
        dummy_audio = np.zeros(160, dtype=np.float32)
        images: list[object] = []
        audios: list[np.ndarray] = []
        content_parts: list[str] = []
        for modality in modality_tuple:
            if modality == "visual":
                images.append(dummy_image)
                content_parts.append("<image>./</image>")
            else:
                audios.append(dummy_audio)
                content_parts.append("<audio>./</audio>")
        content_parts.append(prompt)
        rendered = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": "".join(content_parts)}],
            tokenize=False,
            add_generation_prompt=True,
            use_tts_template=True,
            enable_thinking=False,
        )
        data = self.processor(
            [rendered],
            [images],
            [audios],
            [[0] * len(audios)],
            max_slice_nums=1,
            use_image_id=False,
            stream_input=False,
            return_tensors="pt",
            sampling_rate=16000,
            max_length=None,
        )
        if not isinstance(data, MutableMapping):
            raise RuntimeError("Realtime-Venus-Omni processor output must be a mutable mapping")
        self._repair_audio_placeholder_layout(data, expected_audio)
        return self._canonical_from_processor(
            data, expected_images=len(images), expected_audio_segments=len(audios)
        )

    def _encode_conversation_images(
        self, images: Sequence[object]
    ) -> tuple[torch.Tensor, ...]:
        """Encode message images outside the video memory through the vision encoder."""
        image_tuple = tuple(images)
        if not image_tuple:
            return ()
        frames = tuple(
            (
                SampledFrame(
                    ordinal=index,
                    source_frame_index=index,
                    target_timestamp_seconds=float(index),
                    decoded_timestamp_seconds=float(index),
                    sampling_reason="official_msgs_context",
                )
                for index in range(len(image_tuple))
            )
        )
        store = self.encode_visual(self.prepare_visual_chunk(image_tuple, frames))
        return tuple((store.embeddings[index] for index in range(store.frame_count)))

    def _encode_conversation_audios(
        self, audios: Sequence[np.ndarray]
    ) -> tuple[torch.Tensor, ...]:
        """Encode reference audio separately from previously encoded memory audio."""
        encoded: list[torch.Tensor] = []
        frame = SampledFrame(
            ordinal=0,
            source_frame_index=0,
            target_timestamp_seconds=0.0,
            decoded_timestamp_seconds=0.0,
            sampling_reason="official_msgs_context",
        )
        for index, value in enumerate(audios):
            waveform = np.ascontiguousarray(np.asarray(value, dtype=np.float32))
            if (
                waveform.ndim != 1
                or waveform.size <= 0
                or (not np.isfinite(waveform).all())
            ):
                raise ValueError(
                    f"msgs audio item {index} must be finite non-empty mono audio"
                )
            prepared = self.prepare_audio_prefix(waveform, (frame,))
            blocks = self.encode_audio(prepared)
            if len(blocks) != 1:
                raise RuntimeError(
                    "one msgs audio item must produce exactly one repaired audio block"
                )
            encoded.append(blocks[0])
        return tuple(encoded)

    def prepare_selected_conversation(
        self,
        *,
        modalities: Sequence[str],
        memory_visual_frames: Sequence[tuple[tuple[int, ...], torch.Tensor]],
        memory_audio_embeddings: Sequence[torch.Tensor],
        prompt: str,
        prompt_context: Mapping[str, Any],
    ) -> PreparedSelectedConversation:
        """Preserve conversation messages while replacing video media with selected embeddings."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(prompt_context, Mapping):
            raise TypeError("prompt_context must be a mapping")
        messages = prompt_context.get("msgs")
        if (
            not isinstance(messages, Sequence)
            or isinstance(messages, (str, bytes))
            or (not messages)
        ):
            raise ValueError("prompt_context.msgs must be a non-empty sequence")
        slot_type = prompt_context.get("memory_media_slot_type")
        if not isinstance(slot_type, str) or not slot_type:
            raise ValueError("prompt_context must define memory_media_slot_type")
        modality_tuple = tuple(modalities)
        if any((value not in {"visual", "audio"} for value in modality_tuple)):
            raise ValueError("modalities must contain only visual or audio")
        memory_visual = tuple(memory_visual_frames)
        memory_audio = tuple(memory_audio_embeddings)
        if len(memory_visual) != modality_tuple.count("visual"):
            raise ValueError("memory visual frames must align with visual modalities")
        if len(memory_audio) != modality_tuple.count("audio"):
            raise ValueError("memory audio embeddings must align with audio modalities")
        try:
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "selected conversation preparation requires Pillow"
            ) from error
        dummy_image = Image.new("RGB", (16, 16), color=(0, 0, 0))
        dummy_audio = np.zeros(16000, dtype=np.float32)
        external_images: list[object] = []
        external_audios: list[np.ndarray] = []
        image_sources: list[tuple[str, int]] = []
        audio_sources: list[tuple[str, int]] = []
        processor_images: list[object] = []
        processor_audios: list[np.ndarray] = []
        audio_parts: list[int] = []
        rendered_messages: list[dict[str, Any]] = []
        memory_slot_count = 0
        memory_visual_index = 0
        memory_audio_index = 0
        omni_mode = bool(prompt_context.get("omni_mode", False))
        separator = "" if omni_mode else "\n"
        for message_index, source_message in enumerate(messages):
            if not isinstance(source_message, Mapping):
                raise TypeError("each prompt_context message must be a mapping")
            role = source_message.get("role")
            if role not in {"system", "user", "assistant"}:
                raise ValueError(f"unsupported Chat role: {role!r}")
            content = source_message.get("content")
            if isinstance(content, str):
                items = (content,)
            elif isinstance(content, Sequence) and (
                not isinstance(content, (str, bytes))
            ):
                items = tuple(content)
            else:
                raise TypeError("message content must be text or a content sequence")
            parts: list[str] = []
            for item in items:
                if isinstance(item, Mapping) and item.get("type") == slot_type:
                    memory_slot_count += 1
                    for modality in modality_tuple:
                        if modality == "visual":
                            processor_images.append(dummy_image)
                            image_sources.append(("memory", memory_visual_index))
                            memory_visual_index += 1
                            parts.append("<image>./</image>")
                        else:
                            processor_audios.append(dummy_audio)
                            audio_parts.append(message_index)
                            audio_sources.append(("memory", memory_audio_index))
                            memory_audio_index += 1
                            parts.append("<audio>./</audio>")
                elif isinstance(item, Image.Image):
                    external_index = len(external_images)
                    external_images.append(item)
                    processor_images.append(dummy_image)
                    image_sources.append(("external", external_index))
                    parts.append("<image>./</image>")
                elif isinstance(item, np.ndarray):
                    external_index = len(external_audios)
                    external_audios.append(item)
                    processor_audios.append(dummy_audio)
                    audio_parts.append(message_index)
                    audio_sources.append(("external", external_index))
                    parts.append("<audio>./</audio>")
                elif isinstance(item, str):
                    parts.append(item)
                else:
                    raise TypeError(
                        f"unsupported preserved msgs content item: {type(item).__name__}"
                    )
            rendered_messages.append({"role": role, "content": separator.join(parts)})
        if memory_slot_count != 1:
            raise RuntimeError(
                "complete msgs must contain exactly one Memory media insertion slot"
            )
        if memory_visual_index != len(memory_visual) or memory_audio_index != len(
            memory_audio
        ):
            raise RuntimeError(
                "not every selected Memory embedding reached the msgs slot"
            )
        external_visual_embeddings = self._encode_conversation_images(external_images)
        external_audio_embeddings = self._encode_conversation_audios(external_audios)
        visual_frames: list[tuple[tuple[int, ...], torch.Tensor]] = []
        for source, index in image_sources:
            if source == "memory":
                visual_frames.append(memory_visual[index])
            else:
                visual_frames.append(
                    (tuple(range(64)), external_visual_embeddings[index])
                )
        audio_embeddings = tuple(
            (
                (
                    memory_audio[index]
                    if source == "memory"
                    else external_audio_embeddings[index]
                )
                for (source, index) in audio_sources
            )
        )
        use_tts_template = bool(prompt_context.get("use_tts_template", False))
        if processor_audios:
            use_tts_template = True
        rendered_prompt = self.tokenizer.apply_chat_template(
            rendered_messages,
            tokenize=False,
            add_generation_prompt=True,
            use_tts_template=use_tts_template,
            enable_thinking=bool(prompt_context.get("enable_thinking", False)),
        )
        processor_audio_parts = (
            [audio_parts]
            if bool(prompt_context.get("merge_audio_from_same_content", True))
            else None
        )
        data = self.processor(
            [rendered_prompt],
            [processor_images],
            [processor_audios],
            processor_audio_parts,
            max_slice_nums=1,
            use_image_id=prompt_context.get("use_image_id"),
            stream_input=False,
            return_tensors="pt",
            sampling_rate=16000,
            max_length=None,
        )
        if not isinstance(data, MutableMapping):
            raise RuntimeError("Realtime-Venus-Omni processor output must be a mutable mapping")
        self._repair_audio_placeholder_layout(
            data, tuple((int(item.shape[0]) for item in audio_embeddings))
        )
        canonical = self._canonical_from_processor(
            data,
            expected_images=len(visual_frames),
            expected_audio_segments=len(audio_embeddings),
        )
        requested_limit = prompt_context.get("max_input_length", self.max_input_length)
        if (
            isinstance(requested_limit, bool)
            or not isinstance(requested_limit, int)
            or requested_limit <= 0
        ):
            raise ValueError("max_inp_length must be a positive integer")
        canonical = replace(
            canonical, max_input_length=min(self.max_input_length, requested_limit)
        )
        return PreparedSelectedConversation(
            canonical=canonical,
            visual_frames=tuple(visual_frames),
            audio_embeddings=audio_embeddings,
            rendered_prompt=str(rendered_prompt),
        )

    def prepare_decoded_input(
        self, decoded: DecodedMedia, sampled_frames: Sequence[SampledFrame], prompt: str
    ) -> PreparedExample:
        """Build a question-specific processor sequence from reusable decoded media."""
        frames_tuple = tuple(sampled_frames)
        self._validate_manifest_frames(frames_tuple)
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt must be a non-empty string")
        if decoded.audio_sample_rate != 16000:
            raise RuntimeError(
                f"media decoder must return 16000 Hz audio, got {decoded.audio_sample_rate}"
            )
        if len(decoded.frames) != len(frames_tuple):
            raise RuntimeError(
                f"decoded {len(decoded.frames)} frames for {len(frames_tuple)} manifest entries"
            )
        audio_segments = self._split_audio_by_target_timestamps(
            decoded.audio_waveform, frames_tuple
        )
        events: list[tuple[float, int, int, object]] = []
        events.extend(
            (
                (frame.target_timestamp_seconds, 0, index, decoded.frames[index])
                for (index, frame) in enumerate(frames_tuple)
            )
        )
        events.extend(
            (
                (segment.start_sample / 16000, 1, index, segment.waveform)
                for (index, segment) in enumerate(audio_segments)
            )
        )
        events.sort(key=lambda item: (item[0], item[1], item[2]))
        content_parts: list[str] = []
        images: list[object] = []
        audios: list[np.ndarray] = []
        for _, kind, _, payload in events:
            if kind == 0:
                images.append(payload)
                content_parts.append("<image>./</image>")
            else:
                audios.append(payload)
                content_parts.append("<audio>./</audio>")
        content_parts.append(prompt)
        messages = [{"role": "user", "content": "".join(content_parts)}]
        rendered_prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            use_tts_template=True,
            enable_thinking=False,
        )
        data = self.processor(
            [rendered_prompt],
            [images],
            [audios],
            [[0] * len(audios)],
            max_slice_nums=1,
            use_image_id=False,
            stream_input=False,
            return_tensors="pt",
            sampling_rate=16000,
            max_length=None,
        )
        if not isinstance(data, MutableMapping):
            raise RuntimeError("Realtime-Venus-Omni processor output must be a mutable mapping")
        source_segment_sample_counts = tuple(
            (
                int(segment.end_sample - segment.start_sample)
                for segment in audio_segments
            )
        )
        processor_segment_sample_counts = tuple(
            (int(segment.waveform.size) for segment in audio_segments)
        )
        segment_token_counts = self._merged_audio_token_counts(
            self.processor, processor_segment_sample_counts, sample_rate=16000
        )
        placeholder_layout_repaired = self._repair_audio_placeholder_layout(
            data, segment_token_counts
        )
        projected_segment_indices = tuple(
            (index for (index, count) in enumerate(segment_token_counts) if count > 0)
        )
        zero_token_segment_indices = tuple(
            (index for (index, count) in enumerate(segment_token_counts) if count == 0)
        )
        if hasattr(data, "to"):
            moved = data.to(self.device)
            if moved is not None:
                data = moved
        canonical = self._canonical_from_processor(
            data,
            expected_images=len(images),
            expected_audio_segments=len(projected_segment_indices),
        )
        metadata = AudioMetadata(
            source_sample_rate=16000,
            source_sample_count=int(decoded.audio_waveform.size),
            source_duration_seconds=float(decoded.audio_waveform.size / 16000),
            segment_sample_counts=tuple(
                (
                    processor_segment_sample_counts[index]
                    for index in projected_segment_indices
                )
            ),
            segment_start_seconds=tuple(
                (
                    audio_segments[index].start_sample / 16000
                    for index in projected_segment_indices
                )
            ),
            segment_end_seconds=tuple(
                (
                    audio_segments[index].end_sample / 16000
                    for index in projected_segment_indices
                )
            ),
            segment_frame_indices=tuple(
                (
                    audio_segments[index].frame_index
                    for index in projected_segment_indices
                )
            ),
            segment_token_counts=tuple(
                (segment_token_counts[index] for index in projected_segment_indices)
            ),
            placeholder_layout_repaired=placeholder_layout_repaired,
            source_segment_sample_counts=source_segment_sample_counts,
            processor_segment_sample_counts=processor_segment_sample_counts,
            processor_padding_sample_count=sum(processor_segment_sample_counts)
            - sum(source_segment_sample_counts),
            zero_token_segment_indices=zero_token_segment_indices,
            zero_token_segment_sample_count=sum(
                (
                    source_segment_sample_counts[index]
                    for index in zero_token_segment_indices
                )
            ),
        )
        return PreparedExample(
            data=data,
            canonical=canonical,
            sampled_frames=frames_tuple,
            rendered_prompt=str(rendered_prompt),
            audio_metadata=metadata,
        )

    def _canonical_from_processor(
        self,
        data: Mapping[str, object],
        expected_images: int,
        expected_audio_segments: int,
    ) -> CanonicalOmniInput:
        input_ids = data.get("input_ids")
        attention_mask = data.get("attention_mask")
        if (
            not isinstance(input_ids, torch.Tensor)
            or input_ids.ndim != 2
            or input_ids.shape[0] != 1
        ):
            raise RuntimeError("processor input_ids must have shape [1,L]")
        if (
            not isinstance(attention_mask, torch.Tensor)
            or attention_mask.shape != input_ids.shape
        ):
            raise RuntimeError("processor attention_mask must match input_ids")
        if not attention_mask.to(dtype=torch.bool).all():
            raise RuntimeError(
                "batch-size-one processor output must not contain padding"
            )
        sequence_length = input_ids.shape[1]
        image_bounds = _as_batch_tensor(data.get("image_bound"), "image_bound")
        audio_bounds = _as_batch_tensor(data.get("audio_bounds"), "audio_bounds")
        if image_bounds.ndim != 2 or image_bounds.shape[1:] != (2,):
            raise RuntimeError("processor image_bound must have shape [F,2]")
        if audio_bounds.ndim != 2 or audio_bounds.shape[1:] != (2,):
            raise RuntimeError("processor audio_bounds must have shape [A,2]")
        if image_bounds.shape[0] != expected_images:
            raise RuntimeError(
                f"processor produced {image_bounds.shape[0]} image blocks for {expected_images} decoded frames"
            )
        if audio_bounds.shape[0] != expected_audio_segments:
            raise RuntimeError(
                f"processor produced {audio_bounds.shape[0]} audio blocks for {expected_audio_segments} complete-audio segments"
            )
        lengths = image_bounds[:, 1] - image_bounds[:, 0]
        if not torch.all(lengths == 64):
            raise RuntimeError(
                f"expected every image block to contain 64 tokens, got {lengths.tolist()}"
            )
        tokenizer = self.tokenizer
        start_ids = {int(tokenizer.im_start_id), int(tokenizer.slice_start_id)}
        end_ids = {int(tokenizer.im_end_id), int(tokenizer.slice_end_id)}
        image_spans: list[tuple[int, int]] = []
        for index, (start, end) in enumerate(image_bounds.detach().cpu().tolist()):
            (block_start, block_end) = (start - 1, end + 1)
            if block_start < 0 or block_end > sequence_length:
                raise RuntimeError(f"image block {index} markers are out of range")
            if int(input_ids[0, block_start]) not in start_ids:
                raise RuntimeError(f"image block {index} is missing its start marker")
            if int(input_ids[0, end]) not in end_ids:
                raise RuntimeError(f"image block {index} is missing its end marker")
            image_spans.append((block_start, block_end))
        for index, (start, end) in enumerate(audio_bounds.detach().cpu().tolist()):
            if start <= 0 or end >= sequence_length:
                raise RuntimeError(f"audio block {index} markers are out of range")
            if int(input_ids[0, start - 1]) != int(tokenizer.audio_start_id):
                raise RuntimeError(f"audio block {index} is missing its start marker")
            if int(input_ids[0, end]) != int(tokenizer.audio_end_id):
                raise RuntimeError(f"audio block {index} is missing its end marker")
        return CanonicalOmniInput(
            input_ids=input_ids,
            image_bounds=image_bounds.to(device=input_ids.device, dtype=torch.long),
            audio_bounds=audio_bounds.to(device=input_ids.device, dtype=torch.long),
            image_block_spans=tuple(image_spans),
            max_input_length=self.max_input_length,
        )

    @torch.inference_mode()
    def encode_visual(
        self, prepared: PreparedExample | PreparedVisualChunk
    ) -> FrameTokenStore:
        """Return the VPM→Resampler outputs in manifest order."""
        result = self.model.get_vision_embedding(prepared.data)
        if not isinstance(result, Sequence) or len(result) != 1:
            raise RuntimeError("get_vision_embedding must return one batch item")
        embeddings = result[0]
        if not isinstance(embeddings, torch.Tensor):
            raise RuntimeError("get_vision_embedding batch item must be a tensor")
        expected_frames = len(prepared.sampled_frames)
        if embeddings.ndim != 3 or embeddings.shape[:2] != (expected_frames, 64):
            raise RuntimeError(
                f"expected [F,64,D] Resampler output with F={expected_frames}, got {tuple(embeddings.shape)}"
            )
        expected_hidden_size = int(self.model.llm.model.embed_tokens.weight.shape[1])
        if embeddings.shape[2] != expected_hidden_size:
            raise RuntimeError(
                f"Resampler hidden size {embeddings.shape[2]} does not match LLM hidden size {expected_hidden_size}"
            )
        timestamps = torch.tensor(
            [frame.target_timestamp_seconds for frame in prepared.sampled_frames],
            dtype=torch.float32,
            device=embeddings.device,
        )
        source_indices = torch.tensor(
            [frame.source_frame_index for frame in prepared.sampled_frames],
            dtype=torch.long,
            device=embeddings.device,
        )
        return FrameTokenStore(embeddings, timestamps, source_indices)

    @torch.inference_mode()
    def encode_audio(self, prepared: PreparedExample) -> tuple[torch.Tensor, ...]:
        """Map audio chunks back to the processor's original audio bounds."""
        chunk_length = getattr(self.model.config, "audio_chunk_length", -1)
        result = self.model.get_audio_embedding(
            prepared.data, chunk_length=chunk_length
        )
        if not isinstance(result, Sequence) or len(result) != 1:
            raise RuntimeError("get_audio_embedding must return one batch item")
        chunks = result[0]
        if not isinstance(chunks, Sequence) or not chunks:
            raise RuntimeError(
                "get_audio_embedding returned no complete-audio embeddings"
            )
        if any(
            (
                not isinstance(chunk, torch.Tensor)
                or chunk.ndim != 2
                or chunk.shape[0] <= 0
                for chunk in chunks
            )
        ):
            raise RuntimeError("every audio embedding chunk must have shape [T,D]")
        expected_hidden_size = int(self.model.llm.model.embed_tokens.weight.shape[1])
        if any((chunk.shape[1] != expected_hidden_size for chunk in chunks)):
            raise RuntimeError(
                f"audio embedding hidden size does not match LLM hidden size {expected_hidden_size}"
            )
        chunk_tuple = tuple(chunks)
        bound_lengths = [
            int(end - start)
            for (start, end) in prepared.canonical.audio_bounds.detach().cpu().tolist()
        ]
        total_chunk_tokens = sum((int(chunk.shape[0]) for chunk in chunk_tuple))
        if total_chunk_tokens != sum(bound_lengths):
            raise RuntimeError(
                f"audio embedding length {total_chunk_tokens} does not match processor bounds total {sum(bound_lengths)}"
            )
        remapped: list[torch.Tensor] = []
        chunk_index = 0
        chunk_offset = 0
        for length in bound_lengths:
            remaining = length
            parts: list[torch.Tensor] = []
            while remaining > 0:
                chunk = chunk_tuple[chunk_index]
                available = int(chunk.shape[0]) - chunk_offset
                take = min(remaining, available)
                parts.append(chunk[chunk_offset : chunk_offset + take])
                chunk_offset += take
                remaining -= take
                if chunk_offset == chunk.shape[0]:
                    chunk_index += 1
                    chunk_offset = 0
            remapped.append(parts[0] if len(parts) == 1 else torch.cat(parts, dim=0))
        return tuple(remapped)

    @torch.inference_mode()
    def generate(
        self, assembled: AssembledInput, generation: Mapping[str, object]
    ) -> str:
        """Generate from custom embeddings through the text decode path."""
        kwargs: dict[str, Any] = dict(generation)
        if kwargs.pop("generate_audio", False):
            raise ValueError("generate_audio must remain false in complete-media Chat")
        kwargs.pop("enable_thinking", None)
        reserved = {
            "inputs_embeds",
            "attention_mask",
            "pad_token_id",
            "eos_token_id",
            "output_hidden_states",
            "return_dict_in_generate",
        }
        overlap = reserved.intersection(kwargs)
        if overlap:
            raise ValueError(
                f"generation cannot override reserved keys: {sorted(overlap)}"
            )
        do_sample = kwargs.pop("do_sample", False)
        max_new_tokens = kwargs.pop("max_new_tokens", 50)
        min_new_tokens = kwargs.pop("min_new_tokens", 0)
        official_kwargs = self.model.prepare_generation_config(
            do_sample=do_sample,
            max_new_tokens=max_new_tokens,
            min_new_tokens=min_new_tokens,
            **kwargs,
        )
        if not isinstance(official_kwargs, Mapping):
            raise RuntimeError("prepare_generation_config must return a mapping")
        official_kwargs = dict(official_kwargs)
        overlap = reserved.intersection(official_kwargs)
        if overlap:
            raise RuntimeError(
                f"official generation config contains reserved keys: {sorted(overlap)}"
            )
        outputs = self.model._decode(
            assembled.inputs_embeds,
            self.tokenizer,
            assembled.attention_mask,
            **official_kwargs,
        )
        sequences = getattr(outputs, "sequences", None)
        if (
            not isinstance(sequences, torch.Tensor)
            or sequences.ndim != 2
            or sequences.shape[0] != 1
        ):
            raise RuntimeError("official _decode() must return one sequences tensor")
        decoded = self.model._decode_text(sequences, self.tokenizer)
        if (
            not isinstance(decoded, Sequence)
            or isinstance(decoded, (str, bytes))
            or len(decoded) != 1
            or (not isinstance(decoded[0], str))
        ):
            raise RuntimeError("official _decode_text() must return one text string")
        return decoded[0].split("<|tts_eos|>", 1)[0]
