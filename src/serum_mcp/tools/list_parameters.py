"""``list_parameters`` MCP tool implementation."""

from __future__ import annotations

import json
from dataclasses import asdict

from serum_mcp.preset import schema


def _dump(defs: dict[str, schema.ParamDef]) -> dict[str, dict]:
    return {key: asdict(param_def) for key, param_def in defs.items()}


def list_parameters() -> str:
    """Return the full documented Serum 2 parameter schema (modules, ranges,
    units, enum values, and confidence level) as JSON.

    Intended for a client to consult before proposing an edit, so it knows
    what parameter names and ranges are actually valid.
    """
    result = {
        "oscillator": _dump(schema.OSCILLATOR_PARAMS),
        "wavetable_oscillator": _dump(schema.WTOSC_PARAMS),
        "simple_warp_modes": schema.SIMPLE_WARP_MODES,
        "simple_wavetables": {
            name: wt.relative_path for name, wt in schema.SIMPLE_WAVETABLES.items()
        },
        "noise_oscillator": _dump(schema.NOISEOSC_PARAMS),
        "sub_oscillator": _dump(schema.SUBOSC_PARAMS),
        "simple_sub_shapes": schema.SIMPLE_SUB_SHAPES,
        "voice_filter": _dump(schema.VOICE_FILTER_PARAMS),
        "simple_filter_types": schema.SIMPLE_FILTER_TYPES,
        "envelope": _dump(schema.ENV_PARAMS),
        "lfo": _dump(schema.LFO_PARAMS),
        "macro": _dump(schema.MACRO_PARAMS),
        "global": _dump(schema.GLOBAL_PARAMS),
        "mod_matrix_slot": _dump(schema.MODSLOT_PARAMS),
        "mod_source_ids": schema.MOD_SOURCE_IDS,
        "mod_dest_targets": {
            name: {
                "dest_type": dest.dest_type,
                "dest_id": dest.dest_id,
                "param_name": dest.param_name,
            }
            for name, dest in schema.MOD_DEST_TARGETS.items()
        },
        "fx_type_ids": schema.FX_TYPE_IDS,
        "fx_params": {name: _dump(defs) for name, defs in schema.FX_PARAMS.items()},
    }
    return json.dumps(result, indent=2)
