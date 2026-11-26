"""Multimodal RoPE index with explicit (compacted) visual positions.

Port of ``inference/runtime_sources/rope_utils.py::get_rope_index`` for a single
unpadded request. The only behavioural addition over the reference is
``image_position_ids``, which lets MGVB place ``min(native, budget)`` visual
tokens at their own 3-D coordinates instead of the native merged grid.
"""

from __future__ import annotations

import numpy as np


def get_rope_index(
    *,
    spatial_merge_size: int,
    image_token_id: int,
    video_token_id: int,
    vision_start_token_id: int,
    input_ids: np.ndarray,
    image_grid_thw: np.ndarray | None = None,
    image_position_ids: list[np.ndarray] | None = None,
) -> tuple[np.ndarray, int]:
    """Return ``(position_ids, mrope_position_delta)`` for one request.

    ``position_ids`` has shape ``(3, seq_len)`` and holds the temporal, height and
    width coordinates that the backbone turns into interleaved M-RoPE angles.
    """
    ids = np.asarray(input_ids, dtype=np.int64).reshape(-1)
    if image_grid_thw is None:
        position_ids = np.arange(ids.shape[0], dtype=np.int32).reshape(1, -1)
        return np.repeat(position_ids, 3, axis=0), 0

    grids = np.asarray(image_grid_thw, dtype=np.int64).reshape(-1, 3)
    tokens = ids.tolist()
    image_nums = 0
    vision_starts = np.nonzero(ids == vision_start_token_id)[0]
    for start in vision_starts:
        if start + 1 < len(tokens) and tokens[start + 1] == image_token_id:
            image_nums += 1
    if any(
        start + 1 < len(tokens) and tokens[start + 1] == video_token_id
        for start in vision_starts
    ):
        raise ValueError("video inputs are not supported by the WePM MLX runtime")

    positions = np.ones((3, ids.shape[0]), dtype=np.int64)
    llm_pos_ids_list: list[np.ndarray] = []
    st = 0
    remain_images = image_nums
    image_index = 0
    for _ in range(image_nums):
        if image_token_id in tokens[st:] and remain_images > 0:
            ed = tokens.index(image_token_id, st)
        else:
            break
        t, h, w = grids[image_index].tolist()
        explicit = image_position_ids[image_index] if image_position_ids is not None else None
        image_index += 1
        remain_images -= 1

        llm_grid_t, llm_grid_h, llm_grid_w = t, h // spatial_merge_size, w // spatial_merge_size
        text_len = ed - st
        st_idx = llm_pos_ids_list[-1].max() + 1 if llm_pos_ids_list else 0
        llm_pos_ids_list.append(np.repeat(np.arange(text_len)[None, :] + st_idx, 3, axis=0))

        if explicit is not None:
            visual_positions = np.asarray(explicit, dtype=np.int64)
            if visual_positions.ndim != 2 or visual_positions.shape[-1] != 3:
                raise ValueError(
                    "image_position_ids entries must have shape [visual_tokens, 3], "
                    f"got {visual_positions.shape!r}"
                )
            visual_positions = np.ascontiguousarray(visual_positions.T)
        else:
            t_index = np.repeat(np.arange(llm_grid_t), llm_grid_h * llm_grid_w)
            h_index = np.tile(np.repeat(np.arange(llm_grid_h), llm_grid_w), llm_grid_t)
            w_index = np.tile(np.arange(llm_grid_w), llm_grid_t * llm_grid_h)
            visual_positions = np.stack([t_index, h_index, w_index])

        visual_length = visual_positions.shape[1]
        actual = 0
        while ed + actual < len(tokens) and tokens[ed + actual] == image_token_id:
            actual += 1
        if actual != visual_length:
            raise ValueError(
                f"visual placeholder length={actual} does not match position length="
                f"{visual_length} for token_id={image_token_id}"
            )
        llm_pos_ids_list.append(visual_positions + text_len + st_idx)
        st = ed + visual_length

    if st < len(tokens):
        st_idx = llm_pos_ids_list[-1].max() + 1 if llm_pos_ids_list else 0
        text_len = len(tokens) - st
        llm_pos_ids_list.append(np.repeat(np.arange(text_len)[None, :] + st_idx, 3, axis=0))

    llm_positions = np.concatenate(llm_pos_ids_list, axis=1).reshape(3, -1)
    if llm_positions.shape[1] != ids.shape[0]:
        raise ValueError(
            f"M-RoPE produced {llm_positions.shape[1]} positions for "
            f"{ids.shape[0]} input tokens"
        )
    positions[:, :] = llm_positions
    if image_position_ids is not None and image_index != len(image_position_ids):
        raise ValueError(
            f"consumed {image_index} explicit image position tensors, "
            f"but received {len(image_position_ids)}"
        )
    delta = int(llm_positions.max()) + 1 - ids.shape[0]
    return positions.astype(np.int32), delta
