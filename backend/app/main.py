from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field, SecretStr
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, StreamingResponse, Response

from .ai_chat import chat_stream
from .ai_providers import provider_status, save_ai_settings
from .ai_tools import execute_tool, tool_definitions
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
from .garmin_connection import (
    GarminConnectProvider,
    begin_login,
    complete_mfa,
    connection_state,
    disconnect,
    read_only_probe,
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
    SyncAlreadyRunning,
    SyncConnectionRequired,
    SyncError,
    recover_interrupted_sync_jobs,
    run_sync,
    scheduled_sync_decision,
    set_sync_schedule,
    sync_plan,
    sync_status,
)
from .settings import get_settings, save_goals, save_profile
from .ai_actions import confirm_settings_change
from .maintenance import list_maintenance, log_maintenance, update_maintenance, undo_maintenance, event_history
from .maintenance_csv import export_maintenance_csv, preview_maintenance_csv, apply_maintenance_csv
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


class GarminLoginRequest(BaseModel):
    email: str
    password: SecretStr


class GarminMfaRequest(BaseModel):
    code: SecretStr


class SyncScheduleRequest(BaseModel):
    enabled: bool


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    preferred_distance_unit: str = "km"
    preferred_weight_unit: str = "kg"
    birth_date: str | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None


class GoalUpdate(BaseModel):
    id: str | None = None
    goal_type: str = "general"
    title: str
    target_value: float | None = None
    target_unit: str | None = None
    target_date: str | None = None
    status: str = "active"
    notes: str | None = None


class GoalsUpdate(BaseModel):
    goals: list[GoalUpdate]


class AISettingsUpdate(BaseModel):
    active_provider: str
    ollama_model: str
    openai_model: str


class AIToolExecutionRequest(BaseModel):
    arguments: dict[str, object]


class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class AIChatRequest(BaseModel):
    operation_id: str | None = Field(default=None, min_length=1, max_length=120)
    clarification_id: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=1, max_length=4_000)
    history: list[AIChatMessage] = Field(default_factory=list, max_length=20)
    timezone: str | None = Field(default=None, max_length=100)



class MaintenanceLogRequest(BaseModel):
    model_config = {"extra": "forbid"}
    events: list[dict[str, object]] = Field(min_length=1, max_length=25)
    operation_id: str = Field(min_length=1, max_length=120)
    timezone: str | None = None


class MaintenanceUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    changes: dict[str, object]
    expected_revision: int = Field(ge=1, strict=True)
    operation_id: str = Field(min_length=1, max_length=120)
    deleted: bool | None = None
    timezone: str | None = None


class MaintenanceUndoRequest(BaseModel):
    operation_id: str = Field(min_length=1, max_length=120)


class MaintenanceCSVPreviewRequest(BaseModel):
    content: str = Field(max_length=2_097_152)
    mapping: dict[str, str] | None = None


class MaintenanceCSVApplyRequest(BaseModel):
    preview_id: str
    decisions: dict[str, str] = Field(default_factory=dict)
    operation_id: str = Field(min_length=1, max_length=120)

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


@app.get("/api/settings")
def application_settings() -> dict[str, object]:
    return get_settings()


@app.put("/api/settings/profile")
def update_profile(payload: ProfileUpdate) -> dict[str, object]:
    try:
        return save_profile(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/settings/goals")
def update_goals(payload: GoalsUpdate) -> list[dict[str, object]]:
    try:
        return save_goals([goal.model_dump() for goal in payload.goals])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/settings/ai")
def update_ai_settings(payload: AISettingsUpdate) -> dict[str, object]:
    try:
        return save_ai_settings(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/ai/providers/status")
def ai_provider_status() -> dict[str, object]:
    return provider_status()


@app.get("/api/ai/tools")
def ai_tool_catalog() -> list[dict[str, object]]:
    return tool_definitions()


@app.post("/api/ai/tools/{tool_name}")
def run_ai_tool(
    tool_name: str, payload: AIToolExecutionRequest
) -> dict[str, object]:
    try:
        return execute_tool(tool_name, payload.arguments)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/ai/settings-changes/{proposal_id}/confirm")
def confirm_ai_settings_change(proposal_id: str) -> dict[str, object]:
    try:
        return confirm_settings_change(proposal_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/ai/chat")
def ai_chat(payload: AIChatRequest) -> StreamingResponse:
    return StreamingResponse(
        chat_stream(
            payload.message,
            [item.model_dump() for item in payload.history],
            payload.timezone,
            operation_id=payload.operation_id,
            clarification_id=payload.clarification_id,
        ),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )



@app.get("/api/maintenance")
def maintenance_history(equipment: str | None = None, query: str | None = None, category: str | None = None,
                        start_date: str | None = None, end_date: str | None = None,
                        include_deleted: bool = False, limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
    try:
        return list_maintenance(equipment=equipment, query=query, category=category, start_date=start_date,
                                end_date=end_date, include_deleted=include_deleted, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/maintenance")
def create_maintenance(payload: MaintenanceLogRequest) -> dict[str, object]:
    try:
        return log_maintenance(payload.events, payload.operation_id, timezone_name=payload.timezone)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/maintenance/events/{event_id}")
def maintenance_event(event_id: str) -> dict[str, object]:
    try:
        return event_history(event_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.patch("/api/maintenance/events/{event_id}")
def edit_maintenance(event_id: str, payload: MaintenanceUpdateRequest) -> dict[str, object]:
    try:
        return update_maintenance(event_id, payload.changes, payload.expected_revision, payload.operation_id,
                                  timezone_name=payload.timezone, deleted=payload.deleted)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/maintenance/operations/{target_id}/undo")
def undo_maintenance_action(target_id: str, payload: MaintenanceUndoRequest) -> dict[str, object]:
    try:
        return undo_maintenance(target_id, payload.operation_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/maintenance/export.csv")
def download_maintenance_csv() -> Response:
    return Response(export_maintenance_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="maintenance.csv"'})


@app.post("/api/maintenance/csv/preview")
def maintenance_csv_preview(payload: MaintenanceCSVPreviewRequest) -> dict[str, object]:
    try:
        return preview_maintenance_csv(payload.content, payload.mapping)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/maintenance/csv/apply")
def maintenance_csv_apply(payload: MaintenanceCSVApplyRequest) -> dict[str, object]:
    try:
        return apply_maintenance_csv(payload.preview_id, payload.decisions, payload.operation_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

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


@app.put("/api/sync/schedule")
def synchronization_schedule(payload: SyncScheduleRequest) -> dict[str, object]:
    return set_sync_schedule(payload.enabled)


@app.get("/api/garmin/connection")
def garmin_connection_status() -> dict[str, object]:
    return connection_state()


@app.post("/api/garmin/connection/login")
def garmin_login(payload: GarminLoginRequest) -> dict[str, object]:
    try:
        return begin_login(payload.email, payload.password.get_secret_value())
    except (ValueError, SyncConnectionRequired) as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@app.post("/api/garmin/connection/mfa")
def garmin_mfa(payload: GarminMfaRequest) -> dict[str, object]:
    try:
        return complete_mfa(payload.code.get_secret_value())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SyncConnectionRequired as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@app.post("/api/garmin/connection/probe")
def garmin_probe() -> dict[str, object]:
    try:
        return read_only_probe()
    except SyncConnectionRequired as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except SyncError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.delete("/api/garmin/connection")
def garmin_disconnect() -> dict[str, object]:
    return disconnect()


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
def synchronization_run(
    through_date: date | None = None,
    reconcile_from: date | None = None,
) -> dict[str, object]:
    resolved_through_date = through_date or date.today()
    if reconcile_from and reconcile_from > resolved_through_date:
        raise HTTPException(
            status_code=400,
            detail="reconcile_from must be on or before through_date",
        )
    try:
        provider = GarminConnectProvider.from_saved_session()
        return run_sync(
            provider,
            resolved_through_date,
            trigger="manual",
            reconcile_from=reconcile_from,
            request_delay_seconds=0.25,
        )
    except SyncConnectionRequired as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except SyncAlreadyRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SyncError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/sync/scheduled")
def scheduled_synchronization_run(
    through_date: date | None = None,
) -> dict[str, object]:
    resolved_through_date = through_date or date.today()
    decision = scheduled_sync_decision(resolved_through_date)
    if not decision["due"]:
        return {"status": "skipped", **decision}
    try:
        provider = GarminConnectProvider.from_saved_session()
        return run_sync(
            provider,
            resolved_through_date,
            trigger="scheduled",
            request_delay_seconds=0.25,
        )
    except SyncConnectionRequired as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except SyncAlreadyRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SyncError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


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
