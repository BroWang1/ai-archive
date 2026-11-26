"""Runner 服务：以**子进程**方式启动 ``python main.py run ...``。

**选用子进程方案**的原因：
    * 完全复用现有 CLI（``main.py``），零改动零风险；
    * 工作流中可能长时间阻塞（LLM 调用 / 轮询审校），放到子进程里
      Web 事件循环才不会卡住；
    * 日志天然隔离，每个 run 一个 stdout 流，便于分流落盘和广播。

每个 run：
    * 分配唯一 run_id = ``<language>_<yyyymmddHHMMSS>``；
    * stdout/stderr 读取线程推送到 :class:`LogBus`，并落盘到
      ``workspace/server_logs/<run_id>.log``；
    * 元信息写入 ``workspace/server_meta/runs.json``。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .log_bus import LogBus

logger = logging.getLogger(__name__)


@dataclass
class RunRecord:
    run_id: str
    language: str
    status: str  # running | finished | failed | killed
    started_at: str
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    fresh: bool = False
    batch: Optional[str] = None
    log_file: Optional[str] = None
    pid: Optional[int] = None
    cmd: List[str] = field(default_factory=list)

    def to_public(self) -> Dict[str, object]:
        d = asdict(self)
        d.pop("pid", None)
        return d


class RunnerService:
    """以子进程方式启动工作流。"""

    def __init__(self, *, project_root: Path, log_bus: LogBus) -> None:
        self.project_root = Path(project_root).resolve()
        self.log_bus = log_bus
        self._procs: Dict[str, subprocess.Popen] = {}
        self._records: Dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self._records_file = (
            self.project_root / "workspace" / "server_meta" / "runs.json"
        )
        self._logs_dir = self.project_root / "workspace" / "server_logs"
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        # 启动时打印一次解释器信息，方便诊断 "装了但是用不到" 的问题。
        # Web 界面点"运行"派生的子进程 cmd[0] = sys.executable，所以这里打印的
        # 就是子进程将要使用的 Python。
        logger.info(
            "RunnerService: subprocess will use python=%s (venv=%s)",
            sys.executable,
            os.environ.get("VIRTUAL_ENV", "<none>"),
        )
        self._load_history()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(
        self,
        *,
        language: str,
        fresh: bool = False,
        batch: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> RunRecord:
        """启动一次运行。"""
        run_id = f"{language}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        cmd = [sys.executable, "main.py", "run", "--language", language]
        if fresh:
            cmd.append("--fresh")
        if batch:
            cmd.extend(["--batch", batch])
        if stage:
            cmd.extend(["--stage", stage])

        # 兜底：目录可能在服务运行期间被清理/手动删除，这里再次确保存在
        try:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover
            logger.warning("Failed to ensure server_logs dir %s: %s", self._logs_dir, exc)
        log_file = self._logs_dir / f"{run_id}.log"

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")

        logger.info("Launching run %s: %s", run_id, " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            logger.exception("Failed to start subprocess for run %s", run_id)
            record = RunRecord(
                run_id=run_id, language=language, status="failed",
                started_at=_now(), finished_at=_now(), exit_code=-1,
                fresh=fresh, batch=batch, log_file=str(log_file), cmd=cmd,
            )
            with self._lock:
                self._records[run_id] = record
                self._persist()
            self.log_bus.publish(run_id, f"failed to spawn: {exc}", stream="meta")
            return record

        record = RunRecord(
            run_id=run_id, language=language, status="running",
            started_at=_now(), fresh=fresh, batch=batch,
            log_file=str(log_file), pid=proc.pid, cmd=cmd,
        )

        with self._lock:
            self._procs[run_id] = proc
            self._records[run_id] = record
            self._persist()

        # 开一条后台线程：读取子进程 stdout，推 LogBus + 落盘
        t = threading.Thread(
            target=self._pump_output,
            args=(run_id, proc, log_file),
            name=f"TiMi_HOK_Game_Translator-run-{run_id}",
            daemon=True,
        )
        t.start()

        self.log_bus.publish(run_id, f"started: {' '.join(cmd)}", stream="meta")
        return record

    def stop(self, run_id: str) -> bool:
        with self._lock:
            proc = self._procs.get(run_id)
        if not proc:
            return False
        try:
            proc.terminate()
        except ProcessLookupError:
            return False
        self.log_bus.publish(run_id, "terminate signal sent", stream="meta")
        return True

    def shutdown_all(self) -> None:
        with self._lock:
            procs = list(self._procs.items())
        for run_id, proc in procs:
            try:
                proc.terminate()
            except Exception:  # pylint: disable=broad-except  # pragma: no cover
                pass
            self.log_bus.publish(run_id, "server shutdown — terminated", stream="meta")

    def list_runs(self, limit: int = 50) -> List[Dict[str, object]]:
        # 列表接口也先做一次全量对账，防止列表页显示陈旧的"运行中"
        self._reconcile()
        with self._lock:
            records = list(self._records.values())
        records.sort(key=lambda r: r.started_at, reverse=True)
        return [r.to_public() for r in records[:limit]]

    def get(self, run_id: str) -> Optional[RunRecord]:
        # 读取前先做一次"状态对账"：若后台 pump 线程异常挂掉，
        # 这里兜底修正 running → finished/failed，避免前端一直看到"运行中"。
        self._reconcile(run_id)
        with self._lock:
            return self._records.get(run_id)

    def _reconcile(self, run_id: Optional[str] = None) -> None:
        """对账：检查子进程是否仍存活；对已退出的进程强制回填记录状态。

        正常情况下 ``_pump_output`` 会在 ``finally`` 中更新 record。
        但若 pump 线程被异常/阻塞卡死，record 会永远停在 ``running``。
        这里提供一道兜底：根据 ``proc.poll()`` 真实状态强制同步。
        """
        with self._lock:
            targets = (
                [(run_id, self._procs.get(run_id))] if run_id is not None
                else list(self._procs.items())
            )
        for rid, proc in targets:
            if proc is None:
                # 没有活跃 proc，但记录可能仍是 running（历史遗留 / pump 异常）
                with self._lock:
                    rec = self._records.get(rid) if rid else None
                    if rec is not None and rec.status == "running":
                        rec.status = "failed"
                        rec.finished_at = _now()
                        if rec.exit_code is None:
                            rec.exit_code = -1
                        self._persist()
                continue
            code = proc.poll()
            if code is None:
                continue  # 子进程仍在跑，无需处理
            # 子进程已退出但 record 仍是 running —— pump 线程大概率卡死
            with self._lock:
                rec = self._records.get(rid)
                if rec is not None and rec.status == "running":
                    rec.exit_code = code
                    rec.finished_at = _now()
                    rec.status = (
                        "finished" if code == 0
                        else ("killed" if code < 0 else "failed")
                    )
                    self._persist()
                self._procs.pop(rid, None)

    def read_log_file(self, run_id: str, *, tail: int = 2000) -> List[str]:
        rec = self.get(run_id)
        if not rec or not rec.log_file:
            return []
        p = Path(rec.log_file)
        if not p.exists():
            return []
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return []
        if tail and len(lines) > tail:
            lines = lines[-tail:]
        return [ln.rstrip("\n") for ln in lines]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _pump_output(self, run_id: str, proc: subprocess.Popen, log_file: Path) -> None:
        # 打开日志文件；若打开失败（如父目录被外部清理），不中断 stdout 消费，
        # 只是放弃落盘，避免子进程 PIPE 缓冲区满而阻塞。
        f = None
        try:
            try:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                f = log_file.open("w", encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.exception("Failed to open log file %s", log_file)
                self.log_bus.publish(
                    run_id, f"[log file open failed] {exc}; 日志仅通过 WebSocket 推送",
                    stream="meta",
                )

            assert proc.stdout is not None
            for line in proc.stdout:
                if f is not None:
                    try:
                        f.write(line)
                        f.flush()
                    except OSError as exc:  # pragma: no cover - defensive
                        logger.warning("write log failed for %s: %s", run_id, exc)
                        try:
                            f.close()
                        except Exception:  # pylint: disable=broad-except
                            pass
                        f = None
                self.log_bus.publish(run_id, line)
        except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover - defensive
            logger.exception("pump output failed for %s", run_id)
            self.log_bus.publish(run_id, f"[pump error] {exc}", stream="meta")
        finally:
            if f is not None:
                try:
                    f.close()
                except Exception:  # pylint: disable=broad-except
                    pass
            exit_code = proc.wait()
            status = "finished" if exit_code == 0 else (
                "killed" if exit_code is not None and exit_code < 0 else "failed"
            )
            with self._lock:
                rec = self._records.get(run_id)
                if rec is not None:
                    rec.exit_code = exit_code
                    rec.finished_at = _now()
                    rec.status = status
                self._procs.pop(run_id, None)
                self._persist()
            self.log_bus.publish(
                run_id, f"exited with code={exit_code} status={status}", stream="meta",
            )

    def _persist(self) -> None:
        # 必须在 self._lock 上下文内调用
        self._records_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [r.to_public() for r in self._records.values()]
        tmp = self._records_file.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(self._records_file)
        except OSError as exc:  # pragma: no cover
            logger.warning("Failed to persist runs.json: %s", exc)

    def _load_history(self) -> None:
        if not self._records_file.exists():
            return
        try:
            with self._records_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        for item in data or []:
            try:
                # 过去的 run 不再 attach 真实进程，仅复原状态
                item.pop("pid", None)
                if item.get("status") == "running":
                    item["status"] = "killed"
                    item.setdefault("finished_at", _now())
                rec = RunRecord(**item)
            except TypeError:
                continue
            self._records[rec.run_id] = rec


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
