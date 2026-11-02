---
base_model: inclusionAI/ZwZ2-4B
base_model_relation: quantized
datasets:
- inclusionAI/ZwZ2-RL-VQA
language:
- en
license: apache-2.0
library_name: gguf
pipeline_tag: image-text-to-text
tags:
- gguf
- zwz2
- vision-language
---

**ZwZ2-4B-GGUF**

<p align="center">
  📃 <a href="https://arxiv.org/pdf/2610.37037">Paper</a> | 🏠 <a href="https://github.com/inclusionAI/Zooming-without-Zooming-v2">Project</a> | 🤗 <a href="https://huggingface.co/collections/inclusionAI/zooming-without-zooming-v2">Collection</a>
</p>

GGUF-format weights for [ZwZ2-4B](https://huggingface.co/inclusionAI/ZwZ2-4B),
part of Zooming without Zooming v2.
The model is split into two components:

- **Language model:** FP16, Q8_0, Q4_K_M.
- **Vision encoder and projector (`mmproj`):** FP16, Q8_0, Q4_K_M.

Choose a language model and a matching vision component from this repository.
Different precision levels can be combined. Quantization can affect accuracy;
see the original model page for the published evaluation results.

## How to Use

Use a recent [llama.cpp](https://github.com/ggml-org/llama.cpp) build with Qwen3.5
multimodal support.

### CLI Inference (`llama-mtmd-cli`)

For example, to run ZwZ2-4B with a Q8_0 vision encoder and Q8_0 quantized LLM:

```bash
llama-mtmd-cli \
  -m ZwZ2-4B-Q8_0.gguf \
  --mmproj mmproj-ZwZ2-4B-Q8_0.gguf \
  --image /path/to/image.jpg \
  -p "Describe this image." \
  --temp 0 -n 2048
```

### Web Chat (using `llama-server`)

To serve ZwZ2-4B via an OpenAI-compatible API with a web UI:

```bash
llama-server \
  -m ZwZ2-4B-Q8_0.gguf \
  --mmproj mmproj-ZwZ2-4B-Q8_0.gguf \
  --host 127.0.0.1 --port 8080
```

Replace the filenames to use FP16 or Q4_K_M weights. For image input, always
provide the corresponding `mmproj` component.

## Citation

```bibtex
@article{wei2026zoomingv2,
  title={Zooming without Zooming v2: From Seeing Details to Connecting Evidence for Generalizable Multimodal Perception},
  author={Wei, Lai and Li, Yatai and He, Liangbo and Lan, Jun and Gu, Renjie and Cao, Linhan and Lin, Junkai and Zhu, Huijia and Wang, Weiqiang and Kong, Linghe and Wang, Yue and Zhang, Zhuosheng and Huang, Weiran},
  journal={arXiv preprint arXiv:2610.37037},
  year={2026}
}
```

## License

This model follows the Apache 2.0 License.
