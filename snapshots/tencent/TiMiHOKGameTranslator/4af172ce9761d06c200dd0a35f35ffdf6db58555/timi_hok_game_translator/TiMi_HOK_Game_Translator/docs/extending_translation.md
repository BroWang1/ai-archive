# 扩展翻译策略

`TiMi_HOK_Game_Translator.translation` 是**编排层**：负责三段式（`filter → translate → process`）、串行/并发、去重、兄弟行广播、进度回调。而 `TiMi_HOK_Game_Translator.llm` 是**调用层**：负责把 prompt 送给具体后端。

## 两种扩展方式

### 方式 1：纯配置（零代码）

只需在 `configs/languages/<lang>.json` 写 `strategy_config`，框架会自动使用 `GenericTranslationStrategy`：

```json
{
  "id": "es",
  "target_locale": "es",
  "workflow": ["pull_vcs", "translate", "validate_data", "push_vcs"],
  "strategy_config": {
    "display_name": "Spanish translator",
    "prompt_template": "Translate to Spanish. Preserve placeholders like {value}: {text}",
    "returns_english_data": false,
    "use_concurrent_by_default": true,
    "default_max_workers": 4,
    "allow_empty": false
  }
}
```

### 方式 2：Python 子类

当你需要**语种专属**的 filter（如"越南语时过滤含日文/泰文/韩文的原文"）或 translate 逻辑（如"越南语自身直返原文，否则调 llama3-70B"），继承 `BaseTranslationStrategy` 并用装饰器注册：

```python
from typing import Optional, Tuple
from TiMi_HOK_Game_Translator.translation import (
    BaseTranslationStrategy, Entry,
    register_translation_strategy,
)


@register_translation_strategy("vi")
class VietnameseStrategy(BaseTranslationStrategy):
    default_max_workers = 5
    returns_english_data = False

    def filter(self, source_text: str, *, entry: Entry) -> bool:
        # 只翻译不含日文/泰文/韩文的原文
        for ch in source_text:
            code = ord(ch)
            if 0x3040 <= code <= 0x30FF:  # 假名
                return False
            if 0x0E00 <= code <= 0x0E7F:  # 泰文
                return False
            if 0xAC00 <= code <= 0xD7AF:  # 韩文
                return False
        return True

    def translate(self, source_text, *, entry, source_locale, target_locale, context):
        response = self.llm.translate(
            source_text,
            source_locale=source_locale,
            target_locale=target_locale,
            context=context or "Translate to Vietnamese",
        )
        return response.text, None
```

## `process()` 提供的能力（无需子类实现）

- **去重**：同 `source_text` 只送 LLM 一次，其余 sibling 行自动广播翻译；
- **并发/串行**：由 `use_concurrent_by_default` 决定，独立 `_lock` 保证共享 list 安全；
- **异常收集**：`translate` 抛异常时不会中断整个批次，错误落到 `TranslationResult.errors[key]`；
- **空返回处理**：`translate` 返回 `""` 视为失败，进入 `untranslated`；
- **进度回调**：`process(..., progress_callback=lambda done, total: ...)`；
- **post_translate 钩子**：翻译流程结束后可注入质量校验、术语检查。

## `strategy_config` 支持的键

| 键 | 类型 | 说明 |
|---|---|---|
| `display_name` | str | 日志前缀 |
| `use_concurrent_by_default` | bool | 默认走并发执行器 |
| `default_max_workers` | int | 线程池大小 |
| `batch_size` | int | 推荐批处理大小 |
| `progress_log_interval` | int | 每 N 条打印一次进度 |
| `returns_english_data` | bool | 是否请求 LLM 返回英文侧翻译 |
| `prompt_template` | str | `{text}` / `{context}` 变量替换 |
| `allow_empty` | bool | 是否翻译空字符串 |
| `skip_predicate` | callable | `(text, entry) -> bool`；返回 True 则跳过 |

未列出的键会原样保留在 `self.strategy_config` 里，供子类自行读取。

## 兄弟行广播

场景：源文件里 3 行不同 key 共用同一 `source_text`。默认行为：

1. 只有 1 行送 LLM；
2. 得到翻译后，其余 2 行的 `target_text` 也被自动填上。

如需触发**外部**副作用（把广播事件写入 Excel、通知统计），实现 `SiblingBroadcaster` 协议：

```python
from TiMi_HOK_Game_Translator.translation import BaseTranslationStrategy, SiblingBroadcaster, Entry


class ExcelBroadcaster:
    def broadcast(self, translated: Entry, all_entries) -> int:
        # ... 写 Excel，返回被触碰的兄弟行数
        return 3


strategy = get_translation_strategy("vi", sibling_broadcaster=ExcelBroadcaster())
```

## 测试友好

仓库内置的 `tests/unit/test_translation.py`（可选参考）展示了如何注入 mock LLM（`_RaisingLLM`）验证异常路径、如何断言并发执行器保序、如何用 `progress_callback` 验证进度节奏——直接照抄即可。
