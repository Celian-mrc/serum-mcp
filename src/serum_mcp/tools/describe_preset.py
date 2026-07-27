"""``describe_preset`` MCP tool implementation."""

from __future__ import annotations

from serum_mcp.preset.introspect import extract_spec
from serum_mcp.preset.packer import unpack_file

_OSC_LABELS = ("A", "B", "C", "Noise", "Sub")


def describe_preset(preset_path: str) -> str:
    """Return a human-readable summary of an existing preset's sound-shaping
    parameters, so a user can understand what was generated/edited without
    opening Serum."""
    preset = unpack_file(preset_path)
    spec = extract_spec(preset.data)

    lines = [f"Preset: {preset.metadata.get('presetName') or '(unnamed)'}"]
    if preset.metadata.get("presetDescription"):
        lines.append(f"Description: {preset.metadata['presetDescription']}")
    lines.append(f"Author: {preset.metadata.get('presetAuthor', '?')}")
    lines.append("")

    for label, osc in zip(_OSC_LABELS, spec.oscillators, strict=True):
        state = "ON " if osc.enabled else "off"
        lines.append(
            f"Osc {label}: {state}  octave={osc.octave:+.0f}  volume={osc.volume:.2f}  "
            f"pan={osc.pan:+.0f}  table_pos={osc.table_position:.1f}"
        )

    lines.append("")
    for i, flt in enumerate(spec.filters, start=1):
        state = "ON " if flt.enabled else "off"
        lines.append(
            f"Filter {i}: {state}  type={flt.type}  cutoff={flt.cutoff:.2f}  "
            f"resonance={flt.resonance:.0f}%  drive={flt.drive:.0f}%"
        )

    lines.append("")
    for i, env in enumerate(spec.envelopes, start=1):
        lines.append(
            f"Env {i}: attack={env.attack * 1000:.1f}ms  decay={env.decay:.2f}s  "
            f"sustain={env.sustain:.2f}  release={env.release:.2f}s"
        )

    lines.append("")
    if spec.fx_chain:
        lines.append("FX chain:")
        for fx in spec.fx_chain:
            lines.append(f"  - {fx.type} (wet={fx.wet:.0f}%)")
    else:
        lines.append("FX chain: (empty)")

    lines.append("")
    if spec.mod_routes:
        lines.append("Mod matrix (recognized routes only):")
        for route in spec.mod_routes:
            bip = ", bipolar" if route.bipolar else ""
            lines.append(f"  - {route.source} -> {route.destination}: {route.amount:+.0f}%{bip}")
    else:
        lines.append("Mod matrix: (no recognized routes)")

    lines.append("")
    lines.append(
        f"Global: master_volume={spec.global_.master_volume:.2f}  "
        f"mono={'on' if spec.global_.mono else 'off'}"
    )

    return "\n".join(lines)
