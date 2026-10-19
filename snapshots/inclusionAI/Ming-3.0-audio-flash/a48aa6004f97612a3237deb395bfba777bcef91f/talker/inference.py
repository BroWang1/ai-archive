"""Synchronous Ming Talker, adapted from talker_transformers_inference.

Native prompt formatting, text normalization, CFM, DiT, Aggregator and AudioVAE
are retained. Qwen2 uses the installed Transformers cache API; inference needs
neither vLLM nor engine workers, CUDA graphs, thread pools or temporary files.
"""

from contextlib import nullcontext
from functools import cached_property
from pathlib import Path
import random
import re

import numpy as np
import onnxruntime
from safetensors.torch import load_file
import torch
from torch import nn
import torchaudio
from torchaudio.compliance import kaldi
from transformers import AutoTokenizer, Qwen2Config, Qwen2Model

from .AudioVAE.configuration_audio_vae import AudioVAEconfig
from .AudioVAE.modeling_audio_vae import AudioVAE
from .configuration_bailing_talker import BailingTalkerConfig
from .front.number_en import normalize_numbers
from .front.text_segment_cut import cut_text_by_semantic_length, is_chinese
from .front.toolkit import (
    add_period,
    normalize_text_kit,
    preprosess_text,
    tokenize_mixed_text_iterator,
)
from .talker_module.aggregator import Aggregator
from .talker_module.cfm import CFM, get_epss_timesteps
from .talker_module.dit import DiT
from .talker_tn.talker_tn import TalkerTN
from .tts_prompt import (
    DEFAULT_TTS_PROMPT,
    append_optional_target_language,
    build_task_instruction,
    contains_paralinguistic_tag,
    preserve_multilingual_text,
    protect_paralinguistic_tags,
    resolve_request_language,
    restore_paralinguistic_tags,
    target_language_from_prompt,
)


class MingTalker(nn.Module):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.config = BailingTalkerConfig.from_pretrained(path)
        self.tokenizer = AutoTokenizer.from_pretrained(path / "llm")
        llm_config = Qwen2Config.from_pretrained(path / "llm")
        llm_config._attn_implementation = "sdpa"
        self.model = Qwen2Model(llm_config)
        self.cfm = CFM(
            DiT(llm_cond_dim=llm_config.hidden_size, **self.config.flowmodel),
            steps=self.config.steps,
        )
        self.aggregator = Aggregator(
            llm_input_dim=llm_config.hidden_size, **self.config.aggregator
        )
        self.stop_head = nn.Linear(llm_config.hidden_size, 2)
        self.spk_head = nn.Linear(192, llm_config.hidden_size)
        self.normalizer = TalkerTN()
        self.latent_dim = 64
        self.patch_size = self.config.patch_size
        self.history_patch_size = self.config.history_patch_size

    @classmethod
    def from_pretrained(cls, path, *, dtype=torch.bfloat16, device="cuda:0"):
        path = Path(path).resolve()
        model = cls(path).to(dtype=dtype)
        weights = load_file(str(path / "model.safetensors"))
        # Recent x-transformers computes RoPE frequencies instead of persisting them.
        state_keys = model.state_dict().keys()
        weights = {
            key: value
            for key, value in weights.items()
            if not (key.endswith("rotary_embed.inv_freq") and key not in state_keys)
        }
        model.load_state_dict(weights, strict=True)
        vae_config = AudioVAEconfig.from_pretrained(path / "vae")
        vae_config._attn_implementation = "eager"
        for section in (
            vae_config.enc_kwargs["backbone"],
            vae_config.dec_kwargs["backbone"],
        ):
            section["_attn_implementation"] = "eager"
            section["attn_implementation"] = "eager"
        model.audio_vae = AudioVAE(vae_config).to(dtype=dtype)
        model.audio_vae.load_state_dict(
            load_file(str(path / "vae/model.safetensors")), strict=True
        )
        return model.to(device).eval()

    @property
    def device(self):
        return next(self.model.parameters()).device

    @property
    def dtype(self):
        return next(self.model.parameters()).dtype

    @cached_property
    def speaker_encoder(self):
        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        options.intra_op_num_threads = 2
        return onnxruntime.InferenceSession(
            str(self.path / "campplus.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    def reference_features(self, reference, continuation):
        waveform = torch.as_tensor(reference["samples"], dtype=torch.float32).reshape(
            1, -1
        )
        sample_rate = reference["sample_rate"]
        speaker_waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
        features = kaldi.fbank(
            speaker_waveform, num_mel_bins=80, dither=0, sample_frequency=16000
        )
        features -= features.mean(dim=0, keepdim=True)
        embedding = self.speaker_encoder.run(
            None,
            {self.speaker_encoder.get_inputs()[0].name: features.unsqueeze(0).numpy()},
        )[0]
        speaker = [
            self.spk_head(
                torch.as_tensor(
                    embedding, device=self.device, dtype=self.dtype
                ).reshape(1, 192)
            )
        ]
        if not continuation:
            return speaker, None, None
        waveform = torchaudio.functional.resample(
            waveform, sample_rate, self.audio_vae.config.sample_rate
        )
        alignment = (
            self.audio_vae.encoder.hop_size
            * max(1, self.audio_vae.encoder.patch_size)
            * self.patch_size
        )
        waveform = nn.functional.pad(waveform, ((-waveform.shape[-1]) % alignment, 0))
        latents, _ = self.audio_vae.encode_latent(
            waveform.to(device=self.device, dtype=self.dtype),
            torch.tensor([waveform.shape[-1]], device=self.device),
        )
        embeddings = self.aggregator(
            latents.reshape(-1, self.patch_size, self.latent_dim)
        )
        return (
            speaker,
            latents,
            embeddings.reshape(1, -1, self.model.config.hidden_size),
        )

    def text_fragments(self, value, max_length=50):
        """Mirror the legacy TTS-family buffering before TN."""
        streaming_text = []
        count = 0
        for index, ele in enumerate(tokenize_mixed_text_iterator(value)):
            if len(ele) == 0:
                continue
            should_process = False
            if ele[-1] in "！？。!?" and (
                len(streaming_text) >= 12 or (count > 0 and len(streaming_text) >= 8)
            ):
                should_process = True
                streaming_text.append(ele)
            elif ele[-1] in "，," and len(streaming_text) >= 36:
                should_process = True
                streaming_text.append(ele)
            elif (
                ele[-1] == "."
                and (
                    len(streaming_text) >= 12
                    or (count > 0 and len(streaming_text) >= 8)
                )
                and (not bool(re.search("[0-9]", streaming_text[-1][-1])))
            ):
                should_process = True
                streaming_text.append(ele)
            elif ele[-1] == "\n":
                if len(streaming_text) > 0:
                    if re.search("[\\u4e00-\\u9fff]", "".join(streaming_text)):
                        if re.search("[\\u4e00-\\u9fff]", streaming_text[-1][-1]):
                            ele = "，"
                            streaming_text.append(ele)
                    else:
                        if len(ele) > 1 and re.search("[a-zA-Z]", ele[-2]):
                            ele = ele[:-1] + "."
                        else:
                            ele = ele[:-1]
                        streaming_text.append(ele)
                if len(streaming_text) >= 12 or (
                    count > 0 and len(streaming_text) >= 8
                ):
                    should_process = True
            else:
                streaming_text.append(ele)
                continue
            if should_process:
                buffered_text = preprosess_text("".join(streaming_text))
                text_list = cut_text_by_semantic_length(buffered_text, max_length)[
                    "fragments"
                ]
                count += len(text_list)
                yield from text_list
                streaming_text = []
        if streaming_text and re.search(
            "[a-zA-Z\\u4e00-\\u9fff1-9]", "".join(streaming_text)
        ):
            buffered_text = preprosess_text("".join(streaming_text))
            buffered_text = add_period(buffered_text)
            yield from cut_text_by_semantic_length(buffered_text, max_length)[
                "fragments"
            ]

    def input_embeddings(
        self, text, prompt, instruction, speaker, prompt_text, prompt_embeddings
    ):
        encode = self.tokenizer.encode
        speaker_tokens = []
        for index, _ in enumerate(speaker or []):
            speaker_tokens += (
                encode(f"  speaker_{index + 1}:")
                + encode("<|vision_start|>")
                + encode("<|vision_pad|>")
                + encode("<|vision_end|>\n")
            )
        continuation = prompt_embeddings is not None and prompt_text is not None
        tokens = (
            encode("<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n")
            + encode("<|im_start|>user\n")
            + encode(prompt)
            + speaker_tokens
            + encode(" Text input:\n")
            + (encode(prompt_text) if continuation else [])
            + encode(text)
            + encode("<|im_end|>\n")
            + encode("<|im_start|>assistant\n")
            + (encode(instruction) + encode("<|im_end|>") if instruction else [])
            + encode("<audio>")
            + (
                encode("<audioPatch>") * prompt_embeddings.shape[1]
                if continuation
                else []
            )
        )
        ids = torch.tensor([tokens], device=self.device)
        embeddings = self.model.get_input_embeddings()(ids)
        if speaker:
            positions = torch.where(ids[0] == encode("<|vision_start|>")[0])[0]
            for position, embedding in zip(positions, speaker):
                embeddings[0, position + 1] = embedding
        if continuation:
            start = torch.where(ids[0] == encode("<audio>")[0])[0][0] + 1
            embeddings[0, start : start + prompt_embeddings.shape[1]] = (
                prompt_embeddings[0]
            )
        return embeddings

    def generate_latents(
        self, embeddings, prompt_latents, max_steps, cfg, sigma, temperature
    ):
        history = embeddings.new_zeros(1, self.history_patch_size, self.latent_dim)
        if prompt_latents is not None:
            tail = prompt_latents[:, -self.history_patch_size :]
            history[:, -tail.shape[1] :] = tail
        past = None
        latents = []
        for step in range(max_steps):
            output = self.model(
                inputs_embeds=embeddings, past_key_values=past, use_cache=True
            )
            past = output.past_key_values
            hidden = output.last_hidden_state[:, -1:]
            noise = torch.randn(
                (1, self.patch_size, self.latent_dim),
                device=self.device,
                dtype=self.dtype,
            )
            timesteps = get_epss_timesteps(self.config.steps, self.device, self.dtype)
            sde_noise = torch.randn(
                (self.config.steps, *noise.shape), device=self.device, dtype=self.dtype
            )
            latent = self.cfm.sample(
                hidden,
                history,
                noise,
                timesteps,
                hidden.new_tensor([cfg, sigma, temperature]),
                sde_noise,
            )
            embeddings = self.aggregator(latent)
            latents.append(latent)
            history = torch.cat([history, latent], dim=1)[:, -self.history_patch_size :]
            stop = self.stop_head(hidden[:, -1]).softmax(dim=-1)[0, 1]
            if step > 3 and stop.item() > 0.5:
                break
        return torch.cat(latents, dim=1)

    @torch.inference_mode()
    def synthesize(
        self,
        text,
        *,
        ip_name="灵小柔",
        reference=None,
        prompt_text=None,
        language=None,
        max_steps=1000,
        seed=None,
        cfg=2.0,
        sigma=0.25,
        temperature=0.0,
    ):
        context = (
            torch.cuda.device(self.device)
            if self.device.type == "cuda"
            else nullcontext()
        )
        with context, torch.autocast(device_type=self.device.type, dtype=self.dtype):
            if seed is not None:
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)
            text = re.sub(r"^[A-Za-z]{1,16}\t", "", text)
            task = "IP" if reference is None else "TTS"
            language, text = resolve_request_language(
                text, language=language, taskname=task
            )
            prompt = append_optional_target_language(DEFAULT_TTS_PROMPT, language)
            instruction = (
                build_task_instruction("IP", ip=ip_name) if reference is None else None
            )
            skip_tn = preserve_multilingual_text(target_language_from_prompt(prompt))
            speaker, prompt_latents, prompt_embeddings = (
                self.reference_features(reference, prompt_text is not None)
                if reference is not None
                else (None, None, None)
            )
            chunks = []
            for fragment in self.text_fragments(text):
                protected = contains_paralinguistic_tag(fragment)
                fragment = (
                    protect_paralinguistic_tags(fragment) if protected else fragment
                )
                if not skip_tn:
                    if not is_chinese(fragment):
                        fragment = normalize_numbers(fragment)
                    fragment = normalize_text_kit(
                        self.normalizer.normalize(fragment)
                    ).lstrip("，")
                if protected:
                    fragment = restore_paralinguistic_tags(fragment)
                embeddings = self.input_embeddings(
                    fragment,
                    prompt,
                    instruction,
                    speaker,
                    prompt_text,
                    prompt_embeddings,
                )
                latents = self.generate_latents(
                    embeddings, prompt_latents, max_steps, cfg, sigma, temperature
                )
                waveform, _, _ = self.audio_vae.decode(
                    latents, use_cache=False, last_chunk=True
                )
                chunks.append(
                    self.silence_holder(
                        waveform.detach().float().cpu(),
                        self.audio_vae.config.sample_rate,
                    )[0]
                )
            return {
                "audio": torch.cat(chunks, dim=-1),
                "sr": self.audio_vae.config.sample_rate,
            }

    @staticmethod
    def silence_holder(
        speech, sample_rate, sil_cache=None, last_chunk=True, sil_th=1e-3, last_sil=0.3
    ):
        if speech.numel() == 0:
            assert not last_chunk
            return speech, sil_cache

        frame_step, frame_size = int(sample_rate * 0.1), int(sample_rate * 0.1)
        if sil_cache is None:
            sil_cache = {"holder": [], "buffer": []}
        if sil_cache["buffer"]:
            speech = torch.cat([*sil_cache["buffer"], speech], dim=-1)
            sil_cache["buffer"] = []
        if speech.shape[-1] < frame_size:
            sil_cache["buffer"].append(speech)
            if last_chunk:
                speech = torch.cat(sil_cache["holder"] + sil_cache["buffer"], dim=-1)
                return speech[..., : int(last_sil * sample_rate)], sil_cache
            return torch.zeros(
                (*speech.shape[:-1], 0), device=speech.device, dtype=speech.dtype
            ), sil_cache

        num_frame = (speech.shape[-1] - frame_size) // frame_step + 1
        cur_len = (num_frame - 1) * frame_step + frame_size
        if speech.shape[-1] > cur_len:
            sil_cache["buffer"].append(speech[..., cur_len:])
            speech = speech[..., :cur_len]
        spe_frames = speech.unfold(-1, frame_size, frame_step)
        scores = spe_frames.abs().mean(dim=-1)
        scores = scores.mean(dim=list(range(scores.dim() - 1)))
        idx = scores.shape[0] - 1
        while idx >= 0:
            if scores[idx] > sil_th:
                break
            idx -= 1
        if idx < 0:
            sil_cache["holder"].append(speech)
            if last_chunk:
                speech = torch.cat(sil_cache["holder"] + sil_cache["buffer"], dim=-1)
                return speech[..., : int(last_sil * sample_rate)], sil_cache
            return torch.zeros(
                (*speech.shape[:-1], 0), device=speech.device, dtype=speech.dtype
            ), sil_cache
        non_sil_len = idx * frame_step + frame_size
        if last_chunk:
            non_sil_len += int(last_sil * sample_rate)
        speech = torch.cat([*sil_cache["holder"], speech[..., :non_sil_len]], dim=-1)
        sil_cache["holder"] = []
        if non_sil_len < speech.shape[-1]:
            sil_cache["holder"].append(speech[..., non_sil_len:])
        return speech, sil_cache
