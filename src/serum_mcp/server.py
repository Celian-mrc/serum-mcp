"""MCP server entry point: exposes generate_preset, edit_preset,
list_parameters and describe_preset over stdio for Claude Code / Claude
Desktop / any MCP client.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from serum_mcp.tools.describe_preset import describe_preset as _describe_preset
from serum_mcp.tools.edit_preset import edit_preset as _edit_preset
from serum_mcp.tools.generate_preset import generate_preset as _generate_preset
from serum_mcp.tools.list_parameters import list_parameters as _list_parameters

mcp = FastMCP(
    name="serum-mcp",
    instructions=(
        "Generate, edit and save Xfer Serum 2 (.SerumPreset) files from natural "
        "language descriptions. Presets are written directly to the user's "
        "configured Serum presets folder (see SERUM_PRESETS_PATH) as valid "
        ".SerumPreset files -- no DAW, plugin host, or audio rendering is "
        "involved at any point."
    ),
)


@mcp.tool()
def generate_preset(description: str) -> str:
    """Generate a new Serum 2 preset from a natural-language description
    (e.g. "an aggressive Future Bass lead", "a dark evolving pad with chorus")
    and save it to the user's Serum presets folder.

    Returns the absolute path of the written .SerumPreset file.
    """
    return _generate_preset(description)


@mcp.tool()
def edit_preset(preset_path: str, instruction: str) -> str:
    """Apply a natural-language edit instruction (e.g. "make it warmer and
    less aggressive", "add a slow chorus") to an existing .SerumPreset file,
    in place.

    Returns the absolute path of the edited file (same as ``preset_path``).
    """
    return _edit_preset(preset_path, instruction)


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
    parameters (oscillators, filters, envelopes, FX chain, globals)."""
    return _describe_preset(preset_path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
