# -*- coding: utf-8 -*-
"""基于标准五位 Cron 的自动调度器。"""

from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta
from typing import Any, Callable

from ..core.cron import CronExpression

LogFn = Callable[[str], None]
RunFn = Callable[[], list[str]]
DEFAULT_CRON = "0 9 * * *"


class DailyScheduler:
    """按系统本地时区运行 Cron，并在每次触发后应用随机延迟。"""

    def __init__(self, config: dict[str, Any], run_fn: RunFn, log_fn: LogFn) -> None:
        self.config = config
        self.run_fn = run_fn
        self.log = log_fn
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False
        self._next_run: datetime | None = None
        self._last_run: datetime | None = None
        self._last_error = ""
        self._schedule_signature = self._make_schedule_signature(self._schedule_config())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="miyouqian-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def reload(self, config: dict[str, Any]) -> None:
        self.config = config
        signature = self._make_schedule_signature(self._schedule_config())
        with self._lock:
            if signature != self._schedule_signature:
                self._schedule_signature = signature
                self._next_run = None
        self._wake.set()

    def run_now(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
        threading.Thread(target=self._run_once, name="miyouqian-manual-run", daemon=True).start()
        return True

    def status(self) -> dict[str, Any]:
        with self._lock:
            schedule = dict(self._schedule_config())
            return {
                "enabled": bool(schedule.get("enable", False)),
                "running": self._running,
                "next_run": self._next_run.isoformat(timespec="seconds") if self._next_run else "",
                "last_run": self._last_run.isoformat(timespec="seconds") if self._last_run else "",
                "last_error": self._last_error,
                "schedule": schedule,
            }

    def _loop(self) -> None:
        schedule = self._schedule_config()
        if schedule.get("run_on_start", False):
            self.run_now()

        while not self._stop.is_set():
            schedule = self._schedule_config()
            if not schedule.get("enable", False):
                with self._lock:
                    self._next_run = None
                self._wait_for_change(30)
                continue

            try:
                with self._lock:
                    if self._next_run is None:
                        self._next_run = self._compute_next_base_run(schedule, datetime.now())
                        self.log(f"下次 Cron 自动执行时间：{self._next_run:%Y-%m-%d %H:%M:%S}")
                    due_run = self._next_run

                wait_seconds = max((due_run - datetime.now()).total_seconds(), 0)
                if self._wait_for_change(min(wait_seconds, 60)):
                    continue
                if datetime.now() < due_run:
                    continue

                # 先计算下一个 Cron 时刻，确保每次触发都独立排程。
                with self._lock:
                    if self._running:
                        self._next_run = self._compute_next_base_run(schedule, datetime.now())
                        continue
                    self._next_run = self._compute_next_base_run(schedule, due_run)

                jitter = max(int(schedule.get("jitter_minutes", 45) or 0), 0)
                delay_seconds = random.randint(0, jitter * 60) if jitter else 0
                if delay_seconds:
                    delay_text = (
                        f"{delay_seconds // 60}分{delay_seconds % 60}秒"
                        if delay_seconds >= 60 else f"{delay_seconds}秒"
                    )
                    self.log(
                        f"Cron 已触发（{due_run:%Y-%m-%d %H:%M:%S}），"
                        f"随机延后 {delay_text} 后执行"
                    )
                    if self._wait_for_change(delay_seconds):
                        continue

                if self._stop.is_set():
                    break
                # 若等待期间用户改了 Cron/开关/随机延迟，放弃旧计划。
                if self._make_schedule_signature(self._schedule_config()) != self._schedule_signature:
                    with self._lock:
                        self._next_run = None
                    continue

                with self._lock:
                    if self._running:
                        continue
                    self._running = True
                self._run_once()
                # 执行耗时或随机延迟可能跨过后续触发点；不补跑过期任务，避免形成追赶队列。
                with self._lock:
                    self._next_run = self._compute_next_base_run(
                        self._schedule_config(), datetime.now()
                    )
            except (TypeError, ValueError) as exc:
                self.log(f"Cron 调度配置错误：{exc}")
                with self._lock:
                    self._next_run = None
                self._wait_for_change(30)

    def _wait_for_change(self, timeout: float) -> bool:
        if timeout <= 0:
            return False
        changed = self._wake.wait(timeout=timeout)
        if changed:
            self._wake.clear()
        return changed

    def _run_once(self) -> None:
        self.log("开始执行签到任务")
        try:
            for line in self.run_fn():
                self.log(line)
            with self._lock:
                self._last_run = datetime.now()
                self._last_error = ""
            self.log("签到任务执行完成")
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            self.log(f"签到任务失败：{exc}")
        finally:
            with self._lock:
                self._running = False

    def _schedule_config(self) -> dict[str, Any]:
        schedule = self.config.get("schedule", {})
        return schedule if isinstance(schedule, dict) else {}

    def _compute_next_base_run(self, schedule: dict[str, Any], after: datetime) -> datetime:
        expression = str(schedule.get("cron", DEFAULT_CRON)).strip() or DEFAULT_CRON
        return CronExpression.parse(expression).next_after(after)

    def _make_schedule_signature(self, schedule: dict[str, Any]) -> tuple[Any, ...]:
        return (
            bool(schedule.get("enable", False)),
            str(schedule.get("cron", DEFAULT_CRON)),
            int(schedule.get("jitter_minutes", 45) or 0),
        )
