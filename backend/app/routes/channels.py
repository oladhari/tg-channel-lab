# backend/app/routes/channels.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models import Channel
from app.schemas.channel import ChannelCreate, ChannelOut, ChannelUpdate

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelOut])
def list_channels():
    db = SessionLocal()
    try:
        return db.query(Channel).order_by(Channel.id.asc()).all()
    finally:
        db.close()


@router.post("", response_model=ChannelOut)
def create_channel(payload: ChannelCreate):
    db = SessionLocal()
    try:
        ch = Channel(
            key=payload.key.lower().strip(),
            telegram_username=payload.telegram_username.strip().lstrip("@"),
            enabled=payload.enabled,
            live_enabled=payload.live_enabled,
        )
        db.add(ch)
        db.commit()
        db.refresh(ch)
        return ch
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Channel key or telegram_username already exists")
    finally:
        db.close()


@router.patch("/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: int, payload: ChannelUpdate):
    db = SessionLocal()
    try:
        ch = db.query(Channel).filter(Channel.id == channel_id).one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        if payload.enabled is not None:
            ch.enabled = payload.enabled
        if payload.live_enabled is not None:
            ch.live_enabled = payload.live_enabled
        if payload.telegram_username is not None:
            ch.telegram_username = payload.telegram_username.strip().lstrip("@")

        db.commit()
        db.refresh(ch)
        return ch
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="telegram_username already exists")
    finally:
        db.close()

@router.post("/{channel_id}/toggle-live", response_model=ChannelOut)
def toggle_live(channel_id: int):
    db = SessionLocal()
    try:
        ch = db.query(Channel).filter(Channel.id == channel_id).one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")
        ch.live_enabled = not ch.live_enabled
        db.commit()
        db.refresh(ch)
        return ch
    finally:
        db.close()

@router.post("/{channel_id}/toggle", response_model=ChannelOut)
def toggle_enabled(channel_id: int):
    db = SessionLocal()
    try:
        ch = db.query(Channel).filter(Channel.id == channel_id).one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")
        ch.enabled = not ch.enabled

        # Optional safety: if disabling recording, also disable live
        if not ch.enabled:
            ch.live_enabled = False

        db.commit()
        db.refresh(ch)
        return ch
    finally:
        db.close()
