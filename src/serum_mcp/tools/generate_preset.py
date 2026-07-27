"""``generate_preset`` MCP tool implementation."""

from __future__ import annotations

import re
from pathlib import Path

from serum_mcp import config
from serum_mcp.generation.llm_mapper import generate_spec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_file, unpack_file

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures"
INIT_PRESET_PATH = FIXTURES_DIR / "init_preset.SerumPreset"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 _\-]", "", name).strip()
    return slug or "Untitled"


def generate_preset(description: str) -> str:
    """Generate a new Serum 2 preset from a natural-language description and
    write it to the user's configured Serum presets folder.

    Returns the absolute path of the written ``.SerumPreset`` file.
    """
    spec = generate_spec(description)
    base = unpack_file(INIT_PRESET_PATH)
    data = apply_spec(base.data, spec)

    metadata = dict(base.metadata)
    metadata["presetName"] = spec.name
    metadata["presetDescription"] = spec.description
    metadata["presetAuthor"] = "serum-mcp"

    out_preset = SerumPreset(metadata=metadata, data=data)
    dest = config.get_presets_dir() / f"{_slugify(spec.name)}.SerumPreset"
    written = pack_file(out_preset, dest)
    return str(written)
