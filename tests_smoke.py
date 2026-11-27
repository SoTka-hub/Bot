"""Локальная проверка БД и защиты от повторной отправки (без Telegram API)."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from database import Database


async def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        db = Database(db_path, default_active_limit=20)
        await db.connect()

        ok, _ = await db.add_chat(-1001, title="Chat A")
        assert ok
        ok, msg = await db.add_chat(-1001, title="Chat A")
        assert not ok

        await db.add_chat(-1002, title="Chat B")
        await db.add_chat(-1003, title="Chat C")
        await db.set_chat_active(-1003, False)

        counts = await db.count_chats()
        assert counts["total"] == 3
        assert counts["active"] == 2
        assert counts["inactive"] == 1

        await db.set_setting("active_chats_limit", "1")
        limit = await db.get_active_limit()
        active = await db.get_active_chats(limit=limit)
        assert len(active) == 1

        msg_id = await db.create_message("Привет <b>мир</b>", parse_mode="HTML")
        assert msg_id > 0
        current = await db.get_current_message()
        assert current and current["text"].startswith("Привет")

        cycle = "2026-11-26"
        run_id = await db.create_broadcast_run("manual", cycle)
        await db.add_send_log(run_id, -1001, "Chat A", "success", cycle)
        await db.add_send_log(run_id, -1002, "Chat B", "error", cycle, "forbidden")
        await db.finish_broadcast_run(run_id, 2, 1, 1)

        assert await db.was_sent_in_cycle(-1001, cycle)
        assert not await db.was_sent_in_cycle(-1002, cycle)
        sent = await db.get_sent_chat_ids_in_cycle(cycle)
        assert sent == {-1001}

        history = await db.get_broadcast_history(30)
        assert len(history) == 1
        errors = await db.get_run_errors(run_id)
        assert len(errors) == 1

        await db.mark_stale_runs_finished()
        await db.close()

    print("OK: smoke tests passed")


if __name__ == "__main__":
    asyncio.run(run())
