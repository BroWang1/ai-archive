---
license: mit
library_name: custom
pipeline_tag: image-text-to-image
inference: false
tags:
  - image-text-to-image
  - layer-decomposition
  - rgba
  - graphic-design
---

# Ming-Image-0.1-Design-Layer

[🧩 ModelScope](https://www.modelscope.cn/models/inclusionAI/Ming-Image-0.1-Design-Layer) · [🤗 Hugging Face](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer) · [📄 Blog](https://mp.weixin.qq.com/s/VGdtxfM8kbHIQJw50VD_Sw) · [🖥️ Demo](https://huggingface.co/spaces/Xiaolong-Wang/Ming-Image-0.1-Design-Layer)<br>
[🎨 Design Skill](https://github.com/inclusionAI/ling-cookbook/tree/main/resources/recommended-skills/ling-ui-design) · [📊 PPT Skill](https://github.com/inclusionAI/ling-cookbook/tree/main/resources/recommended-skills/image-to-editable-ppt)

Ming-Image-0.1-Design-Layer decomposes a flattened design image into a
requested number of RGBA layers using an image and a layer plan.

## Quick Start

Use the companion [Ming-Image repository](https://github.com/inclusionAI/Ming-Image)
for installation and inference:

```bash
git clone https://github.com/inclusionAI/Ming-Image
cd Ming-Image
pip install -r requirements.txt

python infer.py \
  --model inclusionAI/Ming-Image-0.1-Design-Layer \
  --task layer-decompose \
  --input-image assets/layer_samples/card_making_input.png \
  --prompt assets/layer_samples/card_making_prompt.txt \
  --attn-implementation flash_attention_2 \
  --resolution 1024 \
  --output-dir outputs/layers
```

This runs the released six-layer card-making example. See the full
[layer-decomposition demo](https://github.com/inclusionAI/Ming-Image#layer-decomposition-demo)
for the output structure and layer-count behavior.

Prompt enhancement (PE) can use `Ling-3.0-flash-VL` or `qwen3.8-27B`; see
[layer-decomposition prompt rewriting](https://github.com/inclusionAI/Ming-Image#layer-decomposition-prompt-rewriting).

## Deployment

We recommend the following inference frameworks to serve the model:

- vLLM-Omni: see the [recipes](https://github.com/vllm-project/vllm-omni/blob/main/recipes/inclusionAI/Ming-Image.md)
  and [installation guide](https://docs.vllm.ai/projects/vllm-omni/en/latest/getting_started/quickstart/).

## Recommended settings

- Working-resolution bucket: **1024** (recommended), or **512** for faster
  layer decomposition. The output preserves the input image's aspect ratio.
- Sampling steps: **12**.
- CFG scale: **2.0**.
- Precision: **BF16**.
- Hardware: **one CUDA GPU with 80 GiB VRAM** (validated configuration).

Provide `--input-image` plus either a detailed layer specification through
`--prompt`, or omit `--prompt` and set `--num-layers N` to create the default
request. When `--prompt` is supplied, the layer count declared in that prompt
controls the output count. The standalone outputs are saved as RGBA PNG files.

## Gallery

<p align="center">
  <img src="./assets/showcase.webp" width="100%" alt="Ming-Image-0.1-Design-Layer decomposition example">
</p>

The example shows the input design, six decomposed layers, and the recomposed
result.

<p align="center">
  <img src="./assets/gallery.webp" width="100%" alt="Ming-Image-0.1-Design-Layer gallery">
</p>

The gallery shows additional flattened designs, their transparent layers, and
the corresponding recomposed results.

## Performance

<p align="center">
  <img src="./assets/performance.webp" width="100%" alt="Layer-decomposition results on the Crello test set">
</p>

The table reports quantitative layer-decomposition results on the Crello test
set; lower RGB L1 and higher Alpha soft IoU are better.

## License

This model is released under the [MIT License](./LICENSE).
