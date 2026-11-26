"""TiMi_HOK_Game_Translator.utils 子包。"""

from .sibling_broadcast import (
    broadcast_siblings_by_source,
    collapse_by_source,
    filter_against_pending,
    load_pending_source_pairs,
    save_incr_snapshot,
)
# 公共 API 从 2026-10-09 起统一走格式无关版 ``table_merger``。
# ``dtxml_merger`` 模块仍保留，但其公共函数不再从此处转出——
# 若有历史代码需要导入老接口，请显式 ``from .dtxml_merger import ...``。
from .table_merger import (
    delete_entries_from_incremental,
    infer_full_table_path,
    load_full_table_keys,
    merge_incremental_into_full,
    split_translated,
)

__all__ = [
    "broadcast_siblings_by_source",
    "collapse_by_source",
    "delete_entries_from_incremental",
    "filter_against_pending",
    "infer_full_table_path",
    "load_full_table_keys",
    "load_pending_source_pairs",
    "merge_incremental_into_full",
    "save_incr_snapshot",
    "split_translated",
]
