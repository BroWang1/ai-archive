---
library_name: audio.cpp
license: other
license_name: funasr-model-license-1.1
license_link: https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512-hf/blob/main/README.md
base_model: FunAudioLLM/Fun-ASR-Nano-2512-hf
pipeline_tag: automatic-speech-recognition
tags:
- audio.cpp
- gguf
- speech-recognition
- multilingual
- funasr
---

# Fun-ASR-Nano-2512 GGUF

Standalone audio.cpp GGUF builds of
[FunAudioLLM/Fun-ASR-Nano-2512-hf](https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512-hf).
Each file embeds the model configuration, processor configuration, tokenizer,
chat template, and the audio.cpp model package specification.

## Files

| File | Size | SHA256 |
| --- | ---: | --- |
| `fun-asr-nano-2512-q8_0.gguf` | 1,045,334,432 bytes | `4d727357574b079b7f43336b2930f39da086ca02f5d8d50872090b4c1c3d5e0a` |
| `fun-asr-nano-2512-f16.gguf` | 1,675,708,832 bytes | `3d906c3ccfed07efef88ff53d6cc94b788b9d2edf1492a5679d041b43e98c5be` |

The source checkpoint is pinned to revision
`854d88f94205cd17d2afdb24332130d86fbe654a`. The source
`model.safetensors` SHA256 is
`335ca3e74917f1156690400e2c344350112950165789cf78ce3d0a367affd821`.

## audio.cpp

```bash
audiocpp_cli \
  --task asr \
  --family fun_asr_nano \
  --model fun-asr-nano-2512-q8_0.gguf \
  --backend cuda \
  --audio speech.wav
```

Fun-ASR-Nano currently provides offline multilingual ASR. It does not expose
streaming or timestamp output. On CUDA, audio.cpp keeps the Q8_0 encoder and
adaptor weights native and loads decoder weights as BF16 by default for stable
logits. An explicit `fun_asr_nano.decoder_weight_type` session option overrides
that default.

## Reproducibility

The files were generated with audio.cpp's `audiocpp_gguf` converter:

```bash
audiocpp_gguf \
  --input model.safetensors \
  --root /path/to/Fun-ASR-Nano-2512-hf \
  --output fun-asr-nano-2512-q8_0.gguf \
  --type q8_0 \
  --family fun_asr_nano \
  --model-spec model_specs/fun_asr_nano.json
```

Both formats were checked with `audiocpp_gguf --inspect` and full reference
audio transcription on CPU and NVIDIA H100 CUDA.

## License

The original model and these converted weights are governed by the
FunASR Model Open Source License Agreement v1.1 distributed with the source
model. Review that agreement before using or redistributing the files.
