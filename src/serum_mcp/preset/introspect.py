"""Read a raw CBOR payload back into a semantic
:class:`~serum_mcp.generation.spec.PresetSpec`.

The inverse of :func:`serum_mcp.preset.mapping.apply_spec`. Used to give the
LLM a compact, semantic view of an existing preset when editing it, and to
power ``describe_preset``. Missing/`"default"`-sentinel values fall back to
the confirmed defaults recorded in :mod:`.schema`.
"""

from __future__ import annotations

from typing import Any

from serum_mcp.generation.spec import (
    EnvelopeSpec,
    FilterSpec,
    FxUnitSpec,
    GlobalSpec,
    LfoSpec,
    MacroSpec,
    OscillatorSpec,
    PresetSpec,
)

from . import schema

_REVERSE_FILTER_TYPES = {v: k for k, v in schema.SIMPLE_FILTER_TYPES.items()}


def _resolve(plain_params: Any, key: str, param_defs: dict[str, schema.ParamDef]) -> Any:
    default = param_defs[key].default
    if not isinstance(plain_params, dict):
        return default
    return plain_params.get(key, default)


def _sub_plain_params(container: dict[str, Any], key: str) -> Any:
    sub = container.get(key)
    return sub.get("plainParams") if isinstance(sub, dict) else None


def extract_spec(data: dict[str, Any]) -> PresetSpec:
    """Best-effort reconstruction of a :class:`PresetSpec` from raw preset data."""
    oscillators = []
    for i in range(5):
        container = data.get(f"Oscillator{i}", {}) or {}
        pp = container.get("plainParams")
        wt_pp = _sub_plain_params(container, f"WTOsc{i}")
        # kParamEnable's default is slot-dependent: only Osc A (index 0)
        # defaults to on. schema.OSCILLATOR_PARAMS records the common case
        # (off); override for slot 0 explicitly rather than baking a
        # per-index default into the shared schema table.
        enabled = pp.get("kParamEnable") if isinstance(pp, dict) else None
        if enabled is None:
            enabled = i == 0
        oscillators.append(
            OscillatorSpec(
                enabled=bool(enabled),
                octave=_resolve(pp, "kParamOctave", schema.OSCILLATOR_PARAMS),
                volume=_resolve(pp, "kParamVolume", schema.OSCILLATOR_PARAMS),
                pan=_resolve(pp, "kParamPan", schema.OSCILLATOR_PARAMS),
                table_position=_resolve(wt_pp, "kParamTablePos", schema.WTOSC_PARAMS),
                warp_amount=_resolve(wt_pp, "kParamWarp", schema.WTOSC_PARAMS),
            )
        )

    filters = []
    for i in range(2):
        pp = (data.get(f"VoiceFilter{i}", {}) or {}).get("plainParams")
        raw_type = _resolve(pp, "kParamType", schema.VOICE_FILTER_PARAMS)
        filters.append(
            FilterSpec(
                enabled=bool(_resolve(pp, "kParamEnable", schema.VOICE_FILTER_PARAMS)),
                type=_REVERSE_FILTER_TYPES.get(raw_type, raw_type),
                cutoff=_resolve(pp, "kParamFreq", schema.VOICE_FILTER_PARAMS),
                resonance=_resolve(pp, "kParamReso", schema.VOICE_FILTER_PARAMS),
                drive=_resolve(pp, "kParamDrive", schema.VOICE_FILTER_PARAMS),
            )
        )

    envelopes = []
    for i in range(4):
        pp = (data.get(f"Env{i}", {}) or {}).get("plainParams")
        envelopes.append(
            EnvelopeSpec(
                attack=_resolve(pp, "kParamAttack", schema.ENV_PARAMS),
                decay=_resolve(pp, "kParamDecay", schema.ENV_PARAMS),
                sustain=_resolve(pp, "kParamSustain", schema.ENV_PARAMS),
                release=_resolve(pp, "kParamRelease", schema.ENV_PARAMS),
            )
        )

    lfos = []
    for i in range(10):
        pp = (data.get(f"LFO{i}", {}) or {}).get("plainParams")
        lfos.append(
            LfoSpec(
                rate=_resolve(pp, "kParamRate", schema.LFO_PARAMS),
                mode=_resolve(pp, "kParamMode", schema.LFO_PARAMS),
            )
        )

    macros = []
    for i in range(8):
        container = data.get(f"Macro{i}", {}) or {}
        pp = container.get("plainParams")
        macros.append(
            MacroSpec(
                name=container.get("name", ""),
                value=_resolve(pp, "kParamValue", schema.MACRO_PARAMS),
            )
        )

    fx_chain = []
    for entry in (data.get("FXRack0", {}) or {}).get("FX", []) or []:
        type_id = entry.get("type")
        fx_name = schema.FX_TYPE_IDS.get(type_id)
        if fx_name is None or fx_name not in entry:
            continue
        pp = entry[fx_name].get("plainParams", {}) or {}
        wet_default = schema.FX_PARAMS[fx_name].get("kParamWet")
        wet = pp.get("kParamWet", wet_default.default if wet_default else 100.0)
        params = {k: v for k, v in pp.items() if k != "kParamWet"}
        fx_chain.append(FxUnitSpec(type=fx_name, wet=wet, params=params))

    global_pp = (data.get("Global0", {}) or {}).get("plainParams")
    global_spec = GlobalSpec(
        master_volume=_resolve(global_pp, "kParamMasterVolume", schema.GLOBAL_PARAMS),
        mono=bool(_resolve(global_pp, "kParamMonoToggle", schema.GLOBAL_PARAMS)),
    )

    return PresetSpec(
        name="",
        description="",
        oscillators=oscillators,
        filters=filters,
        envelopes=envelopes,
        lfos=lfos,
        macros=macros,
        fx_chain=fx_chain,
        **{"global": global_spec},
    )
