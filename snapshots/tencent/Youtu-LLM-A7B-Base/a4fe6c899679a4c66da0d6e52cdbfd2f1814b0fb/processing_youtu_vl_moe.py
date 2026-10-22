# coding=utf-8
"""
UTU-VL MoE 处理器（适配 transformers 5.3）

直接复用 Qwen3VLProcessor，UTU-VL MoE 使用与 V4 相同的图像处理流程和 tokenizer 特殊 token 设置。
- image_token_id = 128017 (<|image_pad|>)
- video_token_id = 128040 (<｜place▁holder▁no▁40｜>, 与 Stage3 VIDEO_TOKEN_ID 一致；128032 在 union tokenizer 中是字面量 ｜DSML｜)
"""

from transformers.models.qwen3_vl import Qwen3VLProcessor


class YoutuVLMoEProcessor(Qwen3VLProcessor):
    """
    UTU-VL MoE processor.

    It is intentionally a thin Qwen3VLProcessor subclass with UTU-VL token
    aliases populated on the tokenizer.
    """

    image_token = "<|image_pad|>"
    video_token = "<｜place▁holder▁no▁40｜>"
    vision_start_token = "<|vision_start|>"
    vision_end_token = "<|vision_end|>"

    tokenizer_class = ("PreTrainedTokenizerFast",)

    def __init__(self, image_processor=None, tokenizer=None, video_processor=None, chat_template=None, **kwargs):
        if tokenizer is not None:
            tokenizer.image_token = self.image_token
            tokenizer.video_token = self.video_token
            tokenizer.vision_start_token = self.vision_start_token
            tokenizer.vision_end_token = self.vision_end_token
            tokenizer.image_token_id = tokenizer.convert_tokens_to_ids(self.image_token)
            tokenizer.video_token_id = tokenizer.convert_tokens_to_ids(self.video_token)
            tokenizer.vision_start_token_id = tokenizer.convert_tokens_to_ids(self.vision_start_token)
            tokenizer.vision_end_token_id = tokenizer.convert_tokens_to_ids(self.vision_end_token)
        super().__init__(image_processor, tokenizer, video_processor, chat_template=chat_template, **kwargs)


__all__ = ["YoutuVLMoEProcessor"]
