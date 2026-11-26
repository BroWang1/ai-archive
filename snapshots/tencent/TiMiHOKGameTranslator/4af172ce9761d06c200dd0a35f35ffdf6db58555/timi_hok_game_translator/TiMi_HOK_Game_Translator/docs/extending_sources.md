# 扩展指南：新增一种源文件格式

假设你使用 [Fluent](https://projectfluent.org/)（`.ftl`），
希望 `TiMi_HOK_Game_Translator` 能读写它。

## 1. 继承 `LocalizationSource`

```python
# my_project/fluent_source.py
from typing import List, Sequence

from TiMi_HOK_Game_Translator.sources import Entry, LocalizationSource, register_source


@register_source("fluent")
class FluentSource(LocalizationSource):
    """Fluent 格式的最小实现示例。"""

    file_extensions = (".ftl",)

    def load(self, path: str) -> List[Entry]:
        text = self._read_text(path, self.encoding)
        entries: List[Entry] = []
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            entries.append(Entry(key=key, source_text=value))
        return entries

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        lines = [f"{e.key} = {e.target_text or e.source_text}" for e in entries]
        self._write_text(path, "\n".join(lines) + "\n", self.encoding)
```

`@register_source("fluent")` 装饰器会把这个类接入工厂，此后
`TiMi_HOK_Game_Translator` 就能识别 `source.format: fluent` 了。

## 2. 保留元数据以支持往返读写

每个 `Entry` 都有一个可选的 `metadata: dict` 字段。凡是无法直接
用你的文件格式表达的信息（例如审校状态、译者 ID、修订号），
都建议放进 `metadata`，从而在多次 `load → dump` 之间保留下来。
真实示例可看 `xliff_source.py`。

## 3. 合并语义

默认的 `merge()` 方法（见 `LocalizationSource.merge`）按 key 做合并：
`patch` 会覆盖同名 key，并追加新增的 key。如果你的格式支持更精细的
合并语义（例如 Fluent 的 attribute / variant），请重写 `merge()`。

## 4. 测试清单

参考 `tests/unit/test_sources_json_yaml.py` 的模式：

- **正常加载**：解析一个小文件并检查 key / 文本；
- **空文件**：`load()` 必须返回 `[]`，而不是抛异常；
- **格式错误**：`load()` 必须抛 `SourceError`，且信息足以定位；
- **往返一致**：`dump()` 之后再 `load()`，得到的 entries 应一致；
- **元数据保留**：特定后端字段应能在往返后依旧存在。
