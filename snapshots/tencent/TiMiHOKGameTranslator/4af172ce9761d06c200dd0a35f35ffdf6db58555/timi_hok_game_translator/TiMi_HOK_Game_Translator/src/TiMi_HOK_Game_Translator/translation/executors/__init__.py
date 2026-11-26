"""供 :class:`BaseTranslationStrategy.process` 使用的执行引擎。

内置两个实现：

* :mod:`.serial`\u2014\u2014逐条串行处理。开销小、顺序确定、便于调试；
  当策略的独立条目少于 2 条或显式禁用并发时会选用它。
* :mod:`.concurrent`\u2014\u2014使用固定大小线程池并发处理，
  适合 I/O 密集的 LLM 调用。

两个执行器**签名完全一致**，调用方切换时无需修改分支；返回值也一致，
均为 ``(translated, untranslated, errors)``。
"""

from .concurrent import run_concurrent
from .serial import run_serial

__all__ = ["run_concurrent", "run_serial"]
