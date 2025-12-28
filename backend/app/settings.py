from __future__ import annotations
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "prod"
    APP_NAME: str = "tg-channel-lab"

    DATABASE_URL: str

    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_SESSION_NAME: str = "tg_lab_session"

    SCAN_DELAY_SEC: int = 6
    RECORDING_WINDOW_MIN: int = 25
    ENTRY_PRICE_TIMEOUT_SEC: int = 10

    SIM_TP_PCT: float = 35.0
    SIM_SL_PCT: float = 20.0

    class Config:
        env_file = ".env"

settings = Settings()
