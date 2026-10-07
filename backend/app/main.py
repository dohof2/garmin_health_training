from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query

from .database import migrate, schema_status
from .extended_archive_import import (
    ExtendedArchiveImportError,
    import_extended_archive,
    preview_extended_archive_import,
)
from .garmin_import import (
    GarminImportError,
    import_garmin_export,
    preview_garmin_export,
)
from .history import (
    get_activity,
    history_summary,
    list_activities,
    list_metrics,
    weekly_calories_summary,
)
from .import_coverage import import_coverage
from .wellness_import import (
    WellnessImportError,
    import_wellness_records,
    preview_wellness_import,
)


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


@app.get("/api/history/weekly-calories")
def weekly_calories() -> dict[str, object] | None:
    return weekly_calories_summary()


@app.get("/api/activities")
def activities(
    limit: int = Query(default=20, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )
    return list_activities(limit=limit, start_date=start_date, end_date=end_date)


@app.get("/api/activities/{activity_id}")
def activity_detail(activity_id: str) -> dict[str, object]:
    activity = get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@app.get("/api/metrics")
def metrics(
    metric_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    return list_metrics(metric_type=metric_type, limit=limit)


@app.get("/api/imports/garmin/preview")
def garmin_import_preview() -> dict[str, object]:
    try:
        return preview_garmin_export()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GarminImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/imports/coverage")
def coverage() -> dict[str, object]:
    return import_coverage()


@app.get("/api/imports/wellness/preview")
def wellness_import_preview() -> dict[str, object]:
    try:
        return preview_wellness_import()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WellnessImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/imports/wellness")
def wellness_import(confirm: bool = Query(default=False)) -> dict[str, object]:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Import requires confirm=true after reviewing the preview.",
        )
    try:
        return import_wellness_records()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WellnessImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/imports/extended/preview")
def extended_import_preview() -> dict[str, object]:
    try:
        return preview_extended_archive_import()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ExtendedArchiveImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/imports/extended")
def extended_import(confirm: bool = Query(default=False)) -> dict[str, object]:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Import requires confirm=true after reviewing the preview.",
        )
    try:
        return import_extended_archive()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ExtendedArchiveImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/imports/garmin")
def garmin_import(
    confirm: bool = Query(default=False),
) -> dict[str, object]:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Import requires confirm=true after reviewing the preview.",
        )
    try:
        return import_garmin_export()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GarminImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
