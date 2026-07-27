"""``edit_preset`` MCP tool implementation."""

from __future__ import annotations

from pathlib import Path

from serum_mcp.generation.spec import PresetSpec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_file, unpack_file

from ._naming import slugify_preset_name


def edit_preset(preset_path: str, spec: PresetSpec) -> str:
    """Apply a partial ``spec`` update to an existing preset, in place.

    Only the sections/indices present in ``spec`` are touched -- e.g. an
    edit that only sets ``filters=[...]`` leaves oscillators, envelopes,
    macros, FX and mod routes exactly as they were. ``spec.description``
    updates the preset's metadata only if non-empty.

    If ``spec.name`` differs from the preset's current name, the file is
    renamed to match (Serum's own preset browser displays the filename, not
    the internal ``presetName`` metadata -- confirmed against a live Serum
    2 install, editing metadata alone left the displayed name unchanged).
    The old file is removed once the renamed one is written successfully.

    Returns the absolute path of the edited file -- the new path if the
    preset was renamed, otherwise the same as ``preset_path``.
    """
    existing = unpack_file(preset_path)
    data = apply_spec(existing.data, spec)

    metadata = dict(existing.metadata)
    old_name = metadata.get("presetName", "")
    if spec.name:
        metadata["presetName"] = spec.name
    if spec.description:
        metadata["presetDescription"] = spec.description

    out_preset = SerumPreset(metadata=metadata, data=data)

    src_path = Path(preset_path)
    dest_path = src_path
    if spec.name and spec.name != old_name:
        dest_path = src_path.with_name(f"{slugify_preset_name(spec.name)}{src_path.suffix}")

    written = pack_file(out_preset, dest_path)
    if dest_path != src_path and src_path.exists():
        src_path.unlink()
    return str(written)
