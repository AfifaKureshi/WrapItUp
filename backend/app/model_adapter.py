"""Optional locally installed model. Disabled by default; no training or uploads.

Set MODEL_ADAPTER=your_package.module:predict after implementing the contract.
The callable receives copies of inputs and passing candidate snapshots, and
returns {material_id: {quality_days: float, model_version: str}}. It cannot
reinstate a rejected candidate or replace compatibility checks.
"""
from copy import deepcopy
from importlib import import_module
import logging
import math
from .config import settings

log = logging.getLogger(__name__)


def enrich(result, inputs):
    path = settings().model_adapter
    result['model'] = {'status': 'not_connected', 'mode': 'rules_and_calculations'}
    if not path:
        return result
    try:
        module, name = path.split(':', 1)
        predict = getattr(import_module(module), name)
        output = predict(deepcopy(inputs.model_dump()), deepcopy(result['candidates']))
        if not isinstance(output, dict):
            raise ValueError('Model output must be a dictionary')
        validated = {}
        ids = {c['material_id'] for c in result['candidates']}
        if set(output) - ids:
            raise ValueError('Model attempted to return an unsupported material')
        for key, prediction in output.items():
            days = float(prediction['quality_days'])
            version = str(prediction['model_version'])
            if not math.isfinite(days) or not 0 < days <= 1095 or not 1 <= len(version) <= 100:
                raise ValueError('Invalid prediction')
            validated[key] = {'quality_days': days, 'model_version': version, 'type': 'external_model_estimate'}
        for candidate in result['candidates']:
            if candidate['material_id'] in validated:
                candidate['model_prediction'] = validated[candidate['material_id']]
        result['model'] = {'status': 'connected', 'predictions': len(validated), 'mode': 'rules_then_external_model'}
    except Exception:
        log.exception('Model adapter failed; retaining transparent screening output')
        result['model'] = {'status': 'unavailable', 'mode': 'rules_and_calculations', 'message': 'Model unavailable; screening calculations remain available.'}
    return result
