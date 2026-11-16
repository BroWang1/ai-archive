# vLLM 0.33.0 补丁：工具结果的图片顺序（Sage-S2.1-Flash）

[English](README.md) | [中文](README_zh.md)

## 修什么

Sage-S2.1-Flash 的 chat 模板按 assistant 的 `tool_calls` 顺序渲染一段工具结果，vLLM 却按消息顺序
收集其中的图片。结果返回顺序和调用顺序不一致时，图片会静默配给错误的结果。

## 补丁改了什么

只改一个文件 `vllm/renderers/hf.py`：

- 新增 `_glm5_next_tool_media_order()`：按模板自己的规则，把一段工具结果排成 `tool_calls`
  顺序；只在这段结果里有图片或视频时才排。
- 在 `HfRenderer.render_messages` 和 `render_messages_async` 里，调用 `parse_chat_messages`
  之前先调用它。
- 只对 `model_type == "glm5_next"` 生效，渲染出的 prompt 文本不变。

## 文件

| 文件 | 用途 |
|---|---|
| `vllm-0.33.0/vllm/renderers/hf.py` | 打好补丁的 vLLM 0.33.0 文件，直接覆盖安装目录里的同名文件 |
| `vllm-0.33.0-glm5-tool-media-order.patch` | 同一改动的 git diff，供审阅或其他版本使用 |
| `check_tool_media_order.py` | CPU 检查脚本（不需要权重） |

## 打补丁（vLLM 0.33.0）

```bash
PATCH=<权重目录>/vllm_patch
VLLM_DIR=$(python -c "import vllm, os; print(os.path.dirname(vllm.__file__))")
sha256sum $VLLM_DIR/renderers/hf.py
# 必须是 3c84c86b348b539fc741085327b165f4b6bf958cc6c0e19fb5dc0f54430432d2（官方 0.33.0）
cp $VLLM_DIR/renderers/hf.py $VLLM_DIR/renderers/hf.py.bak
cp $PATCH/vllm-0.33.0/vllm/renderers/hf.py $VLLM_DIR/renderers/hf.py
sha256sum $VLLM_DIR/renderers/hf.py
# 1ce7ab5909848579e37174d6ad2af3fa48b797198376e9e7757bc26af575eda7
```

第一个 sha256 对不上，说明不是官方 0.33.0 的原文件，不要覆盖。还原时把 `hf.py.bak` 拷回去。

## 检查

```bash
python -c "import vllm.renderers.hf as h; print(hasattr(h, '_glm5_next_tool_media_order'))"  # True
python $PATCH/check_tool_media_order.py <权重目录>    # 全部 OK
```

之后照常启动 `vllm serve`。

## 其他版本

这个 diff 也能打到 0.30.0、0.31.0、0.32.0 和 nightly 0.34.0rc1.dev397 上，在 `site-packages`
下执行：

```bash
git apply --check $PATCH/vllm-0.33.0-glm5-tool-media-order.patch
git apply $PATCH/vllm-0.33.0-glm5-tool-media-order.patch    # 或者 patch -p1 -b < ...
```

0.30.0 之前的版本不支持 `glm5_next` 架构，用 vLLM 的 Rust 前端
（`VLLM_USE_RUST_FRONTEND=1 --tokenizer-mode glm5_next`）时也不需要。

## 验证

- CPU（`check_tool_media_order.py`）：在 0.30.0 到 0.33.0 和 nightly 上跑 7 种情形。补丁前倒序
  情形配错，补丁后 7 种全部与模板一致。
- GPU（0.33.0，4×H200）：工具结果倒序时，补丁前模型答成另一张图的颜色，补丁后答对。

上游：vllm-project/vllm#67108（草稿）做了不区分模型的同类排序。
