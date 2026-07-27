"""``edit_preset`` MCP tool implementation."""

from __future__ import annotations

from serum_mcp.generation.llm_mapper import generate_spec
from serum_mcp.preset.introspect import extract_spec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_file, unpack_file


def edit_preset(preset_path: str, instruction: str) -> str:
    """Apply a natural-language edit instruction to an existing preset, in place.

    Reads the current state of ``preset_path``, asks the LLM to produce an
    updated target spec given ``instruction``, merges it back onto the
    existing raw data (leaving anything not mentioned untouched) and
    overwrites the file. Returns the path.
    """
    existing = unpack_file(preset_path)
    current_spec = extract_spec(existing.data)
    current_spec.name = existing.metadata.get("presetName", "")
    current_spec.description = existing.metadata.get("presetDescription", "")

    new_spec = generate_spec(instruction, current_spec=current_spec)
    data = apply_spec(existing.data, new_spec)

    metadata = dict(existing.metadata)
    if new_spec.name:
        metadata["presetName"] = new_spec.name
    if new_spec.description:
        metadata["presetDescription"] = new_spec.description

    out_preset = SerumPreset(metadata=metadata, data=data)
    written = pack_file(out_preset, preset_path)
    return str(written)
