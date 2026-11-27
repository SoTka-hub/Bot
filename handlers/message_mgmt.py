"""Управление сообщением для рассылки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database import Database
from keyboards.inline import (
    cancel_kb,
    message_menu_kb,
    parse_mode_kb,
)
from services.broadcast import BroadcastService

router = Router(name="message")


class MessageStates(StatesGroup):
    waiting_create = State()
    waiting_edit = State()
    waiting_replace = State()
    waiting_photo = State()


def _message_summary(msg: dict | None) -> str:
    if not msg:
        return (
            "💬 <b>Управление сообщением</b>\n\n"
            "Сообщение ещё не создано."
        )
    preview = (msg.get("text") or "")[:200]
    if msg.get("text") and len(msg["text"]) > 200:
        preview += "…"
    photo = "да" if msg.get("photo_file_id") else "нет"
    return (
        "💬 <b>Управление сообщением</b>\n\n"
        f"Формат: <b>{msg.get('parse_mode', 'HTML')}</b>\n"
        f"Фото: <b>{photo}</b>\n"
        f"Обновлено: {str(msg.get('updated_at', '')).replace('T', ' ')}\n\n"
        f"<b>Текст:</b>\n{preview or '<i>пустой</i>'}"
    )


@router.callback_query(F.data == "menu:message")
async def message_menu(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    await state.clear()
    msg = await db.get_current_message()
    await callback.message.edit_text(
        _message_summary(msg),
        reply_markup=message_menu_kb(has_message=msg is not None),
    )
    await callback.answer()


@router.callback_query(F.data == "msg:create")
async def msg_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MessageStates.waiting_create)
    await callback.message.edit_text(
        "➕ <b>Создание сообщения</b>\n\n"
        "Отправьте текст сообщения.\n"
        "Можно сразу прислать фото с подписью — оно станет вложением.\n\n"
        "Поддерживается HTML (по умолчанию) или MarkdownV2 "
        "(режим можно сменить позже).",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(MessageStates.waiting_create)
async def msg_create_save(message: Message, state: FSMContext, db: Database) -> None:
    text, photo = _extract_content(message)
    if not text and not photo:
        await message.answer(
            "❌ Нужен текст или фото. Попробуйте ещё раз.",
            reply_markup=cancel_kb(),
        )
        return
    await db.create_message(text=text, parse_mode="HTML", photo_file_id=photo)
    await state.clear()
    msg = await db.get_current_message()
    await message.answer(
        "✅ Сообщение создано.\n\n" + _message_summary(msg),
        reply_markup=message_menu_kb(True),
    )


@router.callback_query(F.data == "msg:edit")
async def msg_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MessageStates.waiting_edit)
    await callback.message.edit_text(
        "✏️ Отправьте новый текст сообщения.\n"
        "Фото (если есть) сохранится.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(MessageStates.waiting_edit)
async def msg_edit_save(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or message.caption or "").strip()
    if not text:
        await message.answer("❌ Текст не должен быть пустым.", reply_markup=cancel_kb())
        return
    ok = await db.update_current_message(text=text)
    await state.clear()
    if not ok:
        await message.answer("Сообщение не найдено. Создайте новое.")
        return
    msg = await db.get_current_message()
    await message.answer(
        "✅ Текст обновлён.\n\n" + _message_summary(msg),
        reply_markup=message_menu_kb(True),
    )


@router.callback_query(F.data == "msg:replace")
async def msg_replace_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MessageStates.waiting_replace)
    await callback.message.edit_text(
        "🔄 <b>Полная замена</b>\n\n"
        "Отправьте новый текст или фото с подписью.\n"
        "Старое содержимое будет заменено.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(MessageStates.waiting_replace)
async def msg_replace_save(message: Message, state: FSMContext, db: Database) -> None:
    text, photo = _extract_content(message)
    if not text and not photo:
        await message.answer(
            "❌ Нужен текст или фото.",
            reply_markup=cancel_kb(),
        )
        return
    current = await db.get_current_message()
    parse_mode = current.get("parse_mode", "HTML") if current else "HTML"
    await db.create_message(text=text, parse_mode=parse_mode, photo_file_id=photo)
    await state.clear()
    msg = await db.get_current_message()
    await message.answer(
        "✅ Сообщение полностью заменено.\n\n" + _message_summary(msg),
        reply_markup=message_menu_kb(True),
    )


@router.callback_query(F.data == "msg:photo")
async def msg_photo_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MessageStates.waiting_photo)
    await callback.message.edit_text(
        "🖼 Отправьте фотографию.\n"
        "Подпись к фото можно не указывать — текущий текст сохранится.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(MessageStates.waiting_photo, F.photo)
async def msg_photo_save(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    caption = (message.caption or "").strip()
    current = await db.get_current_message()
    if not current:
        await db.create_message(
            text=caption,
            parse_mode="HTML",
            photo_file_id=photo_id,
        )
    else:
        kwargs = {"photo_file_id": photo_id}
        if caption:
            kwargs["text"] = caption
        await db.update_current_message(**kwargs)
    await state.clear()
    msg = await db.get_current_message()
    await message.answer(
        "✅ Фото сохранено.\n\n" + _message_summary(msg),
        reply_markup=message_menu_kb(True),
    )


@router.message(MessageStates.waiting_photo)
async def msg_photo_invalid(message: Message) -> None:
    await message.answer("❌ Пришлите именно фотографию.", reply_markup=cancel_kb())


@router.callback_query(F.data == "msg:clear_photo")
async def msg_clear_photo(callback: CallbackQuery, db: Database) -> None:
    ok = await db.update_current_message(clear_photo=True)
    if not ok:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return
    msg = await db.get_current_message()
    await callback.message.edit_text(
        "✅ Фото удалено.\n\n" + _message_summary(msg),
        reply_markup=message_menu_kb(True),
    )
    await callback.answer()


@router.callback_query(F.data == "msg:parse_mode")
async def msg_parse_mode(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🔤 Выберите режим форматирования:",
        reply_markup=parse_mode_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("msg:set_mode:"))
async def msg_set_mode(callback: CallbackQuery, db: Database) -> None:
    mode = callback.data.split(":")[2]
    ok = await db.update_current_message(parse_mode=mode)
    if not ok:
        await callback.answer("Сначала создайте сообщение", show_alert=True)
        return
    msg = await db.get_current_message()
    await callback.message.edit_text(
        f"✅ Режим форматирования: <b>{mode}</b>\n\n" + _message_summary(msg),
        reply_markup=message_menu_kb(True),
    )
    await callback.answer()


@router.callback_query(F.data == "msg:preview")
async def msg_preview(callback: CallbackQuery, db: Database) -> None:
    msg = await db.get_current_message()
    if not msg:
        await callback.answer("Сообщение не создано", show_alert=True)
        return

    await callback.answer()
    parse_mode = BroadcastService._resolve_parse_mode(msg.get("parse_mode", "HTML"))
    text = msg.get("text") or ""
    try:
        if msg.get("photo_file_id"):
            await callback.message.answer_photo(
                photo=msg["photo_file_id"],
                caption=text or None,
                parse_mode=parse_mode if text else None,
            )
        else:
            await callback.message.answer(text, parse_mode=parse_mode)
        await callback.message.answer(
            "👁 Это предпросмотр сообщения перед рассылкой.",
            reply_markup=message_menu_kb(True),
        )
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка предпросмотра (проверьте разметку):\n<code>{e}</code>",
            reply_markup=message_menu_kb(True),
        )


@router.callback_query(F.data == "msg:delete")
async def msg_delete(callback: CallbackQuery, db: Database) -> None:
    ok = await db.delete_current_message()
    if ok:
        await callback.message.edit_text(
            "🗑 Сообщение удалено.",
            reply_markup=message_menu_kb(False),
        )
        await callback.answer("Удалено")
    else:
        await callback.answer("Нечего удалять", show_alert=True)


def _extract_content(message: Message) -> tuple[str, str | None]:
    photo = None
    if message.photo:
        photo = message.photo[-1].file_id
        text = (message.caption or "").strip()
    else:
        text = (message.text or "").strip()
    return text, photo
