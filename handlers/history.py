"""История отправок."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import Database
from keyboards.inline import back_main_kb, history_kb

router = Router(name="history")


@router.callback_query(F.data == "menu:history")
@router.callback_query(F.data.startswith("history:page:"))
async def show_history(callback: CallbackQuery, db: Database) -> None:
    page = 0
    if callback.data and callback.data.startswith("history:page:"):
        try:
            page = int(callback.data.split(":")[2])
        except (IndexError, ValueError):
            page = 0

    runs = await db.get_broadcast_history(limit=30)
    if not runs:
        await callback.message.edit_text(
            "📋 История пуста. Рассылок ещё не было.",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📋 <b>История последних рассылок</b> (до 30)\n"
        "Нажмите на запись, чтобы увидеть ошибки:",
        reply_markup=history_kb(runs, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:run:"))
async def show_run_details(callback: CallbackQuery, db: Database) -> None:
    run_id = int(callback.data.split(":")[2])
    runs = await db.get_broadcast_history(limit=100)
    run = next((r for r in runs if r["id"] == run_id), None)
    if not run:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    errors = await db.get_run_errors(run_id)
    started = str(run.get("started_at", "")).replace("T", " ")
    finished = str(run.get("finished_at") or "—").replace("T", " ")
    lines = [
        f"📋 <b>Рассылка #{run_id}</b>",
        "",
        f"Тип: {run.get('trigger_type')}",
        f"Цикл: {run.get('cycle_date')}",
        f"Статус: {run.get('status')}",
        f"Начало: {started}",
        f"Конец: {finished}",
        f"Всего: {run.get('total')}",
        f"Успешно: {run.get('success')}",
        f"Ошибки: {run.get('failed')}",
    ]
    if errors:
        lines.append("")
        lines.append("<b>Ошибки:</b>")
        for err in errors[:20]:
            title = err.get("chat_title") or err.get("chat_id")
            lines.append(f"• {title}: {err.get('error_message')}")
        if len(errors) > 20:
            lines.append(f"… и ещё {len(errors) - 20}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=history_kb(runs, page=0),
    )
    await callback.answer()
