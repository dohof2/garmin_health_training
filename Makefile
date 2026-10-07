.PHONY: setup seed garmin-preview garmin-import fit-inventory fit-preview fit-import xml-preview xml-import health-fit-inventory health-fit-preview health-fit-import wellness-preview wellness-import extended-preview extended-import backend frontend test build

setup:
	/usr/local/bin/python3.13 -m venv .venv
	.venv/bin/python -m pip install --index-url https://pypi.org/simple -r backend/requirements.lock.txt
	cd frontend && npm_config_cache=.npm-cache npm ci --registry=https://registry.npmjs.org

seed:
	PYTHONPATH=backend .venv/bin/python -m app.fixtures

garmin-preview:
	PYTHONPATH=backend .venv/bin/python -m app.garmin_import preview

garmin-import:
	PYTHONPATH=backend .venv/bin/python -m app.garmin_import import

fit-inventory:
	PYTHONPATH=backend .venv/bin/python -m app.fit_import inventory

fit-preview:
	PYTHONPATH=backend .venv/bin/python -m app.fit_import preview

fit-import:
	PYTHONPATH=backend .venv/bin/python -m app.fit_import import

xml-preview:
	PYTHONPATH=backend .venv/bin/python -m app.xml_activity_import preview

xml-import:
	PYTHONPATH=backend .venv/bin/python -m app.xml_activity_import import

health-fit-inventory:
	PYTHONPATH=backend .venv/bin/python -m app.health_fit_import inventory

health-fit-preview:
	PYTHONPATH=backend .venv/bin/python -m app.health_fit_import preview

health-fit-import:
	PYTHONPATH=backend .venv/bin/python -m app.health_fit_import import

wellness-preview:
	PYTHONPATH=backend .venv/bin/python -m app.wellness_import preview

wellness-import:
	PYTHONPATH=backend .venv/bin/python -m app.wellness_import import

extended-preview:
	PYTHONPATH=backend .venv/bin/python -m app.extended_archive_import preview

extended-import:
	PYTHONPATH=backend .venv/bin/python -m app.extended_archive_import import

backend:
	.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

test:
	PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build
