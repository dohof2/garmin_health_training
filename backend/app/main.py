from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
import os
from .time_utils import timezone_info
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field, SecretStr
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, StreamingResponse, Response, JSONResponse

from .ai_chat import chat_stream
from .ai_providers import provider_status, save_ai_settings
from .ai_tools import execute_tool, tool_definitions
from .charts import catalog, chart_data, read_layout, save_layout, add_weight
from .dashboard import dashboard_card_layout, save_dashboard_card_layout
from .readiness import readiness_history, get_readiness_settings, save_readiness_settings
from .training import training_context, save_preferences, draft_week, list_training, accept_plan, update_workout, progression_proposal
from .training_coach import read_brief, save_brief, preview as coach_preview, create_draft as coach_draft, parse_request
from .nutrition import food_search, preview_meal, save_meal, remove_meal, daily_status, save_library, list_library, scale_library, target_preview, save_target, target_history
from .food_vision import analyze_photo, analyze_text
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
    from .activity_metrics import backfill_fit_ascent
    backfill_fit_ascent()
    recover_interrupted_sync_jobs()
    from .garmin_training_publish import recover
    recover()
    yield


app = FastAPI(
    title="Garmin Health and Training API",
    version="0.1.0",
    lifespan=lifespan,
)


class GarminPublicationPreview(BaseModel):
    enable_rolling: bool = False
    model_config={'extra':'forbid'}
    workout_ids: list[str] = Field(default_factory=list,max_length=21)
    definition: dict[str,object] | None = None
    schedule: bool = True
    scheduled_date: date | None = None
    timezone: str = 'UTC'


@app.get('/api/training/publication/rolling')
def rolling_publication_status():
    from .rolling_publication import status
    return status()


@app.post('/api/training/publication/rolling/disable')
def disable_rolling_publication():
    from .rolling_publication import disable
    return disable()


@app.get('/api/training/publication/capabilities')
def garmin_publication_capabilities():
    state=connection_state()
    return {'provider':'garminconnect (unofficial)','connection_status':state['status'],'has_saved_session':state['has_saved_session'],'sports':['cycling','running','strength'],'strength_mapping':'Explicit supported exercises only; live Garmin/device validation pending','targets':['prescribed_watts','prescribed_bpm','effort_in_notes'],'scheduling':True,'device_delivery':'unverified','unsupported':{'hiking':'No verified Garmin workout mapping in this release.'}}


@app.post('/api/training/publication/preview')
def preview_garmin_publication(payload: GarminPublicationPreview):
    from .garmin_training_publish import preview
    try:return preview(payload.model_dump(mode='json',exclude_none=True))
    except Exception as error:
        if isinstance(error,ValueError):raise HTTPException(400,str(error)) from error
        raise HTTPException(400,'Could not verify the Garmin connection. Reconnect Garmin and try again.') from error


@app.get('/api/training/publication/jobs')
def list_garmin_publications():
    from .garmin_training_publish import history
    return history()


@app.get('/api/training/publication/jobs/{job_id}')
def read_garmin_publication(job_id: str):
    from .garmin_training_publish import view
    try:return view(job_id)
    except ValueError as error:raise HTTPException(404,str(error)) from error


@app.post('/api/training/publication/jobs/{job_id}/approve')
def approve_garmin_publication(job_id: str):
    from .garmin_training_publish import approve, run
    try:
        result=approve(job_id)
        return JSONResponse(result,background=BackgroundTask(run,job_id))
    except ValueError as error:raise HTTPException(409,str(error)) from error
    except Exception as error:raise HTTPException(400,'Reconnect Garmin before sending this workout.') from error


@app.post('/api/training/publication/jobs/{job_id}/retry')
def retry_garmin_publication(job_id: str):
    from .garmin_training_publish import retry, run
    try:
        result=retry(job_id)
        return JSONResponse(result,background=BackgroundTask(run,job_id))
    except ValueError as error:raise HTTPException(409,str(error)) from error
    except Exception as error:raise HTTPException(400,'Reconnect Garmin before reconciliation.') from error


class ChartRequest(BaseModel):
    spec: dict[str, object]


class WidgetLayoutRequest(BaseModel):
    widgets: list[dict[str, object]]


class WeightRequest(BaseModel):
    date: date
    value: float = Field(gt=0, allow_inf_nan=False)
    unit: Literal['kg', 'lb'] = 'kg'


@app.get('/api/charts/catalog')
def chart_catalog():
    return catalog()


@app.post('/api/charts/query')
def query_chart(request: ChartRequest):
    try:
        return chart_data(request.spec)
    except (ValueError, TypeError) as error:
        raise HTTPException(400, str(error)) from error


@app.get('/api/dashboard/widgets')
def get_widgets():
    return {'widgets': read_layout()}


@app.put('/api/dashboard/widgets')
def put_widgets(request: WidgetLayoutRequest):
    try:
        return {'widgets': save_layout(request.widgets)}
    except (ValueError, TypeError) as error:
        raise HTTPException(400, str(error)) from error


@app.get('/api/health/sleep')
def sleep_night(day: date | None = None, timezone: str = "UTC"):
    from .sleep_card import night
    try:
        return night(day.isoformat() if day else None,timezone_name=timezone)
    except ValueError as error:
        raise HTTPException(400,str(error)) from error


@app.get('/api/health/widgets')
def health_widgets():
    return {'widgets': read_layout(scope='health')}


@app.put('/api/health/widgets')
def save_health_widgets(request: WidgetLayoutRequest):
    try:
        return {'widgets': save_layout(request.widgets, scope='health')}
    except (ValueError, TypeError) as error:
        raise HTTPException(400, str(error)) from error


class WeightPublicationRequest(BaseModel):
    timezone: str


@app.post('/api/weight/{reading_id}/garmin')
def publish_weight(reading_id: str, request: WeightPublicationRequest):
    from .weight_publish import publish
    try:
        return publish(reading_id, request.timezone)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post('/api/weight')
def log_weight(request: WeightRequest):
    try:
        return add_weight(request.date.isoformat(), request.value, request.unit)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


class NutritionDraft(BaseModel):
    model_config = {"extra": "forbid"}
    payload: dict[str, object]


class NutritionSave(NutritionDraft):
    confirmed: Literal[True]
    operation_id: str = Field(min_length=1, max_length=100)
    expected_revision: int | None = Field(default=None, strict=True, ge=1)


class NutritionTargetSave(NutritionDraft):
    confirmed: Literal[True]
    expected_revision: int = Field(strict=True, ge=0)


class NutritionLibrarySave(NutritionDraft):
    expected_revision: int | None = Field(default=None, strict=True, ge=1)


class NutritionRemoval(BaseModel):
    model_config = {"extra": "forbid"}
    expected_revision: int = Field(strict=True, ge=1)
    removed: bool = Field(strict=True)


class FoodDescription(BaseModel):
    model_config = {"extra": "forbid"}
    message: str = Field(min_length=1, max_length=4000)


class NutritionConversation(FoodDescription):
    day: date
    timezone: str = Field(max_length=100)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    draft_items: list[str] = Field(default_factory=list, max_length=30)
    meal_type: str = Field(default='meal', max_length=30)
    pending_target: dict | None = None
    pending_foods: list[dict] = Field(default_factory=list, max_length=30)


class NutritionSuggestedTargetSave(BaseModel):
    model_config = {"extra": "forbid"}
    request: dict
    day: date
    fingerprint: str = Field(min_length=64, max_length=64)
    expected_revision: int = Field(strict=True, ge=0)
    confirmed: bool


class FoodPhoto(BaseModel):
    model_config = {"extra": "forbid"}
    image_base64: str = Field(min_length=1, max_length=8*1024*1024)


def nutrition_call(function, *args, **kwargs):
    try: return function(*args, **kwargs)
    except ValueError as error: raise HTTPException(status_code=400, detail=str(error)) from error


@app.get('/api/nutrition/foods')
def nutrition_foods(q: str = Query(min_length=1, max_length=120)):
    return nutrition_call(food_search,q)


@app.get('/api/nutrition/day')
def nutrition_day(day: date, timezone: str = Query(max_length=100)):
    return nutrition_call(daily_status,day,timezone)


@app.post('/api/nutrition/preview')
def nutrition_preview(body: NutritionDraft):
    return nutrition_call(preview_meal,body.payload)


@app.post('/api/nutrition/meals')
def nutrition_save(body: NutritionSave):
    return nutrition_call(save_meal,body.payload,body.operation_id)


@app.put('/api/nutrition/meals/{identifier}')
def nutrition_edit(identifier: str, body: NutritionSave):
    return nutrition_call(save_meal,body.payload,body.operation_id,identifier,body.expected_revision)


@app.patch('/api/nutrition/meals/{identifier}/removed')
def nutrition_remove(identifier: str, body: NutritionRemoval):
    return nutrition_call(remove_meal,identifier,body.expected_revision,body.removed)


@app.get('/api/nutrition/library')
def nutrition_library():
    return list_library()


@app.post('/api/nutrition/library')
def nutrition_library_save(body: NutritionLibrarySave):
    return nutrition_call(save_library,body.payload)


@app.put('/api/nutrition/library/{identifier}')
def nutrition_library_edit(identifier: str, body: NutritionLibrarySave):
    return nutrition_call(save_library,body.payload,identifier,body.expected_revision)


@app.get('/api/nutrition/library/{identifier}/scale')
def nutrition_library_scale(identifier: str, servings: float = Query(gt=0,le=1000)):
    return nutrition_call(scale_library,identifier,servings)


@app.get('/api/nutrition/targets')
def nutrition_targets():
    return target_history()


@app.post('/api/nutrition/targets/preview')
def nutrition_target_preview(body: NutritionDraft):
    return nutrition_call(target_preview,body.payload)


@app.post('/api/nutrition/targets')
def nutrition_target_save(body: NutritionTargetSave):
    return nutrition_call(save_target,body.payload,body.expected_revision)


@app.post('/api/nutrition/assistant')
def nutrition_assistant(body: FoodDescription):
    return nutrition_call(analyze_text,body.message)


@app.post('/api/nutrition/chat')
def nutrition_conversation(body: NutritionConversation):
    from .nutrition_chat import chat
    return nutrition_call(chat, body.message, body.day.isoformat(), body.timezone, body.history, body.draft_items, body.meal_type, pending_target=body.pending_target, pending_foods=body.pending_foods)


@app.post('/api/nutrition/targets/suggestion/save')
def nutrition_suggested_target_save(body: NutritionSuggestedTargetSave):
    if not body.confirmed:
        raise HTTPException(status_code=422, detail='Review and confirm the nutrition target before saving')
    from .nutrition_targets import save
    return nutrition_call(save, body.request, body.day.isoformat(), body.fingerprint, body.expected_revision)


@app.post('/api/nutrition/photo')
def nutrition_photo(body: FoodPhoto):
    return nutrition_call(analyze_photo,body.image_base64)


class DashboardCardUpdate(BaseModel):
    id: str
    position: int
    is_visible: bool


class DashboardLayoutUpdate(BaseModel):
    cards: list[DashboardCardUpdate]


class ReadinessSettingsUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    parameters: dict[str, object]


class TrainingPreferencesUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    answers: dict[str, object]
    expected_revision: int = Field(ge=0, strict=True)


class CoachingRequest(BaseModel):
    model_config = {"extra": "forbid"}
    brief: dict[str, object]
    week_start: date
    timezone: str
    message: str | None = Field(default=None, max_length=4000)
    replace_plan_id: str | None = Field(default=None, max_length=160)
    candidate_answers: dict[str, object] | None = None
    session_changes: list[dict[str, object]] | None = None
    fingerprint: str | None = Field(default=None, max_length=64)


class CoachingBriefUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    brief: dict[str, object]
    expected_revision: int = Field(ge=0, strict=True)


class TrainingWeekRequest(BaseModel):
    model_config = {"extra": "forbid"}
    week_start: date
    timezone: str
    expected_preference_revision: int = Field(ge=0, strict=True)


class TrainingWorkoutUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    changes: dict[str, object]
    expected_revision: int = Field(ge=1, strict=True)


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
    chatgpt_model: str = ""


class AIToolExecutionRequest(BaseModel):
    arguments: dict[str, object]


class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class AIChatRequest(BaseModel):
    chat_role: Literal['auto','trainer','assistant','nutrition'] = 'auto'
    previous_role: Literal['trainer','assistant','nutrition'] | None = None
    nutrition_context: dict[str, object] | None = None
    coaching_context: dict[str, object] | None = None
    plot_context: list[dict[str, object]] | None = Field(default=None, max_length=4)
    ride_context: str | None = Field(default=None, max_length=160)
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
        "preview": os.getenv('HT_APP_PREVIEW') == '1',
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
            plot_context=payload.plot_context,
            ride_context=payload.ride_context,
            coaching_context=payload.coaching_context,
            chat_role=payload.chat_role,previous_role=payload.previous_role,nutrition_context=payload.nutrition_context,
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
def weekly_calories(timezone: str = 'UTC') -> dict[str, object] | None:
    try:return weekly_calories_summary(timezone_name=timezone)
    except ValueError as error:raise HTTPException(400,str(error)) from error


@app.get("/api/dashboard/cards")
def dashboard_cards() -> list[dict[str, object]]:
    return dashboard_card_layout()


@app.get("/api/readiness")
def training_readiness(end_date: date | None = None, days: int = Query(default=14, ge=1, le=90), timezone: str = "UTC", config_version: str | None = None):
    try:
        return readiness_history(end_date, days, timezone, config_version=config_version)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/readiness/forecast")
def tomorrow_readiness(timezone: str = "UTC"):
    from .readiness_forecast import forecast
    try:
        return forecast(timezone)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/readiness/settings")
def readiness_settings():
    return get_readiness_settings()


class ActiveTrainingRequest(BaseModel):
    model_config = {"extra": "forbid"}
    timezone: str = "UTC"
    message: str | None = Field(default=None, max_length=1500)
    status: str | None = None
    trigger: Literal['auto','manual'] = 'auto'
    root_plan_id: str | None = None
    expected_revision: int | None = None


class TodayTrainingRequest(BaseModel):
    model_config = {"extra": "forbid"}
    minutes: int = Field(ge=10, le=360, strict=True)
    timezone: str = "UTC"
    sport: str | None = None
    mode: Literal['independent','plan'] = 'independent'
    workout_id: str | None = None


class TrainingSetupRequest(BaseModel):
    model_config={"extra":"forbid"}
    answers: dict[str,object]
    brief: dict[str,object]
    expected_preference_revision: int = Field(ge=0,strict=True)
    expected_brief_revision: int = Field(ge=0,strict=True)


@app.post('/api/training/setup')
def store_training_setup(payload: TrainingSetupRequest):
    from .training_coach import save_setup
    try:return save_setup(payload.answers,payload.brief,payload.expected_preference_revision,payload.expected_brief_revision)
    except ValueError as error:raise HTTPException(status_code=400,detail=str(error)) from error


class TrainingPlanDeleteRequest(BaseModel):
    expected_plan_revision: int
    confirm: bool


@app.delete('/api/training/plans/{plan_id}')
def delete_training_plan(plan_id: str, payload: TrainingPlanDeleteRequest):
    from .training_lifecycle import delete_plan
    try:return delete_plan(plan_id,payload.expected_plan_revision,payload.confirm)
    except ValueError as error:raise HTTPException(status_code=409,detail=str(error)) from error


@app.post('/api/training/today')
def today_training(payload: TodayTrainingRequest):
    from .active_training import suggest_today
    try:
        return suggest_today(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400,detail=str(error)) from error


@app.get('/api/training/active')
def read_active_training(timezone: str = 'UTC'):
    from .active_training import active_view
    try:return active_view(timezone_name=timezone)
    except ValueError as error:raise HTTPException(400,str(error)) from error


class TrainingEventRequest(BaseModel):
    model_config={'extra':'forbid'}
    root_plan_id: str
    expected_revision: int
    timezone: str = 'UTC'
    operation: Literal['upsert','remove']
    event: dict[str,object] | None = None
    event_id: str | None = None
    message: str | None = None


@app.post('/api/training/active/events')
def save_active_training_event(payload: TrainingEventRequest):
    from .active_training import save_event
    try:return save_event(payload.model_dump())
    except ValueError as error:raise HTTPException(409,str(error)) from error


@app.post('/api/training/active/review')
def review_active_training(payload: ActiveTrainingRequest):
    from .active_training import review
    try:
        return review(timezone_name=payload.timezone,trigger=payload.trigger)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class TrainingAdaptationRequest(BaseModel):
    model_config={'extra':'forbid'}
    message: str
    fingerprint: str


@app.post('/api/training/active/adapt')
def save_training_adaptation(payload: TrainingAdaptationRequest):
    from .training_adjustments import save
    try:return save(payload.model_dump())
    except (ValueError,KeyError) as error:raise HTTPException(409,str(error)) from error


@app.post('/api/training/active/change')
def change_active_training(payload: ActiveTrainingRequest):
    from .active_training import request_change, set_status
    try:
        if payload.status:
            from .training_lifecycle import set_program_status
            if not payload.root_plan_id or payload.expected_revision is None:raise ValueError('Select the root program and its current revision')
            return set_program_status(payload.root_plan_id,payload.expected_revision,payload.status)
        return request_change(payload.message, payload.timezone)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.patch('/api/training/workouts/{workout_id}/schedule')
def move_active_workout(workout_id: str, payload: TrainingWorkoutUpdate):
    from .active_training import reschedule
    if set(payload.changes)!={'scheduled_for'} and (set(payload.changes)-{'scheduled_date','start_time','timezone'} or 'scheduled_date' not in payload.changes):
        raise HTTPException(status_code=400,detail='Choose a scheduled date, optionally including a start time')
    try:
        return reschedule(workout_id,payload.changes.get('scheduled_for'),payload.expected_revision,scheduled_date=payload.changes.get('scheduled_date'),start_time=payload.changes.get('start_time'))
    except (ValueError,TypeError) as error:
        raise HTTPException(status_code=400,detail=str(error)) from error


@app.get("/api/training/context")
def get_training_preferences():
    return training_context()


@app.put("/api/training/preferences")
def update_training_preferences(payload: TrainingPreferencesUpdate):
    try:
        return save_preferences(payload.answers, payload.expected_revision)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/training/coach")
def get_coaching_brief():
    return read_brief()


@app.get("/api/training/coach/candidate")
def get_coaching_candidate(timezone: str = "UTC"):
    from .training_questionnaire import candidate_snapshot
    try:return candidate_snapshot(tz=timezone)
    except ValueError as error:raise HTTPException(400,str(error)) from error


@app.put("/api/training/coach")
def put_coaching_brief(payload: CoachingBriefUpdate):
    try:
        return save_brief(payload.brief,payload.expected_revision)
    except ValueError as error:
        raise HTTPException(status_code=400,detail=str(error)) from error


@app.post("/api/training/coach/preview")
def preview_coaching_plan(payload: CoachingRequest):
    try:
        brief,recognized=parse_request(payload.message,payload.brief,payload.week_start,datetime.now(timezone_info(payload.timezone)).date()) if payload.message else (payload.brief,[])
        return {**coach_preview(brief,payload.week_start,payload.timezone,replace_plan_id=payload.replace_plan_id,candidate_answers=payload.candidate_answers,session_changes=payload.session_changes), 'recognized':recognized}
    except ValueError as error:
        raise HTTPException(status_code=400,detail=str(error)) from error


@app.post("/api/training/coach/approve")
def approve_coaching_plan(payload: CoachingRequest):
    from .training_coach import approve
    try:
        return approve(payload.brief,payload.week_start,payload.timezone,payload.fingerprint,replace_plan_id=payload.replace_plan_id,candidate_answers=payload.candidate_answers,session_changes=payload.session_changes)
    except ValueError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error


@app.post("/api/training/coach/draft")
def draft_coaching_plan(payload: CoachingRequest):
    try:
        return coach_draft(payload.brief,payload.week_start,payload.timezone,payload.fingerprint,replace_plan_id=payload.replace_plan_id)
    except ValueError as error:
        raise HTTPException(status_code=400,detail=str(error)) from error


@app.get("/api/training")
def training_history(compact: bool = False):
    return list_training(compact=compact)


@app.get("/api/training/progression")
def training_progression():
    return progression_proposal()


@app.post("/api/training/draft")
def draft_training_week(payload: TrainingWeekRequest):
    try:
        return draft_week(payload.week_start, payload.timezone, payload.expected_preference_revision)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/training/plans/{plan_id}/accept")
def accept_training_plan(plan_id: str):
    try:
        return accept_plan(plan_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.patch("/api/training/workouts/{workout_id}")
def edit_training_workout(workout_id: str, payload: TrainingWorkoutUpdate):
    try:
        return update_workout(workout_id, payload.expected_revision, payload.changes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/readiness/settings")
def update_readiness_settings(payload: ReadinessSettingsUpdate):
    try:
        return save_readiness_settings(payload.parameters)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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
    offset: int = Query(default=0, ge=0),
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = None,
) -> list[dict[str, object]]:
    try:
        return list_activities(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class ActivityRemovalRequest(BaseModel):
    removed: bool = Field(strict=True)


@app.get('/api/activities/removed')
def removed_activity_list():
    from .activity_removal import removed_activities
    return {'activities': removed_activities()}


@app.patch('/api/activities/{activity_id}/removed')
def remove_activity(activity_id: str, request: ActivityRemovalRequest):
    from .activity_removal import set_removed
    try:
        return set_removed(activity_id, request.removed)
    except LookupError as error:
        raise HTTPException(404,str(error)) from error
    except ValueError as error:
        raise HTTPException(400,str(error)) from error


@app.get("/api/activities/{activity_id}/plots")
def recorded_activity_plots(activity_id: str):
    from .activity_sections import plots
    try:return plots(activity_id)
    except ValueError as error:raise HTTPException(status_code=400,detail=str(error)) from error


@app.get("/api/activities/{activity_id}/full-stats")
def activity_full_stats(activity_id: str, timezone: str | None = None) -> dict[str, object]:
    from .fit_access import inspect
    try:
        if get_activity(activity_id, timezone_name=timezone) is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        return inspect({'activity_id': activity_id, 'timezone': timezone, 'message_type': 'session_mesgs', 'limit': 200})
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
        from .fit_import import import_fit_activity_samples
        from .xml_activity_import import import_xml_activity_details
        from .health_fit_import import import_health_fit_samples
        result = import_garmin_export()
        stages = {}
        for name, importer in (
            ('activity_fit', import_fit_activity_samples),
            ('activity_xml', import_xml_activity_details),
            ('health_fit', import_health_fit_samples),
            ('wellness', import_wellness_records),
            ('extended', import_extended_archive),
        ):
            try:
                stages[name] = importer()
            except (ValueError, OSError, RuntimeError) as error:
                stages[name] = {'status': 'failed', 'error': str(error)}
        result['stages'] = stages
        if any(stage.get('status') != 'completed' for stage in stages.values()):
            result['status'] = 'completed_with_failures'
        return result
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GarminImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _chatgpt_local_request(request):
    origin=request.headers.get('origin')
    if origin and origin not in {'http://127.0.0.1:5173','http://127.0.0.1:5174','http://127.0.0.1:8000'}:
        raise HTTPException(status_code=403,detail='Use ChatGPT settings from the local app.')


@app.post('/api/ai/chatgpt/connect')
def chatgpt_connect(request: Request,account: str | None = None):
    _chatgpt_local_request(request)
    from .chatgpt_auth import start
    try:return start(account=account)
    except ValueError as error:raise HTTPException(status_code=400,detail=str(error)) from error


@app.get('/auth/callback')
def chatgpt_callback(request: Request):
    from .chatgpt_auth import finish, failure_message
    from html import escape
    from starlette.responses import HTMLResponse
    try:
        finish(dict(request.query_params))
        return HTMLResponse('<h1>ChatGPT connected</h1><p>Return to Garmin Settings, refresh the account status and choose a model.</p>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except Exception as error:
        return HTMLResponse('<h1>ChatGPT connection was not completed</h1><p>'+escape(failure_message(error))+'</p><p><a href="http://127.0.0.1:5173/#settings">Return to Garmin Settings</a></p>',status_code=400,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@app.get('/api/ai/chatgpt/models')
def chatgpt_models():
    from .chatgpt_auth import models
    try:return models()
    except Exception as error:raise HTTPException(status_code=400,detail='ChatGPT models could not be loaded. Reconnect or check your plan access.') from error


@app.post('/api/ai/chatgpt/disconnect')
def chatgpt_disconnect(request: Request):
    _chatgpt_local_request(request)
    from .chatgpt_auth import sign_out
    return sign_out()


class LoadHistoryRequest(BaseModel):
    timezone: str = 'UTC'


@app.post('/api/charts/training-load/refresh')
def refresh_training_load(request: LoadHistoryRequest):
    from .training_load_charts import refresh_history
    from .time_utils import timezone_info
    try:
        timezone_info(request.timezone)
        return refresh_history(timezone=request.timezone)
    except Exception as error:
        raise HTTPException(400, 'Could not refresh load history. Check your Garmin connection and try again.') from error
