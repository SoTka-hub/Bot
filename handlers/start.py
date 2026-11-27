"""Команда /start и главное меню."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.inline import main_menu_kb

router = Router(name="start")


def main_menu_text() -> str:
    return (
        "🤖 <b>Панель управления рассылкой</b>\n\n"
        "Выберите раздел:"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(main_menu_text(), reply_markup=main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(main_menu_text(), reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Справка</b>\n\n"
        "/start — открыть панель управления\n"
        "/menu — главное меню\n"
        "/help — эта справка\n"
        "/add_chat — добавить текущую группу в рассылку "
        "(отправьте команду в группе, где есть бот)\n\n"
        "Все настройки и данные сохраняются в базе и "
        "не сбрасываются после перезапуска."
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(main_menu_text(), reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "action:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(main_menu_text(), reply_markup=main_menu_kb())
    await callback.answer("Отменено")
