from io import BytesIO
from pypdf import PdfReader


def create(client, headers, payload):
    r = client.post("/api/projects", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_registration_role_and_logout(client):
    data = {"name": "New Researcher", "email": "new@example.com", "password": "SomethingSafe123!", "role": "researcher"}
    r = client.post("/api/auth/register", json=data)
    assert r.status_code == 201
    assert r.json()["user"]["is_reviewer"] is False
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/review-queue", headers=h).status_code == 403
    assert client.post("/api/auth/register", json={**data, "is_reviewer": True}).status_code == 422
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_candidate_report_trial_batch_end_to_end(client, auth, payload):
    h = auth()
    p = create(client, h, payload)
    assert p["result"]["candidates"]
    assert p["result"]["evidence_level"] == "illustrative"
    material = p["result"]["candidates"][0]["material_id"]
    assert client.post(f"/api/projects/{p['id']}/select", headers=h, json={"material_id": material}).status_code == 200
    batch = client.post("/api/batches", headers=h, json={"project_id": p["id"], "code": "KW-001", "quantity": 20})
    assert batch.status_code == 201
    assert batch.json()["qr_payload"].startswith("packwise:batch:")
    assert client.post(f"/api/projects/{p['id']}/select", headers=h, json={"material_id": material}).status_code == 409
    trial = client.post("/api/trials", headers=h, json={"project_id": p["id"], "material_id": material, "study_id": "lab-1", "observed_days": 15, "failure": "moisture", "notes": "=2+2"})
    assert trial.status_code == 201
    report = client.get(f"/api/projects/{p['id']}/report", headers=h)
    assert report.status_code == 200 and report.content.startswith(b"%PDF")
    report_text = " ".join(page.extract_text() for page in PdfReader(BytesIO(report.content)).pages)
    assert "Khakhra" in report_text and "Illustrative" in report_text
    assert "'=2+2" in client.get("/api/trials/export", headers=h).text
    assert client.get("/api/dashboard", headers=h).json()["trials"] == 1


def test_ownership_and_review_consent(client, auth, payload):
    owner, stranger, expert = auth(), auth("farmer"), auth("researcher")
    p = create(client, owner, payload)
    for endpoint in [f"/api/projects/{p['id']}", f"/api/projects/{p['id']}/report"]:
        assert client.get(endpoint, headers=stranger).status_code == 404
        assert client.get(endpoint, headers=expert).status_code == 404
    assert client.post(f"/api/projects/{p['id']}/share-review", headers=owner, json={"enabled": True}).status_code == 200
    assert client.get(f"/api/projects/{p['id']}", headers=expert).status_code == 200
    r = client.post(f"/api/projects/{p['id']}/review", headers=expert, json={"decision": "trial_recommended", "notes": "Conduct a controlled humidity storage trial."})
    assert r.status_code == 201
    assert client.post(f"/api/projects/{p['id']}/share-review", headers=owner, json={"enabled": False}).status_code == 200
    assert client.get(f"/api/projects/{p['id']}", headers=expert).status_code == 404


def test_unsafe_cheap_choice_cannot_win(client, auth, payload):
    p = create(client, auth(), {**payload, "equipment": "tray_sealer", "priority": "cost"})
    assert not p["result"]["candidates"]
    assert p["result"]["status"] == "no_supported_candidate"
    assert all("Incompatible" in " ".join(r["failures"]) for r in p["result"]["rejected"])


def test_simulator_changes_risk_and_does_not_mutate(client, auth, payload):
    h = auth()
    p = create(client, h, payload)
    r = client.post(f"/api/projects/{p['id']}/simulate", headers=h, json={**payload, "temperature_c": 35, "relative_humidity": 90})
    assert r.status_code == 200
    assert r.json()["scenario"]["requirements"]["max_wvtr_reference"] < p["result"]["requirements"]["max_wvtr_reference"]
    assert client.get(f"/api/projects/{p['id']}", headers=h).json()["inputs"]["temperature_c"] == 25
    rev = client.post(f"/api/projects/{p['id']}/revise", headers=h, json={**payload, "target_days": 10})
    assert rev.json()["revision"] == 2 and rev.json()["parent_id"] == p["id"]


def test_impossible_target_and_input_validation(client, auth, payload):
    h = auth()
    p = create(client, h, {**payload, "target_days": 700})
    assert not p["result"]["candidates"]
    assert p["result"]["suggested_changes"]
    assert client.post("/api/projects", headers=h, json={**payload, "water_activity": 2}).status_code == 422
    assert client.post("/api/projects", headers=h, json={**payload, "food_id": "unknown"}).status_code == 422
    assert client.post("/api/projects", headers=h, json={**payload, "stages": [{"name": "journey", "days": 2, "temperature_c": 25, "relative_humidity": 60}]}).status_code == 422


def test_fresh_produce_has_dedicated_gas_model(client, auth):
    p = create(client, auth("farmer"), {"name": "Tomatoes", "food_id": "tomato", "temperature_c": 12, "relative_humidity": 85, "storage_type": "chilled", "target_days": 5})
    assert p["result"]["candidates"]
    assert all(c["gas"] is not None for c in p["result"]["candidates"])
    assert all(c["gas"]["trajectory"][0]["o2_pct"] == 20.9 for c in p["result"]["candidates"])
    p2 = create(client, auth("farmer"), {"name": "Excess produce mass", "food_id": "tomato", "temperature_c": 12, "storage_type": "chilled", "target_days": 5, "weight_g": 50000})
    assert not p2["result"]["candidates"]


def test_bulk_is_atomic_and_sensor_timestamps_are_checked(client, auth, payload):
    h = auth()
    csv = "name,food_id,target_days\nFirst,khakhra,14\nSecond,missing,14\n"
    r = client.post("/api/imports/bulk", headers=h, files={"file": ("products.csv", csv, "text/csv")})
    assert r.status_code == 422
    assert client.get("/api/projects", headers=h).json() == []
    p = create(client, h, payload)
    good = "timestamp,temperature_c,relative_humidity\n2026-01-01T00:00:00Z,20,50\n2026-01-02T00:00:00Z,30,80\n2026-01-04T00:00:00Z,25,60\n"
    r = client.post(f"/api/projects/{p['id']}/sensor-log", headers=h, files={"file": ("log.csv", good)})
    assert r.status_code == 201, r.text
    assert abs(r.json()["mean_temperature_c"] - 26.67) < 0.01
    bad = good.replace("2026-01-04", "2026-01-01")
    assert client.post(f"/api/projects/{p['id']}/sensor-log", headers=h, files={"file": ("log.csv", bad)}).status_code == 422


def test_material_edits_do_not_rewrite_saved_results(client, auth, payload):
    owner, expert = auth(), auth("researcher")
    p = create(client, owner, payload)
    material = p["result"]["candidates"][0]["material_snapshot"]
    update = {"expected_revision": 1, "notes": "Correcting the illustrative catalog record", "source": "Reviewed illustrative fixture; no supplier validation", "otr": 0.8, "wvtr": 0.2, "otr_test": "23 C, 0% RH, 1 atm", "wvtr_test": "38 C, 90% to 0% RH"}
    r = client.patch(f"/api/catalog/materials/{material['id']}", headers=expert, json=update)
    assert r.status_code == 200 and r.json()["revision"] == 2
    assert client.patch(f"/api/catalog/materials/{material['id']}", headers=expert, json=update).status_code == 409
    saved = client.get(f"/api/projects/{p['id']}", headers=owner).json()
    assert saved["result"]["candidates"][0]["material_snapshot"]["revision"] == 1


def test_training_gate_never_claims_untrained_accuracy(client, auth):
    h = auth("researcher")
    r = client.get("/api/research/status", headers=h)
    assert r.json()["latest_evaluation"] is None
    assert client.post("/api/research/train", headers=h).status_code == 422


def test_unknown_fields_and_cors(client, auth, payload):
    assert client.post("/api/projects", headers=auth(), json={**payload, "owner_id": "someone"}).status_code == 422
    r = client.options("/api/projects", headers={"Origin": "https://malicious.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
