"""Управление чатами рассылки."""

from __future__ import annotations

import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database import Database
from keyboards.inline import (
    cancel_kb,
    chat_actions_kb,
    chat_list_kb,
    chats_menu_kb,
)
from services.broadcast import BroadcastService

router = Router(name="chats")


class ChatStates(StatesGroup):
    waiting_chat_id = State()
    waiting_limit = State()


@router.callback_query(F.data == "menu:chats")
async def chats_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "👥 <b>Управление чатами</b>\n\n"
        "Добавляйте только те группы, где администраторы "
        "разрешили публикации и добавили бота.\n"
        "Бот <b>не вступает</b> в группы самостоятельно.",
        reply_markup=chats_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "chats:add")
async def chats_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChatStates.waiting_chat_id)
    await callback.message.edit_text(
        "➕ <b>Добавление чата</b>\n\n"
        "Отправьте Telegram ID чата (например <code>-1001234567890</code>).\n\n"
        "Также можно в самой группе выполнить команду /add_chat "
        "(бот должен быть участником группы).",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ChatStates.waiting_chat_id)
async def chats_add_id(
    message: Message,
    state: FSMContext,
    db: Database,
    broadcast: BroadcastService,
    bot: Bot,
) -> None:
    raw = (message.text or "").strip()
    if not re.fullmatch(r"-?\d+", raw):
        await message.answer(
            "❌ Некорректный ID. Отправьте числовой ID чата.",
            reply_markup=cancel_kb(),
        )
        return

    chat_id = int(raw)
    title = str(chat_id)
    username = None
    try:
        chat = await bot.get_chat(chat_id)
        title = getattr(chat, "title", None) or getattr(chat, "full_name", title)
        username = getattr(chat, "username", None)
    except Exception:
        pass

    ok, msg = await db.add_chat(chat_id, title=title, username=username)
    await state.clear()
    if ok:
        can, status = await broadcast.check_chat_access(chat_id)
        await message.answer(
            f"✅ {msg}\n"
            f"Название: <b>{title}</b>\n"
            f"ID: <code>{chat_id}</code>\n"
            f"Проверка: {status}",
            reply_markup=chats_menu_kb(),
        )
    else:
        await message.answer(f"⚠️ {msg}", reply_markup=chats_menu_kb())


@router.message(Command("add_chat"))
async def cmd_add_chat(
    message: Message,
    db: Database,
    broadcast: BroadcastService,
) -> None:
    """Добавить текущий чат (удобно вызывать из группы)."""
    chat = message.chat
    if chat.type == "private":
        await message.answer(
            "Эту команду нужно отправить в группе, куда добавлен бот.\n"
            "Либо добавьте чат по ID через панель управления."
        )
        return

    ok, msg = await db.add_chat(
        chat.id,
        title=chat.title or str(chat.id),
        username=chat.username,
    )
    if ok:
        can, status = await broadcast.check_chat_access(chat.id)
        await message.answer(
            f"✅ Группа добавлена в рассылку.\nПроверка: {status}"
        )
    else:
        await message.answer(f"⚠️ {msg}")


@router.callback_query(F.data == "chats:list")
@router.callback_query(F.data.startswith("chats:list:"))
async def chats_list(callback: CallbackQuery, db: Database) -> None:
    page = 0
    if callback.data and callback.data.startswith("chats:list:"):
        try:
            page = int(callback.data.split(":")[2])
        except (IndexError, ValueError):
            page = 0

    chats = await db.get_all_chats()
    if not chats:
        await callback.message.edit_text(
            "Список чатов пуст. Добавьте первый чат.",
            reply_markup=chats_menu_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📋 <b>Чаты рассылки</b> ({len(chats)})\n"
        "✅ — активен, ⏸ — отключён\n"
        "Нажмите на чат для управления:",
        reply_markup=chat_list_kb(chats, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chats:view:"))
async def chat_view(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[2])
    chat = await db.get_chat(chat_id)
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return

    status = "активен ✅" if chat["is_active"] else "отключён ⏸"
    check = chat.get("last_check_status") or "ещё не проверялся"
    check_at = chat.get("last_check_at") or "—"
    username = f"@{chat['username']}" if chat.get("username") else "—"

    text = (
        f"💬 <b>{chat['title']}</b>\n\n"
        f"ID: <code>{chat['chat_id']}</code>\n"
        f"Username: {username}\n"
        f"Статус: {status}\n"
        f"Добавлен: {chat['added_at'].replace('T', ' ')}\n"
        f"Последняя проверка: {check}\n"
        f"Время проверки: {str(check_at).replace('T', ' ')}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=chat_actions_kb(chat_id, bool(chat["is_active"])),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chats:toggle:"))
async def chat_toggle(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[2])
    chat = await db.get_chat(chat_id)
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return

    new_active = not bool(chat["is_active"])

    if new_active:
        counts = await db.count_chats()
        limit = await db.get_active_limit()
        if limit > 0 and counts["active"] >= limit:
            await callback.answer(
                f"Достигнут лимит активных чатов ({limit}). "
                "Увеличьте лимит или отключите другой чат.",
                show_alert=True,
            )
            return

    await db.set_chat_active(chat_id, new_active)
    chat = await db.get_chat(chat_id)
    status = "включён" if new_active else "отключён"
    await callback.answer(f"Чат {status}")
    await callback.message.edit_reply_markup(
        reply_markup=chat_actions_kb(chat_id, new_active)
    )


@router.callback_query(F.data.startswith("chats:check:"))
async def chat_check(
    callback: CallbackQuery,
    db: Database,
    broadcast: BroadcastService,
) -> None:
    chat_id = int(callback.data.split(":")[2])
    await callback.answer("Проверяю…")
    can, status = await broadcast.check_chat_access(chat_id)
    icon = "✅" if can else "❌"
    chat = await db.get_chat(chat_id)
    if not chat:
        return
    text = (
        f"💬 <b>{chat['title']}</b>\n\n"
        f"ID: <code>{chat['chat_id']}</code>\n"
        f"Проверка: {icon} {status}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=chat_actions_kb(chat_id, bool(chat["is_active"])),
    )


@router.callback_query(F.data.startswith("chats:delete:"))
async def chat_delete(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[2])
    removed = await db.remove_chat(chat_id)
    if removed:
        await callback.answer("Чат удалён")
        chats = await db.get_all_chats()
        if chats:
            await callback.message.edit_text(
                f"📋 <b>Чаты рассылки</b> ({len(chats)})",
                reply_markup=chat_list_kb(chats),
            )
        else:
            await callback.message.edit_text(
                "Список чатов пуст.",
                reply_markup=chats_menu_kb(),
            )
    else:
        await callback.answer("Чат не найден", show_alert=True)


@router.callback_query(F.data == "chats:count")
async def chats_count(callback: CallbackQuery, db: Database) -> None:
    counts = await db.count_chats()
    limit = await db.get_active_limit()
    await callback.message.edit_text(
        "📊 <b>Количество чатов</b>\n\n"
        f"Всего: <b>{counts['total']}</b>\n"
        f"Активных: <b>{counts['active']}</b>\n"
        f"Отключённых: <b>{counts['inactive']}</b>\n"
        f"Лимит активных: <b>{limit if limit > 0 else 'без лимита'}</b>",
        reply_markup=chats_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "chats:limit")
async def chats_limit_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    current = await db.get_active_limit()
    await state.set_state(ChatStates.waiting_limit)
    await callback.message.edit_text(
        "🔢 <b>Лимит активных чатов</b>\n\n"
        f"Текущий лимит: <b>{current if current > 0 else 'без лимита'}</b>\n\n"
        "Отправьте новое число.\n"
        "• <code>20</code> — не больше 20 активных\n"
        "• <code>0</code> — без ограничения\n\n"
        "Лимит ограничивает, сколько активных чатов участвует в рассылке.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ChatStates.waiting_limit)
async def chats_limit_set(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("❌ Введите целое число ≥ 0.", reply_markup=cancel_kb())
        return
    value = int(raw)
    await db.set_setting("active_chats_limit", str(value))
    await state.clear()
    text = "без ограничения" if value == 0 else str(value)
    await message.answer(
        f"✅ Лимит активных чатов установлен: <b>{text}</b>",
        reply_markup=chats_menu_kb(),
    )
