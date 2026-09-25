# WrapItUp (PackWise) — Food Packaging Decision Workspace

WrapItUp (PackWise) is a Flutter + FastAPI + PostgreSQL/SQLite decision-support platform for food packaging material selection. It is built around the SIH PS 236 scope: food profiling, storage journeys, barrier requirements, material screening, fresh-produce gas exchange, sustainability/cost trade-offs, trial feedback, and role-specific workspaces.

---

## 📱 Download the Android App (APK)

Anyone can easily download and install the latest Android APK directly from GitHub:

* **[Download Latest APK from GitHub Releases](https://github.com/AfifaKureshi/WrapItUp/releases)**
* **[Download Build Artifacts from GitHub Actions](https://github.com/AfifaKureshi/WrapItUp/actions)**
* Detailed instructions are available in [docs/DOWNLOAD_APK.md](docs/DOWNLOAD_APK.md).

---

The repository contains:

- `.github/workflows/build-apk.yml`: Automated CI/CD workflow to build and publish the Android APK.
- `backend/`: FastAPI API, SQLAlchemy models, Alembic migration, deterministic screening engine, PDF specification export and research gates.
- `frontend/`: Flutter application for farmer, manufacturer and researcher roles with dynamic server switching.
- `docker-compose.yml`: PostgreSQL and API development stack.

## Run the backend with PostgreSQL

Install Docker Desktop, then from this directory run:

```bash
docker compose up --build
```

The API is at `http://localhost:8000`; Swagger is at `http://localhost:8000/docs`.

Demo accounts are enabled by the compose file:

| Role | Email | Password |
| --- | --- | --- |
| Farmer | `farmer@packwise.demo` | `PackWiseDemo123!` |
| Manufacturer | `manufacturer@packwise.demo` | `PackWiseDemo123!` |
| Researcher/reviewer | `researcher@packwise.demo` | `PackWiseDemo123!` |

The catalog records are deliberately marked illustrative. Before an operational or regulatory claim, replace them with supplier grades, laboratory measurements, test methods and reviewed food profiles.

## Windows without Docker

If `docker` is not recognized, use the included Windows launchers. They use SQLite for local development and keep the same FastAPI API and demo accounts:

```text
1. Double-click run_backend_windows.bat
2. In a second window, double-click run_frontend_windows.bat
```

Or double-click `run_packwise_windows.bat` to open both windows. The first run creates a Python virtual environment and installs the backend dependencies. Install Python 3.12+ and Flutter first, and add both to PATH.

## Run locally without Docker

The backend can run against SQLite for UI development. From `backend/`:

```bash
../.venv/bin/python scripts/dev_bootstrap.py
SEED_DEMO=true DEMO_PASSWORD=PackWiseDemo123! DATABASE_URL=sqlite:///./packwise-dev.db ../.venv/bin/uvicorn app.main:app --reload --port 8000
```

For PostgreSQL, copy `.env.example` to `.env`, set a long random `SECRET_KEY`, start PostgreSQL, run `../.venv/bin/alembic upgrade head`, then start Uvicorn.

## Run Flutter

Install Flutter through the official stable SDK, then from `frontend/`:

```bash
flutter pub get
flutter run -d chrome --dart-define=API_URL=http://localhost:8000
```

The default API URL is `http://localhost:8000`. Android emulators should use `http://10.0.2.2:8000`:

```bash
flutter run --dart-define=API_URL=http://10.0.2.2:8000
```

## Product flows included

- Guided simple/expert product profiling with pack geometry, water activity, storage journey and user priorities.
- Compatibility-first recommendations with OTR/WVTR test conditions, thickness, sealability, mechanical requirements, cost and sustainability notes.
- Fresh-produce respiration and illustrative MAP gas trajectory for breathable candidates.
- Ranked alternatives, rejection reasons, target-feasibility suggestions and next-measurement advice.
- Existing-pack audit, what-if scenario simulation, saved revisions and history.
- Supplier datasheet extraction with human verification status.
- CSV bulk recommendation intake, sensor CSV import, batch/QR payloads and PDF specification export.
- Expert review queue, reviewed trial data and an ML training gate that refuses to train on too little or unreviewed data.

## Evidence boundary

The recommendation engine is intentionally transparent. Rules enforce constraints before ranking; scientific calculations show scenario assumptions; the experimental ML module is never used for recommendations until independent reviewed trials meet its data gate. Displayed quality ranges are sensitivity bands, not confidence intervals, expiry dates or food-safety certification.

## Complete workspace coverage

The app also includes secure token storage, password rotation, offline snapshots, multilingual navigation, voice-assisted issue capture, QR batch records, supplier quotation matching, secondary and active-packaging review checklists, supplier evidence upload and human verification, CSV product imports, timestamped sensor reassessment, expert review decisions, reviewed-data export, feedback, notifications, and a guarded model adapter.

The application package includes `docs/MODEL_INTEGRATION.md`. Set `MODEL_ADAPTER=package.module:function` only after your trained model has a tested `predict(inputs, candidates)` implementation. The screening engine continues to enforce compatibility before the model can annotate passing candidates.
