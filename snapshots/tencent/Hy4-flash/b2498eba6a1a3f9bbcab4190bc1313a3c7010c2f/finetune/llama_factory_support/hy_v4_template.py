"""
HY4 Flash chat template registration for LLaMA Factory.

This module registers templates for the HY4 Flash model (hy_v4_flash).
The Flash model uses 'opensource' namespace for special tokens.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from llamafactory.data.template import ReasoningTemplate, register_template
from llamafactory.data.formatter import EmptyFormatter, StringFormatter
from llamafactory.data.mm_plugin import (
    BasePlugin,
    get_mm_plugin,
    register_mm_plugin,
)
from llamafactory.extras.constants import IMAGE_PLACEHOLDER

if TYPE_CHECKING:
    import torch
    from llamafactory.data.mm_plugin import MMProcessor, ImageInput, VideoInput, AudioInput

@dataclass
class HYV4VLPlugin(BasePlugin):
    """Multimodal plugin for HYV4-VL models in LLaMA Factory.

    Replaces <image> in messages with N copies of the real image placeholder
    token, where N = image_grid_thw.prod() / merge_length.
    """

    def _get_mm_inputs(self, images, videos, audios, processor):
        """Process images/videos through the HYV4VL image processor."""
        image_processor = getattr(processor, "image_processor", None)
        mm_inputs = {}
        if len(images) != 0 and image_processor is not None:
            images = self._regularize_images(
                images,
                image_max_pixels=getattr(processor, "image_max_pixels",
                    getattr(processor, "max_pixels", 4194304)),
                image_min_pixels=getattr(processor, "image_min_pixels",
                    getattr(processor, "min_pixels", 4096)),
            )["images"]
            mm_inputs.update(image_processor(images, return_tensors="pt"))
        if len(videos) != 0:
            video_processor = getattr(processor, "video_processor", image_processor)
            if video_processor is not None:
                videos_data = self._regularize_videos(
                    videos,
                    image_max_pixels=getattr(processor, "video_max_pixels", 256 * 256),
                    image_min_pixels=getattr(processor, "video_min_pixels", 16 * 16),
                    video_fps=getattr(processor, "video_fps", 2.0),
                    video_maxlen=getattr(processor, "video_maxlen", 128),
                )["videos"]
                import inspect
                if "videos" in inspect.signature(video_processor.preprocess).parameters:
                    mm_inputs.update(video_processor(images=None, videos=videos_data, return_tensors="pt"))
                else:
                    mm_inputs.update(video_processor(videos_data, return_tensors="pt"))
        return mm_inputs

    @staticmethod
    def _num_frame_tokens(grid_h, grid_w, merge_size):
        """Compute the number of tokens per frame, including one newline token per merged row.

        Must match HYV4VLProcessor._num_frame_tokens in transformers-hy4vl.
        """
        return (grid_h // merge_size) * (grid_w // merge_size + 1)

    def process_messages(self, messages, images, videos, audios, processor):
        """Replace <image> placeholders with expanded image placeholder tokens."""
        self._validate_input(processor, images, videos, audios)
        self._validate_messages(messages, images, videos, audios)
        num_image_tokens, num_video_tokens = 0, 0
        messages = deepcopy(messages)
        image_processor = getattr(processor, "image_processor", None)
        merge_size = getattr(image_processor, "merge_size", 2)
        if self.expand_mm_tokens and (len(images) > 0 or len(videos) > 0):
            mm_inputs = self._get_mm_inputs(images, videos, audios, processor)
            image_grid_thw = mm_inputs.get("image_grid_thw", [])
            video_grid_thw = mm_inputs.get("video_grid_thw", [])
        else:
            image_grid_thw = [None] * len(images)
            video_grid_thw = [None] * len(videos)
        for message in messages:
            content = message["content"]
            while IMAGE_PLACEHOLDER in content:
                if self.expand_mm_tokens and num_image_tokens < len(image_grid_thw):
                    _, grid_h, grid_w = image_grid_thw[num_image_tokens]
                    image_seqlen = self._num_frame_tokens(grid_h, grid_w, merge_size)
                else:
                    image_seqlen = 1
                content = content.replace(IMAGE_PLACEHOLDER, self.image_token * image_seqlen, 1)
                num_image_tokens += 1
            if self.video_token is not None:
                from llamafactory.extras.constants import VIDEO_PLACEHOLDER
                while VIDEO_PLACEHOLDER in content:
                    if self.expand_mm_tokens and num_video_tokens < len(video_grid_thw):
                        grid_t, grid_h, grid_w = video_grid_thw[num_video_tokens]
                        video_seqlen = grid_t * self._num_frame_tokens(grid_h, grid_w, merge_size)
                    else:
                        video_seqlen = 1
                    content = content.replace(VIDEO_PLACEHOLDER, self.video_token * video_seqlen, 1)
                    num_video_tokens += 1
            message["content"] = content
        return messages

# Register the custom plugin
register_mm_plugin("hyv4_flash_vl", HYV4VLPlugin)

# ---------------------------------------------------------------------------
# HY4 Flash (MoE, pure text) chat template
# Uses 'opensource' namespace for special tokens
# ---------------------------------------------------------------------------

register_template(
    name="hy_v4_flash",
    template_class=ReasoningTemplate,
    format_user=StringFormatter(slots=["<｜hy_start:opensource｜>user<｜hy_middle:opensource｜>{{content}}<｜hy_end:opensource｜><｜hy_start:opensource｜>assistant<｜hy_middle:opensource｜>"]),
    format_assistant=StringFormatter(slots=["{{content}}<｜hy_end:opensource｜>"]),
    format_system=StringFormatter(slots=["<｜hy_start:opensource｜>system<｜hy_middle:opensource｜>{{content}}<｜hy_end:opensource｜>"]),
    default_system="<｜reasoning_mode:opensource｜>reasoning_effort:no_think",
    format_prefix=EmptyFormatter(slots=[]),
    thought_words=("<think:opensource>", "</think:opensource>"),
    stop_words=["<｜hy_end:opensource｜>"],
    efficient_eos=False,
)

# ---------------------------------------------------------------------------
# HY4 Flash VL (Vision-Language) chat template
# Uses 'opensource' namespace for special tokens
# ---------------------------------------------------------------------------

register_template(
    name="hy_v4_flash_vl",
    template_class=ReasoningTemplate,
    format_user=StringFormatter(slots=["<｜hy_start:opensource｜>user<｜hy_middle:opensource｜>{{content}}<｜hy_end:opensource｜><｜hy_start:opensource｜>assistant<｜hy_middle:opensource｜>"]),
    format_assistant=StringFormatter(slots=["{{content}}<｜hy_end:opensource｜>"]),
    format_system=StringFormatter(slots=["<｜hy_start:opensource｜>system<｜hy_middle:opensource｜>{{content}}<｜hy_end:opensource｜>"]),
    default_system="<｜reasoning_mode:opensource｜>reasoning_effort:no_think",
    format_prefix=EmptyFormatter(slots=[]),
    thought_words=("<think:opensource>", "</think:opensource>"),
    stop_words=["<｜hy_end:opensource｜>"],
    efficient_eos=False,
    mm_plugin=get_mm_plugin(
        name="hyv4_flash_vl",
        image_token="<｜hy_image\u2581pad:opensource｜>",
        video_token="<｜hy_video\u2581pad:opensource｜>",
    ),
)
