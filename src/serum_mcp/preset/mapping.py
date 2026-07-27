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

from serum_mcp.generation.spec import FxUnitSpec, ModRouteSpec, PresetSpec

from . import schema
from .validator import validate_params

_OSC_KEYS = {
    "octave": "kParamOctave",
    "volume": "kParamVolume",
    "pan": "kParamPan",
    "unison": "kParamUnison",
    "detune": "kParamDetune",
}
_WTOSC_KEYS = {
    "table_position": "kParamTablePos",
    "warp_amount": "kParamWarp",
}
# Which slot indices use which sound-source engine. Slots 0-2 (Osc A/B/C)
# default to the wavetable engine; slot 3 is always Noise, slot 4 always
# Sub -- real Serum presets never have a WTOsc3/WTOsc4 key, only
# NoiseOsc3/SubOsc4, so table_position/warp_amount must not be written
# there (see docs/PARAMETER_SCHEMA.md).
_WTOSC_SLOTS = (0, 1, 2)
_NOISE_SLOT = 3
_SUB_SLOT = 4
_FILTER_KEYS = {
    "cutoff": "kParamFreq",
    "resonance": "kParamReso",
    "drive": "kParamDrive",
    "stereo": "kParamStereo",
}
_ENV_KEYS = {
    "attack": "kParamAttack",
    "hold": "kParamHold",
    "decay": "kParamDecay",
    "sustain": "kParamSustain",
    "release": "kParamRelease",
}
_LFO_KEYS = {
    "rate": "kParamRate",
    "beat_sync": "kParamBeatSync",
    "delay": "kParamDelay",
    "rise": "kParamRise",
    "smooth": "kParamSmooth",
}


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


def _build_modslot_entry(route: ModRouteSpec) -> dict[str, Any]:
    if route.source not in schema.MOD_SOURCE_IDS:
        raise ValueError(
            f"unknown mod source {route.source!r}; expected one of {sorted(schema.MOD_SOURCE_IDS)}"
        )
    if route.destination not in schema.MOD_DEST_TARGETS:
        raise ValueError(
            f"unknown mod destination {route.destination!r}; "
            f"expected one of {sorted(schema.MOD_DEST_TARGETS)}"
        )
    dest = schema.MOD_DEST_TARGETS[route.destination]
    plain_params: dict[str, Any] = {"kParamAmount": route.amount}
    if route.bipolar:
        plain_params["kParamBipolar"] = True
    validate_params("ModSlot", plain_params, schema.MODSLOT_PARAMS)

    return {
        "source": [schema.MOD_SOURCE_IDS[route.source], 0],
        "destModuleID": dest.dest_id,
        "destModuleParamID": dest.param_id,
        "destModuleParamName": dest.param_name,
        "destModuleTypeString": dest.dest_type,
        "plainParams": plain_params,
    }


def _free_modslot_indices(data: dict[str, Any], count: int) -> list[int]:
    used = {
        int(k[len("ModSlot") :])
        for k in data
        if isinstance(k, str) and k.startswith("ModSlot") and k[len("ModSlot") :].isdigit()
    }
    free = [i for i in range(64) if i not in used]
    if len(free) < count:
        raise ValueError(
            f"not enough free mod matrix slots: need {count}, only {len(free)} of 64 free"
        )
    return free[:count]


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

        if i in _WTOSC_SLOTS:
            wtosc_params = _plain_params(osc_container, f"WTOsc{i}")
            for spec_key, param_key in _WTOSC_KEYS.items():
                wtosc_params[param_key] = getattr(osc, spec_key)
            wtosc_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                osc.warp_mode, osc.warp_mode
            )
            validate_params(f"WTOsc{i}", wtosc_params, schema.WTOSC_PARAMS)
        elif i == _NOISE_SLOT:
            noise_params = _plain_params(osc_container, f"NoiseOsc{i}")
            noise_params["kParamNoiseType"] = osc.noise_type
            validate_params(f"NoiseOsc{i}", noise_params, schema.NOISEOSC_PARAMS)
        elif i == _SUB_SLOT:
            sub_params = _plain_params(osc_container, f"SubOsc{i}")
            sub_params["kParamShape"] = schema.SIMPLE_SUB_SHAPES.get(osc.sub_shape, osc.sub_shape)
            validate_params(f"SubOsc{i}", sub_params, schema.SUBOSC_PARAMS)

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

    if spec.mod_routes:
        indices = _free_modslot_indices(data, len(spec.mod_routes))
        for idx, route in zip(indices, spec.mod_routes, strict=True):
            data[f"ModSlot{idx}"] = _build_modslot_entry(route)

    global_params = _plain_params(data, "Global0")
    global_params["kParamMasterVolume"] = spec.global_.master_volume
    global_params["kParamMonoToggle"] = spec.global_.mono
    global_params["kParamPortamentoTime"] = spec.global_.portamento_time
    global_params["kParamPolyCount"] = spec.global_.poly_count
    validate_params("Global0", global_params, schema.GLOBAL_PARAMS)

    return data
