"""Geometry helpers shared by MGVB and multimodal M-RoPE (numpy port).

Values are identical to ``inference/runtime_sources/mgvb_utils.py``; only the
tensor backend changes, so the MLX runtime emits the same compact token order and
the same visual positions as the PyTorch runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, order=True)
class SpatialCell:
    temporal: int
    top: int
    left: int
    bottom: int
    right: int

    @property
    def area(self) -> int:
        return (self.bottom - self.top) * (self.right - self.left)

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def width(self) -> int:
        return self.right - self.left


def merged_grid_shape(grid_thw, spatial_merge_size: int) -> tuple[int, int, int]:
    values = [int(v) for v in np.asarray(grid_thw).reshape(-1).tolist()]
    if len(values) != 3:
        raise ValueError(f"grid_thw must contain exactly three values, got {values!r}")
    temporal, height, width = values
    merge = int(spatial_merge_size)
    if temporal < 1 or height < 1 or width < 1 or merge < 1:
        raise ValueError(f"invalid visual grid={values!r}, spatial_merge_size={merge}")
    if height % merge or width % merge:
        raise ValueError(f"visual grid {values!r} is not divisible by spatial_merge_size={merge}")
    return temporal, height // merge, width // merge


def native_visual_token_count(grid_thw, spatial_merge_size: int) -> int:
    temporal, height, width = merged_grid_shape(grid_thw, spatial_merge_size)
    return temporal * height * width


def native_visual_positions(grid_thw, spatial_merge_size: int) -> np.ndarray:
    temporal, height, width = merged_grid_shape(grid_thw, spatial_merge_size)
    t = np.arange(temporal).reshape(-1, 1, 1)
    h = np.arange(height).reshape(1, -1, 1)
    w = np.arange(width).reshape(1, 1, -1)
    return np.stack(
        [
            np.broadcast_to(t, (temporal, height, width)),
            np.broadcast_to(h, (temporal, height, width)),
            np.broadcast_to(w, (temporal, height, width)),
        ],
        axis=-1,
    ).reshape(-1, 3)


def partition_spatial_grid(
    temporal: int, height: int, width: int, cell_count: int
) -> list[SpatialCell]:
    """Split a THW grid into exactly ``cell_count`` deterministic non-empty rectangles."""
    temporal, height, width, cell_count = map(int, (temporal, height, width, cell_count))
    token_count = temporal * height * width
    if temporal < 1 or height < 1 or width < 1:
        raise ValueError(f"invalid merged grid {(temporal, height, width)!r}")
    if cell_count < 1 or cell_count > token_count:
        raise ValueError(f"cell_count={cell_count} must be in [1, {token_count}]")

    cells = [SpatialCell(t, 0, 0, height, width) for t in range(temporal)]
    if cell_count < len(cells):
        raise ValueError(
            f"cell_count={cell_count} cannot preserve temporal slices for temporal={temporal}"
        )

    while len(cells) < cell_count:
        candidates = [
            (cell.area, max(cell.height, cell.width), -index, index)
            for index, cell in enumerate(cells)
            if cell.area > 1
        ]
        if not candidates:
            raise RuntimeError(
                f"cannot split merged grid {(temporal, height, width)} into {cell_count} cells"
            )
        _, _, _, split_index = max(candidates)
        cell = cells.pop(split_index)
        if cell.width >= cell.height and cell.width > 1:
            middle = cell.left + cell.width // 2
            children = [
                SpatialCell(cell.temporal, cell.top, cell.left, cell.bottom, middle),
                SpatialCell(cell.temporal, cell.top, middle, cell.bottom, cell.right),
            ]
        else:
            middle = cell.top + cell.height // 2
            children = [
                SpatialCell(cell.temporal, cell.top, cell.left, middle, cell.right),
                SpatialCell(cell.temporal, middle, cell.left, cell.bottom, cell.right),
            ]
        cells.extend(children)

    return sorted(cells)


def cell_center_positions(cells: list[SpatialCell]) -> np.ndarray:
    return np.asarray(
        [
            [
                cell.temporal,
                (cell.top + cell.bottom - 1) // 2,
                (cell.left + cell.right - 1) // 2,
            ]
            for cell in cells
        ],
        dtype=np.int64,
    ).reshape(-1, 3)


def cell_edges(
    cells: list[SpatialCell], height: int, width: int, *, halo: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """Return flattened token indices and their destination cell ids."""
    token_indices: list[int] = []
    cell_indices: list[int] = []
    halo = max(0, int(halo))
    for cell_id, cell in enumerate(cells):
        top = max(0, cell.top - halo)
        left = max(0, cell.left - halo)
        bottom = min(height, cell.bottom + halo)
        right = min(width, cell.right + halo)
        base = cell.temporal * height * width
        for row in range(top, bottom):
            start = base + row * width + left
            count = right - left
            token_indices.extend(range(start, start + count))
            cell_indices.extend([cell_id] * count)
    return (
        np.asarray(token_indices, dtype=np.int64),
        np.asarray(cell_indices, dtype=np.int64),
    )


def build_mgvb_visual_positions(
    grid_thw,
    *,
    spatial_merge_size: int,
    token_budget: int,
    global_tokens: int,
    region_tokens: int,
) -> np.ndarray:
    """Build positions in the exact order emitted by MGVB."""
    temporal, height, width = merged_grid_shape(grid_thw, spatial_merge_size)
    native_count = temporal * height * width
    compact_count = min(native_count, int(token_budget))
    if compact_count == native_count:
        return native_visual_positions(grid_thw, spatial_merge_size)

    global_count = int(global_tokens)
    region_count = int(region_tokens)
    fine_count = compact_count - global_count - region_count
    if global_count < 1 or region_count < 1 or fine_count < 1:
        raise ValueError(
            "compressed MGVB budget must leave positive global, region, and fine counts; "
            f"got total={compact_count}, global={global_count}, region={region_count}, "
            f"fine={fine_count}"
        )

    center = np.asarray(
        [[(temporal - 1) // 2, (height - 1) // 2, (width - 1) // 2]], dtype=np.int64
    )
    center = np.repeat(center, global_count, axis=0)
    region_cells = partition_spatial_grid(temporal, height, width, region_count)
    fine_cells = partition_spatial_grid(temporal, height, width, fine_count)
    return np.concatenate(
        [center, cell_center_positions(region_cells), cell_center_positions(fine_cells)],
        axis=0,
    )
