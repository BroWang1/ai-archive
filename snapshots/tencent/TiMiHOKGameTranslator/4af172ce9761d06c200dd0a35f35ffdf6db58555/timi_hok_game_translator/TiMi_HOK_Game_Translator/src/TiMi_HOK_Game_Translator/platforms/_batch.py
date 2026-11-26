"""审校批次（batch）辅助。

一个"批次"指：某一次 ``TiMi_HOK_Game_Translator run`` 的 ``first_review`` 或
``second_review`` 向审校平台（Crowdin / Phrase）提交的一组产物。
批次统一落在 ``workspace/batches/<batch_name>/<stage>/`` 下，便于
留痕、重跑定位、以及人工排错。

命名约定::

    批次名：<target_locale>_<yyyyMMddHHmmss>
    例如：vi_20261008200000

    产物文件：<batch_name>_<中文审校阶段>.xlsx / .xliff
    例如：vi_20261008200000_第一轮审核.xlsx
          vi_20261008200000_第二轮审核.xlsx

目录布局::

    workspace/batches/<batch_name>/
    ├── first_review/
    │   ├── <batch_name>_第一轮审核.xlsx     ← 上传到平台
    │   ├── <batch_name>_第一轮审核.xliff    ← 从平台导出
    │   └── first_review.meta.json
    └── second_review/
        ├── <batch_name>_第二轮审核.xlsx
        ├── <batch_name>_第二轮审核.xliff
        └── second_review.meta.json
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Final

#: 批次下按阶段细分的子目录名；与 :class:`ReviewStage` 对齐。
_STAGE_SUBDIR: Final = {
    "first": "first_review",
    "second": "second_review",
    "light": "light_review",
}

#: 产物文件后缀——使用中文，便于审校员一眼识别审校阶段。
_STAGE_FILE_SUFFIX: Final = {
    "first": "第一轮审核",
    "second": "第二轮审核",
    "light": "轻度审核",
}

#: ``target_locale`` 允许的字符白名单；其它字符替换成 ``_``。
_SAFE_RE = re.compile(r"[^A-Za-z0-9]+")


def build_batch_name(
    *,
    project_code: str = "",
    target_locale: str,
    timestamp: str = "",
) -> str:
    """按 ``<target_locale>_<yyyyMMddHHmmss>`` 规则生成批次名。

    参数：
        project_code: 保留参数，当前实现忽略——批次名已去除 project_code
            前缀以保持简洁；保留签名便于未来扩展/避免调用方破坏。
        target_locale: 目标语种，如 ``vi``。
        timestamp: ``yyyyMMddHHmmss`` 格式时间戳；为空时用当前时间。
    返回：
        形如 ``vi_20261008200000`` 的批次名。
    """
    _ = project_code  # 当前不参与命名，仅保留签名
    safe_locale = _SAFE_RE.sub("_", target_locale.strip()) or "target"
    ts = timestamp or time.strftime("%Y%m%d%H%M%S", time.localtime())
    return f"{safe_locale}_{ts}"


def batch_root(workspace: Path, batch_name: str) -> Path:
    """返回批次根目录；不自动创建。"""
    return Path(workspace) / "batches" / batch_name


def stage_dir(workspace: Path, batch_name: str, review_stage: str) -> Path:
    """返回批次下指定阶段的目录；自动 ``mkdir``。"""
    subdir = _STAGE_SUBDIR.get(review_stage, review_stage)
    path = batch_root(workspace, batch_name) / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def stage_file_stem(batch_name: str, review_stage: str) -> str:
    """生成形如 ``<batch_name>_第一轮审核`` 的文件 stem。"""
    suffix = _STAGE_FILE_SUFFIX.get(review_stage, review_stage)
    return f"{batch_name}_{suffix}"


__all__ = [
    "build_batch_name",
    "batch_root",
    "stage_dir",
    "stage_file_stem",
]
