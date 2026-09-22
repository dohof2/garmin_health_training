.PHONY: setup seed backend frontend test build

setup:
	/usr/local/bin/python3.13 -m venv .venv
	.venv/bin/python -m pip install --index-url https://pypi.org/simple -r backend/requirements.lock.txt
	cd frontend && npm_config_cache=.npm-cache npm ci --registry=https://registry.npmjs.org

seed:
	PYTHONPATH=backend .venv/bin/python -m app.fixtures

backend:
	.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

test:
	PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build
