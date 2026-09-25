import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Register(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: Literal["farmer", "manufacturer", "researcher"]


class Login(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Stage(StrictModel):
    name: str = Field(min_length=1, max_length=40)
    days: float = Field(gt=0, le=730)
    temperature_c: float = Field(ge=-35, le=60)
    relative_humidity: float = Field(ge=0, le=100)


class ProjectInput(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    food_id: str = Field(min_length=1, max_length=48)
    mode: Literal["simple", "expert"] = "simple"
    weight_g: float = Field(default=250, ge=10, le=50000)
    area_m2: float = Field(default=0.06, ge=0.002, le=10)
    headspace_ml: float = Field(default=250, ge=1, le=20000)
    target_days: float = Field(default=30, ge=1, le=730)
    temperature_c: float = Field(default=25, ge=-35, le=60)
    relative_humidity: float = Field(default=60, ge=0, le=100)
    storage_type: Literal["ambient", "chilled", "frozen"] = "ambient"
    equipment: Literal["hand_sealer", "band_sealer", "ffs", "tray_sealer", "unsealed"] = "hand_sealer"
    priority: Literal["balanced", "cost", "sustainability"] = "balanced"
    budget_inr: float = Field(default=10, gt=0, le=5000)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    water_activity: float | None = Field(default=None, ge=0, le=1)
    fat_pct: float | None = Field(default=None, ge=0, le=100)
    ph: float | None = Field(default=None, ge=0, le=14)
    respiration_ml_kg_h: float | None = Field(default=None, ge=0, le=1000)
    food_value_inr: float = Field(default=50, ge=0, le=100000)
    loss_percent: float = Field(default=5, ge=0, le=100)
    packing_inr: float = Field(default=0.5, ge=0, le=5000)
    logistics_inr: float = Field(default=1, ge=0, le=5000)
    current_material_id: str | None = Field(default=None, max_length=48)
    problem: str = Field(default="", max_length=500)
    stages: list[Stage] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_journey(self):
        if self.stages and not math.isclose(sum(stage.days for stage in self.stages), self.target_days, abs_tol=0.05):
            raise ValueError("Journey stage durations must add up to the target shelf-life days")
        if self.moisture_pct is not None and self.fat_pct is not None and self.moisture_pct + self.fat_pct > 100:
            raise ValueError("Moisture and fat percentages cannot exceed 100% together")
        return self


class Selection(StrictModel):
    material_id: str = Field(max_length=48)


class ShareReview(StrictModel):
    enabled: bool


class ReviewInput(StrictModel):
    decision: Literal["trial_recommended", "changes_requested", "rejected"]
    notes: str = Field(min_length=10, max_length=3000)


class TrialInput(StrictModel):
    project_id: str
    material_id: str
    study_id: str = Field(min_length=2, max_length=100)
    observed_days: float = Field(gt=0, le=1095)
    failure: Literal["moisture", "oxidation", "wilting", "mechanical", "microbial", "other", "no_failure_yet"]
    notes: str = Field(default="", max_length=3000)


class BatchInput(StrictModel):
    project_id: str
    code: str = Field(min_length=2, max_length=100)
    quantity: int = Field(ge=1, le=10000000)
    notes: str = Field(default="", max_length=1000)


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1000)


class MaterialRevision(StrictModel):
    expected_revision: int = Field(ge=1)
    notes: str = Field(min_length=10, max_length=1000)
    source: str = Field(min_length=10, max_length=2000)
    otr: float = Field(gt=0, le=1000000)
    wvtr: float = Field(gt=0, le=10000)
    otr_test: str = Field(min_length=5, max_length=200)
    wvtr_test: str = Field(min_length=5, max_length=200)
