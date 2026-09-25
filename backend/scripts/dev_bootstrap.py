import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite:///./packwise-dev.db")
os.environ.setdefault("SEED_DEMO", "false")
os.environ.setdefault("SECRET_KEY", "local-development-only-secret-with-32-characters")

from app.catalog import seed_catalog, seed_users
from app import workspace_models
from app.database import Base, SessionLocal, engine

Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed_catalog(db)
    seed_users(db, os.getenv("DEMO_PASSWORD", "PackWiseDemo123!"))
print("Local database ready. Demo accounts use password PackWiseDemo123!")
