"""Middleware: доступ только для владельца бота."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class OwnerOnlyMiddleware(BaseMiddleware):
    """Блокирует всех пользователей, кроме OWNER_ID."""

    def __init__(self, owner_id: int) -> None:
        self.owner_id = owner_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None or user.id != self.owner_id:
            # В группах молча игнорируем чужие сообщения,
            # в личке и на callback — сообщаем об отказе.
            if isinstance(event, Message) and event.chat.type == "private":
                await event.answer(
                    "⛔ Доступ запрещён.\n"
                    "Этот бот доступен только владельцу."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ запрещён", show_alert=True)
            return None

        return await handler(event, data)
