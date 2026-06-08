"""
DScheduler - D 盘每日自动扫描调度器

在 Flask 后台线程中运行，每天定时触发增量扫描。
也支持手动触发。
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from config.logging_config import get_logger

logger = get_logger("d_scheduler")


class DScheduler:
    """每日扫描调度器"""

    def __init__(self, indexer, scan_hour: int = 3, scan_minute: int = 0):
        """
        Args:
            indexer: DIndexer 实例
            scan_hour: 每天几点扫描 (默认凌晨 3 点)
            scan_minute: 分钟
        """
        self.indexer = indexer
        self.scan_hour = scan_hour
        self.scan_minute = scan_minute
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._last_scan: Optional[datetime] = None
        self._last_result = None
        self._on_scan_complete: Optional[Callable] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def last_scan_time(self) -> Optional[str]:
        return self._last_scan.isoformat() if self._last_scan else None

    @property
    def last_result(self):
        return self._last_result

    def start(self, on_complete: Callable = None):
        """启动后台调度线程"""
        if self._running:
            return

        self._on_scan_complete = on_complete
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("已启动, 每天 %02d:%02d 自动扫描", self.scan_hour, self.scan_minute)

    def stop(self):
        """停止调度"""
        self._stop_event.set()
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("已停止")

    def trigger_now(self) -> dict:
        """立即手动触发一次扫描"""
        return self._do_scan("manual")

    def _run_loop(self):
        """调度主循环"""
        while not self._stop_event.is_set():
            now = datetime.now()
            next_scan = now.replace(
                hour=self.scan_hour,
                minute=self.scan_minute,
                second=0,
                microsecond=0,
            )
            if next_scan <= now:
                next_scan += timedelta(days=1)

            wait_seconds = (next_scan - now).total_seconds()
            logger.info("下次扫描: %s (等待 %.1f 小时)",
                       next_scan.strftime("%Y-%m-%d %H:%M"), wait_seconds / 3600)

            # 分段等待，方便响应 stop
            while wait_seconds > 0 and not self._stop_event.is_set():
                sleep_time = min(wait_seconds, 60)
                time.sleep(sleep_time)
                wait_seconds -= sleep_time

            if not self._stop_event.is_set():
                self._do_scan("scheduled")

    def _do_scan(self, trigger: str) -> dict:
        """执行扫描"""
        logger.info("开始 %s 扫描...", trigger)
        start = time.time()

        try:
            # 首次或索引为空则全量，否则增量
            if self.indexer.count == 0:
                result = self.indexer.index_all()
            else:
                result = self.indexer.incremental_scan()

            self._last_scan = datetime.now()
            self._last_result = result

            duration = time.time() - start
            logger.info("%s 扫描完成: %d 文件 %d 新chunk 耗时 %.1fs",
                       trigger, result.total_files, result.new_chunks, duration)

            if self._on_scan_complete:
                self._on_scan_complete(result)

            return {
                "trigger": trigger,
                "total_files": result.total_files,
                "new_chunks": result.new_chunks,
                "skipped_chunks": result.skipped_chunks,
                "duration_seconds": round(duration, 2),
                "timestamp": self.last_scan_time,
            }
        except Exception as e:
            logger.error("%s 扫描失败: %s", trigger, e)
            return {"trigger": trigger, "error": str(e)}
