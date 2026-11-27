"""Слой работы с SQLite: схема, CRUD и настройки."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    """Асинхронный доступ к SQLite."""

    def __init__(
        self,
        path: str,
        *,
        default_timezone: str = "Europe/Moscow",
        default_active_limit: int = 20,
    ) -> None:
        self.path = path
        self.default_timezone = default_timezone
        self.default_active_limit = default_active_limit
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._init_schema()
        logger.info("База данных подключена: %s", self.path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Соединение с БД закрыто")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("База данных не подключена")
        return self._db

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        try:
            yield self.db
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def _init_schema(self) -> None:
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL DEFAULT '',
                username TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                added_at TEXT NOT NULL,
                last_check_status TEXT,
                last_check_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL DEFAULT '',
                parse_mode TEXT NOT NULL DEFAULT 'HTML',
                photo_file_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS broadcast_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                total INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                trigger_type TEXT NOT NULL,
                cycle_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running'
            );

            CREATE TABLE IF NOT EXISTS send_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                sent_at TEXT NOT NULL,
                cycle_date TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES broadcast_runs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_send_logs_cycle
                ON send_logs(cycle_date, chat_id, status);
            CREATE INDEX IF NOT EXISTS idx_send_logs_run
                ON send_logs(run_id);
            CREATE INDEX IF NOT EXISTS idx_chats_active
                ON chats(is_active);
            """
        )
        await self.db.commit()
        await self._ensure_defaults()

    async def _ensure_defaults(self) -> None:
        defaults = {
            "schedule_time": "10:00",
            "timezone": self.default_timezone,
            "auto_enabled": "1",
            "active_chats_limit": str(self.default_active_limit),
            "broadcast_paused": "0",
            "last_broadcast_at": "",
        }
        for key, value in defaults.items():
            await self.db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await self.db.commit()

    # ── Settings ──────────────────────────────────────────────

    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.db.commit()

    async def get_all_settings(self) -> dict[str, str]:
        async with self.db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}

    # ── Chats ─────────────────────────────────────────────────

    async def add_chat(
        self,
        chat_id: int,
        title: str = "",
        username: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Добавить чат. Возвращает (успех, сообщение)."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            await self.db.execute(
                "INSERT INTO chats (chat_id, title, username, is_active, added_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (chat_id, title or str(chat_id), username, now),
            )
            await self.db.commit()
            return True, "Чат успешно добавлен"
        except aiosqlite.IntegrityError:
            return False, "Этот чат уже есть в списке рассылки"

    async def remove_chat(self, chat_id: int) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM chats WHERE chat_id = ?", (chat_id,)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_chat(self, chat_id: int) -> Optional[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM chats WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_chats(self) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM chats ORDER BY added_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_active_chats(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM chats WHERE is_active = 1 ORDER BY added_at ASC"
        if limit is not None and limit > 0:
            query += f" LIMIT {int(limit)}"
        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def set_chat_active(self, chat_id: int, active: bool) -> bool:
        cursor = await self.db.execute(
            "UPDATE chats SET is_active = ? WHERE chat_id = ?",
            (1 if active else 0, chat_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def update_chat_info(
        self,
        chat_id: int,
        title: Optional[str] = None,
        username: Optional[str] = None,
        check_status: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        fields: list[str] = []
        values: list[Any] = []
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if username is not None:
            fields.append("username = ?")
            values.append(username)
        if check_status is not None:
            fields.append("last_check_status = ?")
            values.append(check_status)
            fields.append("last_check_at = ?")
            values.append(now)
        if not fields:
            return
        values.append(chat_id)
        await self.db.execute(
            f"UPDATE chats SET {', '.join(fields)} WHERE chat_id = ?",
            values,
        )
        await self.db.commit()

    async def count_chats(self) -> dict[str, int]:
        async with self.db.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active, "
            "SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive "
            "FROM chats"
        ) as cursor:
            row = await cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "active": row["active"] or 0,
                "inactive": row["inactive"] or 0,
            }

    async def get_active_limit(self) -> int:
        raw = await self.get_setting("active_chats_limit", "20")
        try:
            return max(0, int(raw))
        except ValueError:
            return 20

    # ── Messages ──────────────────────────────────────────────

    async def get_current_message(self) -> Optional[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM messages WHERE is_current = 1 ORDER BY id DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        photo_file_id: Optional[str] = None,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        async with self.transaction() as db:
            await db.execute("UPDATE messages SET is_current = 0")
            cursor = await db.execute(
                "INSERT INTO messages "
                "(text, parse_mode, photo_file_id, created_at, updated_at, is_current) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (text, parse_mode, photo_file_id, now, now),
            )
            return cursor.lastrowid or 0

    async def update_current_message(
        self,
        text: Optional[str] = None,
        parse_mode: Optional[str] = None,
        photo_file_id: Optional[str] = None,
        clear_photo: bool = False,
    ) -> bool:
        current = await self.get_current_message()
        if not current:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        fields = ["updated_at = ?"]
        values: list[Any] = [now]
        if text is not None:
            fields.append("text = ?")
            values.append(text)
        if parse_mode is not None:
            fields.append("parse_mode = ?")
            values.append(parse_mode)
        if clear_photo:
            fields.append("photo_file_id = NULL")
        elif photo_file_id is not None:
            fields.append("photo_file_id = ?")
            values.append(photo_file_id)
        values.append(current["id"])
        await self.db.execute(
            f"UPDATE messages SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await self.db.commit()
        return True

    async def delete_current_message(self) -> bool:
        current = await self.get_current_message()
        if not current:
            return False
        await self.db.execute("DELETE FROM messages WHERE id = ?", (current["id"],))
        await self.db.commit()
        return True

    # ── Broadcast runs & logs ─────────────────────────────────

    async def create_broadcast_run(
        self,
        trigger_type: str,
        cycle_date: str,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cursor = await self.db.execute(
            "INSERT INTO broadcast_runs "
            "(started_at, trigger_type, cycle_date, status) "
            "VALUES (?, ?, ?, 'running')",
            (now, trigger_type, cycle_date),
        )
        await self.db.commit()
        return cursor.lastrowid or 0

    async def finish_broadcast_run(
        self,
        run_id: int,
        total: int,
        success: int,
        failed: int,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        await self.db.execute(
            "UPDATE broadcast_runs SET finished_at = ?, total = ?, "
            "success = ?, failed = ?, status = 'finished' WHERE id = ?",
            (now, total, success, failed, run_id),
        )
        await self.set_setting("last_broadcast_at", now)

    async def get_running_broadcast(self) -> Optional[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM broadcast_runs WHERE status = 'running' "
            "ORDER BY id DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def mark_stale_runs_finished(self) -> None:
        """Пометить зависшие запуски как прерванные после рестарта."""
        now = datetime.now().isoformat(timespec="seconds")
        await self.db.execute(
            "UPDATE broadcast_runs SET status = 'interrupted', finished_at = ? "
            "WHERE status = 'running'",
            (now,),
        )
        await self.db.commit()

    async def add_send_log(
        self,
        run_id: int,
        chat_id: int,
        chat_title: str,
        status: str,
        cycle_date: str,
        error_message: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        await self.db.execute(
            "INSERT INTO send_logs "
            "(run_id, chat_id, chat_title, status, error_message, sent_at, cycle_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, chat_id, chat_title, status, error_message, now, cycle_date),
        )
        await self.db.commit()

    async def was_sent_in_cycle(self, chat_id: int, cycle_date: str) -> bool:
        """Проверка: уже успешно отправлено в этом дневном цикле?"""
        async with self.db.execute(
            "SELECT 1 FROM send_logs "
            "WHERE chat_id = ? AND cycle_date = ? AND status = 'success' LIMIT 1",
            (chat_id, cycle_date),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def get_sent_chat_ids_in_cycle(self, cycle_date: str) -> set[int]:
        async with self.db.execute(
            "SELECT DISTINCT chat_id FROM send_logs "
            "WHERE cycle_date = ? AND status = 'success'",
            (cycle_date,),
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["chat_id"] for row in rows}

    async def get_broadcast_history(self, limit: int = 30) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM broadcast_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_run_errors(self, run_id: int) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM send_logs WHERE run_id = ? AND status = 'error' "
            "ORDER BY id",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_send_stats(self) -> dict[str, int]:
        async with self.db.execute(
            "SELECT "
            "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success, "
            "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed "
            "FROM send_logs"
        ) as cursor:
            row = await cursor.fetchone()
            return {
                "success": row["success"] or 0,
                "failed": row["failed"] or 0,
            }

    async def get_recent_send_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM send_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
