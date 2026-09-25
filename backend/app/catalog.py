"""Explicitly synthetic fixtures: never represent these as supplier or lab data."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Food, Material, User
from .security import hasher

CATALOG_NOTE = "Illustrative development data. Replace with sourced measurements and supplier grades before operational use."


def seed_catalog(db: Session):
    foods = [
        ("khakhra", "Khakhra", "dry", "ખાખરા / खाखरा", 0.20, 3, 12, 6.5, 60, 6, 1500, 0, ["moisture", "mechanical"]),
        ("peanuts", "Roasted peanuts", "dry", "शेंगदाणे / મગફળી", 0.30, 2, 48, 6.5, 90, 10, 550, 0, ["oxidation", "moisture"]),
        ("tomato", "Whole tomatoes", "fresh", "टमाटर / ટામેટાં", 0.98, 94, 0.2, 4.3, 7, 0, 0, 18, ["respiration", "mechanical"]),
        ("banana", "Whole bananas", "fresh", "केला / કેળા", 0.97, 75, 0.3, 5.0, 6, 0, 0, 25, ["respiration", "mechanical"]),
        ("spinach", "Whole spinach leaves", "fresh", "पालक / પાલક", 0.99, 92, 0.4, 6.2, 3, 0, 0, 60, ["respiration", "wilting"]),
        ("rice", "Dry rice", "dry", "चावल / ચોખા", 0.45, 12, 1, 6.5, 180, 35, 5000, 0, ["moisture"]),
        ("biscuits", "Plain biscuits", "dry", "बिस्कुट / બિસ્કિટ", 0.25, 3, 15, 6.7, 90, 8, 1200, 0, ["moisture", "oxidation"]),
        ("spices", "Ground dry spices", "dry", "मसाले / મસાલા", 0.30, 8, 8, 6, 120, 12, 700, 0, ["moisture", "oxidation", "light"]),
        ("milkpowder", "Whole milk powder", "dry", "दूध पाउडर / દૂધ પાવડર", 0.20, 3, 26, 6.7, 120, 10, 300, 0, ["oxidation", "moisture"]),
        ("frozenpeas", "Frozen peas", "frozen", "जमे हुए मटर / વટાણા", 0.98, 78, 0.4, 6.2, 120, 0, 0, 0, ["moisture_loss", "temperature"]),
    ]
    for id_, name, category, aliases, aw, moisture, fat, ph, base, budget, o2_budget, respiration, risks in foods:
        if db.get(Food, id_):
            continue
        fresh = category == "fresh"
        db.add(Food(id=id_, name=name, category=category, data={
            "aliases": aliases, "state": "whole fresh" if fresh else ("frozen" if category == "frozen" else "dry processed"),
            "water_activity": aw, "moisture_pct": moisture, "fat_pct": fat, "ph": ph,
            "reference_quality_days": base, "reference_temperature_c": -18 if category == "frozen" else 20,
            "moisture_budget_g_kg": budget, "oxygen_budget_ml_kg": o2_budget,
            "respiration_ml_kg_h": respiration, "risks": risks,
            "min_temperature_c": 8 if id_ in ["tomato", "banana"] else (0 if fresh else -25 if category == "frozen" else 5),
            "max_temperature_c": -12 if category == "frozen" else 35 if fresh else 40,
            "o2_min_pct": 3 if fresh else None, "co2_max_pct": 5 if fresh else None,
            "suggested_storage": "frozen" if category == "frozen" else "chilled" if fresh else "ambient",
            "is_demo": True, "source": CATALOG_NOTE, "revision": 1,
            "limitations": "Not applicable to fresh-cut, cooked, fermented or formulation-modified variants. No microbial safety model.",
        }))
    # family, structure, nominal thickness um, OTR, WVTR, density kg/m3,
    # illustrative resin cost INR/kg, recycle description, categories, light barrier
    families = [
        ("ldpe", "LDPE", "LDPE monolayer", 50, 6500, 8, 920, 150, "PE film stream, where collected", ["dry", "frozen"], False),
        ("hdpe", "HDPE", "HDPE monolayer", 40, 3000, 3, 950, 155, "PE film stream, where collected", ["dry", "frozen"], False),
        ("bopp", "BOPP", "Heat-sealable BOPP", 30, 1800, 4, 910, 170, "PP film stream, where collected", ["dry"], False),
        ("petpe", "PET/PE", "PET 12 / adhesive / PE", 70, 80, 2.8, 1080, 210, "Specialist multilayer recovery", ["dry", "frozen"], False),
        ("metpet", "Metallised PET/PE", "PET 12 / metallised PET 12 / PE", 75, 1.0, 0.45, 1150, 245, "Specialist multilayer recovery", ["dry"], True),
        ("foil", "Aluminium laminate", "PET 12 / aluminium 9 / PE", 90, 0.05, 0.05, 1450, 320, "Specialist composite recovery", ["dry"], True),
        ("mdope", "MDO-PE/PE", "MDO-PE 25 / PE sealant", 80, 2000, 1.8, 940, 225, "PE stream subject to local acceptance", ["dry", "frozen"], False),
        ("evoh", "PE/EVOH/PE", "PE / tie / EVOH / tie / PE", 80, 0.5, 2, 970, 265, "Depends on EVOH proportion and local acceptance", ["dry", "frozen"], False),
        ("pla", "PLA", "Seal-grade PLA", 40, 900, 18, 1240, 290, "Industrial composting only if certified and collected", ["dry"], False),
        ("kraft", "Kraft/PLA", "Kraft paper / PLA lining", 120, 1500, 20, 850, 220, "Coating-dependent; collection verification needed", ["dry"], True),
        ("perforatedpp", "Micro-perforated PP", "Micro-perforated PP film", 35, 10000, 20, 910, 220, "PP stream, where collected", ["fresh"], False),
        ("breathable", "Breathable PE", "High-exchange breathable PE film", 40, 12000, 24, 920, 195, "PE film stream, where collected", ["fresh"], False),
    ]
    for family, name, structure, base_t, otr, wvtr, density, price, recovery, categories, opaque in families:
        for multiplier, suffix in [(1, "A"), (1.4, "B")]:
            id_ = f"demo-{family}-{suffix.lower()}"
            if db.get(Material, id_):
                continue
            fresh = "fresh" in categories
            thickness = round(base_t * multiplier)
            db.add(Material(id=id_, name=f"{name} · {thickness} µm", family=family, data={
                "grade": f"DEMO-{family.upper()}-{suffix}", "structure": structure,
                "thickness_um": thickness, "otr": round(otr / multiplier, 4), "wvtr": round(wvtr / multiplier, 4),
                "otr_unit": "cm³/(m²·day·atm)", "wvtr_unit": "g/(m²·day)",
                "otr_test": "Illustrative: 23 °C, 0% RH, oxygen partial-pressure difference 1 atm",
                "wvtr_test": "Illustrative: 38 °C, 90% to 0% RH",
                "density_kg_m3": density, "price_inr_kg": price, "recovery": recovery,
                "mono_material": family in ["ldpe", "hdpe", "bopp", "mdope", "perforatedpp", "breathable"],
                "categories": categories, "min_temp_c": -25 if "frozen" in categories else 0,
                "max_temp_c": 40 if family in ["pla", "kraft"] else 60,
                "equipment": ["hand_sealer", "band_sealer", "ffs"],
                "seal_range_c": "Confirm supplier-specific seal window", "sealant": "PE" if family in ["foil", "metpet", "petpe", "evoh", "mdope"] else name,
                "mechanical": "Film-only protection; secondary packaging required for crush-sensitive food",
                "light_barrier": opaque, "breathable": fresh,
                "o2_conductance_ml_day_fraction": (11000 if family == "perforatedpp" else 7000) / multiplier if fresh else None,
                "co2_conductance_ml_day_fraction": (17000 if family == "perforatedpp" else 14000) / multiplier if fresh else None,
                "conductance_reference_area_m2": 0.06,
                "food_contact_evidence": "missing", "documents": [], "supplier": "Illustrative record; obtain a real quotation",
                "moq_kg": 25, "lead_time_days": 7, "is_demo": True, "source": CATALOG_NOTE,
                "revision_date": "2026-09-23", "pack_format": "pouch" if not fresh else "produce bag",
            }))
    db.commit()


def seed_users(db: Session, password: str):
    if len(password) < 10:
        raise ValueError("DEMO_PASSWORD must contain at least 10 characters")
    for role, name in [("farmer", "Asha Patel"), ("manufacturer", "Sandeep"), ("researcher", "Dr. Meera Shah")]:
        email = f"{role}@packwise.demo"
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(name=name, email=email, role=role, password_hash=hasher.hash(password), is_reviewer=role == "researcher"))
    db.commit()
