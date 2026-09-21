# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Fused per-block hexagonal SAD search for the fixed 512x512 matching branch."""

from __future__ import annotations
from functools import lru_cache
import torch


@lru_cache(maxsize=1)
def _load_kernel() -> tuple[object, object]:
    """Import Triton lazily so CPU-only tools can import the package."""
    try:
        import triton
        import triton.language as tl
    except ImportError as error:
        raise RuntimeError(
            "preencoding_gating.matching.backend=triton_cuda requires Triton; use the Triton package bundled with the cloud PyTorch installation"
        ) from error

    @triton.jit
    def block_sad(
        current_ptr,
        reference_ptr,
        pair_id,
        block_x,
        block_y,
        dx,
        dy,
        PIXEL_LANES: tl.constexpr,
    ):
        lanes = tl.arange(0, PIXEL_LANES)
        valid_pixel = lanes < 16 * 16 * 3
        channel = lanes % 3
        spatial = lanes // 3
        pixel_x = spatial % 16
        pixel_y = spatial // 16
        current_offset = (
            pair_id * 512 * 512 * 3
            + (block_y + pixel_y) * 512 * 3
            + (block_x + pixel_x) * 3
            + channel
        )
        reference_x = block_x + pixel_x + dx
        reference_y = block_y + pixel_y + dy
        valid_reference = (
            valid_pixel
            & (reference_x >= 0)
            & (reference_x < 512)
            & (reference_y >= 0)
            & (reference_y < 512)
        )
        reference_offset = (
            pair_id * 512 * 512 * 3 + reference_y * 512 * 3 + reference_x * 3 + channel
        )
        current = tl.load(current_ptr + current_offset, mask=valid_pixel, other=0)
        reference = tl.load(
            reference_ptr + reference_offset, mask=valid_reference, other=0
        )
        difference = tl.abs(current.to(tl.int32) - reference.to(tl.int32))
        return tl.sum(tl.where(valid_pixel, difference, 0), axis=0)

    @triton.jit
    def fused_hex_search(
        current_ptr,
        reference_ptr,
        appearance_ptr,
        motion_ptr,
        cost_ptr,
        program_offset,
        total_programs,
        RADIUS: tl.constexpr,
        MOTION_WEIGHT: tl.constexpr,
        MAX_ITERATIONS: tl.constexpr,
        PIXEL_LANES: tl.constexpr,
    ):
        local_program = tl.program_id(0)
        program = local_program + program_offset
        valid_program = program < total_programs
        blocks_per_pair = 32 * 32
        pair_id = program // blocks_per_pair
        block_id = program % blocks_per_pair
        block_x = block_id % 32 * 16
        block_y = block_id // 32 * 16
        center_dx = 0
        center_dy = 0
        iteration = 0
        active = valid_program
        while (iteration < MAX_ITERATIONS) & active:
            best_cost = 1e30
            best_motion_l1 = 1 << 30
            best_dx = center_dx
            best_dy = center_dy
            for candidate_index in tl.static_range(0, 7):
                if candidate_index == 0:
                    offset_x = 0
                    offset_y = 0
                elif candidate_index == 1:
                    offset_x = -2
                    offset_y = 0
                elif candidate_index == 2:
                    offset_x = -1
                    offset_y = -2
                elif candidate_index == 3:
                    offset_x = 1
                    offset_y = -2
                elif candidate_index == 4:
                    offset_x = 2
                    offset_y = 0
                elif candidate_index == 5:
                    offset_x = 1
                    offset_y = 2
                else:
                    offset_x = -1
                    offset_y = 2
                candidate_dx = center_dx + offset_x
                candidate_dy = center_dy + offset_y
                candidate_valid = (
                    valid_program
                    & (candidate_dx >= -RADIUS)
                    & (candidate_dx <= RADIUS)
                    & (candidate_dy >= -RADIUS)
                    & (candidate_dy <= RADIUS)
                    & (block_x + candidate_dx >= 0)
                    & (block_x + candidate_dx + 16 <= 512)
                    & (block_y + candidate_dy >= 0)
                    & (block_y + candidate_dy + 16 <= 512)
                )
                sad = block_sad(
                    current_ptr,
                    reference_ptr,
                    pair_id,
                    block_x,
                    block_y,
                    candidate_dx,
                    candidate_dy,
                    PIXEL_LANES,
                )
                motion_l1 = tl.abs(candidate_dx) + tl.abs(candidate_dy)
                candidate_cost = sad.to(tl.float64) / 195840.0
                candidate_cost += (
                    MOTION_WEIGHT * motion_l1.to(tl.float64) / (2.0 * RADIUS)
                )
                better = candidate_valid & (
                    (candidate_cost < best_cost)
                    | (candidate_cost == best_cost)
                    & (
                        (motion_l1 < best_motion_l1)
                        | (motion_l1 == best_motion_l1)
                        & (
                            (candidate_dy < best_dy)
                            | (candidate_dy == best_dy) & (candidate_dx < best_dx)
                        )
                    )
                )
                best_cost = tl.where(better, candidate_cost, best_cost)
                best_motion_l1 = tl.where(better, motion_l1, best_motion_l1)
                best_dx = tl.where(better, candidate_dx, best_dx)
                best_dy = tl.where(better, candidate_dy, best_dy)
            moved = (best_dx != center_dx) | (best_dy != center_dy)
            center_dx = best_dx
            center_dy = best_dy
            active = active & moved
            iteration += 1
        best_cost = 1e30
        best_appearance = 1e30
        best_motion_l1 = 1 << 30
        best_dx = center_dx
        best_dy = center_dy
        for local_index in tl.static_range(0, 9):
            offset_x = local_index % 3 - 1
            offset_y = local_index // 3 - 1
            candidate_dx = center_dx + offset_x
            candidate_dy = center_dy + offset_y
            candidate_valid = (
                valid_program
                & (candidate_dx >= -RADIUS)
                & (candidate_dx <= RADIUS)
                & (candidate_dy >= -RADIUS)
                & (candidate_dy <= RADIUS)
                & (block_x + candidate_dx >= 0)
                & (block_x + candidate_dx + 16 <= 512)
                & (block_y + candidate_dy >= 0)
                & (block_y + candidate_dy + 16 <= 512)
            )
            sad = block_sad(
                current_ptr,
                reference_ptr,
                pair_id,
                block_x,
                block_y,
                candidate_dx,
                candidate_dy,
                PIXEL_LANES,
            )
            appearance = sad.to(tl.float64) / 195840.0
            motion_l1 = tl.abs(candidate_dx) + tl.abs(candidate_dy)
            candidate_cost = appearance + MOTION_WEIGHT * motion_l1.to(tl.float64) / (
                2.0 * RADIUS
            )
            better = candidate_valid & (
                (candidate_cost < best_cost)
                | (candidate_cost == best_cost)
                & (
                    (motion_l1 < best_motion_l1)
                    | (motion_l1 == best_motion_l1)
                    & (
                        (candidate_dy < best_dy)
                        | (candidate_dy == best_dy) & (candidate_dx < best_dx)
                    )
                )
            )
            best_cost = tl.where(better, candidate_cost, best_cost)
            best_appearance = tl.where(better, appearance, best_appearance)
            best_motion_l1 = tl.where(better, motion_l1, best_motion_l1)
            best_dx = tl.where(better, candidate_dx, best_dx)
            best_dy = tl.where(better, candidate_dy, best_dy)
        best_motion = best_motion_l1.to(tl.float64) / (2.0 * RADIUS)
        tl.store(appearance_ptr + program, best_appearance, mask=valid_program)
        tl.store(motion_ptr + program, best_motion, mask=valid_program)
        tl.store(cost_ptr + program, best_cost, mask=valid_program)

    return (triton, fused_hex_search)


def fused_hex_search_512(
    current: torch.Tensor,
    reference: torch.Tensor,
    *,
    radius: int,
    motion_weight: float,
    program_batch_size: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Return flattened block metrics for aligned uint8 CUDA frame pairs."""
    if (
        current.device.type != "cuda"
        or reference.device != current.device
        or current.dtype != torch.uint8
        or (reference.dtype != torch.uint8)
        or (tuple(current.shape[1:]) != (512, 512, 3))
        or (reference.shape != current.shape)
        or (not current.is_contiguous())
        or (not reference.is_contiguous())
    ):
        raise ValueError(
            "fused Triton matching requires aligned contiguous uint8 CUDA tensors shaped [N,512,512,3]"
        )
    if radius <= 0 or program_batch_size <= 0 or motion_weight < 0:
        raise ValueError("invalid fused matching radius, weight, or batch size")
    (triton, kernel) = _load_kernel()
    total_programs = int(current.shape[0]) * 32 * 32
    appearance = torch.empty(total_programs, device=current.device, dtype=torch.float64)
    motion = torch.empty_like(appearance)
    cost = torch.empty_like(appearance)
    for program_offset in range(0, total_programs, program_batch_size):
        count = min(program_batch_size, total_programs - program_offset)
        kernel[count,](
            current,
            reference,
            appearance,
            motion,
            cost,
            program_offset,
            total_programs,
            RADIUS=radius,
            MOTION_WEIGHT=float(motion_weight),
            MAX_ITERATIONS=2 * radius + 4,
            PIXEL_LANES=triton.next_power_of_2(16 * 16 * 3),
            num_warps=8,
        )
    return (appearance, motion, cost)
