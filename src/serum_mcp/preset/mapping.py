"""Merge a semantic :class:`~serum_mcp.generation.spec.PresetSpec` onto the
raw CBOR payload of a base preset (typically ``fixtures/init_preset.SerumPreset``).

Only the fields present on the spec are touched -- everything else in the
base preset's ``data`` dict (mod matrix, arpeggiator, GUI state, unmodeled
oscillator engines, ...) passes through unchanged, so editing an existing
preset only perturbs what the instruction actually asked for.
"""

from __future__ import annotations

import copy
from typing import Any

from serum_mcp.generation.spec import FxUnitSpec, PresetSpec

from . import schema
from .validator import validate_params

_OSC_KEYS = {
    "octave": "kParamOctave",
    "volume": "kParamVolume",
    "pan": "kParamPan",
}
_WTOSC_KEYS = {
    "table_position": "kParamTablePos",
    "warp_amount": "kParamWarp",
}
_FILTER_KEYS = {
    "cutoff": "kParamFreq",
    "resonance": "kParamReso",
    "drive": "kParamDrive",
}
_ENV_KEYS = {
    "attack": "kParamAttack",
    "decay": "kParamDecay",
    "sustain": "kParamSustain",
    "release": "kParamRelease",
}
_LFO_KEYS = {"rate": "kParamRate"}


def _plain_params(container: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``container[key]["plainParams"]`` as a real dict, replacing the
    sentinel string ``"default"`` Serum uses for untouched modules with {}."""
    sub = container.setdefault(key, {})
    if not isinstance(sub.get("plainParams"), dict):
        sub["plainParams"] = {}
    return sub["plainParams"]


def _build_fx_entry(fx: FxUnitSpec) -> dict[str, Any]:
    fx_module_key = fx.type
    if fx_module_key not in schema.FX_PARAMS:
        raise ValueError(f"unknown FX type {fx.type!r}; expected one of {sorted(schema.FX_PARAMS)}")
    fx_schema = schema.FX_PARAMS[fx_module_key]
    plain_params: dict[str, Any] = {"kParamWet": fx.wet}
    plain_params.update(fx.params)
    validate_params(fx_module_key, plain_params, fx_schema)

    type_id = next(i for i, name in schema.FX_TYPE_IDS.items() if name == fx_module_key)
    return {
        "type": type_id,
        "kUIParamMixOrGain": 0.0,
        fx_module_key: {"plainParams": plain_params},
    }


def apply_spec(base_data: dict[str, Any], spec: PresetSpec) -> dict[str, Any]:
    """Return a new raw ``data`` dict with ``spec`` merged onto ``base_data``."""
    data = copy.deepcopy(base_data)

    # Oscillator's own plainParams live directly on the Oscillator{i} dict,
    # not nested -- handled separately from the generic _plain_params helper
    # (which is for the sub-modules keyed *inside* Oscillator{i}, e.g. WTOsc{i}).
    for i, osc in enumerate(spec.oscillators):
        osc_container = data.setdefault(f"Oscillator{i}", {})
        if not isinstance(osc_container.get("plainParams"), dict):
            osc_container["plainParams"] = {}
        osc_params = osc_container["plainParams"]
        osc_params["kParamEnable"] = osc.enabled
        for spec_key, param_key in _OSC_KEYS.items():
            osc_params[param_key] = getattr(osc, spec_key)
        validate_params(f"Oscillator{i}", osc_params, schema.OSCILLATOR_PARAMS)

        wtosc_params = _plain_params(osc_container, f"WTOsc{i}")
        for spec_key, param_key in _WTOSC_KEYS.items():
            wtosc_params[param_key] = getattr(osc, spec_key)
        validate_params(f"WTOsc{i}", wtosc_params, schema.WTOSC_PARAMS)

    for i, flt in enumerate(spec.filters):
        filter_params = _plain_params(data, f"VoiceFilter{i}")
        filter_params["kParamEnable"] = flt.enabled
        filter_params["kParamType"] = schema.SIMPLE_FILTER_TYPES.get(flt.type, flt.type)
        for spec_key, param_key in _FILTER_KEYS.items():
            filter_params[param_key] = getattr(flt, spec_key)
        validate_params(f"VoiceFilter{i}", filter_params, schema.VOICE_FILTER_PARAMS)

    for i, env in enumerate(spec.envelopes):
        env_params = _plain_params(data, f"Env{i}")
        for spec_key, param_key in _ENV_KEYS.items():
            env_params[param_key] = getattr(env, spec_key)
        validate_params(f"Env{i}", env_params, schema.ENV_PARAMS)

    for i, lfo in enumerate(spec.lfos):
        lfo_params = _plain_params(data, f"LFO{i}")
        for spec_key, param_key in _LFO_KEYS.items():
            lfo_params[param_key] = getattr(lfo, spec_key)
        lfo_params["kParamMode"] = lfo.mode
        validate_params(f"LFO{i}", lfo_params, schema.LFO_PARAMS)

    for i, macro in enumerate(spec.macros):
        macro_container = data.setdefault(f"Macro{i}", {})
        if macro.name:
            macro_container["name"] = macro.name
        macro_params = _plain_params(data, f"Macro{i}")
        macro_params["kParamValue"] = macro.value
        validate_params(f"Macro{i}", macro_params, schema.MACRO_PARAMS)

    if spec.fx_chain:
        fx_rack = data.setdefault("FXRack0", {})
        fx_rack["FX"] = [_build_fx_entry(fx) for fx in spec.fx_chain]

    global_params = _plain_params(data, "Global0")
    global_params["kParamMasterVolume"] = spec.global_.master_volume
    global_params["kParamMonoToggle"] = spec.global_.mono
    validate_params("Global0", global_params, schema.GLOBAL_PARAMS)

    return data
