"""Планировщик ежедневной рассылки на базе APScheduler."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import Database
from services.broadcast import BroadcastService

logger = logging.getLogger(__name__)

JOB_ID = "daily_broadcast"


class BroadcastScheduler:
    """Управление задачей ежедневной рассылки."""

    def __init__(
        self,
        db: Database,
        broadcast: BroadcastService,
        owner_id: int,
    ) -> None:
        self.db = db
        self.broadcast = broadcast
        self.owner_id = owner_id
        self.scheduler = AsyncIOScheduler()
        self._started = False

    def start(self) -> None:
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("Планировщик запущен")

    def shutdown(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("Планировщик остановлен")

    async def setup_from_db(self) -> None:
        """Прочитать настройки из БД и поставить/снять задачу."""
        await self.reschedule()

    async def reschedule(self) -> None:
        auto = await self.db.get_setting("auto_enabled", "1")
        if self.scheduler.get_job(JOB_ID):
            self.scheduler.remove_job(JOB_ID)

        if auto != "1":
            logger.info("Авторассылка выключена — задача не планируется")
            return

        time_str = await self.db.get_setting("schedule_time", "10:00")
        tz = await self.db.get_setting("timezone", "Europe/Moscow")
        try:
            hour_s, minute_s = time_str.split(":")
            hour, minute = int(hour_s), int(minute_s)
        except ValueError:
            hour, minute = 10, 0
            logger.warning("Некорректное время в настройках, используем 10:00")

        trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)
        self.scheduler.add_job(
            self._job_wrapper,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "Задача рассылки запланирована на %02d:%02d (%s)",
            hour,
            minute,
            tz,
        )

    async def _job_wrapper(self) -> None:
        """Точка входа cron-задачи с защитой от параллельного запуска."""
        logger.info("Сработало расписание ежедневной рассылки")
        if self.broadcast.is_running:
            logger.warning("Пропуск: рассылка уже выполняется")
            return
        try:
            await self.broadcast.run(
                trigger_type="auto",
                notify_owner=True,
                owner_id=self.owner_id,
            )
        except Exception:
            logger.exception("Критическая ошибка в задаче рассылки")

    def make_reschedule_callback(self) -> Callable[[], Awaitable[None]]:
        async def _cb() -> None:
            await self.reschedule()

        return _cb
