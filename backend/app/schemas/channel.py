# backend/app/schemas/channel.py
from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    key: str = Field(..., examples=["matt"])
    telegram_username: str = Field(..., examples=["mattprintalphacalls"])
    enabled: bool = True
    live_enabled: bool = False
    live_buy_amount_sol: float = Field(default=0.005, gt=0)

class ChannelOut(BaseModel):
    id: int
    key: str
    telegram_username: str
    enabled: bool
    live_enabled: bool
    live_buy_amount_sol: float
    live_tp_pct: float | None = None
    live_sl_pct: float | None = None

    class Config:
        from_attributes = True


class ChannelUpdate(BaseModel):
    enabled: bool | None = None
    live_enabled: bool | None = None
    telegram_username: str | None = None
    live_buy_amount_sol: float | None = Field(default=None, gt=0)
    live_tp_pct: float | None = Field(default=None, gt=0)
    live_sl_pct: float | None = Field(default=None, gt=0)

