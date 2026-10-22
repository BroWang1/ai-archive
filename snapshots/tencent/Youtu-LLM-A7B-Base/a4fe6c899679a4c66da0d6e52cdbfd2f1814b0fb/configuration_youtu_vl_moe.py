# coding=utf-8
"""UTU-VL MoE configuration."""

from transformers.configuration_utils import PretrainedConfig
from transformers.models.qwen3_vl.configuration_qwen3_vl import Qwen3VLVisionConfig


class YoutuVLMoEConfig(PretrainedConfig):
    r"""
    Configuration for UTU-VL MoE multimodal models.

    默认参数对齐 train_youtu_v2_pro_120b.sh：48L / hidden=3072 / 32 heads /
    KDA head_dim=128 / MLA qk_nope=128、qk_rope=64、q_lora=1024。
    架构特征：KDA + Gated MLA hybrid attention（``experimental_attention_variant='kda'``，
    默认 ``([1]*3+[0]*1)*12``）+ sigmoid MoE + Quantile Balancing 全局 Top-K
    （``moe_router_expert_bias_update_method='quantile'``）；可选 rLatentMoE
    （``moe_latent_size`` + ``moe_latent_rmsnorm``）。120B 默认单 shared
    expert（``enable_multimodal_shared_experts=False``）、modality-aware QB
    bias（token-level text/vision，``moe_router_token_level_modality=True``）、
    MRoPE [12, 10, 10]，且无 SWA/sink/DeepStack。
    """

    model_type = "youtu_vl_moe"
    keys_to_ignore_at_inference = ["past_key_values"]

    def __init__(
        self,
        # ──── LLM 参数 ────
        vocab_size: int = 129280,
        hidden_size: int = 3072,
        intermediate_size: int = 12288,
        moe_intermediate_size: int = 1024,
        num_hidden_layers: int = 48,
        num_attention_heads: int = 32,
        # KDA/MLA training does not use GQA; keep this field for GQA fallback.
        num_key_value_heads: int = 32,
        head_dim: int = 128,
        # KDA + Gated MLA hybrid attention
        multi_latent_attention: bool = True,
        experimental_attention_variant: str | None = "kda",
        linear_attention_pattern: list | None = None,
        q_lora_rank: int = 1024,
        kv_lora_rank: int = 512,
        qk_nope_head_dim: int = 128,
        qk_rope_head_dim: int = 64,
        # Megatron training-side aliases consumed by the VLM builder.
        qk_head_dim: int = 128,
        qk_pos_emb_head_dim: int = 64,
        v_head_dim: int = 128,
        attention_output_gate: bool = True,
        mla_attn_implementation: str = "flash_attention_2",
        mla_output_gate_type: str = "head_wise",
        short_conv_kernel_size: int = 4,
        linear_conv_kernel_dim: int = 4,
        linear_key_head_dim: int = 128,
        linear_value_head_dim: int = 128,
        linear_num_key_heads: int = 32,
        linear_num_value_heads: int = 32,
        use_full_rank_gate: bool = True,
        kda_gate_lower_bound: float = -5.0,
        kda_backend: str = "fla",
        kda_use_fla_short_conv: bool = True,
        kda_use_fused_rmsnorm_gated: bool = True,
        # MoE
        n_routed_experts: int = 256,
        num_experts_per_tok: int = 8,
        first_k_dense_replace: int = 1,
        n_shared_experts: int = 1,
        moe_shared_experts_intermediate_size: int = 1024,
        enable_multimodal_shared_experts: bool = False,
        moe_router_modality_aware_expert_bias: bool = True,
        moe_router_token_level_modality: bool = True,
        n_group: int = 1,
        topk_group: int = 1,
        norm_topk_prob: bool = True,
        routed_scaling_factor: float = 2.83,
        scoring_func: str = "sigmoid",
        topk_method: str = "quantile_balancing",
        moe_router_enable_expert_bias: bool = True,
        moe_router_expert_bias_update_method: str = "quantile",
        moe_latent_size: int | None = None,
        moe_latent_rmsnorm: bool = False,
        # 通用 LLM 参数
        hidden_act: str = "silu",
        max_position_embeddings: int = 262144,
        rms_norm_eps: float = 1e-6,
        rope_theta: float = 1600000.0,
        rope_scaling: dict = None,
        rope_parameters: dict | None = None,
        attention_bias: bool = False,
        attention_dropout: float = 0.0,
        rotary_percent: float = 0.5,
        # ──── MTP 参数（仅训练用，推理不加载；记录用）────
        mtp_num_layers: int = 1,
        mtp_loss_scaling_factor: float = 0.3,
        # ──── MRoPE 参数 ────
        mrope_section: list = None,
        # ──── 多模态 Token IDs（dsv3_tokenizer4youtu_mllm, vocab=129280）────
        image_token_id: int = 128017,
        video_token_id: int = 128040,
        vision_start_token_id: int = 128015,
        vision_end_token_id: int = 128016,
        # ──── ViT 配置 ────
        vision_config=None,
        # PretrainedConfig 通用参数
        bos_token_id: int = 0,
        eos_token_id: int = 1,
        tie_word_embeddings: bool = False,
        **kwargs,
    ):
        kwargs.setdefault("attn_implementation", mla_attn_implementation)

        # LLM
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.moe_intermediate_size = moe_intermediate_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.num_key_value_heads = num_key_value_heads
        self.head_dim = head_dim

        # KDA + Gated MLA hybrid attention.  train_youtu_v2_pro_120b.sh uses
        # --experimental-attention-variant kda with
        # --linear-attention-freq '([1]*3+[0]*1)*12', where 1=KDA and 0=MLA.
        self.multi_latent_attention = multi_latent_attention
        self.experimental_attention_variant = experimental_attention_variant
        self.linear_attention_pattern = (
            linear_attention_pattern
            if linear_attention_pattern is not None
            else ([1, 1, 1, 0] * (num_hidden_layers // 4))
        )
        self.q_lora_rank = q_lora_rank
        self.kv_lora_rank = kv_lora_rank
        self.qk_nope_head_dim = qk_nope_head_dim
        self.qk_rope_head_dim = qk_rope_head_dim
        self.qk_head_dim = qk_head_dim
        self.qk_pos_emb_head_dim = qk_pos_emb_head_dim
        self.v_head_dim = v_head_dim
        self.attention_output_gate = attention_output_gate
        self.mla_attn_implementation = mla_attn_implementation
        self.mla_output_gate_type = mla_output_gate_type
        self.short_conv_kernel_size = short_conv_kernel_size
        self.linear_conv_kernel_dim = linear_conv_kernel_dim
        self.linear_key_head_dim = linear_key_head_dim
        self.linear_value_head_dim = linear_value_head_dim
        self.linear_num_key_heads = linear_num_key_heads
        self.linear_num_value_heads = linear_num_value_heads
        self.use_full_rank_gate = use_full_rank_gate
        self.kda_gate_lower_bound = kda_gate_lower_bound
        self.kda_backend = kda_backend
        self.kda_use_fla_short_conv = kda_use_fla_short_conv
        self.kda_use_fused_rmsnorm_gated = kda_use_fused_rmsnorm_gated

        # MoE
        self.n_routed_experts = n_routed_experts
        self.num_experts_per_tok = num_experts_per_tok
        self.first_k_dense_replace = first_k_dense_replace
        self.n_shared_experts = n_shared_experts
        self.moe_shared_experts_intermediate_size = moe_shared_experts_intermediate_size
        self.enable_multimodal_shared_experts = enable_multimodal_shared_experts
        self.moe_router_modality_aware_expert_bias = moe_router_modality_aware_expert_bias
        self.moe_router_token_level_modality = moe_router_token_level_modality
        self.n_group = n_group
        self.topk_group = topk_group
        self.norm_topk_prob = norm_topk_prob
        self.routed_scaling_factor = routed_scaling_factor
        self.scoring_func = scoring_func
        self.topk_method = topk_method
        self.moe_router_enable_expert_bias = moe_router_enable_expert_bias
        self.moe_router_expert_bias_update_method = moe_router_expert_bias_update_method
        self.moe_latent_size = moe_latent_size
        self.moe_latent_rmsnorm = moe_latent_rmsnorm

        # 通用
        self.hidden_act = hidden_act
        self.max_position_embeddings = max_position_embeddings
        self.rms_norm_eps = rms_norm_eps
        self.rope_theta = rope_theta
        self.rope_scaling = rope_scaling
        self.attention_bias = attention_bias
        self.attention_dropout = attention_dropout
        self.rotary_percent = rotary_percent

        # MTP（记录用，推理不使用）
        self.mtp_num_layers = mtp_num_layers
        self.mtp_loss_scaling_factor = mtp_loss_scaling_factor

        # MRoPE
        self.mrope_section = mrope_section if mrope_section is not None else [12, 10, 10]
        self.rope_parameters = dict(rope_parameters) if rope_parameters is not None else {}
        self.rope_parameters.setdefault("rope_type", "default")
        self.rope_parameters.setdefault("rope_theta", rope_theta)
        self.rope_parameters.setdefault("mrope_section", self.mrope_section)
        # MG vlm_patch/models/interleaved_mrope.py 使用 THW 交错布局。
        self.rope_parameters.setdefault("mrope_interleaved", True)

        # 多模态 token IDs
        self.image_token_id = image_token_id
        self.video_token_id = video_token_id
        self.vision_start_token_id = vision_start_token_id
        self.vision_end_token_id = vision_end_token_id

        # ViT 配置（默认沿用 Qwen3-VL ViT，merger out_hidden_size=LLM hidden）
        if vision_config is None:
            vision_config = {
                "depth": 27,
                "hidden_act": "gelu_pytorch_tanh",
                "hidden_size": 1152,
                "in_channels": 3,
                "initializer_range": 0.02,
                "intermediate_size": 4304,
                "model_type": "qwen3_vl_moe",
                "num_heads": 16,
                "num_position_embeddings": 2304,
                "out_hidden_size": hidden_size,
                "patch_size": 16,
                "spatial_merge_size": 2,
                "temporal_patch_size": 2,
            }
        if isinstance(vision_config, dict):
            self.vision_config = Qwen3VLVisionConfig(**vision_config)
        elif isinstance(vision_config, Qwen3VLVisionConfig):
            self.vision_config = vision_config
        else:
            self.vision_config = Qwen3VLVisionConfig(**vision_config.to_dict())

        self.vision_config.out_hidden_size = hidden_size
        if not hasattr(self.vision_config, "deepstack_visual_indexes"):
            self.vision_config.deepstack_visual_indexes = []

        super().__init__(
            ignore_keys_at_rope_validation={"mrope_section", "mrope_interleaved"},
            bos_token_id=bos_token_id,
            eos_token_id=eos_token_id,
            tie_word_embeddings=tie_word_embeddings,
            **kwargs,
        )

    def to_dict(self):
        output = super().to_dict()
        ignore_keys = output.get("ignore_keys_at_rope_validation")
        if isinstance(ignore_keys, set):
            output["ignore_keys_at_rope_validation"] = sorted(ignore_keys)
        output["vision_config"] = self.vision_config.to_dict()
        return output

    @property
    def text_config(self):
        """Compatibility alias for Qwen3-VL/vLLM helpers."""
        return self

    def is_kda_layer(self, layer_idx: int) -> bool:
        pattern = self.linear_attention_pattern
        if pattern is None:
            pattern = [1, 1, 1, 0] * (self.num_hidden_layers // 4)
        return (
            self.experimental_attention_variant == "kda"
            and int(pattern[layer_idx]) == 1
        )


__all__ = ["YoutuVLMoEConfig"]
