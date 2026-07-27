"""MCP server entry point: exposes generate_preset, edit_preset,
list_parameters and describe_preset over stdio for Claude Code / Claude
Desktop / any MCP client.

Sound design happens in the calling model (you), not inside this server:
generate_preset/edit_preset take a structured PresetSpec, not a free-text
description. There is no LLM call anywhere in this package -- translating a
user's natural-language request into a PresetSpec is entirely your job,
guided by the docstrings below and list_parameters()/describe_preset().
This keeps the tool usable from any MCP client's existing model without a
separate, separately-billed API call.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from serum_mcp.generation.spec import PresetSpec
from serum_mcp.tools.describe_preset import describe_preset as _describe_preset
from serum_mcp.tools.edit_preset import edit_preset as _edit_preset
from serum_mcp.tools.generate_preset import generate_preset as _generate_preset
from serum_mcp.tools.list_parameters import list_parameters as _list_parameters

mcp = FastMCP(
    name="serum-mcp",
    instructions=(
        "Generate, edit and save Xfer Serum 2 (.SerumPreset) files. Presets "
        "are written directly to the user's configured Serum presets folder "
        "(see SERUM_PRESETS_PATH) as valid .SerumPreset files -- no DAW, "
        "plugin host, or audio rendering is involved at any point.\n\n"
        "You (the calling model) are responsible for sound design: turn the "
        "user's natural-language request into a PresetSpec yourself -- this "
        "server has no LLM of its own. Call list_parameters() first if "
        "you're unsure of a valid range or enum value. Guidelines:\n"
        "- Prefer Osc A (index 0) as the primary source unless the request "
        "clearly calls for layering ('fat', 'wide', 'detuned stack').\n"
        "- oscillators[] index 3 is always Noise (use noise_type, one of "
        "list_parameters()['noise_oscillator']['kParamNoiseType']['enum_values']) "
        "and index 4 is always Sub (use sub_shape, one of "
        "list_parameters()['simple_sub_shapes']); table_position/warp_amount only "
        "apply to indices 0-2. unison/detune (indices 0-2) thicken a single "
        "oscillator -- use for 'fat', 'wide', 'supersaw'-style requests.\n"
        "- filters[].type must be one of list_parameters()['simple_filter_types']; "
        "cutoff is 0.0 (closed)..1.0 (open), not Hz.\n"
        "- fx_chain[].type must be a name from list_parameters()['fx_type_ids']; "
        "fx_chain[].params keys are raw kParam* names valid for that type.\n"
        "- mod_routes[].source is 'lfo0'..'lfo9' or 'macro0'..'macro7' only "
        "(other sources aren't wired up yet); destination is a key from "
        "list_parameters()['mod_dest_targets'], e.g. 'filter0.cutoff'. Use "
        "for vibrato (LFO -> oscillator pitch, small amount) or movement "
        "(slow LFO -> filter cutoff).\n"
        "- Envelope times are seconds; macro/resonance/wet/drive are 0-100%."
    ),
)


@mcp.tool()
def generate_preset(spec: PresetSpec) -> str:
    """Write a new Serum 2 preset built from ``spec`` to the user's Serum
    presets folder.

    Build ``spec`` yourself from the user's natural-language description
    (see server instructions for the mapping guidelines). Any section left
    empty (e.g. no ``filters``) keeps that module at its default, inert
    state -- you don't need to fill in every field, only what the sound
    calls for.

    Returns the absolute path of the written .SerumPreset file.
    """
    return _generate_preset(spec)


@mcp.tool()
def edit_preset(preset_path: str, spec: PresetSpec) -> str:
    """Apply a partial ``spec`` update to an existing .SerumPreset file, in place.

    Call describe_preset(preset_path) first to see the current state, then
    only include the sections/indices in ``spec`` that should change --
    e.g. to just brighten the filter, pass ``filters=[FilterSpec(cutoff=0.8, ...)]``
    and leave everything else empty; it will be left untouched.

    Returns the absolute path of the edited file (same as ``preset_path``).
    """
    return _edit_preset(preset_path, spec)


@mcp.tool()
def list_parameters() -> str:
    """Return the full documented Serum 2 parameter schema (modules, value
    ranges, units, enum values, and how confidently each was verified) as
    JSON.

    Call this before proposing an edit so you know what parameter names and
    ranges are actually valid.
    """
    return _list_parameters()


@mcp.tool()
def describe_preset(preset_path: str) -> str:
    """Return a human-readable summary of an existing preset's sound-shaping
    parameters (oscillators, filters, envelopes, FX chain, mod routes, globals)."""
    return _describe_preset(preset_path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
