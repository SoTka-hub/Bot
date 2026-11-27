"""Inline-клавиатуры панели управления."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Управление сообщением", callback_data="menu:message"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 Управление чатами", callback_data="menu:chats"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⏰ Настройка расписания", callback_data="menu:schedule"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="▶️ Запустить рассылку", callback_data="menu:broadcast_start"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⏸ Приостановить рассылку", callback_data="menu:broadcast_pause"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📋 История отправок", callback_data="menu:history"
        )
    )
    return builder.as_markup()


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main")]
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="action:cancel")]
        ]
    )


def chats_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить чат", callback_data="chats:add")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список чатов", callback_data="chats:list")
    )
    builder.row(
        InlineKeyboardButton(
            text="🔢 Лимит активных чатов", callback_data="chats:limit"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Количество чатов", callback_data="chats:count"
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main")
    )
    return builder.as_markup()


def chat_list_kb(
    chats: list[dict[str, Any]],
    page: int = 0,
    per_page: int = 8,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    total = len(chats)
    start = page * per_page
    end = start + per_page
    page_chats = chats[start:end]

    for chat in page_chats:
        status = "✅" if chat["is_active"] else "⏸"
        title = (chat.get("title") or str(chat["chat_id"]))[:30]
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {title}",
                callback_data=f"chats:view:{chat['chat_id']}",
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=f"chats:list:{page - 1}"
            )
        )
    if end < total:
        nav.append(
            InlineKeyboardButton(
                text="➡️", callback_data=f"chats:list:{page + 1}"
            )
        )
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu:chats")
    )
    return builder.as_markup()


def chat_actions_kb(chat_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "⏸ Отключить" if is_active else "▶️ Включить"
    builder.row(
        InlineKeyboardButton(
            text=toggle_text,
            callback_data=f"chats:toggle:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔍 Проверить доступность",
            callback_data=f"chats:check:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=f"chats:delete:{chat_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ К списку", callback_data="chats:list")
    )
    return builder.as_markup()


def message_menu_kb(has_message: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_message:
        builder.row(
            InlineKeyboardButton(
                text="✏️ Редактировать текст", callback_data="msg:edit"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔄 Заменить полностью", callback_data="msg:replace"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🖼 Прикрепить / сменить фото", callback_data="msg:photo"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🗑 Убрать фото", callback_data="msg:clear_photo"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔤 Режим форматирования", callback_data="msg:parse_mode"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="👁 Предпросмотр", callback_data="msg:preview"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🗑 Удалить сообщение", callback_data="msg:delete"
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="➕ Создать сообщение", callback_data="msg:create"
            )
        )
    builder.row(
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main")
    )
    return builder.as_markup()


def parse_mode_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="HTML", callback_data="msg:set_mode:HTML")
    )
    builder.row(
        InlineKeyboardButton(
            text="MarkdownV2", callback_data="msg:set_mode:MarkdownV2"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Без форматирования", callback_data="msg:set_mode:None"
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu:message")
    )
    return builder.as_markup()


def schedule_menu_kb(auto_enabled: bool, paused: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🕐 Изменить время", callback_data="sched:time"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🌍 Изменить часовой пояс", callback_data="sched:tz"
        )
    )
    auto_text = "🔴 Выключить авторассылку" if auto_enabled else "🟢 Включить авторассылку"
    builder.row(
        InlineKeyboardButton(text=auto_text, callback_data="sched:toggle_auto")
    )
    pause_text = "▶️ Возобновить" if paused else "⏸ Приостановить"
    builder.row(
        InlineKeyboardButton(text=pause_text, callback_data="sched:toggle_pause")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main")
    )
    return builder.as_markup()


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить отправку",
                    callback_data="broadcast:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="menu:main",
                )
            ],
        ]
    )


def history_kb(runs: list[dict[str, Any]], page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    per_page = 5
    start = page * per_page
    end = start + per_page
    for run in runs[start:end]:
        started = (run.get("started_at") or "")[:16].replace("T", " ")
        builder.row(
            InlineKeyboardButton(
                text=f"#{run['id']} {started} ✅{run['success']} ❌{run['failed']}",
                callback_data=f"history:run:{run['id']}",
            )
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"history:page:{page - 1}")
        )
    if end < len(runs):
        nav.append(
            InlineKeyboardButton(text="➡️", callback_data=f"history:page:{page + 1}")
        )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main")
    )
    return builder.as_markup()
