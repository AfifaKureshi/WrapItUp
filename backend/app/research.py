"""Opt-in experimental ML, trained only from consented, reviewed real trials."""
import json
from pathlib import Path
from threading import Lock

import joblib
import numpy as np
from fastapi import HTTPException
from sqlalchemy import select

from .config import settings
from .models import Project, Trial, now

training_lock = Lock()
FEATURES = ["temperature_c", "relative_humidity", "weight_g", "area_m2", "headspace_ml", "otr", "wvtr", "thickness_um"]


def eligible_trials(db):
    return db.execute(select(Trial, Project).join(Project, Trial.project_id == Project.id).where(Trial.reviewed.is_(True), Trial.is_demo.is_(False), Project.shared_for_review.is_(True), Trial.failure != "no_failure_yet")).all()


def train(db):
    if not training_lock.acquire(blocking=False):
        raise HTTPException(409, "Training is already running")
    try:
        rows = eligible_trials(db)
        x, y, groups = [], [], []
        for trial, project in rows:
            candidate = next((c for c in project.result["candidates"] if c["material_id"] == trial.material_id), None)
            if candidate is None:
                continue
            m = candidate["material_snapshot"]
            values = {**project.inputs, **{k: m[k] for k in ["otr", "wvtr", "thickness_um"]}}
            x.append([values[k] for k in FEATURES])
            y.append(trial.observed_days)
            # A study stays together. Prefixing by owner avoids accidental
            # collisions between unrelated organisations' study names.
            groups.append(f"{trial.owner_id}:{trial.study_id}")
        if len(x) < 30 or len(set(groups)) < 5:
            raise HTTPException(422, "At least 30 reviewed, non-demo, uncensored trial outcomes across 5 independent studies are required.")
        try:
            from sklearn.dummy import DummyRegressor
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.metrics import mean_absolute_error
            from sklearn.model_selection import GroupShuffleSplit
        except ImportError:
            raise HTTPException(503, "scikit-learn is required for experimental ML training. Install it with pip install scikit-learn.")
        x, y = np.array(x), np.array(y)
        train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42).split(x, y, groups))
        model = RandomForestRegressor(n_estimators=120, min_samples_leaf=3, random_state=42, n_jobs=1)
        model.fit(x[train_idx], y[train_idx])
        baseline = DummyRegressor(strategy="median").fit(x[train_idx], y[train_idx])
        metrics = {"status": "experimental_evaluation", "rows": len(y), "studies": len(set(groups)), "training_rows": len(train_idx), "heldout_rows": len(test_idx), "mae_days": round(float(mean_absolute_error(y[test_idx], model.predict(x[test_idx]))), 3), "baseline_mae_days": round(float(mean_absolute_error(y[test_idx], baseline.predict(x[test_idx]))), 3), "split": "GroupShuffleSplit by owner/study; 25% held out", "features": FEATURES, "trained_at": now().isoformat(), "used_for_recommendations": False, "note": "Research evaluation only. Further validation and an explicit deployment decision are required."}
        directory = Path(settings().model_directory)
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, directory / "research_model.tmp")
        (directory / "research_model.tmp").replace(directory / "research_model.joblib")
        (directory / "metrics.tmp").write_text(json.dumps(metrics, indent=2))
        (directory / "metrics.tmp").replace(directory / "metrics.json")
        return metrics
    finally:
        training_lock.release()


def status(db):
    rows = eligible_trials(db)
    path = Path(settings().model_directory) / "metrics.json"
    return {"eligible_trials": len(rows), "eligible_studies": len({f"{t.owner_id}:{t.study_id}" for t, _ in rows}), "minimum_trials": 30, "minimum_studies": 5, "engine_mode": "Transparent rules + illustrative scientific calculations", "latest_evaluation": json.loads(path.read_text()) if path.exists() else None}
