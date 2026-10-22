"""Bridge FA3 absorbed MLA decode to SGLang's DCP output contract.

The SGLang revision used by this adapter already implements DCP in the common
MLA forward path and FA3 can produce softmax LSE.  Its absorbed-MLA branch,
however, requests/returns LSE only for cascade attention.  DCP consequently
tries to unpack a bare output tensor as ``(output, lse)``.

Keep the workaround model-local and narrowly scoped: only FA3, MLA, DCP decode
uses the copied kernel call below.  Every other path delegates unchanged to
SGLang's original backend method.
"""

from __future__ import annotations

from typing import Any

import torch


def apply_fa3_dcp_patch() -> None:
    import sglang.srt.layers.attention.flashattention_backend as fa_backend
    from sglang.srt.layers.attention.flashattention_backend import (
        FlashAttentionBackend,
    )
    from sglang.srt.layers.dcp.layout import get_dcp_lens
    from sglang.srt.runtime_context import get_parallel

    if getattr(FlashAttentionBackend, "_utu_fa3_dcp_patch", False):
        return

    original_forward_decode = FlashAttentionBackend.forward_decode
    original_init_forward_metadata = FlashAttentionBackend.init_forward_metadata
    original_init_forward_metadata_out_graph = (
        FlashAttentionBackend.init_forward_metadata_out_graph
    )

    def _is_dcp_decode(self, forward_batch):
        # Resolve from ServerArgs/runtime, including direct --dcp-size launches.
        if not (self.fa_impl_ver == 3 and self.use_mla and get_parallel().dcp_enabled):
            return False
        if forward_batch.forward_mode.is_target_verify():
            raise NotImplementedError(
                "UTU FA3+DCP supports ordinary decode only; "
                "disable DCP for speculative verification."
            )
        return forward_batch.forward_mode.is_decode()

    def _localize_metadata(metadata, *, stable_state=None) -> None:
        """Convert FA3's full logical page table to this DCP rank's KV shard."""
        parallel = get_parallel()
        dcp_size = parallel.dcp_size
        dcp_rank = parallel.dcp_rank

        full_page_table = metadata.page_table
        full_kv_lens = metadata.cache_seqlens_int32

        local_kv_lens = get_dcp_lens(full_kv_lens, dcp_size, dcp_rank)
        local_pages = full_page_table[:, dcp_rank::dcp_size] // dcp_size
        local_cu_k = torch.nn.functional.pad(
            torch.cumsum(local_kv_lens, dim=0, dtype=torch.int32),
            (1, 0),
        )

        if stable_state is not None:
            local_page_table = stable_state["local_page_table"]
            local_page_table.zero_()
            local_page_table[:, : local_pages.shape[1]].copy_(local_pages)
            stable_state["local_kv_lens"].copy_(local_kv_lens)
            stable_state["local_cu_k"].copy_(local_cu_k)
            metadata.page_table = local_page_table
            metadata.cache_seqlens_int32 = stable_state["local_kv_lens"]
            metadata.cu_seqlens_k = stable_state["local_cu_k"]
        else:
            metadata.page_table = local_pages
            metadata.cache_seqlens_int32 = local_kv_lens
            metadata.cu_seqlens_k = local_cu_k

        metadata.max_seq_len_k = (
            metadata.max_seq_len_k + dcp_size - 1
        ) // dcp_size

    def _init_forward_metadata(self, forward_batch):
        original_init_forward_metadata(self, forward_batch)
        if _is_dcp_decode(self, forward_batch):
            if self.page_size != 1:
                raise NotImplementedError("UTU FA3+DCP requires page_size=1")
            _localize_metadata(self.forward_metadata)

    def _init_forward_metadata_out_graph(
        self,
        forward_batch,
        in_capture: bool = False,
    ):
        # Restore the full-table tensors before SGLang refreshes them from
        # req_to_token.  After the refresh, copy this rank's strided shard into
        # stable buffers whose addresses were baked into the CUDA graph.
        states = getattr(self, "_utu_fa3_dcp_graph_states", {})
        for state in states.values():
            metadata = state["metadata"]
            metadata.page_table = state["full_page_table"]
            metadata.cache_seqlens_int32 = state["full_kv_lens"]
            metadata.cu_seqlens_k = state["full_cu_k"]

        original_init_forward_metadata_out_graph(
            self,
            forward_batch,
            in_capture=in_capture,
        )
        if not _is_dcp_decode(self, forward_batch):
            return
        if self.page_size != 1:
            raise NotImplementedError("UTU FA3+DCP requires page_size=1")

        metadata = self.forward_metadata
        key = id(metadata)
        state = states.get(key)
        if state is None:
            full_page_table = metadata.page_table
            full_kv_lens = metadata.cache_seqlens_int32
            full_cu_k = metadata.cu_seqlens_k
            dcp_size = get_parallel().dcp_size
            state = {
                "metadata": metadata,
                "full_page_table": full_page_table,
                "full_kv_lens": full_kv_lens,
                "full_cu_k": full_cu_k,
                "local_page_table": torch.empty_like(
                    full_page_table[:, ::dcp_size]
                ),
                "local_kv_lens": torch.empty_like(full_kv_lens),
                "local_cu_k": torch.empty_like(full_cu_k),
            }
            states[key] = state
            self._utu_fa3_dcp_graph_states = states
        _localize_metadata(metadata, stable_state=state)

    def _forward_decode(
        self,
        q: torch.Tensor,
        k: torch.Tensor,
        v: torch.Tensor,
        layer,
        forward_batch,
        save_kv_cache: bool = True,
        *,
        q_rope: torch.Tensor | None = None,
        k_rope: torch.Tensor | None = None,
        sinks: torch.Tensor | None = None,
        q_descale: torch.Tensor | None = None,
        k_descale: torch.Tensor | None = None,
        v_descale: torch.Tensor | None = None,
        score_mod: Any = None,
        aux_tensors: Any = None,
        rel_bias: torch.Tensor | None = None,
        rel_bias_event: Any = None,
    ):
        if not _is_dcp_decode(self, forward_batch):
            return original_forward_decode(
                self,
                q,
                k,
                v,
                layer,
                forward_batch,
                save_kv_cache,
                q_rope=q_rope,
                k_rope=k_rope,
                sinks=sinks,
                q_descale=q_descale,
                k_descale=k_descale,
                v_descale=v_descale,
                score_mod=score_mod,
                aux_tensors=aux_tensors,
                rel_bias=rel_bias,
                rel_bias_event=rel_bias_event,
            )

        # This adapter runs BF16 latent KV without score modifiers.  Fail
        # explicitly if that deployment contract changes rather than silently
        # dropping a newly introduced attention feature.
        unsupported = {
            "sinks": sinks,
            "q_descale": q_descale,
            "k_descale": k_descale,
            "v_descale": v_descale,
            "score_mod": score_mod,
            "aux_tensors": aux_tensors,
            "rel_bias": rel_bias,
            "rel_bias_event": rel_bias_event,
        }
        active = [name for name, value in unsupported.items() if value is not None]
        if active:
            raise NotImplementedError(
                "UTU FA3+DCP bridge does not support: " + ", ".join(active)
            )
        if self.fa_impl_ver != 3:
            raise NotImplementedError(
                f"UTU FA3+DCP bridge expected FA3, got FA{self.fa_impl_ver}"
            )
        if q_rope is None:
            raise ValueError("FA3 absorbed MLA DCP decode requires q_rope")

        if k is not None:
            if v is None:
                raise ValueError("FA3 DCP decode received K without V")
            if save_kv_cache:
                cache_loc = (
                    forward_batch.out_cache_loc
                    if not layer.is_cross_attention
                    else forward_batch.encoder_out_cache_loc
                )
                self.token_to_kv_pool.set_mla_kv_buffer(
                    layer,
                    cache_loc,
                    k,
                    k_rope,
                )

        metadata = self.forward_metadata
        kv_cache = self.token_to_kv_pool.get_key_buffer(layer.layer_id).to(q.dtype)
        c_kv = kv_cache[:, :, : layer.v_head_dim]
        k_rope_cache = kv_cache[:, :, layer.v_head_dim :].view(
            -1,
            self.page_size,
            layer.tp_k_head_num,
            layer.head_dim - layer.v_head_dim,
        )
        c_kv_cache = c_kv.view(
            -1,
            self.page_size,
            layer.tp_v_head_num,
            layer.v_head_dim,
        )
        q_nope = q.view(-1, layer.tp_q_head_num, layer.v_head_dim)
        q_rope = q_rope.view(
            -1,
            layer.tp_q_head_num,
            layer.head_dim - layer.v_head_dim,
        )

        result = fa_backend.flash_attn_with_kvcache(
            q=q_rope,
            qv=q_nope,
            k_cache=k_rope_cache,
            v_cache=c_kv_cache,
            page_table=metadata.page_table,
            cache_seqlens=metadata.cache_seqlens_int32,
            cu_seqlens_q=metadata.cu_seqlens_q,
            cu_seqlens_k_new=metadata.cu_seqlens_k,
            max_seqlen_q=metadata.max_seq_len_q,
            softmax_scale=layer.scaling,
            causal=True,
            softcap=layer.logit_cap,
            return_softmax_lse=True,
            num_splits=self.num_splits,
            ver=self.fa_impl_ver,
        )
        output, lse, *_ = result
        output = output.view(-1, layer.tp_q_head_num * layer.v_head_dim)
        # FA3 emits [num_heads, total_q]; SGLang's DCP reducer consumes
        # [total_q, num_heads], matching its FlashInfer/FlashMLA contracts.
        return output, lse.transpose(0, 1).contiguous()

    FlashAttentionBackend.forward_decode = _forward_decode
    FlashAttentionBackend.init_forward_metadata = _init_forward_metadata
    FlashAttentionBackend.init_forward_metadata_out_graph = (
        _init_forward_metadata_out_graph
    )
    FlashAttentionBackend._utu_fa3_dcp_patch = True
    print("[UTU] FA3 absorbed-MLA DCP LSE bridge applied.", flush=True)
