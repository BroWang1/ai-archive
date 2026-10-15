"""Greedy Step5 inference over pre-sharded tensor-parallel weights.

This standalone entry point loads one ``model-r{rank}.safetensors`` file per
``torchrun`` process and uses :meth:`Step5ForCausalLM.generate_greedy`, whose
vocabulary-parallel selection all-gathers every rank's contiguous vocabulary
window before taking argmax.

Example::

    torchrun --standalone --nproc-per-node=8 inference/generate.py \
        --tp-dir /path/to/step5_tp8/tp8 \
        --ep-size 8 \
        --checkpoint /path/to/original_step5_checkpoint \
        --prompt "请介绍一下张量并行。" \
        --max-new-tokens 128

``--prompt-json`` accepts either a JSON list of token ids or an object containing
``prompt_ids``.  This bypasses tokenization entirely and is useful for exact
parity runs. ``--prompt-json-batch`` accepts either a JSON list of token-id
lists or ``{"prompts": [{"prompt_ids": [...]}, ...]}`` and sends the packed
batch through one ``generate_greedy`` call. Multi-request output is
``{"batch_size": N, "results": [...]}``; a one-request batch retains the
original single-request JSON shape. The original checkpoint is only a tokenizer
source here; model weights always come from ``--tp-dir``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

import torch
import torch.distributed as dist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tp-dir",
        required=True,
        help="Directory containing config-rN.json and model-rN.safetensors.",
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument(
        "--prompt",
        help="User prompt text. A one-turn chat template is applied by default.",
    )
    prompt_group.add_argument(
        "--prompt-json",
        help="JSON list of exact token ids, or an object containing `prompt_ids`.",
    )
    prompt_group.add_argument(
        "--prompt-json-batch",
        help="Packed-batch JSON: either a list of token-id lists or an object "
        "containing `prompts`, whose entries contain `prompt_ids`.",
    )
    parser.add_argument(
        "--tokenizer",
        "--tokenizer-path",
        dest="tokenizer",
        default=None,
        help="Local tokenizer directory. Overrides --checkpoint.",
    )
    parser.add_argument(
        "--checkpoint",
        "--ckpt-path",
        dest="checkpoint",
        default=None,
        help="Original local Step5 checkpoint directory used as the tokenizer "
        "source. TP model weights are still loaded only from --tp-dir.",
    )
    parser.add_argument(
        "--image-inputs",
        help="Local safetensors containing pixel_values, optional patch_pixel_values/num_patches, "
             "or already projected image_embeds. Use with exact prompt IDs containing image placeholders.",
    )
    parser.add_argument(
        "--raw-prompt",
        action="store_true",
        help="Tokenize --prompt as plain text instead of applying the chat template.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=128,
        help="Maximum number of greedily decoded tokens (default: 128).",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="Device type/string; torchrun normally uses cuda (default: cuda).",
    )
    parser.add_argument(
        "--ep-size",
        "--expert-parallel-size",
        dest="ep_size",
        type=int,
        default=8,
        help="Routed-expert sharding degree (default: 8). The current "
        "co-located topology requires EP size to equal TP/world size.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_new_tokens < 0:
        parser.error("--max-new-tokens must be non-negative")
    if args.ep_size < 1:
        parser.error("--ep-size must be positive")
    if args.raw_prompt and args.prompt is None:
        parser.error("--raw-prompt is only valid with --prompt")
    if args.image_inputs and args.prompt is not None:
        parser.error("--image-inputs requires --prompt-json or --prompt-json-batch")
    return args


def validate_parallel_topology(
    config: Any,
    *,
    world: int,
    requested_ep_size: int,
    rank: int = 0,
) -> int:
    """Validate and return the co-located expert-parallel size.

    Older validated TP shards predate the explicit
    ``expert_parallel_size`` metadata, so its only supported fallback is the
    checkpoint TP size. Values read from JSON are checked without coercion:
    accepting (for example) ``8.9`` as EP=8 would defeat the fail-closed
    topology contract.
    """
    config_tp_size = getattr(config, "tp_size", None)
    if (
        isinstance(config_tp_size, bool)
        or not isinstance(config_tp_size, int)
        or config_tp_size < 1
    ):
        raise RuntimeError(
            f"rank {rank}: checkpoint tp_size must be a positive integer, "
            f"got {config_tp_size!r}"
        )
    if config_tp_size != world:
        raise RuntimeError(
            f"rank {rank}: checkpoint TP={config_tp_size}, "
            f"torchrun world size={world}"
        )

    config_ep_size = getattr(config, "expert_parallel_size", config_tp_size)
    if (
        isinstance(config_ep_size, bool)
        or not isinstance(config_ep_size, int)
        or config_ep_size < 1
    ):
        raise RuntimeError(
            "checkpoint expert_parallel_size must be a positive integer, "
            f"got {config_ep_size!r}"
        )
    if config_ep_size != config_tp_size:
        raise RuntimeError(
            "independent TP and EP groups are not implemented: checkpoint "
            f"EP={config_ep_size} must equal TP={config_tp_size}"
        )
    if requested_ep_size != config_ep_size:
        raise RuntimeError(
            f"--ep-size={requested_ep_size} does not match checkpoint/runtime "
            f"EP={config_ep_size}. This release co-locates TP and EP on the "
            "same ranks."
        )
    return config_ep_size


def load_prompt_json(path: str | os.PathLike[str]) -> list[int]:
    """Load and validate the exact token ids in a parity prompt artifact."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    values = payload.get("prompt_ids") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError(
            f"prompt JSON {path} must be a list or an object containing a `prompt_ids` list"
        )
    if not values:
        raise ValueError(f"prompt JSON {path} contains no token ids")

    prompt_ids: list[int] = []
    for index, value in enumerate(values):
        # JSON bool is an int subclass in Python, but never a meaningful token id.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"prompt JSON {path} token {index} is not an integer: {value!r}"
            )
        if value < 0:
            raise ValueError(
                f"prompt JSON {path} token {index} is negative: {value}"
            )
        prompt_ids.append(value)
    return prompt_ids


def load_prompt_json_batch(path: str | os.PathLike[str]) -> list[list[int]]:
    """Load exact token ids for a packed batch.

    Accepted schemas are either ``[[1, 2], [3, 4, 5]]`` or
    ``{"prompts": [{"prompt_ids": [1, 2]}, {"prompt_ids": [3, 4, 5]}]}``.
    Empty batches and empty requests are rejected because neither can be
    represented by the packed model/cache contract.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    object_schema = isinstance(payload, dict)
    prompts = payload.get("prompts") if object_schema else payload
    if not isinstance(prompts, list):
        raise ValueError(
            f"prompt batch JSON {path} must be a list of lists or an object "
            "containing a `prompts` list"
        )
    if not prompts:
        raise ValueError(f"prompt batch JSON {path} contains no prompts")

    batch: list[list[int]] = []
    for prompt_index, prompt in enumerate(prompts):
        if object_schema:
            if not isinstance(prompt, dict):
                raise ValueError(
                    f"prompt batch JSON {path} prompt {prompt_index} must be "
                    "an object containing `prompt_ids`"
                )
            values = prompt.get("prompt_ids")
        else:
            values = prompt
        if not isinstance(values, list):
            raise ValueError(
                f"prompt batch JSON {path} prompt {prompt_index} must contain "
                f"a token-id list"
            )
        if not values:
            raise ValueError(
                f"prompt batch JSON {path} prompt {prompt_index} contains no token ids"
            )

        prompt_ids: list[int] = []
        for token_index, value in enumerate(values):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"prompt batch JSON {path} prompt {prompt_index} token "
                    f"{token_index} is not an integer: {value!r}"
                )
            if value < 0:
                raise ValueError(
                    f"prompt batch JSON {path} prompt {prompt_index} token "
                    f"{token_index} is negative: {value}"
                )
            prompt_ids.append(value)
        batch.append(prompt_ids)
    return batch


def resolve_tokenizer_source(
    *,
    tp_dir: str | os.PathLike[str],
    tokenizer: str | None,
    checkpoint: str | None,
) -> str | None:
    """Resolve explicit tokenizer options, then the pre-shard default layout.

    ``convert.py`` writes weights under ``OUT/tp8`` and tokenizer assets under
    ``OUT/tokenizer_files``. Explicit values are local directories and are
    returned here before the loader validates their tokenizer files.
    """
    if tokenizer:
        return tokenizer
    if checkpoint:
        return checkpoint

    tp_path = Path(tp_dir).expanduser()
    candidates = (
        tp_path / "tokenizer_files",
        tp_path.parent / "tokenizer_files",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return str(candidate)
    return None


def tokenize_text(tokenizer: Any, text: str, *, raw_prompt: bool) -> list[int]:
    """Tokenize one prompt using the checkpoint's chat template or raw text."""
    if raw_prompt:
        encoded = tokenizer(text, add_special_tokens=True)
        values = encoded.input_ids
    else:
        values = tokenizer.apply_chat_template(
            [{"role": "user", "content": text}],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=False,
        )
    if hasattr(values, "input_ids"):
        values = values.input_ids
    elif isinstance(values, dict) and "input_ids" in values:
        values = values["input_ids"]
    if hasattr(values, "ids"):
        values = values.ids
    if isinstance(values, list) and len(values) == 1 and isinstance(values[0], list):
        values = values[0]
    if isinstance(values, torch.Tensor):
        values = values.reshape(-1).tolist()
    if not isinstance(values, list):
        raise TypeError(
            "tokenizer returned unsupported token IDs: "
            f"{type(values).__name__}"
        )
    prompt_ids = [int(token) for token in values]
    if not prompt_ids:
        raise ValueError("tokenizer produced an empty prompt")
    if any(token < 0 for token in prompt_ids):
        raise ValueError("tokenizer produced a negative token id")
    return prompt_ids


def validate_prompt_ids(
    prompt_ids: Sequence[int],
    *,
    vocab_size: int,
    max_position_embeddings: int,
    max_new_tokens: int,
    image_token_id: int | None = None,
) -> None:
    if not prompt_ids:
        raise ValueError("prompt must contain at least one token")
    for index, token in enumerate(prompt_ids):
        if token < 0 or (token >= vocab_size and token != image_token_id):
            raise ValueError(
                f"prompt token {index}={token} is outside vocabulary [0, {vocab_size})"
            )
    requested = len(prompt_ids) + max_new_tokens
    if requested > max_position_embeddings:
        raise ValueError(
            f"prompt ({len(prompt_ids)} tokens) + completion ({max_new_tokens}) "
            f"exceeds max_position_embeddings={max_position_embeddings}"
        )


def _load_rank_config(tp_dir: str, rank: int):
    # Lazy imports keep parser/helper tests independent of transformers and Triton.
    from model import config_from_dict

    path = Path(tp_dir) / f"config-r{rank}.json"
    if not path.is_file():
        raise FileNotFoundError(f"rank {rank}: missing TP config {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return config_from_dict(payload)


def _load_tokenizer(source: str, *, require_chat_template: bool = False):
    source_path = Path(source).expanduser()
    if not source_path.is_dir():
        raise FileNotFoundError(
            f"tokenizer source must be a local directory: {source_path}"
        )
    required_files = (
        "tokenizer.json",
        "tokenizer_config.json",
    )
    missing = [
        name for name in required_files if not (source_path / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"tokenizer source is missing required file(s): "
            f"{', '.join(missing)}"
        )

    from transformers import PreTrainedTokenizerFast

    # Load Step-5's serialized fast tokenizer directly. Automatic class selection
    # in Transformers 5.15 can collapse long byte-level BPE prompts. The generic
    # fast loader preserves the tokenizer.json model, pre-tokenizer, and decoder
    # and is ID-identical to the validated Transformers 4.57.6 loader.
    tokenizer = PreTrainedTokenizerFast.from_pretrained(
        str(source_path),
        trust_remote_code=True,
        local_files_only=True,
    )
    if require_chat_template and not getattr(tokenizer, "chat_template", None):
        raise ValueError(
            "tokenizer has no chat template; define `chat_template` in "
            "tokenizer_config.json or provide chat_template.jinja"
        )
    return tokenizer


def _load_exact_id_tokenizer(
    source: str | None,
    *,
    explicit_source: bool,
):
    """Optionally load the tokenizer used only to decode exact-ID completions."""
    if source is None:
        return None
    try:
        return _load_tokenizer(source, require_chat_template=False)
    except FileNotFoundError:
        if explicit_source:
            raise
        return None


def resolve_generation_eos_token_ids(
    config_eos_token_id: Any,
    tokenizer: Any | None,
) -> set[int]:
    """Union checkpoint and tokenizer EOS ids for production stopping.

    Step5's converted TP config can retain base-model EOS ids while the chat
    tokenizer terminates assistant turns with a different ``<|im_end|>`` id.
    Passing only the config values to ``generate_greedy`` would continue past
    the tokenizer's real end-of-turn marker.  Keep both sets rather than
    replacing either source.
    """

    result: set[int] = set()

    def add(value: Any, *, label: str) -> None:
        if value is None:
            return
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for token in values:
            if isinstance(token, bool) or not isinstance(token, int) or token < 0:
                raise ValueError(
                    f"{label} must contain non-negative integer token ids, "
                    f"got {token!r}"
                )
            result.add(int(token))

    add(config_eos_token_id, label="config eos_token_id")
    if tokenizer is not None:
        add(
            getattr(tokenizer, "eos_token_id", None),
            label="tokenizer eos_token_id",
        )
    if not result:
        raise ValueError("generation has no EOS token ids")
    return result


def _broadcast_error(error: str | None, *, device: torch.device) -> None:
    """Make a rank-0 prompt preparation error visible before any peer blocks."""
    payload: list[str | None] = [error]
    kwargs: dict[str, Any] = {}
    if device.type == "cuda":
        kwargs["device"] = device
    dist.broadcast_object_list(payload, src=0, **kwargs)
    if payload[0] is not None:
        raise RuntimeError(f"rank 0 failed to prepare the prompt: {payload[0]}")


def broadcast_eos_token_ids(
    eos_token_ids: set[int] | None,
    *,
    rank: int,
    device: torch.device,
) -> set[int]:
    """Broadcast rank 0's effective config+tokenizer EOS set to every TP rank."""

    if rank == 0:
        if not eos_token_ids:
            raise ValueError("rank 0 must provide at least one EOS token id")
        values = sorted(eos_token_ids)
        length = torch.tensor([len(values)], dtype=torch.int64, device=device)
    else:
        values = []
        length = torch.zeros(1, dtype=torch.int64, device=device)
    dist.broadcast(length, src=0)
    count = int(length.item())
    if count <= 0:
        raise ValueError(f"broadcast EOS set has invalid length {count}")
    if rank == 0:
        tokens = torch.tensor(values, dtype=torch.int64, device=device)
    else:
        tokens = torch.empty(count, dtype=torch.int64, device=device)
    dist.broadcast(tokens, src=0)
    result = {int(token) for token in tokens.cpu().tolist()}
    if len(result) != count or any(token < 0 for token in result):
        raise ValueError(f"broadcast EOS set is invalid: {sorted(result)}")
    return result


def broadcast_prompt_ids(
    prompt_ids: Sequence[int] | None,
    *,
    rank: int,
    device: torch.device,
) -> list[int]:
    """Broadcast a variable-length rank-0 prompt with tensor collectives."""
    if rank == 0:
        if prompt_ids is None:
            raise ValueError("rank 0 must provide prompt ids")
        length = torch.tensor([len(prompt_ids)], dtype=torch.int64, device=device)
    else:
        length = torch.zeros(1, dtype=torch.int64, device=device)
    dist.broadcast(length, src=0)
    token_count = int(length.item())
    if token_count <= 0:
        raise ValueError(f"broadcast prompt has invalid length {token_count}")

    if rank == 0:
        tokens = torch.tensor(prompt_ids, dtype=torch.long, device=device)
    else:
        tokens = torch.empty(token_count, dtype=torch.long, device=device)
    dist.broadcast(tokens, src=0)
    return [int(token) for token in tokens.cpu().tolist()]


def broadcast_prompt_batch(
    prompt_batch: Sequence[Sequence[int]] | None,
    *,
    rank: int,
    device: torch.device,
) -> list[list[int]]:
    """Broadcast rank 0's packed batch as lengths plus one flat token tensor."""
    if rank == 0:
        if prompt_batch is None:
            raise ValueError("rank 0 must provide a prompt batch")
        batch_size = len(prompt_batch)
        batch_size_tensor = torch.tensor(
            [batch_size], dtype=torch.int64, device=device
        )
    else:
        batch_size_tensor = torch.zeros(1, dtype=torch.int64, device=device)
    dist.broadcast(batch_size_tensor, src=0)
    batch_size = int(batch_size_tensor.item())
    if batch_size <= 0:
        raise ValueError(f"broadcast prompt batch has invalid size {batch_size}")

    if rank == 0:
        assert prompt_batch is not None
        lengths = torch.tensor(
            [len(prompt) for prompt in prompt_batch],
            dtype=torch.int64,
            device=device,
        )
    else:
        lengths = torch.empty(batch_size, dtype=torch.int64, device=device)
    dist.broadcast(lengths, src=0)
    if bool((lengths <= 0).any().item()):
        raise ValueError(
            f"broadcast prompt batch has invalid lengths {lengths.cpu().tolist()}"
        )
    token_count = int(lengths.sum().item())

    if rank == 0:
        assert prompt_batch is not None
        flat_tokens = torch.tensor(
            [token for prompt in prompt_batch for token in prompt],
            dtype=torch.long,
            device=device,
        )
        if flat_tokens.numel() != token_count:
            raise AssertionError(
                f"rank 0 prompt batch has {flat_tokens.numel()} flat tokens, "
                f"but lengths sum to {token_count}"
            )
    else:
        flat_tokens = torch.empty(token_count, dtype=torch.long, device=device)
    dist.broadcast(flat_tokens, src=0)

    host_lengths = [int(length) for length in lengths.cpu().tolist()]
    host_tokens = [int(token) for token in flat_tokens.cpu().tolist()]
    result: list[list[int]] = []
    offset = 0
    for length in host_lengths:
        result.append(host_tokens[offset : offset + length])
        offset += length
    if offset != len(host_tokens):
        raise AssertionError(
            f"broadcast prompt batch consumed {offset} of {len(host_tokens)} tokens"
        )
    return result


def _resolve_device(device_arg: str, local_rank: int) -> torch.device:
    requested = torch.device(device_arg)
    if requested.type == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        # An explicit index remains useful for single-rank debugging.  The normal
        # torchrun spelling is simply --device cuda, which maps LOCAL_RANK here.
        device = (
            torch.device("cuda", local_rank)
            if requested.index is None
            else requested
        )
        torch.cuda.set_device(device)
        return device
    return requested


def _load_rank_model(tp_dir: str, rank: int, config: Any, device: torch.device):
    from convert import validate_rank_shard
    from model import model_class_for_config

    shard = Path(tp_dir) / f"model-r{rank}.safetensors"
    if not shard.is_file():
        raise FileNotFoundError(f"rank {rank}: missing TP weight shard {shard}")
    validate_rank_shard(shard, config, rank)
    model, loading_info = model_class_for_config(config).from_pretrained(
        str(shard), config=config, output_loading_info=True,
    )
    failures = {key: loading_info.get(key) for key in (
        "missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs",
    ) if loading_info.get(key)}
    if failures:
        raise RuntimeError(f"rank {rank}: incomplete checkpoint loading: {failures}")
    # TP shards intentionally keep a full replicated lm_head on disk.  Transformers 4
    # sliced it through ``_load_from_state_dict``; Transformers 5 injects tensors directly,
    # so the module must be narrowed explicitly after strict loading.
    model.lm_head.shard_(rank)
    model = model.to(device).eval()
    model.pack_qkv_()
    model.model.build_rope(device)
    return model


def generate_completion(
    model: Any,
    prompt_ids: list[int],
    *,
    max_new_tokens: int,
    device: torch.device,
) -> list[int]:
    """Run the model's TP-safe greedy path for one request.

    ``Step5ForCausalLM.generate_greedy`` calls ``vocab_parallel_argmax`` at
    every step.  It therefore reconstructs the full vocabulary and returns a
    global token id, rather than treating a rank-local column as a token id.
    """
    completions = generate_completions(
        model,
        [prompt_ids],
        max_new_tokens=max_new_tokens,
        device=device,
    )
    return completions[0]


def generate_completions(
    model: Any,
    prompt_batch: list[list[int]],
    *,
    max_new_tokens: int,
    device: torch.device,
    eos_token_ids: set[int] | None = None,
    image_inputs: dict[str, Any] | None = None,
) -> list[list[int]]:
    """Run one packed batch through the model's TP-safe greedy path."""
    if not prompt_batch:
        raise ValueError("prompt batch must contain at least one request")
    generation_error: BaseException | None = None
    try:
        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "device": device,
        }
        if eos_token_ids is not None:
            generation_kwargs["eos_token_ids"] = eos_token_ids
        if image_inputs:
            generation_kwargs.update(image_inputs)
        completions = model.generate_greedy(prompt_batch, **generation_kwargs)
        if not isinstance(completions, list):
            raise TypeError(
                "generate_greedy must return a list of token-ID lists; "
                f"got {type(completions).__name__}"
            )
        if len(completions) != len(prompt_batch):
            raise RuntimeError(
                f"expected {len(prompt_batch)} completions, got {len(completions)}"
            )
        for completion_index, completion in enumerate(completions):
            if not isinstance(completion, list):
                raise TypeError(
                    f"completion {completion_index} must be a token-ID list; "
                    f"got {type(completion).__name__}"
                )
            for token_index, token in enumerate(completion):
                if isinstance(token, bool) or not isinstance(token, int):
                    raise TypeError(
                        f"completion {completion_index} token {token_index} "
                        f"must be an integer; got {type(token).__name__}"
                    )
                if token < 0:
                    raise ValueError(
                        f"completion {completion_index} token {token_index} "
                        f"must be non-negative; got {token}"
                    )
        return completions
    except BaseException as exc:
        generation_error = exc
        raise
    finally:
        if getattr(device, "type", None) == "cuda":
            try:
                torch.cuda.empty_cache()
            except BaseException as cleanup_error:
                if generation_error is None:
                    raise
                print(
                    "[generate] CUDA allocator cleanup failed after generation "
                    f"error: {type(cleanup_error).__name__}: {cleanup_error}",
                    file=sys.stderr,
                    flush=True,
                )


def format_output(
    *,
    prompt_token_count: int,
    completion_ids: Sequence[int],
    tokenizer: Any | None,
    eos_token_ids: Sequence[int] | None = None,
) -> str:
    completion = (
        tokenizer.decode(list(completion_ids), skip_special_tokens=False)
        if tokenizer is not None
        else None
    )
    payload = {
        "prompt_token_count": prompt_token_count,
        "completion_token_ids": list(completion_ids),
        "completion": completion,
    }
    if eos_token_ids is not None:
        payload["eos_token_ids"] = sorted(int(token) for token in eos_token_ids)
    return json.dumps(payload, ensure_ascii=False)


def format_batch_output(
    *,
    prompt_batch: Sequence[Sequence[int]],
    completion_batch: Sequence[Sequence[int]],
    tokenizer: Any | None,
    eos_token_ids: Sequence[int] | None = None,
) -> str:
    """Format one request exactly as before, or a multi-request result object."""
    if len(prompt_batch) != len(completion_batch):
        raise ValueError(
            f"prompt/completion batch mismatch: {len(prompt_batch)} != "
            f"{len(completion_batch)}"
        )
    if not prompt_batch:
        raise ValueError("cannot format an empty batch")
    if len(prompt_batch) == 1:
        return format_output(
            prompt_token_count=len(prompt_batch[0]),
            completion_ids=completion_batch[0],
            tokenizer=tokenizer,
            eos_token_ids=eos_token_ids,
        )

    results = []
    for prompt_ids, completion_ids in zip(prompt_batch, completion_batch):
        completion_list = list(completion_ids)
        completion = (
            tokenizer.decode(completion_list, skip_special_tokens=False)
            if tokenizer is not None
            else None
        )
        results.append(
            {
                "prompt_token_count": len(prompt_ids),
                "completion_token_ids": completion_list,
                "completion": completion,
            }
        )
    return json.dumps(
        {
            "batch_size": len(results),
            **(
                {"eos_token_ids": sorted(int(token) for token in eos_token_ids)}
                if eos_token_ids is not None
                else {}
            ),
            "results": results,
        },
        ensure_ascii=False,
    )


def load_image_inputs(path, config):
    """Load the same preprocessed inputs on every rank; propagate failures together."""
    inputs, error = {}, None
    if path is not None:
        try:
            from model import Step5VLConfig
            from safetensors.torch import load_file
            if not isinstance(config, Step5VLConfig):
                raise ValueError("--image-inputs requires a step5_vl checkpoint")
            inputs = load_file(path, device="cpu")
            allowed = {"pixel_values", "patch_pixel_values", "num_patches", "image_embeds"}
            if not inputs or set(inputs) - allowed:
                raise ValueError(f"Image input keys must be a nonempty subset of {sorted(allowed)}")
            if ("pixel_values" in inputs) == ("image_embeds" in inputs):
                raise ValueError("Provide exactly one of pixel_values or image_embeds")
            if "image_embeds" in inputs and len(inputs) != 1:
                raise ValueError("image_embeds cannot be combined with crop inputs")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    errors = [error]
    if dist.is_initialized():
        errors = [None] * dist.get_world_size()
        dist.all_gather_object(errors, error)
    if any(errors):
        raise ValueError(f"Unable to load image inputs: {next(e for e in errors if e)}")
    return inputs


def _run(args: argparse.Namespace, *, rank: int, world: int, device: torch.device) -> int:
    model_config = _load_rank_config(args.tp_dir, rank)
    config = model_config.get_text_config()
    image_token_id = getattr(model_config, "image_token_id", None) if args.image_inputs else None
    config_ep_size = validate_parallel_topology(
        config,
        world=world,
        requested_ep_size=args.ep_size,
        rank=rank,
    )

    tokenizer_source = resolve_tokenizer_source(
        tp_dir=args.tp_dir,
        tokenizer=args.tokenizer,
        checkpoint=args.checkpoint,
    )
    tokenizer = None
    explicit_tokenizer_source = (
        args.tokenizer is not None or args.checkpoint is not None
    )
    rank0_prompt_batch: list[list[int]] | None = None
    rank0_eos_token_ids: set[int] | None = None
    prompt_error: str | None = None
    if rank == 0:
        try:
            if args.prompt_json_batch is not None:
                rank0_prompt_batch = load_prompt_json_batch(args.prompt_json_batch)
                # A tokenizer is optional for exact-id input; it is used only to
                # decode completions when one is available.
                tokenizer = _load_exact_id_tokenizer(
                    tokenizer_source,
                    explicit_source=explicit_tokenizer_source,
                )
            elif args.prompt_json is not None:
                rank0_prompt_batch = [load_prompt_json(args.prompt_json)]
                # A tokenizer is optional for exact-id input; it is used only to
                # decode the completion when one was explicitly or automatically found.
                tokenizer = _load_exact_id_tokenizer(
                    tokenizer_source,
                    explicit_source=explicit_tokenizer_source,
                )
            else:
                if tokenizer_source is None:
                    raise ValueError(
                        "--prompt requires --tokenizer/--checkpoint, or tokenizer files "
                        "at <tp-dir>/../tokenizer_files"
                    )
                tokenizer = _load_tokenizer(
                    tokenizer_source,
                    require_chat_template=not args.raw_prompt,
                )
                rank0_prompt_batch = [
                    tokenize_text(tokenizer, args.prompt, raw_prompt=args.raw_prompt)
                ]
            assert rank0_prompt_batch is not None
            for prompt_ids in rank0_prompt_batch:
                validate_prompt_ids(
                    prompt_ids,
                    vocab_size=config.vocab_size,
                    max_position_embeddings=config.max_position_embeddings,
                    max_new_tokens=args.max_new_tokens,
                    image_token_id=image_token_id,
                )
            rank0_eos_token_ids = resolve_generation_eos_token_ids(
                config.eos_token_id,
                tokenizer,
            )
        except Exception as exc:
            prompt_error = f"{type(exc).__name__}: {exc}"

    _broadcast_error(prompt_error, device=device)
    eos_token_ids = broadcast_eos_token_ids(
        rank0_eos_token_ids,
        rank=rank,
        device=device,
    )
    prompt_batch = broadcast_prompt_batch(
        rank0_prompt_batch, rank=rank, device=device
    )
    # Check again on all ranks so a corrupted/mismatched rank config fails before
    # loading hundreds of gigabytes of weights.
    for prompt_ids in prompt_batch:
        validate_prompt_ids(
            prompt_ids,
            vocab_size=config.vocab_size,
            max_position_embeddings=config.max_position_embeddings,
            max_new_tokens=args.max_new_tokens,
            image_token_id=image_token_id,
        )

    if rank == 0:
        prompt_lengths = [len(prompt_ids) for prompt_ids in prompt_batch]
        prompt_description = (
            f"{prompt_lengths[0]} prompt tokens"
            if len(prompt_lengths) == 1
            else f"batch={len(prompt_lengths)}, prompt tokens={prompt_lengths}"
        )
        print(
            f"loading Step5 TP={world}, co-located EP={config_ep_size} "
            f"({prompt_description})",
            file=sys.stderr,
            flush=True,
        )
    image_inputs = load_image_inputs(args.image_inputs, model_config)
    model = _load_rank_model(args.tp_dir, rank, model_config, device)
    completion_batch = generate_completions(
        model,
        prompt_batch,
        max_new_tokens=args.max_new_tokens,
        device=device,
        eos_token_ids=eos_token_ids,
        image_inputs=image_inputs,
    )
    if rank == 0:
        print(
            format_batch_output(
                prompt_batch=prompt_batch,
                completion_batch=completion_batch,
                tokenizer=tokenizer,
                eos_token_ids=eos_token_ids,
            ),
            flush=True,
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not dist.is_available():
        raise SystemExit("torch.distributed is unavailable; launch this CLI with torchrun")
    if not {"RANK", "WORLD_SIZE", "LOCAL_RANK"}.issubset(os.environ):
        raise SystemExit(
            "missing torchrun environment (RANK/WORLD_SIZE/LOCAL_RANK); "
            "launch with torchrun --nproc-per-node=<TP>"
        )

    local_rank = int(os.environ["LOCAL_RANK"])
    device = _resolve_device(args.device, local_rank)
    backend = "nccl" if device.type == "cuda" else "gloo"
    owns_process_group = False
    try:
        if not dist.is_initialized():
            dist.init_process_group(backend=backend)
            owns_process_group = True
        return _run(
            args,
            rank=dist.get_rank(),
            world=dist.get_world_size(),
            device=device,
        )
    finally:
        if owns_process_group and dist.is_available() and dist.is_initialized():
            dist.destroy_process_group()


if __name__ == "__main__":
    raise SystemExit(main())
