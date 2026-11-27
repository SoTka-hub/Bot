"""Настройка расписания автоматической рассылки."""

from __future__ import annotations

import re
from zoneinfo import available_timezones

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database import Database
from keyboards.inline import cancel_kb, schedule_menu_kb

router = Router(name="schedule")

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ScheduleStates(StatesGroup):
    waiting_time = State()
    waiting_tz = State()


async def _schedule_text(db: Database) -> str:
    settings = await db.get_all_settings()
    time_ = settings.get("schedule_time", "10:00")
    tz = settings.get("timezone", "Europe/Moscow")
    auto = settings.get("auto_enabled", "1") == "1"
    paused = settings.get("broadcast_paused", "0") == "1"
    return (
        "⏰ <b>Настройка расписания</b>\n\n"
        f"Время отправки: <b>{time_}</b>\n"
        f"Часовой пояс: <b>{tz}</b>\n"
        f"Частота: <b>1 раз в сутки</b>\n"
        f"Авторассылка: <b>{'включена' if auto else 'выключена'}</b>\n"
        f"Статус: <b>{'приостановлена' if paused else 'активна'}</b>\n\n"
        "Настройки сохраняются в базе и переживают перезапуск."
    )


@router.callback_query(F.data == "menu:schedule")
async def schedule_menu(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    await state.clear()
    settings = await db.get_all_settings()
    auto = settings.get("auto_enabled", "1") == "1"
    paused = settings.get("broadcast_paused", "0") == "1"
    await callback.message.edit_text(
        await _schedule_text(db),
        reply_markup=schedule_menu_kb(auto, paused),
    )
    await callback.answer()


@router.callback_query(F.data == "sched:time")
async def sched_time_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ScheduleStates.waiting_time)
    await callback.message.edit_text(
        "🕐 Отправьте время в формате <b>ЧЧ:ММ</b>\n"
        "Например: <code>09:30</code> или <code>18:00</code>",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ScheduleStates.waiting_time)
async def sched_time_set(
    message: Message,
    state: FSMContext,
    db: Database,
    reschedule_job,
) -> None:
    raw = (message.text or "").strip()
    match = TIME_RE.match(raw)
    if not match:
        await message.answer(
            "❌ Неверный формат. Пример: <code>10:00</code>",
            reply_markup=cancel_kb(),
        )
        return

    time_str = f"{int(match.group(1)):02d}:{match.group(2)}"
    await db.set_setting("schedule_time", time_str)
    await state.clear()
    await reschedule_job()
    settings = await db.get_all_settings()
    await message.answer(
        f"✅ Время отправки установлено: <b>{time_str}</b>\n\n"
        + await _schedule_text(db),
        reply_markup=schedule_menu_kb(
            settings.get("auto_enabled", "1") == "1",
            settings.get("broadcast_paused", "0") == "1",
        ),
    )


@router.callback_query(F.data == "sched:tz")
async def sched_tz_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ScheduleStates.waiting_tz)
    await callback.message.edit_text(
        "🌍 Отправьте название часового пояса (IANA).\n\n"
        "Примеры:\n"
        "• <code>Europe/Moscow</code>\n"
        "• <code>Europe/Kyiv</code>\n"
        "• <code>Asia/Yekaterinburg</code>\n"
        "• <code>UTC</code>",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ScheduleStates.waiting_tz)
async def sched_tz_set(
    message: Message,
    state: FSMContext,
    db: Database,
    reschedule_job,
) -> None:
    tz = (message.text or "").strip()
    if tz not in available_timezones():
        await message.answer(
            "❌ Неизвестный часовой пояс. Проверьте написание.\n"
            "Пример: <code>Europe/Moscow</code>",
            reply_markup=cancel_kb(),
        )
        return

    await db.set_setting("timezone", tz)
    await state.clear()
    await reschedule_job()
    settings = await db.get_all_settings()
    await message.answer(
        f"✅ Часовой пояс: <b>{tz}</b>\n\n" + await _schedule_text(db),
        reply_markup=schedule_menu_kb(
            settings.get("auto_enabled", "1") == "1",
            settings.get("broadcast_paused", "0") == "1",
        ),
    )


@router.callback_query(F.data == "sched:toggle_auto")
async def sched_toggle_auto(
    callback: CallbackQuery,
    db: Database,
    reschedule_job,
) -> None:
    current = await db.get_setting("auto_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("auto_enabled", new_val)
    await reschedule_job()
    settings = await db.get_all_settings()
    await callback.message.edit_text(
        await _schedule_text(db),
        reply_markup=schedule_menu_kb(
            settings.get("auto_enabled", "1") == "1",
            settings.get("broadcast_paused", "0") == "1",
        ),
    )
    await callback.answer(
        "Авторассылка включена" if new_val == "1" else "Авторассылка выключена"
    )


@router.callback_query(F.data == "sched:toggle_pause")
async def sched_toggle_pause(callback: CallbackQuery, db: Database) -> None:
    current = await db.get_setting("broadcast_paused", "0")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("broadcast_paused", new_val)
    settings = await db.get_all_settings()
    await callback.message.edit_text(
        await _schedule_text(db),
        reply_markup=schedule_menu_kb(
            settings.get("auto_enabled", "1") == "1",
            settings.get("broadcast_paused", "0") == "1",
        ),
    )
    await callback.answer(
        "Рассылка возобновлена" if new_val == "0" else "Рассылка приостановлена"
    )
