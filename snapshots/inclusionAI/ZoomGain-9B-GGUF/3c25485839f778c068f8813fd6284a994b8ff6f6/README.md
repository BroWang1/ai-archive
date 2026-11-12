---
library_name: gguf
pipeline_tag: image-text-to-text
tags:
- gguf
- qwen3.5
- vision-language
---

# ZoomGain-9B-GGUF

GGUF-format weights for **ZoomGain-9B**, converted with [llama.cpp](https://github.com/ggml-org/llama.cpp).

- **Language model:** FP16, Q8_0, Q4_K_M.
- **Vision encoder and projector (`mmproj`):** FP16, Q8_0, Q4_K_M.

For image input, provide both the language model and the corresponding `mmproj` file.

## CLI Inference (`llama-mtmd-cli`)

```bash
llama-mtmd-cli \
  -m ZoomGain-9B-Q8_0.gguf \
  --mmproj mmproj-ZoomGain-9B-Q8_0.gguf \
  --image /path/to/image.jpg \
  -p "Describe this image." \
  --temp 0 -n 2048
```

## Web Chat (`llama-server`)

```bash
llama-server \
  -m ZoomGain-9B-Q8_0.gguf \
  --mmproj mmproj-ZoomGain-9B-Q8_0.gguf \
  --host 127.0.0.1 --port 8080
```

Replace `Q8_0` with `F16` or `Q4_K_M` to use another precision.
Use a llama.cpp build with Qwen3.5 multimodal support. Quantization can affect accuracy.
