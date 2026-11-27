"""Раздел статистики."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import Database
from keyboards.inline import back_main_kb

router = Router(name="stats")


@router.callback_query(F.data == "menu:stats")
async def show_stats(callback: CallbackQuery, db: Database) -> None:
    counts = await db.count_chats()
    send_stats = await db.get_send_stats()
    last_at = await db.get_setting("last_broadcast_at", "")
    limit = await db.get_active_limit()
    paused = await db.get_setting("broadcast_paused", "0")
    auto = await db.get_setting("auto_enabled", "1")
    schedule_time = await db.get_setting("schedule_time", "10:00")
    timezone = await db.get_setting("timezone", "Europe/Moscow")

    history = await db.get_broadcast_history(limit=5)
    history_lines = []
    for run in history:
        started = (run.get("started_at") or "")[:16].replace("T", " ")
        status = run.get("status", "")
        history_lines.append(
            f"• #{run['id']} {started} — ✅{run['success']} ❌{run['failed']} ({status})"
        )
    history_block = "\n".join(history_lines) if history_lines else "Пока нет рассылок"

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Всего добавлено чатов: <b>{counts['total']}</b>\n"
        f"Активных чатов: <b>{counts['active']}</b>\n"
        f"Отключённых чатов: <b>{counts['inactive']}</b>\n"
        f"Лимит активных: <b>{limit if limit > 0 else 'без лимита'}</b>\n\n"
        f"Успешных отправок: <b>{send_stats['success']}</b>\n"
        f"Неудачных отправок: <b>{send_stats['failed']}</b>\n"
        f"Последняя рассылка: <b>{last_at.replace('T', ' ') if last_at else '—'}</b>\n\n"
        f"Авторассылка: <b>{'включена' if auto == '1' else 'выключена'}</b>\n"
        f"Статус: <b>{'приостановлена' if paused == '1' else 'активна'}</b>\n"
        f"Расписание: <b>{schedule_time} ({timezone})</b>\n\n"
        f"<b>Последние рассылки:</b>\n{history_block}"
    )
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()
