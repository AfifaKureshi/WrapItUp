import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_DEMO"] = "false"
os.environ["SECRET_KEY"] = "testing-only-key-with-at-least-32-characters"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.catalog import seed_catalog, seed_users
from app.main import app
from app.security import attempts


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_catalog(session)
    seed_users(session, "TestPackwise123!")
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db):
    attempts.clear()
    def override():
        try:
            yield db
        except Exception:
            db.rollback()
            raise
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    def login(role="manufacturer"):
        response = client.post("/api/auth/login", json={"email": f"{role}@packwise.demo", "password": "TestPackwise123!"})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return login


@pytest.fixture
def payload():
    return {"name": "Khakhra / 250g", "food_id": "khakhra", "target_days": 14, "temperature_c": 25, "relative_humidity": 65, "weight_g": 250, "area_m2": 0.06, "budget_inr": 10, "current_material_id": "demo-ldpe-a"}
