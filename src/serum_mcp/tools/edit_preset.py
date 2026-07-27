"""``edit_preset`` MCP tool implementation."""

from __future__ import annotations

from serum_mcp.generation.spec import PresetSpec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_file, unpack_file


def edit_preset(preset_path: str, spec: PresetSpec) -> str:
    """Apply a partial ``spec`` update to an existing preset, in place.

    Only the sections/indices present in ``spec`` are touched -- e.g. an
    edit that only sets ``filters=[...]`` leaves oscillators, envelopes,
    macros, FX and mod routes exactly as they were. ``spec.name`` /
    ``spec.description`` update the preset's metadata only if non-empty.

    Returns the absolute path of the edited file (same as ``preset_path``).
    """
    existing = unpack_file(preset_path)
    data = apply_spec(existing.data, spec)

    metadata = dict(existing.metadata)
    if spec.name:
        metadata["presetName"] = spec.name
    if spec.description:
        metadata["presetDescription"] = spec.description

    out_preset = SerumPreset(metadata=metadata, data=data)
    written = pack_file(out_preset, preset_path)
    return str(written)
