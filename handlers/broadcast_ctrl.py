"""Запуск и приостановка рассылки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import Database
from keyboards.inline import back_main_kb, confirm_broadcast_kb, main_menu_kb
from services.broadcast import BroadcastService

router = Router(name="broadcast_ctrl")


@router.callback_query(F.data == "menu:broadcast_pause")
async def pause_broadcast(callback: CallbackQuery, db: Database) -> None:
    paused = await db.get_setting("broadcast_paused", "0")
    if paused == "1":
        await callback.message.edit_text(
            "ℹ️ Рассылка уже приостановлена.\n"
            "Автоматические запуски не выполняются.\n\n"
            "Возобновить можно в разделе «Настройка расписания».",
            reply_markup=back_main_kb(),
        )
    else:
        await db.set_setting("broadcast_paused", "1")
        await callback.message.edit_text(
            "⏸ <b>Рассылка приостановлена.</b>\n\n"
            "Автоматические ежедневные отправки остановлены.\n"
            "Ручной запуск по-прежнему доступен.",
            reply_markup=back_main_kb(),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:broadcast_start")
async def broadcast_preview(
    callback: CallbackQuery,
    db: Database,
) -> None:
    """Показать итоговый вариант перед ручным запуском."""
    msg = await db.get_current_message()
    if not msg or (not msg.get("text") and not msg.get("photo_file_id")):
        await callback.message.edit_text(
            "⚠️ Сначала создайте сообщение в разделе "
            "«Управление сообщением».",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return

    limit = await db.get_active_limit()
    chats = await db.get_active_chats(limit=limit if limit > 0 else None)
    if not chats:
        await callback.message.edit_text(
            "⚠️ Нет активных чатов для рассылки.",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return

    await callback.answer()
    parse_mode = BroadcastService._resolve_parse_mode(msg.get("parse_mode", "HTML"))
    text = msg.get("text") or ""

    header = (
        "▶️ <b>Предпросмотр перед рассылкой</b>\n\n"
        f"Активных чатов к отправке: <b>{len(chats)}</b>\n"
        f"Формат: <b>{msg.get('parse_mode')}</b>\n"
        "Ниже — итоговый вариант сообщения.\n"
        "Подтвердите отправку, если всё верно."
    )
    await callback.message.edit_text(header)

    try:
        if msg.get("photo_file_id"):
            await callback.message.answer_photo(
                photo=msg["photo_file_id"],
                caption=text or None,
                parse_mode=parse_mode if text else None,
            )
        else:
            await callback.message.answer(text, parse_mode=parse_mode)
    except Exception as e:
        await callback.message.answer(
            f"❌ Не удалось показать предпросмотр:\n<code>{e}</code>\n"
            "Исправьте разметку сообщения."
        )
        return

    await callback.message.answer(
        "Запустить разовую ручную рассылку сейчас?",
        reply_markup=confirm_broadcast_kb(),
    )


@router.callback_query(F.data == "broadcast:confirm")
async def broadcast_confirm(
    callback: CallbackQuery,
    db: Database,
    broadcast: BroadcastService,
    config,
) -> None:
    if broadcast.is_running:
        await callback.answer("Рассылка уже выполняется", show_alert=True)
        return

    await callback.answer("Запускаю…")
    await callback.message.edit_text("⏳ Рассылка запущена, ожидайте отчёт…")

    result = await broadcast.run(
        trigger_type="manual",
        notify_owner=True,
        owner_id=config.owner_id,
    )

    if not result.get("ok") and result.get("reason") != "already_done":
        await callback.message.answer(
            f"⚠️ {result.get('message', 'Не удалось запустить рассылку')}",
            reply_markup=main_menu_kb(),
        )
    elif result.get("reason") == "already_done":
        await callback.message.answer(
            result.get("message", "Уже отправлено сегодня."),
            reply_markup=main_menu_kb(),
        )
    # При успехе отчёт уже уходит владельцу из сервиса
    else:
        await callback.message.answer(
            "✅ Готово. Подробный отчёт отправлен отдельным сообщением.",
            reply_markup=main_menu_kb(),
        )
