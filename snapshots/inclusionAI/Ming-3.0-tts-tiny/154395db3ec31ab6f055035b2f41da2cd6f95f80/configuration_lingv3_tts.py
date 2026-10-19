"""Configuration for the standalone LingV3 TTS Hugging Face model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from transformers.configuration_utils import PretrainedConfig

from .configuration_audio_vae import AudioVAEconfig
from .configuration_bailing_moe_v3 import BailingMoeV3Config


DEFAULT_TTS_CONFIG: Dict[str, Any] = {
    "protocol_version": "legacy_antmmf",
    "prompt_format": "legacy_antmmf",
    "tokenizer_contract": "legacy_antmmf",
    "sampling_contract": "native_fp32",
    "sample_rate": 44100,
    "latent_dim": 64,
    "speaker_embedding_dim": 192,
    "patch_size": 1,
    "history_size": 1,
    "audio_patch_token_id": 157164,
    "audio_start_token_id": 157165,
    "audio_end_token_id": 157166,
    "speaker_start_token_id": 157175,
    "speaker_end_token_id": 157176,
    "minimum_decode_steps": 5,
}

DEFAULT_AGGREGATOR_CONFIG: Dict[str, Any] = {
    "in_channels": 64,
    "hidden_size": 1024,
    "depth": 8,
    "num_heads": 16,
    "mlp_ratio": 4,
    "dropout": 0.1,
    "qk_norm": None,
    "pe_attn_head": None,
    "attn_backend": "torch",
    "attn_mask_enabled": False,
}

DEFAULT_FLOW_CONFIG: Dict[str, Any] = {
    "z_channels": 64,
    "flow_model_type": None,
    "hidden_size": 1024,
    "depth": 16,
    "num_heads": 16,
    "mlp_ratio": 4,
    "dropout": 0.1,
    "qk_norm": None,
    "pe_attn_head": None,
    "attn_backend": "torch",
    "attn_mask_enabled": False,
}


class LingV3TTSConfig(PretrainedConfig):
    """Nested configuration for the LingV3 backbone and TTS modules."""

    model_type = "lingv3_tts"
    is_composition = True

    def __init__(
        self,
        llm_config: Optional[Dict[str, Any] | BailingMoeV3Config] = None,
        audio_config: Optional[Dict[str, Any] | AudioVAEconfig] = None,
        tts_config: Optional[Dict[str, Any]] = None,
        aggregator_config: Optional[Dict[str, Any]] = None,
        flow_config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        if llm_config is None:
            llm_config = {}
        self.llm_config = (
            BailingMoeV3Config(**llm_config)
            if isinstance(llm_config, dict)
            else llm_config
        )

        if audio_config is None:
            audio_config = {}
        self.audio_config = (
            AudioVAEconfig(**audio_config)
            if isinstance(audio_config, dict)
            else audio_config
        )

        supplied_tts = dict(tts_config or {})
        # Checkpoints produced before protocol_version was introduced used
        # the later thinking prompt and token rows.  Infer that one legacy
        # metadata case so existing converted models remain loadable.
        if "protocol_version" not in supplied_tts:
            supplied_patch_id = supplied_tts.get("audio_patch_token_id")
            if supplied_patch_id == 157168:
                supplied_tts["protocol_version"] = "thinking_v1"
        selected_protocol = supplied_tts.get(
            "protocol_version", DEFAULT_TTS_CONFIG["protocol_version"]
        )
        supplied_tts.setdefault("prompt_format", selected_protocol)
        supplied_tts.setdefault("tokenizer_contract", selected_protocol)
        supplied_tts.setdefault(
            "sampling_contract",
            (
                "native_fp32"
                if selected_protocol == "legacy_antmmf"
                else "device_dtype"
            ),
        )
        merged_tts = deepcopy(DEFAULT_TTS_CONFIG)
        merged_tts.update(supplied_tts)
        self.tts_config = merged_tts

        merged_aggregator = deepcopy(DEFAULT_AGGREGATOR_CONFIG)
        merged_aggregator.update(aggregator_config or {})
        self.aggregator_config = merged_aggregator

        merged_flow = deepcopy(DEFAULT_FLOW_CONFIG)
        merged_flow.update(flow_config or {})
        self.flow_config = merged_flow

        kwargs.setdefault(
            "architectures", ["LingV3TTSForConditionalGeneration"]
        )
        # This is a composite checkpoint whose LingV3 input embedding and
        # language-model head are two independently trained matrices.  The
        # PretrainedConfig default is True and would silently collapse them
        # during PreTrainedModel.tie_weights().
        kwargs.setdefault("tie_word_embeddings", False)
        kwargs.setdefault(
            "auto_map",
            {
                "AutoConfig": "configuration_lingv3_tts.LingV3TTSConfig",
                "AutoModel": (
                    "modeling_lingv3_tts."
                    "LingV3TTSForConditionalGeneration"
                ),
            },
        )
        super().__init__(**kwargs)

    def get_text_config(
        self, decoder: Optional[bool] = None, encoder: Optional[bool] = None
    ) -> BailingMoeV3Config:
        """Return the actual LingV3 text config to Hugging Face helpers."""

        return self.llm_config

    def to_dict(self) -> Dict[str, Any]:
        output = super().to_dict()
        output["llm_config"] = self.llm_config.to_dict()
        output["audio_config"] = self.audio_config.to_dict()
        output["tts_config"] = deepcopy(self.tts_config)
        output["aggregator_config"] = deepcopy(self.aggregator_config)
        output["flow_config"] = deepcopy(self.flow_config)
        output["model_type"] = self.model_type
        return output
