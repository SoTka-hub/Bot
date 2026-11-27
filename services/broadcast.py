"""Сервис ежедневной и ручной рассылки сообщений."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramBadRequest,
    TelegramAPIError,
)
from aiogram.enums import ParseMode

from database import Database

logger = logging.getLogger(__name__)

# Минимальная пауза между отправками (защита от flood)
SEND_DELAY_SECONDS = 0.05


class BroadcastService:
    """Логика рассылки с защитой от дублей и flood-control."""

    def __init__(self, db: Database, bot: Bot) -> None:
        self.db = db
        self.bot = bot
        self._lock = asyncio.Lock()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def get_cycle_date(self) -> str:
        """Дата текущего дневного цикла в часовом поясе настроек."""
        tz_name = await self.db.get_setting("timezone", "Europe/Moscow")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")
        return datetime.now(tz).strftime("%Y-%m-%d")

    async def run(
        self,
        trigger_type: str = "auto",
        notify_owner: bool = True,
        owner_id: Optional[int] = None,
    ) -> dict:
        """
        Запустить рассылку.

        Защита:
        - asyncio.Lock — повторный запуск не начнётся, пока идёт текущий;
        - проверка send_logs по cycle_date — не шлём повторно в тот же чат.
        """
        if self._lock.locked() or self._running:
            logger.warning("Рассылка уже выполняется — повторный запуск пропущен")
            return {
                "ok": False,
                "reason": "already_running",
                "message": "Рассылка уже выполняется. Дождитесь завершения.",
            }

        async with self._lock:
            self._running = True
            try:
                return await self._do_broadcast(
                    trigger_type=trigger_type,
                    notify_owner=notify_owner,
                    owner_id=owner_id,
                )
            finally:
                self._running = False

    async def _do_broadcast(
        self,
        trigger_type: str,
        notify_owner: bool,
        owner_id: Optional[int],
    ) -> dict:
        paused = await self.db.get_setting("broadcast_paused", "0")
        if trigger_type == "auto" and paused == "1":
            logger.info("Авторассылка приостановлена — пропуск")
            return {
                "ok": False,
                "reason": "paused",
                "message": "Автоматическая рассылка приостановлена.",
            }

        message = await self.db.get_current_message()
        if not message or (not message.get("text") and not message.get("photo_file_id")):
            text = "Нет сообщения для рассылки. Создайте его в разделе «Управление сообщением»."
            logger.warning(text)
            if notify_owner and owner_id:
                await self._safe_notify(owner_id, f"⚠️ {text}")
            return {"ok": False, "reason": "no_message", "message": text}

        limit = await self.db.get_active_limit()
        chats = await self.db.get_active_chats(limit=limit if limit > 0 else None)
        if not chats:
            text = "Нет активных чатов для рассылки."
            logger.warning(text)
            if notify_owner and owner_id:
                await self._safe_notify(owner_id, f"⚠️ {text}")
            return {"ok": False, "reason": "no_chats", "message": text}

        cycle_date = await self.get_cycle_date()
        already_sent = await self.db.get_sent_chat_ids_in_cycle(cycle_date)

        # Продолжаем только для чатов без успешной отправки в этом цикле
        pending = [c for c in chats if c["chat_id"] not in already_sent]
        skipped = len(chats) - len(pending)

        if not pending:
            text = (
                f"Все активные чаты уже получили сообщение сегодня ({cycle_date}).\n"
                f"Пропущено: {skipped}"
            )
            logger.info(text)
            if notify_owner and owner_id and trigger_type == "manual":
                await self._safe_notify(owner_id, f"ℹ️ {text}")
            return {
                "ok": True,
                "reason": "already_done",
                "message": text,
                "total": len(chats),
                "success": skipped,
                "failed": 0,
                "skipped": skipped,
            }

        run_id = await self.db.create_broadcast_run(trigger_type, cycle_date)
        logger.info(
            "Старт рассылки #%s (%s): чатов=%s, к отправке=%s, уже отправлено=%s",
            run_id,
            trigger_type,
            len(chats),
            len(pending),
            skipped,
        )

        success = 0
        failed = 0
        errors: list[dict] = []

        parse_mode = self._resolve_parse_mode(message.get("parse_mode", "HTML"))

        for chat in pending:
            chat_id = chat["chat_id"]
            title = chat.get("title") or str(chat_id)
            try:
                await self._send_to_chat(chat_id, message, parse_mode)
                await self.db.add_send_log(
                    run_id=run_id,
                    chat_id=chat_id,
                    chat_title=title,
                    status="success",
                    cycle_date=cycle_date,
                )
                success += 1
                logger.info("Отправлено в %s (%s)", title, chat_id)
            except Exception as exc:
                err_text = self._format_error(exc)
                await self.db.add_send_log(
                    run_id=run_id,
                    chat_id=chat_id,
                    chat_title=title,
                    status="error",
                    cycle_date=cycle_date,
                    error_message=err_text,
                )
                failed += 1
                errors.append({"chat_id": chat_id, "title": title, "error": err_text})
                logger.error("Ошибка отправки в %s (%s): %s", title, chat_id, err_text)

            await asyncio.sleep(SEND_DELAY_SECONDS)

        total = len(pending)
        await self.db.finish_broadcast_run(run_id, total, success, failed)

        report = self._build_report(
            total=total,
            success=success,
            failed=failed,
            skipped=skipped,
            errors=errors,
            cycle_date=cycle_date,
            trigger_type=trigger_type,
        )
        logger.info("Рассылка #%s завершена: ok=%s fail=%s", run_id, success, failed)

        if notify_owner and owner_id:
            await self._safe_notify(owner_id, report)

        return {
            "ok": True,
            "run_id": run_id,
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "report": report,
        }

    async def _send_to_chat(
        self,
        chat_id: int,
        message: dict,
        parse_mode: Optional[str],
    ) -> None:
        """Отправка с обработкой RetryAfter."""
        text = message.get("text") or ""
        photo = message.get("photo_file_id")
        retries = 3

        for attempt in range(retries):
            try:
                if photo:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=text or None,
                        parse_mode=parse_mode if text else None,
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=parse_mode,
                    )
                return
            except TelegramRetryAfter as e:
                wait = int(e.retry_after) + 1
                logger.warning(
                    "Flood control: ждём %s сек (попытка %s/%s)",
                    wait,
                    attempt + 1,
                    retries,
                )
                await asyncio.sleep(wait)
            except TelegramNetworkError as e:
                logger.warning("Сетевая ошибка: %s (попытка %s)", e, attempt + 1)
                await asyncio.sleep(2 ** attempt)

        # Последняя попытка — пусть исключение всплывёт
        if photo:
            await self.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text or None,
                parse_mode=parse_mode if text else None,
            )
        else:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )

    async def check_chat_access(self, chat_id: int) -> tuple[bool, str]:
        """Проверить, может ли бот писать в чат."""
        try:
            chat = await self.bot.get_chat(chat_id)
            me = await self.bot.get_me()
            member = await self.bot.get_chat_member(chat_id, me.id)

            status = getattr(member, "status", None)
            if status in ("left", "kicked"):
                msg = "Бот не состоит в этом чате"
                await self.db.update_chat_info(
                    chat_id,
                    title=getattr(chat, "title", None) or getattr(chat, "full_name", None),
                    check_status=msg,
                )
                return False, msg

            can_post = True
            if status == "restricted":
                can_post = bool(getattr(member, "can_send_messages", False))

            # В каналах / супергруппах с темами может понадобиться право на сообщения
            if hasattr(member, "can_post_messages") and member.can_post_messages is False:
                can_post = False

            title = getattr(chat, "title", None) or getattr(chat, "full_name", str(chat_id))
            username = getattr(chat, "username", None)

            if can_post:
                status_text = "OK — бот может отправлять сообщения"
            else:
                status_text = "Нет прав на отправку сообщений"

            await self.db.update_chat_info(
                chat_id,
                title=title,
                username=username,
                check_status=status_text,
            )
            return can_post, status_text
        except TelegramForbiddenError:
            msg = "Бот заблокирован или удалён из чата"
            await self.db.update_chat_info(chat_id, check_status=msg)
            return False, msg
        except TelegramBadRequest as e:
            msg = f"Чат недоступен: {e}"
            await self.db.update_chat_info(chat_id, check_status=msg)
            return False, msg
        except TelegramAPIError as e:
            msg = f"Ошибка API: {e}"
            await self.db.update_chat_info(chat_id, check_status=msg)
            return False, msg
        except Exception as e:
            msg = f"Ошибка проверки: {e}"
            await self.db.update_chat_info(chat_id, check_status=msg)
            return False, msg

    @staticmethod
    def _resolve_parse_mode(mode: str) -> Optional[str]:
        mapping = {
            "HTML": ParseMode.HTML,
            "MarkdownV2": ParseMode.MARKDOWN_V2,
            "Markdown": ParseMode.MARKDOWN,
            "None": None,
            "": None,
        }
        return mapping.get(mode, ParseMode.HTML)

    @staticmethod
    def _format_error(exc: Exception) -> str:
        if isinstance(exc, TelegramForbiddenError):
            return "Бот не может писать в чат (нет прав / удалён)"
        if isinstance(exc, TelegramBadRequest):
            return f"Некорректный запрос: {exc}"
        if isinstance(exc, TelegramRetryAfter):
            return f"Flood control: retry after {exc.retry_after}s"
        if isinstance(exc, TelegramAPIError):
            return f"Telegram API: {exc}"
        return str(exc)[:300]

    @staticmethod
    def _build_report(
        total: int,
        success: int,
        failed: int,
        skipped: int,
        errors: list[dict],
        cycle_date: str,
        trigger_type: str,
    ) -> str:
        kind = "ручная" if trigger_type == "manual" else "автоматическая"
        lines = [
            "📬 Рассылка завершена.",
            "",
            f"Тип: {kind}",
            f"Цикл: {cycle_date}",
            f"Всего чатов к отправке: {total}",
            f"Успешно отправлено: {success}",
            f"Ошибки: {failed}",
        ]
        if skipped:
            lines.append(f"Уже были отправлены ранее сегодня: {skipped}")

        if errors:
            lines.append("")
            lines.append("Чаты с ошибками:")
            for item in errors[:30]:
                lines.append(f"• {item['title']} ({item['chat_id']}): {item['error']}")
            if len(errors) > 30:
                lines.append(f"… и ещё {len(errors) - 30}")

        return "\n".join(lines)

    async def _safe_notify(self, owner_id: int, text: str) -> None:
        try:
            # Telegram лимит ~4096 символов
            if len(text) > 4000:
                text = text[:3990] + "\n…"
            await self.bot.send_message(owner_id, text)
        except Exception as e:
            logger.error("Не удалось отправить отчёт владельцу: %s", e)
