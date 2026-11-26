"""Multi-Granularity Visual Bottleneck (MGVB) in MLX.

Mirrors ``inference/runtime_sources/mgvb.py`` parameter-for-parameter. Only the
inference path is implemented: reconstruction/diversity losses are training-only
and the released checkpoints never invoke them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import mlx.core as mx
import mlx.nn as nn
import numpy as np

from .mgvb_geometry import (
    build_mgvb_visual_positions,
    cell_edges,
    merged_grid_shape,
    native_visual_positions,
    partition_spatial_grid,
)


class _RMSNorm(nn.Module):
    """RMSNorm with fp32 statistics and a plain (non delta) gain."""

    def __init__(self, hidden_size: int, eps: float = 1e-6):
        super().__init__()
        self.weight = mx.ones((hidden_size,))
        self.eps = float(eps)

    def __call__(self, value: mx.array) -> mx.array:
        work = value.astype(mx.float32)
        normalized = work * mx.rsqrt(work.square().mean(axis=-1, keepdims=True) + self.eps)
        return normalized.astype(value.dtype) * self.weight


class _AdapterResidual(nn.Module):
    def __init__(self, adapter_dim: int, hidden_size: int):
        super().__init__()
        self.norm = nn.LayerNorm(adapter_dim)
        self.fc1 = nn.Linear(adapter_dim, adapter_dim * 2, bias=False)
        self.fc2 = nn.Linear(adapter_dim * 2, hidden_size, bias=False)

    def __call__(self, value: mx.array) -> mx.array:
        return self.fc2(nn.gelu(self.fc1(self.norm(value))))


@dataclass
class MGVBOutput:
    embeddings: list[mx.array]
    positions: list[np.ndarray]


class MultiGranularityVisualBottleneck(nn.Module):
    """Replace long native visual sequences with a fixed G/R/F token bank."""

    def __init__(
        self,
        hidden_size: int,
        *,
        adapter_dim: int = 512,
        token_budget: int = 256,
        global_tokens: int = 8,
        region_tokens: int = 64,
        num_global_heads: int = 8,
    ) -> None:
        super().__init__()
        self.hidden_size = int(hidden_size)
        self.adapter_dim = int(adapter_dim)
        self.token_budget = int(token_budget)
        self.global_tokens = int(global_tokens)
        self.region_tokens = int(region_tokens)
        self.fine_tokens = self.token_budget - self.global_tokens - self.region_tokens
        self.num_global_heads = int(num_global_heads)
        if self.hidden_size < 1 or self.adapter_dim < 1:
            raise ValueError("MGVB hidden and adapter dimensions must be positive")
        if self.token_budget < 3:
            raise ValueError("MGVB token budget must be at least three")
        if min(self.global_tokens, self.region_tokens, self.fine_tokens) < 1:
            raise ValueError(
                "MGVB budget must leave positive global, region, and fine branches; "
                f"got total={self.token_budget}, global={self.global_tokens}, "
                f"region={self.region_tokens}, fine={self.fine_tokens}"
            )
        if self.adapter_dim % self.num_global_heads:
            raise ValueError(
                f"adapter_dim={self.adapter_dim} must be divisible by "
                f"num_global_heads={self.num_global_heads}"
            )

        self.input_norm = _RMSNorm(self.hidden_size)
        self.input_proj = nn.Linear(self.hidden_size, self.adapter_dim, bias=False)
        self.query_proj = nn.Linear(self.hidden_size * 2, self.adapter_dim, bias=False)
        self.null_query = mx.zeros((self.adapter_dim,))

        self.global_queries = mx.zeros((self.global_tokens, self.adapter_dim))
        self.global_key = nn.Linear(self.adapter_dim, self.adapter_dim, bias=False)
        self.global_value = nn.Linear(self.adapter_dim, self.adapter_dim, bias=False)
        self.global_query_condition = nn.Linear(
            self.adapter_dim, self.adapter_dim, bias=False
        )
        self.global_residual = _AdapterResidual(self.adapter_dim, self.hidden_size)

        self.region_value = nn.Linear(self.adapter_dim, self.adapter_dim, bias=False)
        self.region_query = nn.Linear(self.adapter_dim, self.adapter_dim, bias=False)
        self.region_position = nn.Linear(4, self.adapter_dim, bias=False)
        self.region_score = nn.Linear(self.adapter_dim, 1, bias=False)
        self.region_residual = _AdapterResidual(self.adapter_dim, self.hidden_size)

        self.fine_value = nn.Linear(self.adapter_dim, self.adapter_dim, bias=False)
        self.fine_query = nn.Linear(self.adapter_dim, self.adapter_dim, bias=False)
        self.fine_position = nn.Linear(4, self.adapter_dim, bias=False)
        self.fine_score = nn.Linear(self.adapter_dim, 1, bias=False)
        self.fine_residual = _AdapterResidual(self.adapter_dim, self.hidden_size)

        self.granularity_embedding = nn.Embedding(3, self.hidden_size)
        self.output_position = nn.Linear(4, self.hidden_size, bias=False)

        # Training-only reconstruction branch, kept so the release weights load strictly.
        self.reconstruction_position = nn.Linear(4, self.hidden_size, bias=False)
        self.reconstruction_norm = nn.LayerNorm(self.hidden_size)
        self.reconstruction_fc1 = nn.Linear(self.hidden_size, self.adapter_dim, bias=False)
        self.reconstruction_fc2 = nn.Linear(self.adapter_dim, self.hidden_size, bias=False)

    @staticmethod
    def _normalized_coordinates(
        temporal: int, height: int, width: int, *, dtype: mx.Dtype
    ) -> mx.array:
        positions = native_visual_positions(
            [temporal, height, width], spatial_merge_size=1
        ).astype(np.float32)
        denominators = np.asarray(
            [max(temporal - 1, 1), max(height - 1, 1), max(width - 1, 1)], dtype=np.float32
        )
        normalized = positions / denominators
        area = np.full(
            (positions.shape[0], 1), 1.0 / max(height * width, 1), dtype=np.float32
        )
        return mx.array(np.concatenate([normalized, area], axis=-1)).astype(dtype)

    def _query(self, query_embedding: mx.array | None, reference: mx.array) -> mx.array:
        if query_embedding is None:
            return self.null_query.astype(reference.dtype)
        if query_embedding.shape[-1] != self.hidden_size * 2:
            raise ValueError(
                f"MGVB query embedding must have size {self.hidden_size * 2}, "
                f"got {query_embedding.shape}"
            )
        projected = self.query_proj(query_embedding.astype(self.query_proj.weight.dtype))
        return projected.astype(reference.dtype)

    @staticmethod
    def _segment_softmax(
        logits: mx.array, segment_ids: np.ndarray, segment_count: int
    ) -> mx.array:
        """Softmax restricted to each token's own cell (masked matrix form)."""
        work = logits.astype(mx.float32)
        membership = mx.array(
            np.arange(segment_count)[:, None] == segment_ids[None, :]
        )
        segmented = mx.where(membership, work[None, :], -mx.inf)
        weights = mx.softmax(segmented, axis=-1)
        gathered = weights[mx.array(segment_ids), mx.arange(segment_ids.shape[0])]
        return gathered.astype(logits.dtype)

    def _segment_pool(
        self,
        *,
        native: mx.array,
        adapter: mx.array,
        normalized_positions: mx.array,
        query: mx.array,
        token_indices: np.ndarray,
        segment_ids: np.ndarray,
        segment_count: int,
        value_proj: nn.Linear,
        query_proj: nn.Linear,
        position_proj: nn.Linear,
        score_proj: nn.Linear,
    ) -> tuple[mx.array, mx.array]:
        index = mx.array(token_indices)
        edge_adapter = adapter[index]
        score_hidden = value_proj(edge_adapter)
        score_hidden = score_hidden + query_proj(query)[None, :]
        score_hidden = score_hidden + position_proj(normalized_positions[index])
        logits = score_proj(mx.tanh(score_hidden)).squeeze(-1)
        weights = self._segment_softmax(logits, segment_ids, segment_count)

        membership = mx.array(
            (np.arange(segment_count)[:, None] == segment_ids[None, :]).astype(np.float32)
        ).astype(native.dtype)
        weighted_native = native[index] * weights.astype(native.dtype)[:, None]
        weighted_adapter = edge_adapter * weights.astype(adapter.dtype)[:, None]
        return membership @ weighted_native, membership @ weighted_adapter

    @staticmethod
    def _position_features(
        positions: np.ndarray, temporal: int, height: int, width: int, *, dtype: mx.Dtype
    ) -> mx.array:
        values = np.asarray(positions, dtype=np.float32)
        denominators = np.asarray(
            [max(temporal - 1, 1), max(height - 1, 1), max(width - 1, 1)], dtype=np.float32
        )
        normalized = values / denominators
        area = np.zeros((values.shape[0], 1), dtype=np.float32)
        return mx.array(np.concatenate([normalized, area], axis=-1)).astype(dtype)

    def _decorate(
        self,
        tokens: mx.array,
        positions: np.ndarray,
        granularity: int,
        temporal: int,
        height: int,
        width: int,
    ) -> mx.array:
        type_ids = mx.array(np.full((positions.shape[0],), granularity, dtype=np.int32))
        position_features = self._position_features(
            positions,
            temporal,
            height,
            width,
            dtype=self.output_position.weight.dtype,
        )
        return (
            tokens
            + self.granularity_embedding(type_ids).astype(tokens.dtype)
            + self.output_position(position_features).astype(tokens.dtype)
        )

    def compress_one(
        self,
        native: mx.array,
        grid_thw: np.ndarray,
        query_embedding: mx.array | None,
        spatial_merge_size: int,
    ) -> tuple[mx.array, np.ndarray]:
        temporal, height, width = merged_grid_shape(grid_thw, spatial_merge_size)
        expected = temporal * height * width
        if tuple(native.shape) != (expected, self.hidden_size):
            raise ValueError(
                f"MGVB expected native embeddings {(expected, self.hidden_size)}, "
                f"got {tuple(native.shape)}"
            )
        native_positions = native_visual_positions(grid_thw, spatial_merge_size)
        if expected <= self.token_budget:
            return native, native_positions

        adapter = self.input_proj(self.input_norm(native))
        query = self._query(query_embedding, adapter)
        normalized_positions = self._normalized_coordinates(
            temporal, height, width, dtype=adapter.dtype
        )

        conditioned = self.global_queries.astype(adapter.dtype)
        conditioned = conditioned + self.global_query_condition(query)[None, :]
        head_dim = self.adapter_dim // self.num_global_heads
        global_query_heads = conditioned.reshape(
            self.global_tokens, self.num_global_heads, head_dim
        )
        global_key_heads = self.global_key(adapter).reshape(
            expected, self.num_global_heads, head_dim
        )
        global_value_heads = self.global_value(adapter).reshape(
            expected, self.num_global_heads, head_dim
        )
        # (heads, global, expected) attention over native tokens
        global_logits = mx.matmul(
            global_query_heads.transpose(1, 0, 2).astype(mx.float32),
            global_key_heads.transpose(1, 2, 0).astype(mx.float32),
        ) / math.sqrt(head_dim)
        global_weights = mx.softmax(global_logits, axis=-1).astype(adapter.dtype)
        # Average the head maps for a stable direct native-feature path; the
        # learned multi-head values supply the branch residual.
        global_native = (
            global_weights.mean(axis=0).astype(native.dtype) @ native
        )
        global_adapter = mx.matmul(
            global_weights, global_value_heads.transpose(1, 0, 2)
        ).transpose(1, 0, 2).reshape(self.global_tokens, self.adapter_dim)
        global_tokens = global_native + self.global_residual(global_adapter).astype(
            native.dtype
        )

        region_cells = partition_spatial_grid(temporal, height, width, self.region_tokens)
        region_indices, region_ids = cell_edges(region_cells, height, width, halo=1)
        region_native, region_adapter = self._segment_pool(
            native=native,
            adapter=adapter,
            normalized_positions=normalized_positions,
            query=query,
            token_indices=region_indices,
            segment_ids=region_ids,
            segment_count=self.region_tokens,
            value_proj=self.region_value,
            query_proj=self.region_query,
            position_proj=self.region_position,
            score_proj=self.region_score,
        )
        region_tokens = region_native + self.region_residual(region_adapter).astype(
            native.dtype
        )

        fine_cells = partition_spatial_grid(temporal, height, width, self.fine_tokens)
        fine_indices, fine_ids = cell_edges(fine_cells, height, width)
        fine_native, fine_adapter = self._segment_pool(
            native=native,
            adapter=adapter,
            normalized_positions=normalized_positions,
            query=query,
            token_indices=fine_indices,
            segment_ids=fine_ids,
            segment_count=self.fine_tokens,
            value_proj=self.fine_value,
            query_proj=self.fine_query,
            position_proj=self.fine_position,
            score_proj=self.fine_score,
        )
        fine_tokens = fine_native + self.fine_residual(fine_adapter).astype(native.dtype)

        positions = build_mgvb_visual_positions(
            grid_thw,
            spatial_merge_size=spatial_merge_size,
            token_budget=self.token_budget,
            global_tokens=self.global_tokens,
            region_tokens=self.region_tokens,
        )
        global_positions = positions[: self.global_tokens]
        region_positions = positions[
            self.global_tokens : self.global_tokens + self.region_tokens
        ]
        fine_positions = positions[self.global_tokens + self.region_tokens :]
        global_tokens = self._decorate(
            global_tokens, global_positions, 0, temporal, height, width
        )
        region_tokens = self._decorate(
            region_tokens, region_positions, 1, temporal, height, width
        )
        fine_tokens = self._decorate(
            fine_tokens, fine_positions, 2, temporal, height, width
        )
        compact = mx.concatenate([global_tokens, region_tokens, fine_tokens], axis=0)
        if tuple(compact.shape) != (self.token_budget, self.hidden_size):
            raise RuntimeError(f"MGVB emitted invalid compact shape {tuple(compact.shape)}")
        return compact, positions

    def __call__(
        self,
        image_embeddings,
        *,
        image_grid_thw,
        query_embeddings=None,
        spatial_merge_size: int = 1,
    ) -> MGVBOutput:
        image_embeddings = list(image_embeddings)
        grids = [np.asarray(g).reshape(3) for g in image_grid_thw]
        if len(image_embeddings) != len(grids):
            raise ValueError(
                f"MGVB received {len(image_embeddings)} image tensors but {len(grids)} grids"
            )
        if query_embeddings is not None and len(query_embeddings) != len(image_embeddings):
            raise ValueError(
                f"MGVB received {len(query_embeddings)} queries for "
                f"{len(image_embeddings)} images"
            )
        outputs: list[mx.array] = []
        positions: list[np.ndarray] = []
        for index, native in enumerate(image_embeddings):
            query = query_embeddings[index] if query_embeddings is not None else None
            compact, coords = self.compress_one(
                native, grids[index], query, spatial_merge_size
            )
            outputs.append(compact)
            positions.append(coords)
        return MGVBOutput(outputs, positions)
