from io import BytesIO
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
import pytest
from app.models import User
from app.config import settings
from app.schemas import ProjectInput
from app.model_adapter import enrich
from test_flows import create


def pdf_bytes(text='OTR: 0.8 WVTR: 0.2 Thickness: 75'):
    b = BytesIO()
    c = Canvas(b)
    c.drawString(40, 700, text)
    c.save()
    return b.getvalue()


def test_demo_config_only_when_explicitly_enabled(client, monkeypatch):
    assert client.get('/api/config').json()['demo_accounts'] == []
    monkeypatch.setattr(settings(), 'seed_demo', True)
    monkeypatch.setattr(settings(), 'demo_password', 'TestPackwise123!')
    config = client.get('/api/config').json()
    assert len(config['demo_accounts']) == 3
    for account in config['demo_accounts']:
        r = client.post('/api/auth/login', json={k: account[k] for k in ('email', 'password')})
        assert r.status_code == 200
        assert r.json()['user']['role'] == account['role']


def test_auth_wrong_password_expired_token_duplicate_and_profile(client, auth):
    assert client.post('/api/auth/login', json={'email': 'farmer@packwise.demo', 'password': 'wrong'}).status_code == 401
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer malformed'}).status_code == 401
    h = auth('farmer')
    assert client.patch('/api/auth/profile', headers=h, json={'name': 'New Name'}).json()['name'] == 'New Name'
    assert client.patch('/api/auth/profile', headers=h, json={'name': 'New Name', 'role': 'researcher'}).status_code == 422
    assert client.post('/api/auth/register', json={'name': 'Duplicate', 'email': 'farmer@packwise.demo', 'password': 'SomePassword123', 'role': 'farmer'}).status_code == 409


def test_password_change_rotates_sessions(client):
    body = {'name': 'Person', 'email': 'person@example.com', 'password': 'OriginalPass123!', 'role': 'manufacturer'}
    reg = client.post('/api/auth/register', json=body).json()
    old = {'Authorization': 'Bearer ' + reg['access_token']}
    assert client.post('/api/auth/change-password', headers=old, json={'current_password': 'bad', 'new_password': 'NewPassword123!'}).status_code == 401
    changed = client.post('/api/auth/change-password', headers=old, json={'current_password': body['password'], 'new_password': 'NewPassword123!'})
    assert changed.status_code == 200
    new = {'Authorization': 'Bearer ' + changed.json()['access_token']}
    assert client.get('/api/auth/me', headers=old).status_code == 401
    assert client.get('/api/auth/me', headers=new).status_code == 200
    assert client.post('/api/auth/login', json={'email': body['email'], 'password': body['password']}).status_code == 401
    assert client.post('/api/auth/login', json={'email': body['email'], 'password': 'NewPassword123!'}).status_code == 200


def test_supplier_matching_crud_and_permissions(client, auth, payload):
    h, farmer = auth(), auth('farmer')
    p = create(client, h, payload)
    c = p['result']['candidates'][0]
    offer = {'name': 'Test Films', 'material_id': c['material_id'], 'moq_kg': 25, 'price_inr_kg': 240, 'lead_time_days': 7, 'available_thickness_um': c['material_snapshot']['thickness_um'], 'equipment': ['hand_sealer'], 'source': 'Supplier quote 2026-09-24'}
    assert client.post('/api/suppliers', headers=farmer, json=offer).status_code == 403
    saved = client.post('/api/suppliers', headers=h, json=offer)
    assert saved.status_code == 201
    assert len(client.get(f"/api/projects/{p['id']}/supplier-matches", headers=h).json()['matches']) == 1
    assert not client.get(f"/api/projects/{p['id']}/supplier-matches?max_moq_kg=10", headers=h).json()['matches']
    assert not client.get(f"/api/projects/{p['id']}/supplier-matches?max_lead_days=2", headers=h).json()['matches']
    stranger = auth('researcher')
    assert client.get('/api/suppliers', headers=stranger).json() == []
    assert client.delete('/api/suppliers/' + saved.json()['id'], headers=stranger).status_code == 404
    assert client.delete('/api/suppliers/' + saved.json()['id'], headers=h).status_code == 204


def test_evidence_upload_review_download_and_revoked_consent(client, auth, payload):
    owner, expert, other = auth(), auth('researcher'), auth('farmer')
    p = create(client, owner, payload)
    raw = pdf_bytes()
    result = client.post('/api/documents', headers=owner, data={'project_id': p['id'], 'title': 'Supplier certificate', 'scope': 'Dry food at ambient temperature', 'expiry_date': '2020-01-01'}, files={'file': ('certificate.pdf', raw, 'application/pdf')})
    assert result.status_code == 201, result.text
    id_ = result.json()['id']
    assert client.get(f'/api/documents/{id_}/download', headers=owner).content == raw
    assert client.get(f'/api/documents/{id_}/download', headers=other).status_code == 404
    assert client.get(f'/api/documents/{id_}/download', headers=expert).status_code == 404
    assert client.get(f"/api/projects/{p['id']}/documents", headers=owner).json()[0]['expired']
    client.post(f"/api/projects/{p['id']}/share-review", headers=owner, json={'enabled': True})
    decision = {'status': 'accepted_for_scope', 'notes': 'Checked the stated food contact scope.'}
    assert client.post(f'/api/documents/{id_}/review', headers=expert, json=decision).status_code == 200
    assert client.post(f'/api/documents/{id_}/review', headers=owner, json=decision).status_code == 403
    client.post(f"/api/projects/{p['id']}/share-review", headers=owner, json={'enabled': False})
    assert client.get(f'/api/documents/{id_}/download', headers=expert).status_code == 404


def test_datasheet_extract_and_verified_apply(client, auth):
    expert, owner = auth('researcher'), auth()
    result = client.post('/api/datasheets/extract', headers=expert, files={'file': ('data.pdf', pdf_bytes())})
    assert result.status_code == 201
    sheet = result.json()
    assert sheet['fields']['otr']['value'] == .8
    assert client.get('/api/datasheets', headers=owner).json() == []
    body = {'material_id': 'demo-metpet-a', 'expected_revision': 1, 'otr': .8, 'wvtr': .2, 'otr_test': '23 C, 0% RH, 1 atm', 'wvtr_test': '38 C, 90% RH', 'notes': 'Manually checked against original PDF.'}
    assert client.post(f"/api/datasheets/{sheet['id']}/verify", headers=owner, json=body).status_code == 403
    assert client.post(f"/api/datasheets/{sheet['id']}/verify", headers=expert, json=body).status_code == 200
    assert client.get('/api/datasheets', headers=expert).json()[0]['status'] == 'verified'


def test_reviewed_data_export_consent_and_trial_approval(client, auth, payload):
    owner, expert = auth(), auth('researcher')
    p = create(client, owner, payload)
    body = {'project_id': p['id'], 'material_id': p['result']['candidates'][0]['material_id'], 'study_id': 'separate-study', 'observed_days': 12, 'failure': 'moisture'}
    t = client.post('/api/trials', headers=owner, json=body).json()
    assert client.post(f"/api/trials/{t['id']}/approve", headers=expert).status_code == 404
    client.post(f"/api/projects/{p['id']}/share-review", headers=owner, json={'enabled': True})
    assert client.post(f"/api/trials/{t['id']}/approve", headers=expert).status_code == 200
    exported = client.get('/api/research/export', headers=expert)
    assert exported.status_code == 200 and t['id'] in exported.text
    assert 'manufacturer@packwise.demo' not in exported.text
    client.post(f"/api/projects/{p['id']}/share-review", headers=owner, json={'enabled': False})
    assert t['id'] not in client.get('/api/research/export', headers=expert).text
    assert client.get('/api/research/export', headers=owner).status_code == 403


def test_sensor_reassessment_preserves_baseline_and_exact_intervals(client, auth, payload):
    h = auth()
    p = create(client, h, payload)
    csv = 'timestamp,temperature_c,relative_humidity\n2026-01-01T00:00:00Z,25,60\n2026-01-01T12:00:00Z,30,80\n2026-01-02T00:00:00Z,25,60\n'
    log = client.post(f"/api/projects/{p['id']}/sensor-log", headers=h, files={'file': ('sensor.csv', csv)}).json()
    result = client.post(f"/api/projects/{p['id']}/sensor-logs/{log['id']}/simulate", headers=h)
    assert result.status_code == 200, result.text
    assert len(result.json()['scenario']['stages']) == 2
    assert result.json()['duration_days'] == 1
    assert client.get(f"/api/projects/{p['id']}", headers=h).json()['inputs']['target_days'] == 14


def test_feedback_advice_and_notifications(client, auth, payload):
    h = auth()
    p = create(client, h, {**payload, 'target_days': 700})
    assert client.get('/api/notifications', headers=h).json()[0]['project_id'] == p['id']
    r = client.post('/api/feedback', headers=h, json={'project_id': p['id'], 'rating': 4, 'category': 'missing_data', 'message': 'Need a locally measured profile.'})
    assert r.status_code == 201
    assert len(client.get('/api/feedback', headers=h).json()) == 1
    assert client.get('/api/feedback', headers=auth('farmer')).json() == []
    advice = client.get(f"/api/projects/{p['id']}/handling-advice", headers=h)
    assert advice.status_code == 200 and len(advice.json()['secondary']) == 2


def test_model_disabled_valid_and_bad_output(monkeypatch):
    import sys, types
    module = types.ModuleType('unit_model')
    sys.modules['unit_model'] = module
    inputs = ProjectInput(name='Demo project', food_id='khakhra')
    monkeypatch.setattr(settings(), 'model_adapter', '')
    assert enrich({'candidates': []}, inputs)['model']['status'] == 'not_connected'
    monkeypatch.setattr(settings(), 'model_adapter', 'unit_model:predict')
    module.predict = lambda inputs, candidates: {'passing': {'quality_days': 22, 'model_version': 'v1'}}
    result = enrich({'candidates': [{'material_id': 'passing'}]}, inputs)
    assert result['candidates'][0]['model_prediction']['quality_days'] == 22
    module.predict = lambda inputs, candidates: {'unsafe': {'quality_days': 22, 'model_version': 'v1'}}
    result = enrich({'candidates': [{'material_id': 'passing'}]}, inputs)
    assert result['model']['status'] == 'unavailable'
    assert 'model_prediction' not in result['candidates'][0]
    module.predict = lambda inputs, candidates: {'passing': {'quality_days': float('nan'), 'model_version': 'v1'}}
    assert enrich({'candidates': [{'material_id': 'passing'}]}, inputs)['model']['status'] == 'unavailable'
    del sys.modules['unit_model']


def test_professional_import_permissions(client, auth):
    farmer = auth('farmer')
    assert client.post('/api/imports/bulk', headers=farmer, files={'file': ('x.csv', 'name,food_id\nDemo,khakhra')}).status_code == 403
    assert client.post('/api/datasheets/extract', headers=farmer, files={'file': ('x.pdf', pdf_bytes())}).status_code == 403
