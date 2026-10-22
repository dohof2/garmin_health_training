"""Daily-use entry point: API and built frontend on the same loopback server."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .main import app

frontend = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if not (frontend / 'index.html').is_file():
    raise RuntimeError('Build the frontend before starting the local app.')

# API routes are registered first. The frontend uses hash-based navigation.
app.mount('/', StaticFiles(directory=frontend, html=True), name='local-frontend')
