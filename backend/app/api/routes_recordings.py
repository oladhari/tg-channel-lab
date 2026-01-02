# backend/app/api/routes_recordings.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.recording import Recording
from app.models.price_point import PricePoint

router = APIRouter()

@router.get("/")
def list_recordings(db: Session = Depends(get_db)):
    return db.query(Recording).order_by(Recording.started_at.desc()).all()

@router.get("/{recording_id}/prices")
def recording_prices(recording_id: int, db: Session = Depends(get_db)):
    return (
        db.query(PricePoint)
        .filter(PricePoint.recording_id == recording_id)
        .order_by(PricePoint.t.asc())
        .all()
    )
