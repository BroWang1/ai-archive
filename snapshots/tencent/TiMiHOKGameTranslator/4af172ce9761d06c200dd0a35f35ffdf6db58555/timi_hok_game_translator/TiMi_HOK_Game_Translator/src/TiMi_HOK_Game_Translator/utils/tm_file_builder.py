"""翻译记忆（TM）文件构建器。

**用途**：
    把 ``workspace/batches/<lang>_*/<stage>/*_approved.xlsx`` 下所有历史已审
    文件扫一遍，去重后生成一份两列的 TM xlsx（源语/目标语），交给
    :mod:`workflow.states.update_tm_state` /
    :mod:`workflow.states.update_grn_tm_state` 调用审校平台
    ``upload_tm`` 接口回灌到对应项目的默认 TM 库，让审校人员在平台界面上
    能看到历史翻译参考。

**实现要点**：
    * **不做"增量合并 vs 全量扫描"的分层基线**——目前 workspace 积累的
      历史数据量不大，首轮直接走全量扫描即可；需要优化时再引入
      ``MERGE_<lang>_ALL.xlsx`` 快照。
    * **不依赖 pandas**——用 :class:`~TiMi_HOK_Game_Translator.sources.xlsx_source.XlsxSource`
      读写，保持与框架其他部分一致的列结构。
    * **统一列名约定**——xlsx 列头统一为 ``Key/Source/Target/...``；
      生成的 TM 文件沿用两列 ``Source/Target``，可被 Crowdin / Phrase
      的 TM import 接口正确解析。

**TM 文件格式**：
    输出到 ``workspace/tm/<lang>_<stage>_tm.xlsx``，两列::

        Source | Target
        -------+-------
        你好    | Xin chào
        ...    | ...

**失败处理**：
    函数不吞异常；调用方（state）自行 try/except → 告警 + 继续。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


#: 审校阶段标识（输入） → batches 下的子目录名。
_STAGE_SUBDIR = {
    "first": "first_review",
    "second": "second_review",
    "light": "light_review",
}

#: 用于生成 TM 文件名的阶段简写（输出）。
_STAGE_FILENAME = {
    "first": "first",
    "second": "second",
    "light": "light",
}


def collect_approved_entries(
    *,
    workspace: Path,
    target_locale: str,
    review_stage: str,
) -> List[Tuple[str, str]]:
    """扫描本地已审历史文件，返回去重后的 ``[(source, target), ...]``。

    扫描范围：

        ``<workspace>/batches/<target_locale>_*/{stage}/*_approved.xlsx``

    其中 ``{stage}`` 根据 ``review_stage`` 映射：
      * ``"first"`` → ``first_review``
      * ``"second"`` → ``second_review``
      * ``"light"`` → ``light_review``

    参数：
        workspace: workspace 根目录（通常 ``ctx.workspace``）。
        target_locale: 目标语种标识，用于过滤 batch 目录前缀。
        review_stage: 审校阶段标识。

    返回：
        ``[(source, target), ...]``，按 ``source`` 去重保留最后一次出现的 target。
        若未扫到任何文件或均为空，返回空列表。
    """
    from ..sources.xlsx_source import XlsxSource  # 局部导入，避免循环

    stage_sub = _STAGE_SUBDIR.get(review_stage)
    if not stage_sub:
        logger.warning(
            "collect_approved_entries: unknown review_stage=%r, nothing to collect",
            review_stage,
        )
        return []

    batches_root = Path(workspace) / "batches"
    if not batches_root.exists():
        logger.info(
            "collect_approved_entries: batches root %s does not exist yet",
            batches_root,
        )
        return []

    # 遍历所有以 ``<target_locale>_`` 开头的批次目录
    pairs: dict = {}  # source → target（后出现的覆盖先出现的）
    scanned_files = 0
    for batch_dir in sorted(batches_root.glob(f"{target_locale}_*")):
        if not batch_dir.is_dir():
            continue
        stage_dir = batch_dir / stage_sub
        if not stage_dir.exists():
            continue
        for approved_file in sorted(stage_dir.glob("*_approved.xlsx")):
            try:
                entries = XlsxSource(encoding="utf-8").load(str(approved_file))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "collect_approved_entries: failed to load %s (%s), skip",
                    approved_file, exc,
                )
                continue
            scanned_files += 1
            for entry in entries:
                src = (entry.source_text or "").strip()
                tgt = (entry.target_text or "").strip()
                if not src or not tgt:
                    continue
                pairs[src] = tgt

    logger.info(
        "collect_approved_entries: scanned %d approved files, collected %d unique "
        "(source, target) pairs for %s/%s",
        scanned_files, len(pairs), target_locale, review_stage,
    )
    return list(pairs.items())


def build_tm_xlsx(
    pairs: Sequence[Tuple[str, str]],
    *,
    output_path: Path,
    source_locale: str = "zh-CN",
    target_locale: str = "",
) -> Optional[Path]:
    """把 ``pairs`` 写入双列 xlsx，供平台 TM import 接口上传。

    输出格式（两列、首行为语种代码表头，兼容 Crowdin 的 ``translation``
    列映射规则 ``key=0, text=1, translation=2`` 的最小子集；Phrase 的
    TMX import 对 Excel 列头也宽容）::

        <source_locale> | <target_locale>
        ----------------+-----------------
        你好            | Xin chào

    参数：
        pairs: ``[(source, target), ...]``。空列表则返回 ``None``（不写文件）。
        output_path: 输出 xlsx 路径。父目录会自动创建。
        source_locale: 第一列列头（默认 ``zh-CN``）。
        target_locale: 第二列列头；为空时报错。

    返回：
        成功时返回写入的路径；``pairs`` 为空或 ``target_locale`` 为空时返回 ``None``。
    """
    if not pairs:
        logger.info("build_tm_xlsx: no pairs provided, skip writing")
        return None
    if not target_locale:
        logger.warning("build_tm_xlsx: target_locale is empty, skip")
        return None

    try:
        import openpyxl  # 本地化已有依赖
    except ImportError:  # pragma: no cover
        logger.error(
            "build_tm_xlsx: openpyxl is required for TM file generation; "
            "install with `pip install openpyxl`"
        )
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TM"
    ws.append([source_locale, target_locale])
    for src, tgt in pairs:
        ws.append([src, tgt])

    # 适度加宽列宽，便于平台 UI 预览
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 60

    wb.save(str(output_path))
    logger.info("build_tm_xlsx: wrote %d TM pairs to %s", len(pairs), output_path)
    return output_path


def build_tm_file_for_stage(
    *,
    workspace: Path,
    target_locale: str,
    source_locale: str,
    review_stage: str,
) -> Optional[Path]:
    """一步到位：扫历史 approved 文件 → 产出 TM xlsx 文件。

    这是对外主入口；state 代码只需要调这一个函数。

    输出路径：``<workspace>/tm/<target_locale>_<stage>_tm.xlsx``
    """
    pairs = collect_approved_entries(
        workspace=workspace,
        target_locale=target_locale,
        review_stage=review_stage,
    )
    if not pairs:
        return None

    stage_name = _STAGE_FILENAME.get(review_stage, review_stage)
    output_path = Path(workspace) / "tm" / f"{target_locale}_{stage_name}_tm.xlsx"
    return build_tm_xlsx(
        pairs,
        output_path=output_path,
        source_locale=source_locale or "zh-CN",
        target_locale=target_locale,
    )


__all__ = [
    "build_tm_file_for_stage",
    "build_tm_xlsx",
    "collect_approved_entries",
]
