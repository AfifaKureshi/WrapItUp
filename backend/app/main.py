from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
import csv
import hashlib
from io import BytesIO, StringIO
import json
import math
import re

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import research
from .catalog import seed_catalog, seed_users
from .config import settings
from .database import SessionLocal, get_db
from .engine import ENGINE_VERSION, recommend, serial_food, serial_material
from .models import Batch, Datasheet, Event, Food, Material, Project, Review, SensorLog, Trial, User, now
from .reports import specification
from .schemas import BatchInput, Login, MaterialRevision, ProjectInput, Question, Register, ReviewInput, Selection, ShareReview, TrialInput
from .security import current_user, dummy_hash, hasher, limit_auth, reviewer, token


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic in production; auto-create tables in development.
    if settings().app_env != "production":
        from .database import Base, engine
        from . import workspace_models  # register workspace tables
        Base.metadata.create_all(bind=engine)
    if settings().seed_demo:
        if not settings().demo_password:
            raise RuntimeError("Set DEMO_PASSWORD before enabling SEED_DEMO")
        with SessionLocal() as db:
            seed_catalog(db)
            seed_users(db, settings().demo_password)
    yield


app = FastAPI(title="PackWise API", version="1.0.0", description="PS 236 packaging recommendation, scenario and research platform.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins, allow_origin_regex=settings().cors_origin_regex, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"])


@app.middleware("http")
async def headers(request: Request, call_next):
    size = request.headers.get("content-length")
    if size and (not size.isdigit() or int(size) > 6 * 1024 * 1024):
        return JSONResponse(status_code=413, content={"detail": "Upload limit is 5 MB"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def user_json(u):
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "is_reviewer": u.is_reviewer}


def event(db, user, entity, action, data=None):
    db.add(Event(actor_id=user.id, entity_id=entity, action=action, data=data or {}))


def own_project(db, id_, user, allow_shared=False):
    project = db.get(Project, id_)
    if not project or (project.owner_id != user.id and not (allow_shared and user.is_reviewer and project.shared_for_review)):
        raise HTTPException(404, "Project not found")
    return project


def project_json(p, detail=True):
    result = {"id": p.id, "name": p.name, "food_id": p.food_id, "status": p.status, "revision": p.revision, "parent_id": p.parent_id, "selected_material_id": p.selected_material_id, "shared_for_review": p.shared_for_review, "created_at": p.created_at.isoformat(), "candidate_count": len(p.result["candidates"]), "result_status": p.result["status"], "target_days": p.inputs["target_days"], "food_name": p.result["food_snapshot"]["name"]}
    if detail:
        result.update(inputs=p.inputs, result=p.result)
    return result


def compute(db, inputs):
    food = db.get(Food, inputs.food_id)
    if not food:
        raise HTTPException(422, "Select a known food profile")
    if inputs.current_material_id and not db.get(Material, inputs.current_material_id):
        raise HTTPException(422, "Unknown current packaging material")
    materials = list(db.scalars(select(Material)))
    if not materials:
        raise HTTPException(503, "The material catalog is empty. Load reviewed data or enable the demo catalog.")
    from .model_adapter import enrich
    return enrich(recommend(inputs, food, materials), inputs)


def save_project(db, user, inputs, parent=None):
    p = Project(owner_id=user.id, name=inputs.name, food_id=inputs.food_id, inputs=inputs.model_dump(), result=compute(db, inputs), revision=parent.revision + 1 if parent else 1, parent_id=parent.id if parent else None)
    db.add(p)
    db.flush()
    event(db, user, p.id, "project_created", {"engine_version": ENGINE_VERSION, "parent_id": p.parent_id})
    return p


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": db.bind.dialect.name, "engine_version": ENGINE_VERSION, "demo_enabled": settings().seed_demo}
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None


@app.post("/api/auth/register", status_code=201, dependencies=[Depends(limit_auth)])
def register(body: Register, db: Session = Depends(get_db)):
    u = User(name=body.name, email=str(body.email).lower(), role=body.role, password_hash=hasher.hash(body.password), is_reviewer=False)
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This email is already registered") from None
    return {"access_token": token(u), "token_type": "bearer", "user": user_json(u)}


@app.post("/api/auth/login", dependencies=[Depends(limit_auth)])
def login(body: Login, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == str(body.email).lower()))
    valid = hasher.verify(body.password, u.password_hash if u else dummy_hash)
    if not u or not valid:
        raise HTTPException(401, "Email or password is incorrect")
    return {"access_token": token(u), "token_type": "bearer", "user": user_json(u)}


@app.get("/api/auth/me")
def me(u: User = Depends(current_user)):
    return user_json(u)


@app.post("/api/auth/logout", status_code=204)
def logout(u: User = Depends(current_user), db: Session = Depends(get_db)):
    u.token_version += 1
    db.commit()


@app.get("/api/catalog/foods")
def foods(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serial_food(f) for f in db.scalars(select(Food).order_by(Food.name))]


@app.get("/api/catalog/materials")
def materials(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serial_material(m) for m in db.scalars(select(Material).order_by(Material.name))]


@app.patch("/api/catalog/materials/{id_}")
def revise_material(id_: str, body: MaterialRevision, u: User = Depends(reviewer), db: Session = Depends(get_db)):
    m = db.scalar(select(Material).where(Material.id == id_).with_for_update())
    if not m:
        raise HTTPException(404, "Material not found")
    if m.revision != body.expected_revision:
        raise HTTPException(409, "Material was revised by another reviewer. Reload it.")
    previous = serial_material(m)
    m.data = {**m.data, **body.model_dump(exclude={"expected_revision", "notes"}), "revision_date": now().date().isoformat()}
    m.revision += 1
    event(db, u, id_, "material_revised", {"previous": previous, "notes": body.notes, "new_revision": m.revision})
    db.commit()
    return serial_material(m)


@app.get("/api/dashboard")
def dashboard(u: User = Depends(current_user), db: Session = Depends(get_db)):
    projects = list(db.scalars(select(Project).where(Project.owner_id == u.id).order_by(Project.created_at.desc())))
    trials = list(db.scalars(select(Trial).where(Trial.owner_id == u.id)))
    counts = Counter(t.failure for t in trials)
    return {"projects": len(projects), "trial_candidates": sum(len(p.result["candidates"]) for p in projects), "trials": len(trials), "batches": db.scalar(select(func.count()).select_from(Batch).where(Batch.owner_id == u.id)), "needs_attention": sum(p.result["status"] == "no_supported_candidate" for p in projects), "recent_projects": [project_json(p, False) for p in projects[:6]], "failure_counts": dict(counts), "materials": db.scalar(select(func.count()).select_from(Material)), "foods": db.scalar(select(func.count()).select_from(Food)), "role": u.role}


@app.post("/api/recommendations/preview")
def preview(body: ProjectInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return compute(db, body)


@app.get("/api/projects")
def projects(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [project_json(p, False) for p in db.scalars(select(Project).where(Project.owner_id == u.id).order_by(Project.created_at.desc()).limit(300))]


@app.post("/api/projects", status_code=201)
def create(body: ProjectInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = save_project(db, u, body)
    db.commit()
    return project_json(p)


@app.get("/api/projects/{id_}")
def detail(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u, True)
    return {**project_json(p), "can_edit": p.owner_id == u.id, "reviews": [{"decision": r.decision, "notes": r.notes, "created_at": r.created_at.isoformat()} for r in db.scalars(select(Review).where(Review.project_id == p.id).order_by(Review.created_at.desc()))]}


@app.post("/api/projects/{id_}/revise", status_code=201)
def revise(id_: str, body: ProjectInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    parent = own_project(db, id_, u)
    p = save_project(db, u, body, parent)
    db.commit()
    return project_json(p)


@app.post("/api/projects/{id_}/simulate")
def simulate(id_: str, body: ProjectInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u)
    result = compute(db, body)
    return {"baseline": p.result, "scenario": result, "candidate_change": len(result["candidates"]) - len(p.result["candidates"]), "saved": False}


@app.post("/api/projects/{id_}/select")
def select_candidate(id_: str, body: Selection, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u)
    if body.material_id not in [c["material_id"] for c in p.result["candidates"]]:
        raise HTTPException(422, "Only a passing trial candidate can be selected")
    if db.scalar(select(func.count()).select_from(Batch).where(Batch.project_id == id_)):
        raise HTTPException(409, "This selection is bound to a batch. Create a project revision to change it.")
    p.selected_material_id = body.material_id
    p.status = "trial_planned"
    event(db, u, p.id, "candidate_selected", {"material_id": body.material_id})
    db.commit()
    return project_json(p)


@app.get("/api/projects/{id_}/audit")
def audit(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u)
    current = p.inputs.get("current_material_id")
    if not current:
        return {"material": None, "message": "Set the current packaging in a project revision to run the audit.", "next_measurements": p.result["next_measurements"]}
    match = next((c for c in p.result["candidates"] + p.result["rejected"] if c["material_id"] == current), None)
    return {"material": match, "message": "Compare observed failures with these screening results; the audit does not prove causation.", "next_measurements": p.result["next_measurements"]}


@app.post("/api/projects/{id_}/share-review")
def share_review(id_: str, body: ShareReview, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u)
    p.shared_for_review = body.enabled
    event(db, u, p.id, "review_consent", {"enabled": body.enabled})
    db.commit()
    return {"shared_for_review": p.shared_for_review}


@app.get("/api/review-queue")
def review_queue(u: User = Depends(reviewer), db: Session = Depends(get_db)):
    return [project_json(p, False) for p in db.scalars(select(Project).where(Project.shared_for_review.is_(True)).order_by(Project.created_at.desc()).limit(200))]


@app.post("/api/projects/{id_}/review", status_code=201)
def review(id_: str, body: ReviewInput, u: User = Depends(reviewer), db: Session = Depends(get_db)):
    p = own_project(db, id_, u, True)
    if p.owner_id == u.id:
        raise HTTPException(422, "Independent review requires a different owner")
    r = Review(project_id=id_, reviewer_id=u.id, **body.model_dump())
    db.add(r)
    event(db, u, id_, "expert_review", body.model_dump())
    db.commit()
    return {"id": r.id, "decision": r.decision}


@app.get("/api/projects/{id_}/report")
def report(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u, True)
    return Response(specification(p), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="PackWise-{p.id[:8]}.pdf"'})


@app.get("/api/projects/{id_}/history")
def history(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    own_project(db, id_, u, True)
    return [{"action": e.action, "data": e.data, "created_at": e.created_at.isoformat()} for e in db.scalars(select(Event).where(Event.entity_id == id_).order_by(Event.created_at))]


@app.post("/api/projects/{id_}/assistant")
def assistant(id_: str, body: Question, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u, True)
    q = body.question.lower()
    if any(s in q for s in ["cost", "price", "cheap"]):
        answer = "Packaging cost is area × thickness × density × the catalog resin price, plus a 12% illustrative conversion allowance. Total cost adds your packing, logistics and food-loss assumptions. Obtain an actual quotation."
        source = "inputs + candidate.cost_inr + candidate.total_cost_inr"
    elif any(s in q for s in ["safe", "expiry", "shelf", "days"]):
        answer = "The displayed range is a quality screening estimate from illustrative parameters, not a safe use-by date. The 70–125% band is a sensitivity band. Conduct storage and relevant safety testing before a shelf-life claim."
        source = "result.notice + candidate.interval_type"
    elif any(s in q for s in ["otr", "oxygen", "wvtr", "barrier"]):
        answer = "OTR describes oxygen transfer at specified test conditions; WVTR describes water-vapour transfer. The result preserves those conditions. Profile-based budgets, pack area and exposure duration set the illustrative barrier limits."
        source = "result.requirements + material_snapshot.otr_test/wvtr_test"
    elif any(s in q for s in ["sustain", "recycl", "eco"]):
        answer = "The comparison uses material mass, mono-material structure and stated recovery routes. It does not calculate a carbon footprint. Confirm local collection and recycling acceptance."
        source = "candidate.sustainability"
    else:
        answer = p.result["message"] + " " + " ".join(p.result["next_measurements"])
        source = "result.message + result.next_measurements"
    return {"answer": answer, "source": source, "mode": "Record-grounded guide; deterministic responses, no external LLM"}


def trial_json(t):
    return {"id": t.id, "project_id": t.project_id, "material_id": t.material_id, "study_id": t.study_id, "observed_days": t.observed_days, "failure": t.failure, "notes": t.notes, "reviewed": t.reviewed, "is_demo": t.is_demo, "created_at": t.created_at.isoformat()}


@app.get("/api/trials")
def trials(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [trial_json(t) for t in db.scalars(select(Trial).where(Trial.owner_id == u.id).order_by(Trial.created_at.desc()).limit(500))]


@app.post("/api/trials", status_code=201)
def create_trial(body: TrialInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, body.project_id, u)
    if body.material_id not in [c["material_id"] for c in p.result["candidates"]]:
        raise HTTPException(422, "The trial must reference a candidate in this project snapshot")
    t = Trial(owner_id=u.id, **body.model_dump())
    db.add(t)
    event(db, u, p.id, "trial_recorded", {"study_id": body.study_id})
    db.commit()
    return trial_json(t)


@app.get("/api/research/trials")
def review_trials(u: User = Depends(reviewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(Trial).join(Project, Trial.project_id == Project.id).where(Project.shared_for_review.is_(True)).order_by(Trial.created_at.desc()).limit(500))
    return [trial_json(t) for t in rows]


@app.post("/api/trials/{id_}/approve")
def approve_trial(id_: str, u: User = Depends(reviewer), db: Session = Depends(get_db)):
    t = db.get(Trial, id_)
    if not t:
        raise HTTPException(404, "Trial not found")
    own_project(db, t.project_id, u, True)
    if t.owner_id == u.id:
        raise HTTPException(422, "Independent review requires a different owner")
    t.reviewed = True
    t.reviewed_by = u.id
    event(db, u, t.project_id, "trial_reviewed", {"trial_id": t.id})
    db.commit()
    return trial_json(t)


@app.get("/api/trials/export")
def export_trials(u: User = Depends(current_user), db: Session = Depends(get_db)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["trial_id", "project_id", "study_id", "material_id", "observed_days", "failure", "reviewed", "notes"])
    def safe(value):
        s = str(value)
        return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else s
    for t in db.scalars(select(Trial).where(Trial.owner_id == u.id)):
        writer.writerow([safe(x) for x in [t.id, t.project_id, t.study_id, t.material_id, t.observed_days, t.failure, t.reviewed, t.notes]])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="packwise-trials.csv"'})


def batch_json(b):
    return {"id": b.id, "project_id": b.project_id, "code": b.code, "quantity": b.quantity, "notes": b.notes, "created_at": b.created_at.isoformat(), "qr_payload": f"packwise:batch:{b.id}"}


@app.get("/api/batches")
def batches(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [batch_json(b) for b in db.scalars(select(Batch).where(Batch.owner_id == u.id).order_by(Batch.created_at.desc()).limit(300))]


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, body.project_id, u)
    if not p.selected_material_id:
        raise HTTPException(422, "Select a trial candidate before creating a batch")
    b = Batch(owner_id=u.id, **body.model_dump())
    db.add(b)
    event(db, u, p.id, "batch_created", {"code": b.code})
    db.commit()
    return batch_json(b)


@app.get("/api/batches/{id_}")
def get_batch(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Batch, id_)
    if not b or b.owner_id != u.id:
        raise HTTPException(404, "Batch not found")
    return {**batch_json(b), "project": project_json(own_project(db, b.project_id, u))}


async def limited_bytes(file: UploadFile):
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Upload limit is 5 MB")
    return data


@app.post("/api/projects/{id_}/sensor-log", status_code=201)
async def sensor_log(id_: str, file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = own_project(db, id_, u)
    raw = await limited_bytes(file)
    try:
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
        if not 2 <= len(rows) <= 10000:
            raise ValueError("Use 2–10,000 readings")
        parsed = []
        last = None
        for row in rows:
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Timestamps need timezone offsets")
            t, rh = float(row["temperature_c"]), float(row["relative_humidity"])
            if not math.isfinite(t) or not math.isfinite(rh) or not -35 <= t <= 60 or not 0 <= rh <= 100:
                raise ValueError("Reading outside supported range")
            if last and timestamp <= last:
                raise ValueError("Timestamps must strictly increase")
            parsed.append({"timestamp": timestamp.isoformat(), "temperature_c": t, "relative_humidity": rh})
            last = timestamp
    except (ValueError, KeyError, UnicodeDecodeError) as exc:
        raise HTTPException(422, f"Invalid sensor CSV: {exc}") from None
    durations = [(datetime.fromisoformat(b["timestamp"]) - datetime.fromisoformat(a["timestamp"])).total_seconds() / 86400 for a, b in zip(parsed, parsed[1:])]
    total = sum(durations)
    if not 0 < total <= 730:
        raise HTTPException(422, "Sensor duration must be positive and at most 730 days")
    avg_t = sum(a["temperature_c"] * d for a, d in zip(parsed, durations)) / total
    avg_rh = sum(a["relative_humidity"] * d for a, d in zip(parsed, durations)) / total
    summary = {"readings": len(parsed), "duration_days": round(total, 4), "mean_temperature_c": round(avg_t, 2), "min_temperature_c": min(x["temperature_c"] for x in parsed), "max_temperature_c": max(x["temperature_c"] for x in parsed), "mean_rh": round(avg_rh, 2), "excursion_readings": sum(abs(x["temperature_c"] - p.inputs["temperature_c"]) > 5 for x in parsed), "method": "Time-weighted, forward-held values between timestamps; final reading has no duration. Use scenario editor to assess the journey."}
    record = SensorLog(owner_id=u.id, project_id=p.id, summary=summary, readings=parsed)
    db.add(record)
    event(db, u, p.id, "sensor_log_imported", summary)
    db.commit()
    return {"id": record.id, **summary}


@app.get("/api/projects/{id_}/sensor-logs")
def sensor_logs(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    own_project(db, id_, u)
    return [{"id": s.id, **s.summary} for s in db.scalars(select(SensorLog).where(SensorLog.project_id == id_).order_by(SensorLog.created_at.desc()))]


@app.post("/api/imports/bulk", status_code=201)
async def bulk(file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    if u.role not in ("manufacturer", "researcher"):
        raise HTTPException(403, "Bulk imports are available to manufacturers and researchers")
    raw = await limited_bytes(file)
    try:
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise HTTPException(422, "Upload a UTF-8 CSV") from None
    if not 1 <= len(rows) <= 100:
        raise HTTPException(422, "Upload between 1 and 100 products")
    validated = []
    errors = []
    for index, row in enumerate(rows, 2):
        try:
            validated.append(ProjectInput.model_validate({k: v for k, v in row.items() if v not in (None, "")}))
        except (ValidationError, TypeError) as exc:
            errors.append({"row": index, "error": str(exc)[:700]})
    if errors:
        raise HTTPException(422, {"message": "No rows saved; correct the CSV and retry", "errors": errors})
    saved = [save_project(db, u, item) for item in validated]
    db.commit()
    return {"created": len(saved), "projects": [project_json(p, False) for p in saved]}


@app.post("/api/datasheets/extract", status_code=201)
async def extract(file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    if u.role not in ("manufacturer", "researcher"):
        raise HTTPException(403, "Datasheet imports are available to manufacturers and researchers")
    raw = await limited_bytes(file)
    if not raw.startswith(b"%PDF"):
        raise HTTPException(422, "Upload a text-based PDF")
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) > 30:
            raise ValueError("Use an unencrypted PDF with at most 30 pages")
        extracted = "\n".join((p.extract_text() or "")[:15000] for p in reader.pages)[:60000]
    except Exception:
        raise HTTPException(422, "PDF could not be read; use an unencrypted text-based document of at most 30 pages") from None
    fields = {}
    for key, label in [("otr", r"(?:OTR|oxygen transmission rate)"), ("wvtr", r"(?:WVTR|water vapou?r transmission rate)"), ("thickness_um", r"(?:thickness)")]:
        match = re.search(label + r"\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", extracted, re.IGNORECASE)
        fields[key] = {"value": float(match.group(1)) if match else None, "evidence": extracted[max(0, match.start() - 60):match.end() + 140] if match else "No unambiguous match"}
    data = {"fields": fields, "preview": extracted[:8000], "status": "human_verification_required", "note": "Units and test conditions must be checked in the original PDF. Scanned-image OCR is not included. No automatic catalog insertion."}
    sheet = Datasheet(owner_id=u.id, filename=(file.filename or "document.pdf")[:180], sha256=hashlib.sha256(raw).hexdigest(), extracted=data)
    db.add(sheet)
    db.commit()
    return {"id": sheet.id, **data}


@app.get("/api/research/status")
def research_status(u: User = Depends(current_user), db: Session = Depends(get_db)):
    if u.role != "researcher" and not u.is_reviewer:
        raise HTTPException(403, "Research workspace is available to researchers")
    return research.status(db)


@app.post("/api/research/train")
def train(u: User = Depends(reviewer), db: Session = Depends(get_db)):
    return research.train(db)


from .workspace import router as workspace_router
app.include_router(workspace_router)
