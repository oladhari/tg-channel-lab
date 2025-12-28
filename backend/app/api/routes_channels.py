from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.channel import Channel

router = APIRouter()

@router.get("/")
def list_channels(db: Session = Depends(get_db)):
    return db.query(Channel).all()

@router.post("/")
def add_channel(username: str, label: str = "CH", db: Session = Depends(get_db)):
    ch = Channel(username=username, label=label)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch

@router.post("/{channel_id}/toggle")
def toggle_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.get(Channel, channel_id)
    ch.enabled = not ch.enabled
    db.commit()
    return ch
