"""
scheduler.py — Планировщик задач JARVIS (Phase 3)
APScheduler + SQLite для хранения напоминаний.

Использование:
    from scheduler import get_scheduler
    sched = get_scheduler()
    sched.set_tts(tts_speak_fn)
    sched.add_reminder("позвонить маме", "18:30")
"""

import re
import os
from datetime import datetime, timedelta
from typing import Callable, Optional


try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    APSCHEDULER_OK = True
except ImportError:
    APSCHEDULER_OK = False


DB_PATH = os.path.join(os.path.dirname(__file__), ".jarvis_tasks.sqlite")


class JarvisScheduler:
    def __init__(self):
        if not APSCHEDULER_OK:
            raise ImportError("pip install apscheduler sqlalchemy")

        jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{DB_PATH}")}
        self._sched = BackgroundScheduler(jobstores=jobstores, timezone="Europe/Moscow")
        self._sched.start()
        self._tts_fn: Optional[Callable[[str], None]] = None

    def set_tts(self, fn: Callable[[str], None]) -> None:
        self._tts_fn = fn

    def _notify(self, message: str) -> None:
        print(f"\n🔔 Напоминание: {message}")
        if self._tts_fn:
            self._tts_fn(f"Напоминание: {message}")

    # ── Добавление задач ──────────────────────────────────────────────────────

    def add_reminder(self, message: str, time_str: str) -> str:
        """Добавить напоминание в HH:MM."""
        m = re.match(r"(\d{1,2})[:\.](\d{2})", time_str.strip())
        if not m:
            return f"Не могу разобрать время: {time_str}"
        h, mn = int(m.group(1)), int(m.group(2))
        job_id = f"reminder_{h:02d}{mn:02d}_{message[:20].replace(' ', '_')}"
        self._sched.add_job(
            self._notify,
            CronTrigger(hour=h, minute=mn),
            id=job_id,
            args=[message],
            replace_existing=True,
        )
        return f"Напоминание '{message}' поставлено на {h:02d}:{mn:02d}"

    def add_once(self, message: str, minutes: int) -> str:
        """Однократное напоминание через N минут."""
        run_at = datetime.now() + timedelta(minutes=minutes)
        job_id = f"once_{message[:20].replace(' ', '_')}"
        self._sched.add_job(
            self._notify,
            DateTrigger(run_date=run_at),
            id=job_id,
            args=[message],
            replace_existing=True,
        )
        return f"Напомню через {minutes} мин: '{message}'"

    def setup_break_reminder(self, interval_min: int = 90) -> None:
        """Регулярное напоминание сделать перерыв."""
        self._sched.add_job(
            self._notify,
            IntervalTrigger(minutes=interval_min),
            id="break_reminder",
            args=["Время сделать перерыв! Встань и разомнись."],
            replace_existing=True,
        )

    def parse_and_add(self, user_text: str) -> str:
        """Парсит фразу вида 'напомни в 18:30 позвонить маме'."""
        time_m = re.search(r"\b(\d{1,2})[:\.](\d{2})\b", user_text)
        if time_m:
            time_str = time_m.group(0)
            message = re.sub(r"напомни[^\d]*\d{1,2}[:.]\d{2}\s*", "", user_text, flags=re.I).strip()
            message = message or "напоминание"
            return self.add_reminder(message, time_str)

        min_m = re.search(r"через\s+(\d+)\s+(?:минут|мин)", user_text, re.I)
        if min_m:
            mins = int(min_m.group(1))
            message = re.sub(r"через\s+\d+\s+(?:минут|мин)\s*", "", user_text, flags=re.I).strip()
            message = re.sub(r"^напомни\s*", "", message, flags=re.I).strip()
            message = message or "напоминание"
            return self.add_once(message, mins)

        return "Не понял время. Например: 'напомни в 18:30 позвонить' или 'напомни через 30 минут'"

    def list_tasks(self) -> list[dict]:
        jobs = []
        for job in self._sched.get_jobs():
            jobs.append({
                "id": job.id,
                "name": str(job.args[0]) if job.args else job.id,
                "next_run": str(job.next_run_time),
            })
        return jobs

    def remove(self, job_id: str) -> None:
        self._sched.remove_job(job_id)

    def shutdown(self) -> None:
        self._sched.shutdown(wait=False)


_instance: Optional[JarvisScheduler] = None


def get_scheduler() -> JarvisScheduler:
    global _instance
    if _instance is None:
        _instance = JarvisScheduler()
    return _instance
