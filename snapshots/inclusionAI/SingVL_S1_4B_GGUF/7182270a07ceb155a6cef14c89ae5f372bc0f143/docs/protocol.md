# GGUF protocol reference

## HTTP 输入输出格式

接口：`POST /v1/systemone`，Content-Type 为 `application/json`。这不是 OpenAI 的 messages/chat-completions 接口。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| state | JSON 值，必填 | 字符串直接使用；对象等序列化为紧凑 JSON。图像请求可用 `{}`。 |
| questions | 非空对象，必填 | 键为用户自定义 question ID，值为题目对象；按顺序逐题计算。 |
| images | 字符串数组，可选 | 最多 4 张，支持 base64、data URL、`--image-root` 内文件路径。路径指服务端文件，不是客户端路径。 |
| return_details | 布尔，可选 | 为 true 时返回 evaluation_trace（token 信息、位置和候选 logits）。 |

题目对象：`type` 必填，取 `choice`、`noul`、`score`；`instructions` 为问题文本，可省略（空字符串）。

- **choice**：`criteria` 为按插入顺序排列的 2～256 个候选组成的对象，如 `{"red":"Red","blue":"Blue"}`。输出 choice 是原键 `red`，不是内部索引 AA。
- **noul**：criteria 可省略，默认 `{"true":"Yes","false":"No"}`；自定义时必须恰好包含 true 和 false 两个键。输出 noul 是 true 的概率，不是布尔值。
- **score**：criteria 必须为 2～10 个等级描述组成的有序数组。输出为从 0 开始的等级期望值，可为小数，同时返回每级概率和 legend。

state 和 instructions 在现有协议中直接拼接，不自动插入分隔符；需要分隔时，在 state 末尾显式保留空格或换行。不要自行添加 chat 标记、答案前缀或模型输出。若 state 没写 `<image>`，图片占位符会按 images 顺序加到前面；若显式写了占位符，数量必须与图片数完全一致。图片标记放在 state，不放在 instructions。普通用户只需填写 JSON，不需要指定内部 token ID。

单题文本请求：

```json
{"state":"The color is red. ","questions":{"color":{"type":"choice","instructions":"Which color is named?","criteria":{"red":"Red","blue":"Blue"}}}}
```

对应 Q8_0 CPU 示例响应（浮点数按实际后端可能略有不同）：

```json
{
  "model": "sing-vl-s1",
  "answers": {
    "color": {
      "type": "choice",
      "choice": "red",
      "probabilities": {"red": 0.9966803216653017, "blue": 0.0033196783346983094}
    }
  },
  "usage": {"input_tokens": 56, "output_tokens": 0}
}
```

`model` 字段保留既有协议标识 `sing-vl-s1`，与 GGUF 文件名不同。`output_tokens=0` 表示直接读取 logits，没有自回归生成答案文本；多题 input_tokens 是每题完整输入长度之和。带图请求额外返回 `image_tokens`；return_details=true 时额外返回 `evaluation_trace`。

choice/noul/score 的完整多题请求见 `examples/request_text_readme.json`；双图请求见 `examples/request_two_images.json`。原始 prompt、候选 IDs/logits 和后处理对照见 `examples/input_output.json`。

错误响应形如 `{"error":"..."}`：非法 JSON/参数或不可读图片通常为 400，超大或缺少长度的请求体为 413，不支持的题型/超长输入/图片数量等为 422，后端执行失败为 500。请求体最大 64 MiB，客户端应发送 Content-Length（上面的 curl 会自动设置）。

## 数据流程

用户 JSON → `Processor.prepare()` → 推理后端加载 GGUF，执行整题前向计算并返回候选 logits → `Processor.finish()` → choice/noul/score 结果。

```python
from processing import Processor

processor = Processor("config")
items = processor.prepare(request["state"], request["questions"], images)
answers = {}
for item in items:
    # 由用户实现 backend：完整题目前向计算，返回以下候选的 logits，顺序必须一致。
    logits = backend(item)
    answers[item["question_id"]] = processor.finish(item, logits)
```

这里的 `images` 为按用户顺序解码后的 PIL 图片；JSON 的 base64/路径解码示例见 `examples/llama_cpp/serve.py`。`backend` 是用户实现的接口占位符，本示例不声称存在通用硬件后端。

每个 item 包含 `prompt`、展开后的 `input_ids`、`candidate_token_ids`、`rgb_images`、`image_features` 和用于参考的 `batch`。后端选择自己的输入形式：llama.cpp 使用提示词和 RGB 图片，在内部编码图像；不要把 RGB 图片和已经展开的 image token 再重复插入。`batch` 是 Transformers 风格的参考输入，不是可直接传给任意 GGUF 引擎的统一张量协议。

模型索引按配置中固定的 256 个 token 顺序分配给本题有序候选。后端返回本题候选 logits，而不是已经归一化的概率；后处理仅在本题候选间做 softmax，返回原 criteria 键。noul 返回 true 概率，score 返回从 0 开始的等级期望值。支持纯文本和最多 4 张图片，不支持视频。

## 后端必须满足的约定

1. GGUF 的 `qwen35.attention.causal=false` 必须实际生效；所有输入的 full-attention 层双向，GDN 保持因果。
2. 一道题的完整文本和图像应一起处理，不能沿用会破坏双向可见性的普通因果分块 prefill。本参考适配器使用一次 `llama_process`，batch/ubatch 容量覆盖完整输入。
3. 每道题独立清空 KV 和循环状态；不能跨题复用前缀缓存。保持图像顺序、图像 token 展开及 M-RoPE 坐标一致。
4. 不把答案拼回输入。读取最后有效输入位置的 logits；按照 `candidate_token_ids` 取值。固定索引、候选顺序、图像预处理和提示词均为协议的一部分。

不能仅用任意 GGUF 聊天程序加载权重就认定实现等价。

