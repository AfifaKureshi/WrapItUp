"""Transparent, deterministic screening; no trained model is pretended to exist.

All catalog parameters currently supplied are synthetic. The Q10 transfer
corrections and uncertainty band are scenario assumptions, not validated fits.
"""
import math
from datetime import datetime, timezone

from .models import Food, Material
from .schemas import ProjectInput

ENGINE_VERSION = "screening-1.0.0"


def clamp(x, low, high):
    return max(low, min(x, high))


def serial_material(material: Material):
    return {"id": material.id, "name": material.name, "family": material.family, "revision": material.revision, **material.data}


def serial_food(food: Food):
    return {"id": food.id, "name": food.name, "category": food.category, **food.data}


def recommend(inputs: ProjectInput, food: Food, materials: list[Material]):
    f = food.data
    values = inputs.model_dump()
    assumptions = []
    for field in ["water_activity", "moisture_pct", "fat_pct", "ph", "respiration_ml_kg_h"]:
        if values[field] is None:
            values[field] = f[field]
            assumptions.append(f"{field.replace('_', ' ')} = {f[field]} from the illustrative {food.name} profile.")
    stages = [stage.model_dump() for stage in inputs.stages] or [{"name": "Storage", "days": inputs.target_days, "temperature_c": inputs.temperature_c, "relative_humidity": inputs.relative_humidity}]
    temps = [s["temperature_c"] for s in stages]
    weights = [s["days"] / inputs.target_days for s in stages]
    temp = sum(t * w for t, w in zip(temps, weights))
    rh = sum(s["relative_humidity"] * w for s, w in zip(stages, weights))
    domain_issues = []
    if min(temps) < f["min_temperature_c"] or max(temps) > f["max_temperature_c"]:
        domain_issues.append(f"Temperature is outside the illustrative {food.name} profile range ({f['min_temperature_c']} to {f['max_temperature_c']} °C).")
    if food.category == "frozen" and inputs.storage_type != "frozen":
        domain_issues.append("Frozen food requires a frozen storage profile.")
    if food.category != "frozen" and inputs.storage_type == "frozen":
        domain_issues.append("This food profile does not cover freezing.")
    if inputs.storage_type == "chilled" and max(temps) > 15:
        domain_issues.append("The chilled journey contains a stage warmer than 15 °C; choose ambient or correct the stages.")
    if food.category == "dry" and values["water_activity"] > 0.65:
        domain_issues.append("Water activity exceeds the dry-food model's scope; expert evaluation is needed.")
    if food.category == "fresh" and values["water_activity"] < 0.9:
        domain_issues.append("Water activity is inconsistent with this whole-fresh-produce profile.")
    aw = values["water_activity"]
    area = inputs.area_m2
    kg = inputs.weight_g / 1000
    q_food = sum(w * 2 ** ((t - f["reference_temperature_c"]) / 10) for w, t in zip(weights, temps))
    intrinsic_life = f["reference_quality_days"] / q_food
    oxygen_exposure_factor = sum(w * 2 ** ((t - 23) / 10) for w, t in zip(weights, temps)) * 0.209
    vapor_factor = sum(w * 2 ** ((s["temperature_c"] - 38) / 10) * max(0, s["relative_humidity"] / 100 - aw) / 0.9 for w, s in zip(weights, stages))
    max_wvtr = f["moisture_budget_g_kg"] * kg / (area * inputs.target_days * vapor_factor) if food.category == "dry" and vapor_factor > 0 else None
    oxygen_allowance = f["oxygen_budget_ml_kg"] * kg - inputs.headspace_ml * 0.209
    max_otr = max(0, oxygen_allowance) / (area * inputs.target_days * oxygen_exposure_factor) if food.category == "dry" else None
    candidates = []
    rejected = []
    for material in materials:
        m = material.data
        failures = list(domain_issues)
        if food.category not in m["categories"]:
            failures.append(f"Material profile does not support {food.category} food.")
        if min(temps) < m["min_temp_c"] or max(temps) > m["max_temp_c"]:
            failures.append("Journey temperature is outside this material's working range.")
        if inputs.equipment not in m["equipment"]:
            failures.append("Incompatible filling/sealing equipment.")
        mass_g = area * m["thickness_um"] * 1e-6 * m["density_kg_m3"] * 1000
        cost = mass_g / 1000 * m["price_inr_kg"] * 1.12
        if cost > inputs.budget_inr:
            failures.append("Estimated packaging cost exceeds the per-pack budget.")
        mechanism = "intrinsic quality"
        life = intrinsic_life
        reasons = [f"{m['thickness_um']} µm {m['structure']}.", f"Compatible with {inputs.equipment.replace('_', ' ')}."]
        gas = None
        if food.category == "dry":
            moisture_rate = m["wvtr"] * area * vapor_factor
            moisture_life = f["moisture_budget_g_kg"] * kg / moisture_rate if moisture_rate > 0 else 1e6
            oxygen_rate = m["otr"] * area * oxygen_exposure_factor
            oxidation_life = max(0, oxygen_allowance) / oxygen_rate if oxygen_rate > 0 else 1e6
            life, mechanism = min([(intrinsic_life, "intrinsic quality"), (moisture_life, "moisture gain"), (oxidation_life, "oxygen exposure")])
            reasons.append(f"Scenario-limiting mechanism: {mechanism}.")
            if "light" in f["risks"] and not m["light_barrier"]:
                failures.append("This light-sensitive profile requires a light barrier.")
        elif food.category == "fresh" and m["breathable"]:
            respiration = values["respiration_ml_kg_h"] * kg * 24 * sum(w * 2 ** ((t - 20) / 10) for w, t in zip(weights, temps))
            go2 = m["o2_conductance_ml_day_fraction"] * area / m["conductance_reference_area_m2"]
            gco2 = m["co2_conductance_ml_day_fraction"] * area / m["conductance_reference_area_m2"]
            o2 = 0.209 - respiration / go2
            co2 = 0.0004 + respiration / gco2
            trajectory = [{"day": d, "o2_pct": round(100 * (o2 + (0.209 - o2) * math.exp(-go2 / inputs.headspace_ml * d)), 2), "co2_pct": round(100 * (co2 + (0.0004 - co2) * math.exp(-gco2 / inputs.headspace_ml * d)), 2)} for d in [0, 0.25, 0.5, 1, 2, 4, 7]]
            gas = {"initial_o2_pct": 20.9, "initial_co2_pct": 0.04, "equilibrium_o2_pct": round(o2 * 100, 2), "equilibrium_co2_pct": round(co2 * 100, 2), "trajectory": trajectory, "method": "Illustrative constant respiration + conductance balance; RQ=1, initial air. Never a validated gas-flush prescription.", "microperforation": "Candidate film only; hole size/count requires measured conductance and a trial."}
            if o2 * 100 < f["o2_min_pct"] or co2 * 100 > f["co2_max_pct"]:
                failures.append("Illustrative gas balance is outside the commodity's screening limits.")
            reasons.append("Breathable film; respiration and gas exchange screened together.")
        elif food.category == "fresh":
            failures.append("Fresh produce needs a supported breathable film model.")
        life = round(clamp(life, 0, 730), 1)
        lower, upper = round(life * 0.7, 1), round(min(730, life * 1.25), 1)
        if lower < inputs.target_days:
            failures.append(f"Conservative scenario duration ({lower:g} days) is below the {inputs.target_days:g}-day target.")
        eco = (35 if m["mono_material"] else 8) + 30 / (1 + mass_g / 4)
        technical = min(100, 50 + 50 * lower / max(inputs.target_days, 1))
        cost_score = 100 / (1 + cost / 2)
        score_weights = {"balanced": (0.4, 0.3, 0.3), "cost": (0.25, 0.6, 0.15), "sustainability": (0.25, 0.15, 0.6)}[inputs.priority]
        score = sum(a * b for a, b in zip(score_weights, [technical, cost_score, eco]))
        entry = {
            "material_id": material.id, "name": material.name, "material_snapshot": serial_material(material),
            "screening_pass": not failures, "production_ready": False,
            "estimated_quality_days": life, "quality_range_days": [lower, upper],
            "interval_type": "Heuristic sensitivity band (70–125%); not a statistical confidence interval or safe use-by date.",
            "limiting_mechanism": mechanism, "cost_inr": round(cost, 2), "material_mass_g": round(mass_g, 2),
            "total_cost_inr": round(cost + inputs.packing_inr + inputs.logistics_inr + inputs.food_value_inr * inputs.loss_percent / 100, 2),
            "loss_assumption_percent": inputs.loss_percent,
            "priority_score": round(score, 1), "score_meaning": "Preference index, not probability or measured performance.",
            "sustainability": {"mono_material": m["mono_material"], "recovery": m["recovery"], "carbon_kg": None, "note": "Material mass and recovery screen only; no life-cycle assessment."},
            "reasons": reasons, "failures": failures, "gas": gas,
            "documents_needed": ["Food-contact conformity for intended use", "Supplier OTR/WVTR with test methods", "Seal integrity and product storage trial"],
        }
        (rejected if failures else candidates).append(entry)
    candidates.sort(key=lambda c: c["priority_score"], reverse=True)
    rejected.sort(key=lambda c: (len(c["failures"]), -c["estimated_quality_days"]))
    selected_ids = set()
    choices = []
    for label, entry in [("Balanced choice", candidates[0] if candidates else None), ("Lowest cost", min(candidates, key=lambda c: c["cost_inr"]) if candidates else None), ("Lower material / recovery option", max(candidates, key=lambda c: (c["sustainability"]["mono_material"], -c["material_mass_g"])) if candidates else None)]:
        if entry:
            choices.append({"label": label, "material_id": entry["material_id"]})
            selected_ids.add(entry["material_id"])
    next_measurements = ["Confirm measured water activity and the quality rejection endpoint.", "Request supplier grade data and seal-integrity results."] if food.category == "dry" else ["Measure respiration for the actual variety, maturity and temperature.", "Measure package conductance and verify gas behaviour in a storage trial."]
    max_supported = max((r["quality_range_days"][0] for r in rejected if all(reason.startswith("Conservative scenario") for reason in r["failures"])), default=0)
    suggestions = [] if candidates else ["Review the rejection reason on each material.", f"The longest otherwise-compatible screening duration is {max_supported:g} days." if max_supported else "Correct unsupported storage or equipment conditions before changing the target.", "Compare a lower target, a different pack size, or a controlled storage journey."]
    return {
        "engine_version": ENGINE_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "trial_candidates" if candidates else "no_supported_candidate",
        "message": f"{len(candidates)} trial candidates meet the illustrative screening constraints." if candidates else "No supported candidate meets this target under the entered conditions.",
        "evidence_level": "illustrative", "notice": "Prototype screening only. Catalog values and Q10 assumptions are illustrative; no validated food-safety or shelf-life claim.",
        "food_snapshot": serial_food(food), "candidates": candidates, "rejected": rejected, "choices": choices,
        "assumptions": assumptions + ["Q10=2 for scenario screening; constant film properties within each stage.", "Initial headspace is air (20.9% O2); user-entered loss is a cost assumption, not a model prediction."],
        "requirements": {"max_otr_reference": round(max_otr, 3) if max_otr is not None else None, "max_wvtr_reference": round(max_wvtr, 3) if max_wvtr is not None else None, "otr_unit": "cm³/(m²·day·atm), reference 23°C / 0% RH", "wvtr_unit": "g/(m²·day), reference 38°C / 90–0% RH", "mean_temperature_c": round(temp, 1), "mean_rh": round(rh, 1)},
        "domain_issues": domain_issues, "next_measurements": next_measurements, "suggested_changes": suggestions,
        "risks": f["risks"], "stages": stages,
        "secondary_packaging": "Use suitable dividers/trays and a transport compression/drop test for fragile or fresh products." if food.category == "fresh" or "mechanical" in f["risks"] else "Validate carton stacking, moisture exposure and handling for the actual journey.",
        "active_packaging": "No active component is prescribed without product-specific compatibility, dosing and migration evidence.",
    }
