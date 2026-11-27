"""Конфигурация бота из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    """Настройки приложения."""

    bot_token: str
    owner_id: int
    database_path: Path
    default_timezone: str
    default_active_limit: int
    log_level: str


def load_config() -> Config:
    """Загрузить и провалидировать конфигурацию."""
    token = os.getenv("BOT_TOKEN", "").strip()
    owner_raw = os.getenv("OWNER_ID", "").strip()

    if not token:
        raise ValueError("BOT_TOKEN не задан в .env")
    if not owner_raw.isdigit():
        raise ValueError("OWNER_ID должен быть числом (ваш Telegram ID)")

    db_path = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bot.db"))
    timezone = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
    limit_raw = os.getenv("DEFAULT_ACTIVE_LIMIT", "20")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    try:
        default_limit = int(limit_raw)
    except ValueError as exc:
        raise ValueError("DEFAULT_ACTIVE_LIMIT должен быть числом") from exc

    path = Path(db_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=token,
        owner_id=int(owner_raw),
        database_path=path,
        default_timezone=timezone,
        default_active_limit=default_limit,
        log_level=log_level,
    )
