"""Точка входа Telegram-бота ежедневной рассылки."""

from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BASE_DIR, load_config
from database import Database
from handlers import setup_routers
from scheduler import BroadcastScheduler
from services.broadcast import BroadcastService
from services.middleware import OwnerOnlyMiddleware


def setup_logging(level: str) -> None:
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        logs_dir / "bot.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Меньше шума от сторонних библиотек
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def main() -> None:
    config = load_config()
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    db = Database(
        str(config.database_path),
        default_timezone=config.default_timezone,
        default_active_limit=config.default_active_limit,
    )
    await db.connect()
    # После рестарта незавершённые запуски помечаем, чтобы не блокировать новые
    await db.mark_stale_runs_finished()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    broadcast = BroadcastService(db=db, bot=bot)
    scheduler = BroadcastScheduler(
        db=db,
        broadcast=broadcast,
        owner_id=config.owner_id,
    )

    # Доступ только владельцу
    owner_mw = OwnerOnlyMiddleware(config.owner_id)
    dp.message.middleware(owner_mw)
    dp.callback_query.middleware(owner_mw)

    dp.include_router(setup_routers())

    # Внедрение зависимостей в хендлеры
    dp["db"] = db
    dp["broadcast"] = broadcast
    dp["config"] = config
    dp["reschedule_job"] = scheduler.make_reschedule_callback()

    scheduler.start()
    await scheduler.setup_from_db()

    me = await bot.get_me()
    logger.info("Бот запущен: @%s (id=%s)", me.username, me.id)
    logger.info("Владелец: %s", config.owner_id)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await db.close()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
