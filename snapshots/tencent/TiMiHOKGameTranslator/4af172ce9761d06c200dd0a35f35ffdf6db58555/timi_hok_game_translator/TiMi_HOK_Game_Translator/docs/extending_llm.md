# 扩展指南：新增一种 LLM 提供方

框架内置的 LLM 提供方：

- `LocalMockLLM`（默认，provider 名 `echo`，老别名 `mock`）——不联网、结果可预测，把原文带 `[locale]` 标签回显，测试专用；
- `OpenAILLM`——可选（`pip install "TiMi_HOK_Game_Translator[openai]"`）。

下面演示如何以插件形式接入另一家——比如 Anthropic 的 Claude。

## 1. 继承 `LLMClient`

```python
# my_project/claude_llm.py
import os
from TiMi_HOK_Game_Translator.llm import LLMClient, LLMResponse
from TiMi_HOK_Game_Translator.commons import LLMProviderMissingError


class ClaudeLLM(LLMClient):
    provider_name = "claude"

    def _client(self):
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise LLMProviderMissingError(
                "请先安装：pip install anthropic"
            ) from exc
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise LLMProviderMissingError("未配置 ANTHROPIC_API_KEY")
        return anthropic.Anthropic(api_key=api_key)

    def translate(self, text, *, source_locale="", target_locale="", context=""):
        client = self._client()
        model = self.model or "claude-3-5-sonnet-latest"
        prompt = (
            f"请把下面的文本从 {source_locale or 'auto'} "
            f"翻译到 {target_locale or 'unspecified'}，保留占位符不动。\n\n"
            f"文本：{text}"
        )
        response = client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        translated = response.content[0].text.strip()
        return LLMResponse(text=translated, provider=self.provider_name, model=model)
```

## 2. 注册

```python
from TiMi_HOK_Game_Translator.llm import register_llm_provider
from .claude_llm import ClaudeLLM

register_llm_provider("claude", ClaudeLLM)
```

## 3. 配置

```yaml
llm:
  provider: claude
  model: claude-3-5-sonnet-latest
  temperature: 0.2
  # api_key 会从 GAME_TRANS_TOOLCHAIN__LLM__API_KEY 或 ANTHROPIC_API_KEY 读取。
```

## 批量效率

默认的 `batch_translate()` 会循环调用 `translate()`。如果你的提供方有
原生 batch 接口（或者一次性把多条内容拼进同一 prompt 更便宜），
请直接重写这个方法：

```python
def batch_translate(self, texts, *, source_locale="", target_locale="", context=""):
    # 把多个 texts 拼成一个 prompt，再把返回的编号列表解析回来。
    ...
```

## 测试

- 单元测试**绝对不要**打真实 API。参考
  `tests/unit/test_llm.py::TestOpenAILLM`，通过 `sys.modules`
  注入 fake 模块；
- 至少覆盖：SDK 未安装、API key 缺失、正常返回、重试后恢复等路径。
