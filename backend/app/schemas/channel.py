# backend/app/schemas/channel.py
from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    key: str = Field(..., examples=["matt"])
    telegram_username: str = Field(..., examples=["mattprintalphacalls"])
    enabled: bool = True
    live_enabled: bool = False


class ChannelOut(BaseModel):
    id: int
    key: str
    telegram_username: str
    enabled: bool
    live_enabled: bool

    class Config:
        from_attributes = True


class ChannelUpdate(BaseModel):
    enabled: bool | None = None
    live_enabled: bool | None = None
    telegram_username: str | None = None
