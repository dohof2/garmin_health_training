from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from .database import migrate, schema_status
from .history import history_summary, list_activities, list_metrics


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate()
    yield


app = FastAPI(
    title="Garmin Health and Training API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": "ready",
        "schema": schema_status(),
        "version": app.version,
    }


@app.get("/api/history/summary")
def summary() -> dict[str, object]:
    return history_summary()


@app.get("/api/activities")
def activities(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, object]]:
    return list_activities(limit=limit)


@app.get("/api/metrics")
def metrics(
    metric_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    return list_metrics(metric_type=metric_type, limit=limit)
