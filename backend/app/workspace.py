"""API-backed workspace flows, imports, evidence, sourcing and account settings."""
from datetime import date
from io import StringIO, BytesIO
import csv
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Material, Project, Datasheet, Trial, SensorLog, now
from .workspace_models import WorkspaceRecord
from .schemas import StrictModel, ProjectInput
from .security import current_user, reviewer, hasher, token
from .config import settings
from . import research

router = APIRouter(prefix='/api')


def common():
    # Delayed import avoids an application/router import cycle.
    from . import main
    return main


def professional(u: User = Depends(current_user)):
    if u.role not in ('manufacturer', 'researcher'):
        raise HTTPException(403, 'This action is available to manufacturers and researchers')
    return u


def serial(r):
    return {'id': r.id, 'kind': r.kind, 'project_id': r.project_id, 'created_at': r.created_at.isoformat(), **r.data}


def owned(db, id_, u, kind=None):
    r = db.get(WorkspaceRecord, id_)
    if not r or r.owner_id != u.id or (kind and r.kind != kind):
        raise HTTPException(404, 'Record not found')
    return r


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ProfileUpdate(StrictModel):
    name: str = Field(min_length=2, max_length=100)


@router.get('/config')
def public_config():
    # Demo values are published only in explicitly seeded development mode.
    demo = settings().seed_demo and settings().app_env != 'production'
    return {'demo_enabled': demo, 'demo_accounts': [
        {'role': role, 'email': f'{role}@packwise.demo', 'password': settings().demo_password}
        for role in ('farmer', 'manufacturer', 'researcher')
    ] if demo else [], 'model_connected': bool(settings().model_adapter)}


@router.patch('/auth/profile')
def update_profile(body: ProfileUpdate, u: User = Depends(current_user), db: Session = Depends(get_db)):
    u.name = body.name
    db.commit()
    return common().user_json(u)


@router.post('/auth/change-password')
def change_password(body: PasswordChange, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if u.email.endswith('@packwise.demo') and settings().seed_demo:
        raise HTTPException(403, 'Shared demo accounts keep fixed credentials; register your own account to change a password')
    if not hasher.verify(body.current_password, u.password_hash):
        raise HTTPException(401, 'Current password is incorrect')
    u.password_hash = hasher.hash(body.new_password)
    u.token_version += 1
    db.commit()
    return {'access_token': token(u), 'token_type': 'bearer', 'user': common().user_json(u)}


@router.get('/model/status')
def model_status(u: User = Depends(current_user)):
    return {'configured': bool(settings().model_adapter), 'mode': 'external_adapter' if settings().model_adapter else 'rules_and_calculations', 'contract': 'docs/MODEL_INTEGRATION.md', 'training_required': not bool(settings().model_adapter), 'note': 'External predictions annotate passing candidates; compatibility checks always run first.'}


class SupplierInput(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    material_id: str = Field(min_length=2, max_length=48)
    contact: str = Field(default='', max_length=200)
    region: str = Field(default='', max_length=100)
    moq_kg: float = Field(ge=0, le=1000000)
    price_inr_kg: float = Field(gt=0, le=1000000)
    lead_time_days: int = Field(ge=0, le=730)
    available_thickness_um: float = Field(gt=0, le=5000)
    equipment: list[Literal['hand_sealer', 'band_sealer', 'ffs', 'tray_sealer', 'unsealed']] = Field(min_length=1)
    source: str = Field(min_length=5, max_length=1000)


@router.get('/suppliers')
def suppliers(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serial(r) for r in db.scalars(select(WorkspaceRecord).where(WorkspaceRecord.owner_id == u.id, WorkspaceRecord.kind == 'supplier').order_by(WorkspaceRecord.created_at.desc()))]


@router.post('/suppliers', status_code=201)
def add_supplier(body: SupplierInput, u: User = Depends(professional), db: Session = Depends(get_db)):
    if not db.get(Material, body.material_id):
        raise HTTPException(422, 'Unknown material')
    r = WorkspaceRecord(owner_id=u.id, kind='supplier', data=body.model_dump())
    db.add(r)
    db.commit()
    return serial(r)


@router.delete('/suppliers/{id_}', status_code=204)
def remove_supplier(id_: str, u: User = Depends(professional), db: Session = Depends(get_db)):
    r = owned(db, id_, u, 'supplier')
    db.delete(r)
    db.commit()


@router.get('/projects/{id_}/supplier-matches')
def supplier_matches(id_: str, max_moq_kg: float = 1000000, max_lead_days: int = 730, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = common().own_project(db, id_, u)
    candidates = {c['material_id']: c for c in p.result['candidates']}
    results = []
    for r in db.scalars(select(WorkspaceRecord).where(WorkspaceRecord.owner_id == u.id, WorkspaceRecord.kind == 'supplier')):
        d = r.data
        c = candidates.get(d['material_id'])
        if c and d['moq_kg'] <= max_moq_kg and d['lead_time_days'] <= max_lead_days and p.inputs['equipment'] in d['equipment'] and abs(d['available_thickness_um'] - c['material_snapshot']['thickness_um']) < .1:
            results.append(serial(r))
    return {'matches': results, 'note': 'Matches your saved supplier quotations, exact nominal thickness and equipment. Confirm availability directly.'}


@router.get('/datasheets')
def datasheets(u: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Datasheet).order_by(Datasheet.created_at.desc()) if u.is_reviewer else select(Datasheet).where(Datasheet.owner_id == u.id).order_by(Datasheet.created_at.desc()))
    return [{'id': r.id, 'owner_id': r.owner_id, 'filename': r.filename, 'created_at': r.created_at.isoformat(), **r.extracted} for r in rows]


class VerifySheet(StrictModel):
    material_id: str
    expected_revision: int = Field(ge=1)
    otr: float = Field(gt=0, le=1000000)
    wvtr: float = Field(gt=0, le=10000)
    otr_test: str = Field(min_length=5, max_length=200)
    wvtr_test: str = Field(min_length=5, max_length=200)
    notes: str = Field(min_length=10, max_length=1000)


@router.post('/datasheets/{id_}/verify')
def verify_sheet(id_: str, body: VerifySheet, u: User = Depends(reviewer), db: Session = Depends(get_db)):
    sheet = db.get(Datasheet, id_)
    if not sheet or (sheet.owner_id != u.id and not u.is_reviewer):
        raise HTTPException(404, 'Datasheet not found')
    from .schemas import MaterialRevision
    revision = MaterialRevision(**body.model_dump(exclude={'material_id'}), source=f'Human-checked PDF: {sheet.filename}; sha256={sheet.sha256}')
    result = common().revise_material(body.material_id, revision, u, db)
    sheet.extracted = {**sheet.extracted, 'status': 'verified', 'verification': {**body.model_dump(), 'reviewer_id': u.id, 'at': now().isoformat()}}
    db.commit()
    return {'datasheet_id': id_, 'material': result, 'status': 'verified'}


@router.post('/documents', status_code=201)
async def add_document(project_id: str = Form(...), title: str = Form(..., min_length=2, max_length=150), scope: str = Form(..., min_length=5, max_length=1000), expiry_date: str = Form(''), file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    common().own_project(db, project_id, u)
    raw = await common().limited_bytes(file)
    if not raw.startswith(b'%PDF'):
        raise HTTPException(422, 'Evidence must be a PDF')
    try:
        if expiry_date:
            date.fromisoformat(expiry_date)
    except ValueError:
        raise HTTPException(422, 'Use YYYY-MM-DD for expiry date') from None
    r = WorkspaceRecord(owner_id=u.id, kind='document', project_id=project_id, data={'title': title, 'scope': scope, 'expiry_date': expiry_date, 'status': 'pending_review', 'filename': (file.filename or 'evidence.pdf')[:180]}, attachment=raw)
    db.add(r)
    db.commit()
    return serial(r)


@router.get('/projects/{id_}/documents')
def documents(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    common().own_project(db, id_, u, True)
    return [{**serial(r), 'expired': bool(r.data.get('expiry_date') and r.data['expiry_date'] < date.today().isoformat())} for r in db.scalars(select(WorkspaceRecord).where(WorkspaceRecord.project_id == id_, WorkspaceRecord.kind == 'document'))]


@router.get('/documents/{id_}/download')
def download_document(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(WorkspaceRecord, id_)
    if not r or r.kind != 'document':
        raise HTTPException(404, 'Document not found')
    common().own_project(db, r.project_id, u, True)
    return Response(r.attachment, media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="evidence.pdf"'})


class EvidenceReview(StrictModel):
    status: Literal['accepted_for_scope', 'changes_requested']
    notes: str = Field(min_length=10, max_length=1000)


@router.post('/documents/{id_}/review')
def review_document(id_: str, body: EvidenceReview, u: User = Depends(reviewer), db: Session = Depends(get_db)):
    r = db.get(WorkspaceRecord, id_)
    if not r or r.kind != 'document':
        raise HTTPException(404, 'Document not found')
    common().own_project(db, r.project_id, u, True)
    if r.owner_id == u.id:
        raise HTTPException(422, 'Independent review requires a different owner')
    r.data = {**r.data, **body.model_dump(), 'reviewer_id': u.id}
    common().event(db, u, r.project_id, 'evidence_reviewed', {'document_id': r.id, **body.model_dump()})
    db.commit()
    return serial(r)


class FeedbackInput(StrictModel):
    project_id: str | None = None
    rating: int = Field(ge=1, le=5)
    category: Literal['usability', 'recommendation', 'missing_data', 'outcome', 'other']
    message: str = Field(min_length=5, max_length=2000)


@router.get('/feedback')
def feedback(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serial(r) for r in db.scalars(select(WorkspaceRecord).where(WorkspaceRecord.owner_id == u.id, WorkspaceRecord.kind == 'feedback').order_by(WorkspaceRecord.created_at.desc()))]


@router.post('/feedback', status_code=201)
def add_feedback(body: FeedbackInput, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.project_id:
        common().own_project(db, body.project_id, u)
    r = WorkspaceRecord(owner_id=u.id, kind='feedback', project_id=body.project_id, data=body.model_dump(exclude={'project_id'}))
    db.add(r)
    db.commit()
    return serial(r)


@router.get('/projects/{id_}/handling-advice')
def handling(id_: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = common().own_project(db, id_, u, True)
    food = p.result['food_snapshot']
    fragile = 'mechanical' in food.get('risks', [])
    return {'secondary': [
        {'item': 'Rigid tray and dividers' if fragile else 'Protective outer carton', 'reason': 'Reduce compression and movement during handling.', 'validation': 'Verify stacking and drop resistance with the packed product.'},
        {'item': 'Ventilated crate' if food['category'] == 'fresh' else 'Dry storage and pallet cover', 'reason': 'Maintain airflow for produce or protect dry packs from moisture.', 'validation': 'Check the complete storage and transport route.'}],
        'active_options': [{'item': 'Oxygen scavenger', 'status': 'expert_review_required', 'reason': 'Consider only with validated food compatibility, capacity and ingestion controls; not for respiring produce.'}, {'item': 'Moisture control insert', 'status': 'expert_review_required', 'reason': 'Requires measured moisture load and suitability testing; no automatic dosage.'}],
        'note': 'Handling guidance is a review checklist, not a validated load rating or active-packaging prescription.'}


@router.get('/research/export')
def research_export(u: User = Depends(reviewer), db: Session = Depends(get_db)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['trial_id', 'study_group', 'food_id', *research.FEATURES, 'observed_days', 'failure'])
    for trial, project in research.eligible_trials(db):
        c = next((c for c in project.result['candidates'] if c['material_id'] == trial.material_id), None)
        if c:
            values = {**project.inputs, **c['material_snapshot']}
            # Opaque group keeps the same study together without exposing owner identity.
            import hashlib
            group = hashlib.sha256(f'{trial.owner_id}:{trial.study_id}'.encode()).hexdigest()[:24]
            writer.writerow([trial.id, group, project.food_id, *[values[k] for k in research.FEATURES], trial.observed_days, trial.failure])
    return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="reviewed-training-data.csv"'})


@router.get('/notifications')
def notifications(u: User = Depends(current_user), db: Session = Depends(get_db)):
    result = []
    for p in db.scalars(select(Project).where(Project.owner_id == u.id).order_by(Project.created_at.desc()).limit(100)):
        if not p.result['candidates']:
            result.append({'id': p.id, 'project_id': p.id, 'title': f'Revisit {p.name}', 'message': p.result['message'], 'kind': 'target'})
        for review in common().detail(p.id, u, db)['reviews'][:1]:
            result.append({'id': p.id + ':review', 'project_id': p.id, 'title': 'Expert review received', 'message': review['notes'], 'kind': 'review'})
    return result


@router.post('/projects/{id_}/sensor-logs/{log_id}/simulate')
def simulate_sensor(id_: str, log_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = common().own_project(db, id_, u)
    log = db.get(SensorLog, log_id)
    if not log or log.owner_id != u.id or log.project_id != id_:
        raise HTTPException(404, 'Sensor log not found')
    from datetime import datetime
    from .engine import recommend, serial_food
    from .models import Food
    stages = []
    for a, b in zip(log.readings, log.readings[1:]):
        days = (datetime.fromisoformat(b['timestamp']) - datetime.fromisoformat(a['timestamp'])).total_seconds() / 86400
        stages.append({'name': 'Measured interval', 'days': days, 'temperature_c': a['temperature_c'], 'relative_humidity': a['relative_humidity']})
    duration = sum(s['days'] for s in stages)
    # Internal model accepts exact intervals; user form still limits manual stages to ten.
    body = ProjectInput.model_validate({**p.inputs, 'target_days': max(1, duration), 'stages': []})
    from .schemas import Stage
    body.stages = [Stage(**s) for s in stages]
    body.target_days = duration
    result = common().compute(db, body)
    return {'baseline': p.result, 'scenario': result, 'saved': False, 'duration_days': duration, 'note': 'Reassessed only over the measured interval. No extrapolation beyond the log.'}
