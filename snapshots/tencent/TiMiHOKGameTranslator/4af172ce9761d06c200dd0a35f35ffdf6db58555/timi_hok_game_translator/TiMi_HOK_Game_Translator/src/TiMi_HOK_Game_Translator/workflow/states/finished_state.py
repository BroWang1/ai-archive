"""``finished`` 状态——流水线终态。

驱动器跳完所有状态后进入。默认实现做三件通用清理：

* 强制 flush 未写盘的 :class:`AutoSaveDict`；
* 强制 :meth:`StatesManager.save`，保证磁盘状态停在“完成”形态；
* 调用 :meth:`VcsClient.cleanup`（大多数后端为空操作，有工作副本锁
  时进行解锁）。

真实项目可继承本类进行扩展，例如发送完成通知、打 git tag 等。
"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)


class FinishedState(WorkflowStateBase):
    """终态状态——执行清理并（可选）发送通知。"""

    name = StateEnum.FINISHED.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        # 1. 显式 flush state_data（autosave 通常已处理，但子类暂停
        # 自动保存时此处作为兵）。
        try:
            cb = getattr(ctx.state_data, "_save_callback", None)
            if callable(cb):
                cb()
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.debug("FinishedState: state_data flush failed: %s", exc)

        # 2. 强制 StatesManager 落盘。
        mgr = ctx.states_manager
        if mgr is not None:
            try:
                mgr.save()
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning("FinishedState: StatesManager save failed: %s", exc)

        # 3. VCS 清理——best effort。
        try:
            ctx.vcs.cleanup()
        except AttributeError:
            # 部分老适配器未暴露 cleanup()，忽略。
            pass
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning("FinishedState: vcs.cleanup failed: %s", exc)

        # 4. 通知。流水线结束的关键节点，自动 @ notification.mentioned 名单。
        if ctx.notifier is not None:
            try:
                mentioned = tuple(
                    (ctx.config.notification.mentioned or [])
                    if getattr(ctx.config, "notification", None)
                    else ()
                )
                target = ctx.config.target_locale or "target"
                ctx.notifier.notify(
                    f"✅ [{ctx.config.project_code}] 翻译流水线已完成（目标语种：{target}）。",
                    mentioned=mentioned,
                )
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning("FinishedState: notifier failed: %s", exc)

        logger.info("FinishedState: pipeline complete.")
        return None


__all__ = ["FinishedState"]
