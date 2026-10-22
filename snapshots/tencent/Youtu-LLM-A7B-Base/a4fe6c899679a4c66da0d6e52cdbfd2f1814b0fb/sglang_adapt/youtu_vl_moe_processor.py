# SPDX-License-Identifier: Apache-2.0
"""UTU-VL Tiny MoE Pro SGLang multimodal processor."""

from sglang.srt.multimodal.processors.qwen_vl import QwenVLImageProcessor

from sglang_adapt.youtu_vl_moe import YoutuVLMoEForConditionalGeneration


class YoutuVLImageProcessor(QwenVLImageProcessor):
    """Reuse Qwen3-VL image/video processing and bind the Tiny MoE Pro arch."""

    models = [YoutuVLMoEForConditionalGeneration]

    def __init__(self, hf_config, server_args, _processor, *args, **kwargs):
        super().__init__(hf_config, server_args, _processor, *args, **kwargs)
        # Tiny MoE Pro uses the same Qwen3-VL ViT + MRoPE preprocessing.  SGLang's
        # rope-index helper dispatches by model_type, so redirect its internal
        # processor model_type to qwen3_vl while leaving hf_config.model_type as
        # youtu_vl_moe for model loading.
        self.model_type = "qwen3_vl"
