# vLLM 0.33.0 patch: tool-result image order (Sage-S2.1-Flash)

[English](README.md) | [中文](README_zh.md)

## What it fixes

Sage-S2.1-Flash's chat template renders a block of tool results in the order of the assistant's
`tool_calls`, but vLLM collects their images in message order. When results come back out of
call order, each image is silently paired with the wrong result.

## What the patch changes

One file, `vllm/renderers/hf.py`:

- Adds `_glm5_next_tool_media_order()`, which sorts a block of tool results into `tool_calls`
  order under the template's own rule, only when the block contains images or videos.
- Calls it right before `parse_chat_messages` in `HfRenderer.render_messages` and
  `render_messages_async`.
- Only `model_type == "glm5_next"` is affected. The rendered prompt text does not change.

## Files

| File | Use |
|---|---|
| `vllm-0.33.0/vllm/renderers/hf.py` | Patched file for vLLM 0.33.0, copied over the installed one |
| `vllm-0.33.0-glm5-tool-media-order.patch` | The same change as a git diff, for review or other versions |
| `check_tool_media_order.py` | CPU check (no weights) |

## Apply (vLLM 0.33.0)

```bash
PATCH=<model dir>/vllm_patch
VLLM_DIR=$(python -c "import vllm, os; print(os.path.dirname(vllm.__file__))")
sha256sum $VLLM_DIR/renderers/hf.py
# must be 3c84c86b348b539fc741085327b165f4b6bf958cc6c0e19fb5dc0f54430432d2 (stock 0.33.0)
cp $VLLM_DIR/renderers/hf.py $VLLM_DIR/renderers/hf.py.bak
cp $PATCH/vllm-0.33.0/vllm/renderers/hf.py $VLLM_DIR/renderers/hf.py
sha256sum $VLLM_DIR/renderers/hf.py
# 1ce7ab5909848579e37174d6ad2af3fa48b797198376e9e7757bc26af575eda7
```

If the first checksum differs, the file is not stock 0.33.0: do not overwrite it. To revert,
copy `hf.py.bak` back.

## Check

```bash
python -c "import vllm.renderers.hf as h; print(hasattr(h, '_glm5_next_tool_media_order'))"  # True
python $PATCH/check_tool_media_order.py <model dir>    # all OK
```

Then start `vllm serve` as usual.

## Other versions

The diff also applies to 0.30.0, 0.31.0, 0.32.0 and nightly 0.34.0rc1.dev397. Run it in
`site-packages`:

```bash
git apply --check $PATCH/vllm-0.33.0-glm5-tool-media-order.patch
git apply $PATCH/vllm-0.33.0-glm5-tool-media-order.patch    # or: patch -p1 -b < ...
```

Not needed before 0.30.0 (no `glm5_next` support), nor with vLLM's Rust frontend
(`VLLM_USE_RUST_FRONTEND=1 --tokenizer-mode glm5_next`).

## Verification

- CPU (`check_tool_media_order.py`): 7 cases on 0.30.0 to 0.33.0 and nightly. Before the patch,
  the reversed cases are mispaired. After it, all 7 match the template.
- GPU (0.33.0, 4xH200): with reversed tool results, the model answered the wrong image's color
  before the patch and the right one after it.

Upstream: vllm-project/vllm#67108 (draft) adds a similar, model-agnostic reordering.
