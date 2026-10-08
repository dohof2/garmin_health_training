from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from .dashboard import dashboard_card_layout, save_dashboard_card_layout
from .database import migrate, schema_status
from .extended_archive_import import (
    ExtendedArchiveImportError,
    import_extended_archive,
    preview_extended_archive_import,
)
from .exports import (
    CSV_DATASETS,
    ExportError,
    create_backup,
    create_original_activity_bundle,
    export_csv,
    export_json,
    original_activity_inventory,
    preview_restore,
    temporary_export_path,
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
from .sync import (
    recover_interrupted_sync_jobs,
    sync_plan,
    sync_status,
)
from .wellness_import import (
    WellnessImportError,
    import_wellness_records,
    preview_wellness_import,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate()
    recover_interrupted_sync_jobs()
    yield


app = FastAPI(
    title="Garmin Health and Training API",
    version="0.1.0",
    lifespan=lifespan,
)


class DashboardCardUpdate(BaseModel):
    id: str
    position: int
    is_visible: bool


class DashboardLayoutUpdate(BaseModel):
    cards: list[DashboardCardUpdate]


def _temporary_download(path: Path, filename: str, media_type: str) -> FileResponse:
    return FileResponse(
        path,
        filename=filename,
        media_type=media_type,
        background=BackgroundTask(path.unlink, missing_ok=True),
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
def summary(timezone: str | None = None) -> dict[str, object]:
    try:
        return history_summary(timezone_name=timezone)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/history/weekly-calories")
def weekly_calories() -> dict[str, object] | None:
    return weekly_calories_summary()


@app.get("/api/dashboard/cards")
def dashboard_cards() -> list[dict[str, object]]:
    return dashboard_card_layout()


@app.put("/api/dashboard/cards")
def update_dashboard_cards(payload: DashboardLayoutUpdate) -> list[dict[str, object]]:
    try:
        return save_dashboard_card_layout(
            [card.model_dump() for card in payload.cards]
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/activities")
def activities(
    limit: int = Query(default=20, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = None,
) -> list[dict[str, object]]:
    try:
        return list_activities(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/activities/{activity_id}")
def activity_detail(activity_id: str, timezone: str | None = None) -> dict[str, object]:
    try:
        activity = get_activity(activity_id, timezone_name=timezone)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@app.get("/api/metrics")
def metrics(
    metric_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    return list_metrics(metric_type=metric_type, limit=limit)


@app.get("/api/sync/status")
def synchronization_status() -> dict[str, object]:
    return sync_status()


@app.get("/api/sync/plan")
def synchronization_plan(
    through_date: date | None = None,
    reconcile_from: date | None = None,
) -> dict[str, object]:
    resolved_through_date = through_date or date.today()
    if reconcile_from and reconcile_from > resolved_through_date:
        raise HTTPException(
            status_code=400,
            detail="reconcile_from must be on or before through_date",
        )
    return sync_plan(resolved_through_date, reconcile_from=reconcile_from)


@app.post("/api/sync/run")
def synchronization_run() -> dict[str, object]:
    raise HTTPException(
        status_code=401,
        detail="Garmin Connect is not signed in. Complete the private local sign-in to enable Sync now.",
    )


@app.get("/api/exports/csv/{dataset}")
def csv_export(
    dataset: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> FileResponse:
    if dataset not in CSV_DATASETS:
        raise HTTPException(status_code=404, detail="Unknown CSV export dataset")
    output = temporary_export_path(f"-{dataset}.csv")
    try:
        export_csv(dataset, output, start_date=start_date, end_date=end_date)
    except ExportError as error:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _temporary_download(output, f"health-training-{dataset}.csv", "text/csv")


@app.get("/api/exports/data.json")
def json_export(
    start_date: date | None = None,
    end_date: date | None = None,
) -> FileResponse:
    output = temporary_export_path("-data.json")
    try:
        export_json(output, start_date=start_date, end_date=end_date)
    except ExportError as error:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _temporary_download(output, "health-training-data.json", "application/json")


@app.get("/api/exports/backup.zip")
def backup_export(include_originals: bool = Query(default=False)) -> FileResponse:
    output = temporary_export_path("-backup.zip")
    try:
        create_backup(output, include_originals=include_originals)
    except ExportError as error:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _temporary_download(output, "health-training-backup.zip", "application/zip")


@app.get("/api/exports/original-activities")
def original_activities() -> dict[str, object]:
    return original_activity_inventory()


@app.get("/api/exports/original-activities.zip")
def original_activity_export() -> FileResponse:
    output = temporary_export_path("-original-activities.zip")
    try:
        create_original_activity_bundle(output)
    except ExportError as error:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _temporary_download(output, "original-activity-files.zip", "application/zip")


@app.post("/api/restores/preview")
async def restore_preview(request: Request) -> dict[str, object]:
    content_type = request.headers.get("content-type", "")
    if "application/zip" not in content_type and "application/octet-stream" not in content_type:
        raise HTTPException(status_code=415, detail="Restore preview requires a ZIP backup")
    upload = temporary_export_path("-restore-preview.zip")
    byte_count = 0
    try:
        with upload.open("wb") as output:
            async for chunk in request.stream():
                byte_count += len(chunk)
                if byte_count > 20 * 1024 * 1024 * 1024:
                    raise ExportError("Backup exceeds the restore size limit")
                output.write(chunk)
        if byte_count == 0:
            raise ExportError("The selected backup is empty")
        return preview_restore(upload)
    except ExportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        upload.unlink(missing_ok=True)


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
