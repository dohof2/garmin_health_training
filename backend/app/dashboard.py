from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .database import connect


@dataclass(frozen=True)
class DashboardCardDefinition:
    id: str
    card_type: str
    label: str
    default_position: int


CARD_REGISTRY = (
    DashboardCardDefinition("latest_steps", "metric", "Latest steps", 0),
    DashboardCardDefinition("last_activity", "activity", "Last activity", 1),
    DashboardCardDefinition(
        "weekly_calories", "metric_summary", "Weekly calories burned", 2
    ),
)


def dashboard_card_layout(path: Path | None = None) -> list[dict[str, object]]:
    """Return the registered cards with saved visibility and ordering applied."""
    with connect(path) as connection:
        saved = {
            row["id"]: row
            for row in connection.execute(
                """
                SELECT id, position, is_visible
                FROM dashboard_cards
                ORDER BY position, id
                """
            )
        }

    ordered = sorted(
        CARD_REGISTRY,
        key=lambda definition: (
            0 if definition.id in saved else 1,
            (
                saved[definition.id]["position"]
                if definition.id in saved
                else definition.default_position
            ),
            definition.default_position,
        ),
    )
    return [
        {
            "id": definition.id,
            "card_type": definition.card_type,
            "label": definition.label,
            "position": position,
            "is_visible": (
                bool(saved[definition.id]["is_visible"])
                if definition.id in saved
                else True
            ),
        }
        for position, definition in enumerate(ordered)
    ]


def save_dashboard_card_layout(
    cards: list[dict[str, object]],
    path: Path | None = None,
) -> list[dict[str, object]]:
    """Validate and atomically save the complete registered card layout."""
    registered = {definition.id: definition for definition in CARD_REGISTRY}
    identifiers = [card.get("id") for card in cards]
    if len(cards) != len(registered) or set(identifiers) != set(registered):
        raise ValueError("Layout must contain every registered dashboard card once")

    positions = [card.get("position") for card in cards]
    if any(type(position) is not int for position in positions):
        raise ValueError("Every dashboard card position must be an integer")
    if set(positions) != set(range(len(cards))):
        raise ValueError("Dashboard card positions must be unique and consecutive")
    if any(type(card.get("is_visible")) is not bool for card in cards):
        raise ValueError("Every dashboard card visibility value must be boolean")

    with connect(path) as connection:
        for card in cards:
            identifier = str(card["id"])
            definition = registered[identifier]
            connection.execute(
                """
                INSERT INTO dashboard_cards(
                    id, card_type, position, settings_json, is_visible
                ) VALUES (?, ?, ?, '{}', ?)
                ON CONFLICT(id) DO UPDATE SET
                    card_type = excluded.card_type,
                    position = excluded.position,
                    is_visible = excluded.is_visible,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    identifier,
                    definition.card_type,
                    int(card["position"]),
                    int(bool(card["is_visible"])),
                ),
            )

    return dashboard_card_layout(path)
