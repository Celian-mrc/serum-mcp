"""``generate_preset`` MCP tool implementation."""

from __future__ import annotations

from pathlib import Path

from serum_mcp import config
from serum_mcp.generation.spec import PresetSpec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_file, unpack_file

from ._naming import sanitize_subfolder, slugify_preset_name

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures"
INIT_PRESET_PATH = FIXTURES_DIR / "init_preset.SerumPreset"


def generate_preset(spec: PresetSpec, subfolder: str | None = None) -> str:
    """Write a new Serum 2 preset, built from ``spec``, to the user's
    configured Serum presets folder.

    ``spec`` is merged onto ``fixtures/init_preset.SerumPreset``, so any
    section left empty (e.g. no ``filters``) keeps that module's default,
    inert state.

    ``subfolder`` (optional) nests the file under a subfolder of the
    presets folder instead of writing it flat (e.g. ``"RAGE Bank"`` ->
    .../Presets/User/RAGE Bank/<name>.SerumPreset) -- useful for a themed
    set of presets generated together. Serum's own browser displays nested
    folders fine (its factory content is organized the same way); the
    folder is created if it doesn't exist yet. Each path segment is
    sanitized the same way preset names are (see
    ``_naming.sanitize_subfolder``), so it can't escape the presets folder.

    Returns the absolute path of the written ``.SerumPreset`` file.
    """
    base = unpack_file(INIT_PRESET_PATH)
    data = apply_spec(base.data, spec)

    metadata = dict(base.metadata)
    metadata["presetName"] = spec.name
    metadata["presetDescription"] = spec.description
    metadata["presetAuthor"] = "serum-mcp"

    out_preset = SerumPreset(metadata=metadata, data=data)
    dest_dir = config.get_presets_dir()
    if subfolder:
        safe_subfolder = sanitize_subfolder(subfolder)
        if safe_subfolder:
            dest_dir = dest_dir / safe_subfolder
    dest = dest_dir / f"{slugify_preset_name(spec.name)}.SerumPreset"
    written = pack_file(out_preset, dest)
    return str(written)
