"""Configuration for a Qwen backbone with a dynamic-option decision head."""
import math
from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5Config


class AutoJevConfig(Qwen3_5Config):
    model_type = "autojev_decision"

    def __init__(self, codes=None, token_ids=None, max_options=255, temperature=1.0,
                 base_model="Qwen/Qwen3.8-27B", initialization_step=0,
                 max_input_length=8192, **kwargs):
        super().__init__(**kwargs)
        if max_options != 255:
            raise ValueError("This artifact uses exactly 255 option positions")
        if not math.isfinite(temperature) or temperature <= 0:
            raise ValueError("temperature must be positive and finite")
        self.max_options = max_options
        self.codes = list(codes or [])
        self.token_ids = list(token_ids or [])
        if self.codes or self.token_ids:
            if len(self.codes) != max_options or len(set(self.codes)) != max_options:
                raise ValueError("Expected 255 unique answer codes")
            if len(self.token_ids) != max_options or len(set(self.token_ids)) != max_options:
                raise ValueError("Expected 255 unique answer token IDs")
            if any(type(i) is not int or not 0 <= i < self.text_config.vocab_size for i in self.token_ids):
                raise ValueError("Answer token IDs outside base vocabulary")
        self.temperature = float(temperature)
        self.base_model = base_model
        self.initialization_step = initialization_step
        self.max_input_length = int(max_input_length)
        if self.max_input_length < 1:
            raise ValueError("max_input_length must be positive")
