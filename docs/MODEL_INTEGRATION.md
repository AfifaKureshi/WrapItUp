# PackWise model integration contract

The application is usable without a trained model. Its current recommendation path is a transparent compatibility filter plus scenario calculations. When the trained model is ready, connect it through `MODEL_ADAPTER` in the backend environment:

```env
MODEL_ADAPTER=your_package.module:predict
```

The configured callable must accept two arguments:

```python
def predict(inputs: dict, candidates: list[dict]) -> dict:
    return {
        "demo-metpet-a": {
            "quality_days": 42.0,
            "model_version": "packwise-quality-v1"
        }
    }
```

`inputs` contains the validated product brief. `candidates` contains only materials that already passed the compatibility and barrier screen. The result must be a dictionary keyed only by those candidate `material_id` values. Each prediction must contain a finite `quality_days` value between 0 and 1,095 and a short `model_version`.

The adapter is deliberately constrained:

- It cannot make an incompatible or rejected material pass.
- It cannot change OTR/WVTR units, test conditions, or the stored project snapshot.
- An invalid, missing or failed model falls back to the transparent screening result and is shown as unavailable in the UI.
- The model annotation is labelled as an external model estimate; it is not a safe use-by date or food-safety certification.

For training, export `/api/research/export` as a verified researcher. Keep records from the same owner/study group together in validation, report held-out error, and retain a model card with the data scope, features, limitations and intended deployment conditions.
