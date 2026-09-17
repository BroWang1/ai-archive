import math
from typing import Iterable, Optional, Tuple, List, TypedDict, Literal, Union, overload

from PIL import Image
import torch
import numpy as np
import torchvision
from torch import nn
from torch.nn import functional as F, LayerNorm
from torchvision.transforms.functional import InterpolationMode
from transformers.activations import ACT2FN
from torchvision import transforms
from torchvision.transforms.functional import InterpolationMode


from .configuration_step3 import Step3VisionEncoderConfig



def get_abs_pos(abs_pos, tgt_size):
    dim = abs_pos.size(-1)
    abs_pos_new = abs_pos.squeeze(0)
    cls_token, old_pos_embed = abs_pos_new[:1], abs_pos_new[1:]

    src_size = int(math.sqrt(abs_pos_new.shape[0] - 1))
    tgt_size = int(math.sqrt(tgt_size))
    dtype = abs_pos.dtype

    if src_size != tgt_size:
        old_pos_embed = old_pos_embed.view(1, src_size, src_size,
                                           dim).permute(0, 3, 1,
                                                        2).contiguous()
        old_pos_embed = old_pos_embed.to(torch.float32)
        new_pos_embed = F.interpolate(
            old_pos_embed,
            size=(tgt_size, tgt_size),
            mode='bicubic',
            antialias=True,
            align_corners=False,
        ).to(dtype)
        new_pos_embed = new_pos_embed.permute(0, 2, 3, 1)
        new_pos_embed = new_pos_embed.view(tgt_size * tgt_size, dim)
        vision_pos_embed = torch.cat([cls_token, new_pos_embed], dim=0)
        vision_pos_embed = vision_pos_embed.view(1, tgt_size * tgt_size + 1,
                                                 dim)
        return vision_pos_embed
    else:
        return abs_pos


class StepCLIPVisionEmbeddings(nn.Module):

    def __init__(self, config: Step3VisionEncoderConfig):
        super().__init__()
        self.config = config
        self.embed_dim = config.hidden_size
        self.image_size = config.image_size
        self.patch_size = config.patch_size

        self.class_embedding = nn.Parameter(torch.randn(1, self.embed_dim))

        self.patch_embedding = nn.Conv2d(
            in_channels=config.num_channels,
            out_channels=self.embed_dim,
            kernel_size=self.patch_size,
            stride=self.patch_size,
            bias=True,
        )

        self.num_patches = (self.image_size // self.patch_size)**2
        self.pad_tp_size = 4  # hard code for padding
        # To load the pretrained weights, we still use P+1 as the seqlen
        self.position_embedding = torch.nn.Embedding(self.num_patches + 1,
                                                     self.embed_dim)
        self.register_buffer("position_ids",
                             torch.arange(self.num_patches + 1).expand(
                                 (1, -1)),
                             persistent=False)
        
    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        batch_size = pixel_values.shape[0]
        target_dtype = self.patch_embedding.weight.dtype
        patch_embeds = self.patch_embedding(pixel_values.to(
            dtype=target_dtype))  # shape = [*, width, grid, grid]
        patch_embeds = patch_embeds.flatten(2).transpose(1, 2)

        # pad
        class_embeds = self.class_embedding.expand(batch_size, 1, -1)
        embeddings = torch.cat([class_embeds, patch_embeds], dim=1)
        embeddings = embeddings + get_abs_pos(
            self.position_embedding(self.position_ids), patch_embeds.size(1))
        embeddings = torch.cat([
            embeddings[:, 0, :].unsqueeze(1).repeat(1, self.pad_tp_size - 1, 1), embeddings
        ], dim=1)
        return embeddings


class StepCLIPAttention(nn.Module):
    def __init__(self, dim: int, num_heads: int = 16) -> None:
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        self.qkv_proj = nn.Linear(dim, dim * 3, bias=True)
        self.out_proj = nn.Linear(dim, dim)
        self.scale = self.head_dim**-0.5

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        b, s, _ = hidden_states.shape
        q, k, v = (
            self.qkv_proj(hidden_states)
            .reshape(b, s, 3, self.num_heads, self.head_dim)
            .permute(2, 0, 3, 1, 4)
            .unbind(0)
        )
        attn_output = F.scaled_dot_product_attention(
            q, k, v,
            is_causal=False,
            scale=self.scale
        )
        attn_output = attn_output.permute(0, 2, 1, 3).reshape(b, s, -1)
        return self.out_proj(attn_output)


class StepCLIPMLP(nn.Module):
    def __init__(self, dim: int, intermediate_size: int, hidden_act: str) -> None:
        super().__init__()
        self.fc1 = nn.Linear(dim, intermediate_size)
        self.act = ACT2FN[hidden_act]
        self.fc2 = nn.Linear(intermediate_size, dim)

    def forward(self, x) -> torch.Tensor:
        return self.fc2(self.act(self.fc1(x)))


class StepCLIPEncoderLayer(nn.Module):
    def __init__(self, config, attn_implementation: str = "sdpa") -> None:
        super().__init__()
        self.embed_dim = config.hidden_size
        self.layer_norm1 = LayerNorm(self.embed_dim, eps=1e-6)
        self.layer_norm2 = LayerNorm(self.embed_dim, eps=1e-6)
        
        self.self_attn = StepCLIPAttention(
            self.embed_dim, num_heads=config.num_attention_heads
        )
        self.mlp = StepCLIPMLP(dim=self.embed_dim, intermediate_size=config.intermediate_size, hidden_act=config.hidden_act)

    def forward(self, hidden_states) -> torch.Tensor:
        hidden_states = hidden_states + self.layer_norm1(self.self_attn(hidden_states))
        hidden_states = hidden_states + self.layer_norm2(self.mlp(hidden_states))
        return hidden_states
    

class StepCLIPEncoder(nn.Module):
    """
    Transformer encoder consisting of `config.num_hidden_layers` self attention layers. Each layer is a
    [`StepCLIPEncoderLayer`].

    Args:
        config: Step3VisionEncoderConfig
    """

    def __init__(self, config: Step3VisionEncoderConfig):
        super().__init__()
        self.config = config
        self.layers = nn.ModuleList([StepCLIPEncoderLayer(config) for _ in range(config.num_hidden_layers)])

    def forward(
        self,
        inputs_embeds,
    ) -> torch.Tensor:

        hidden_states = inputs_embeds
        for encoder_layer in self.layers:
            hidden_states = encoder_layer(
                hidden_states,
            )

        return hidden_states
    
class StepCLIPVisionTransformer(nn.Module):
    def __init__(self, config: Step3VisionEncoderConfig):
        super().__init__()
        self.config = config
        self.image_size = config.image_size
        self.embeddings = StepCLIPVisionEmbeddings(config)
        self.transformer = StepCLIPEncoder(config)

    def forward(
        self,
        pixel_values: torch.Tensor,
    ):
        hidden_states = self.embeddings(pixel_values)
        hidden_states = self.transformer(inputs_embeds=hidden_states)
        return hidden_states
