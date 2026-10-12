"""AutoJev-style full-weight decision model. No autoregressive generation head.

The checkpoint's backbone is copied byte-for-byte from Qwen, while readout rows
are selected from its original LM head. T is used in postprocessing, not CE loss.
"""
from dataclasses import dataclass
import torch
import torch.nn.functional as F
from transformers.utils import ModelOutput
from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model, Qwen3_5PreTrainedModel
from .configuration_autojev import AutoJevConfig


@dataclass
class AutoJevOutput(ModelOutput):
    loss: torch.Tensor | None = None
    logits: torch.Tensor | None = None


class AutoJevForDecisionClassification(Qwen3_5PreTrainedModel):
    config_class = AutoJevConfig
    base_model_prefix = "backbone"

    def __init__(self, config):
        super().__init__(config)
        self.backbone = Qwen3_5Model(config)
        self.readout = torch.nn.Linear(config.text_config.hidden_size, config.max_options, bias=False)
        self.post_init()

    def get_input_embeddings(self):
        return self.backbone.get_input_embeddings()

    def set_input_embeddings(self, value):
        self.backbone.set_input_embeddings(value)

    def forward(self, input_ids=None, attention_mask=None, option_counts=None,
                labels=None, return_dict=True, **kwargs):
        if input_ids is None or input_ids.ndim != 2 or input_ids.shape[1] == 0:
            raise ValueError("input_ids must be a nonempty [batch, length] tensor")
        if input_ids.shape[1] > self.config.max_input_length:
            raise ValueError("Input exceeds max_input_length; truncation is not allowed")
        if attention_mask is None:
            attention_mask = torch.ones_like(input_ids)
        if attention_mask.shape != input_ids.shape or not bool((attention_mask[:, -1] == 1).all()):
            raise ValueError("Left padding required: last prompt position must be valid")
        if option_counts is None:
            raise ValueError("option_counts is required for each input")
        counts = torch.as_tensor(option_counts, device=input_ids.device)
        if counts.dtype == torch.bool or counts.is_floating_point() or counts.shape != (input_ids.shape[0],):
            raise ValueError("option_counts must contain one integer per row")
        if not bool(((counts >= 1) & (counts <= self.config.max_options)).all()):
            raise ValueError("Each question must contain 1..255 options")
        if kwargs.pop("use_cache", False) or kwargs.get("past_key_values") is not None:
            raise ValueError("Decision forward does not accept KV-cache decoding")
        output = self.backbone(input_ids=input_ids, attention_mask=attention_mask,
                               use_cache=False, return_dict=True, **kwargs)
        # Qwen3_5Model.last_hidden_state is AFTER language_model.norm (RMSNorm).
        hidden = output.last_hidden_state[:, -1, :]
        logits = self.readout(hidden).float()
        invalid = torch.arange(self.config.max_options, device=logits.device)[None] >= counts[:, None]
        logits = logits.masked_fill(invalid, -1e9)
        loss = None
        if labels is not None:
            labels = labels.to(logits.device)
            if labels.shape == (len(counts),):
                if labels.is_floating_point() or labels.dtype == torch.bool or not bool(((labels >= 0) & (labels < counts)).all()):
                    raise ValueError("Hard targets must be valid option indices")
                loss = F.cross_entropy(logits, labels.long())
            elif labels.shape == logits.shape:
                target = labels.float()
                if not bool(torch.isfinite(target).all()) or bool((target < 0).any()):
                    raise ValueError("Invalid soft targets")
                if not torch.allclose(target.sum(-1), torch.ones(len(counts), device=target.device), atol=1e-6, rtol=0):
                    raise ValueError("Soft targets must sum to one")
                if bool((target.masked_select(invalid) != 0).any()):
                    raise ValueError("Soft targets assign mass to invalid options")
                loss = -(target * F.log_softmax(logits, dim=-1)).sum(-1).mean()
            else:
                raise ValueError("labels must be [batch] or [batch,255]")
        if not return_dict:
            return (loss, logits) if loss is not None else (logits,)
        return AutoJevOutput(loss=loss, logits=logits)


AutoJevConfig.register_for_auto_class()
AutoJevForDecisionClassification.register_for_auto_class("AutoModel")
