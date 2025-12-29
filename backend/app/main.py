from __future__ import annotations

from fastapi import FastAPI

from app.routes.channels import router as channels_router
from app.routes.stats import router as stats_router
from app.routes import calls

app = FastAPI(title="TG Channel Lab", version="0.1.0")

app.include_router(channels_router)
app.include_router(stats_router)
app.include_router(calls.router)

@app.get("/health")
def health():
    return {"ok": True}
