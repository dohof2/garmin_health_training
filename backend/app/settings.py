from __future__ import annotations

import uuid
import math
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ai_providers import get_ai_settings
from .database import connect, migrate


DISTANCE_UNITS = {"km", "mi"}
WEIGHT_UNITS = {"kg", "lb"}
GOAL_STATUSES = {"active", "paused", "achieved", "archived"}


def _optional_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    text = value.strip()
    if not text:
        return None
    if len(text) > maximum:
        raise ValueError(f"{field} must be {maximum} characters or fewer")
    return text


def _optional_date(value: object, field: str) -> str | None:
    text = _optional_text(value, field, 10)
    if text is None:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must be a valid date") from error


def _optional_number(
    value: object,
    field: str,
    minimum: float,
    maximum: float,
) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error
    if isinstance(value, bool) or not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum:g} and {maximum:g}")
    return number


def _profile_row(connection: object) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT display_name, timezone, preferred_distance_unit,
               preferred_weight_unit, birth_date, sex, height_cm,
               weight_kg, updated_at
        FROM user_profile WHERE id = 1
        """
    ).fetchone()
    if row is None:
        return {
            "display_name": None,
            "timezone": None,
            "preferred_distance_unit": "km",
            "preferred_weight_unit": "kg",
            "birth_date": None,
            "sex": None,
            "height_cm": None,
            "weight_kg": None,
            "updated_at": None,
        }
    return dict(row)


def get_settings(path: Path | None = None) -> dict[str, object]:
    migrate(path)
    ai_settings = get_ai_settings(path)
    with connect(path) as connection:
        goals = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, goal_type, title, target_value, target_unit,
                       target_date, status, notes, created_at, updated_at
                FROM goals
                WHERE status != 'archived'
                ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
                         target_date IS NULL, target_date, created_at
                """
            )
        ]
        return {
            "profile": _profile_row(connection),
            "goals": goals,
            "ai": ai_settings,
        }


def normalize_profile(profile: dict[str, object]) -> tuple[object, ...]:
    timezone_name = _optional_text(profile.get("timezone"), "timezone", 100)
    if timezone_name:
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error

    distance_unit = str(profile.get("preferred_distance_unit") or "km")
    weight_unit = str(profile.get("preferred_weight_unit") or "kg")
    if distance_unit not in DISTANCE_UNITS:
        raise ValueError("preferred_distance_unit must be km or mi")
    if weight_unit not in WEIGHT_UNITS:
        raise ValueError("preferred_weight_unit must be kg or lb")

    values = (
        _optional_text(profile.get("display_name"), "display_name", 80),
        timezone_name,
        distance_unit,
        weight_unit,
        _optional_date(profile.get("birth_date"), "birth_date"),
        _optional_text(profile.get("sex"), "sex", 40),
        _optional_number(profile.get("height_cm"), "height_cm", 50, 260),
        _optional_number(profile.get("weight_kg"), "weight_kg", 20, 500),
    )
    return values


def save_profile(profile: dict[str, object], path: Path | None = None, *, connection=None) -> dict[str, object]:
    values = normalize_profile(profile)
    if connection is None:
        migrate(path)
    with (nullcontext(connection) if connection is not None else connect(path)) as connection:
        connection.execute(
            """
            INSERT INTO user_profile(
                id, display_name, timezone, preferred_distance_unit,
                preferred_weight_unit, birth_date, sex, height_cm, weight_kg
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                timezone = excluded.timezone,
                preferred_distance_unit = excluded.preferred_distance_unit,
                preferred_weight_unit = excluded.preferred_weight_unit,
                birth_date = excluded.birth_date,
                sex = excluded.sex,
                height_cm = excluded.height_cm,
                weight_kg = excluded.weight_kg,
                updated_at = CURRENT_TIMESTAMP
            """,
            values,
        )
        return _profile_row(connection)


def normalize_goals(goals: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(goals) > 20:
        raise ValueError("No more than 20 goals can be saved")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for goal in goals:
        identifier = _optional_text(goal.get("id"), "goal id", 100) or f"goal-{uuid.uuid4()}"
        if identifier in seen:
            raise ValueError("Goal IDs must be unique")
        seen.add(identifier)
        title = _optional_text(goal.get("title"), "goal title", 120)
        if not title:
            raise ValueError("Every goal requires a title")
        status = str(goal.get("status") or "active")
        if status not in GOAL_STATUSES:
            raise ValueError("Goal status is invalid")
        normalized.append(
            {
                "id": identifier,
                "goal_type": _optional_text(goal.get("goal_type"), "goal type", 40) or "general",
                "title": title,
                "target_value": _optional_number(goal.get("target_value"), "target_value", 0, 1_000_000),
                "target_unit": _optional_text(goal.get("target_unit"), "target unit", 30),
                "target_date": _optional_date(goal.get("target_date"), "target_date"),
                "status": status,
                "notes": _optional_text(goal.get("notes"), "goal notes", 1000),
            }
        )

    return normalized


def save_goals(goals: list[dict[str, object]], path: Path | None = None, *, connection=None) -> list[dict[str, object]]:
    normalized = normalize_goals(goals)
    seen = {goal["id"] for goal in normalized}
    if connection is None:
        migrate(path)
    with (nullcontext(connection) if connection is not None else connect(path)) as connection:
        existing = {
            row[0]
            for row in connection.execute("SELECT id FROM goals WHERE status != 'archived'")
        }
        for goal in normalized:
            connection.execute(
                """
                INSERT INTO goals(
                    id, goal_type, title, target_value, target_unit,
                    target_date, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal_type = excluded.goal_type,
                    title = excluded.title,
                    target_value = excluded.target_value,
                    target_unit = excluded.target_unit,
                    target_date = excluded.target_date,
                    status = excluded.status,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                tuple(goal[key] for key in (
                    "id", "goal_type", "title", "target_value", "target_unit",
                    "target_date", "status", "notes",
                )),
            )
        omitted = existing - seen
        if omitted:
            placeholders = ",".join("?" for _ in omitted)
            connection.execute(
                f"UPDATE goals SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                tuple(omitted),
            )
        return [dict(row) for row in connection.execute("SELECT * FROM goals WHERE status != 'archived'")]
