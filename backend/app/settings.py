# backend/app/settings.py
from __future__ import annotations
import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    APP_ENV: str = "prod"
    APP_NAME: str = "tg-channel-lab"

    DATABASE_URL: str

    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str


    SCAN_DELAY_SEC: int = 6
    RECORDING_WINDOW_MIN: int = 25
    ENTRY_PRICE_TIMEOUT_SEC: int = 10

    SIM_TP_PCT: float = 35.0
    SIM_SL_PCT: float = 20.0

    # ✅ amount per trade for paper stats
    PAPER_ENTRY_SOL: float = 0.1

    class Config:
        env_file = ".env"
        extra = "ignore"  # don't crash if .env has extra keys

settings = Settings()
