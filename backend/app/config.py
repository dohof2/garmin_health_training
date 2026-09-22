from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_directory() -> Path:
    """Return the local app-data directory, creating it when needed."""
    configured = os.getenv("HT_APP_DATA_DIR")
    path = Path(configured).expanduser() if configured else PROJECT_ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_directory() / "health_training.sqlite3"
