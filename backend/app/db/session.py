# backend/app/db/session.py
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,     # already good
    pool_recycle=1800,      # helps with stale connections
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Context manager that ALWAYS rollbacks on exceptions.
    Safe replacement for: with SessionLocal() as db:
    """
    db: Session = SessionLocal()
    try:
        yield db
        # For read-only routes, commit is harmless (no-op).
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """
    Optional FastAPI dependency if you want later.
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
