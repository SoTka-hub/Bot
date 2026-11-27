"""Регистрация всех обработчиков."""

from aiogram import Router

from handlers.start import router as start_router
from handlers.stats import router as stats_router
from handlers.message_mgmt import router as message_router
from handlers.chats import router as chats_router
from handlers.schedule import router as schedule_router
from handlers.broadcast_ctrl import router as broadcast_router
from handlers.history import router as history_router


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_router(start_router)
    root.include_router(stats_router)
    root.include_router(message_router)
    root.include_router(chats_router)
    root.include_router(schedule_router)
    root.include_router(broadcast_router)
    root.include_router(history_router)
    return root
