SHELL := /bin/sh

backend-test:
	cd backend && ../.venv/bin/python -m pytest -q

backend-local:
	cd backend && ../.venv/bin/python scripts/dev_bootstrap.py && DATABASE_URL=sqlite:///./packwise-dev.db ../.venv/bin/uvicorn app.main:app --reload --port 8000

frontend-get:
	cd frontend && flutter pub get

frontend-run:
	cd frontend && flutter run -d chrome --dart-define=API_URL=http://localhost:8000
