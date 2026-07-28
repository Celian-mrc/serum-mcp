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

    for i, (label, osc) in enumerate(zip(_OSC_LABELS, spec.oscillators, strict=True)):
        state = "ON " if osc.enabled else "off"
        common = f"octave={osc.octave:+.0f}  volume={osc.volume:.2f}  pan={osc.pan:+.0f}"
        if i in (0, 1, 2):
            if osc.sample_playback_source:
                loop = (
                    f"  loop={osc.sample_loop}"
                    f"({osc.sample_loop_start:.0f}-{osc.sample_loop_end:.0f}%)"
                    if osc.sample_loop != "off"
                    else "  loop=off (one-shot)"
                )
                extra = (
                    f"sample={osc.sample_playback_source}  "
                    f"warp={osc.warp_mode}({osc.warp_amount:.2f}){loop}"
                )
            else:
                extra = (
                    f"wavetable={osc.wavetable}  table_pos={osc.table_position:.1f}  "
                    f"warp={osc.warp_mode}({osc.warp_amount:.2f})"
                )
            if osc.unison > 1:
                extra += f"  unison={osc.unison:.0f}  detune={osc.detune:.2f}"
        elif i == 3:
            extra = f"noise_type={osc.noise_type}"
        else:
            extra = f"sub_shape={osc.sub_shape}"
        lines.append(f"Osc {label}: {state}  {common}  {extra}")

    lines.append("")
    for i, flt in enumerate(spec.filters, start=1):
        state = "ON " if flt.enabled else "off"
        stereo = f"  stereo={flt.stereo:.0f}%" if flt.stereo else ""
        lines.append(
            f"Filter {i}: {state}  type={flt.type}  cutoff={flt.cutoff:.2f}  "
            f"resonance={flt.resonance:.0f}%  drive={flt.drive:.0f}%{stereo}"
        )

    lines.append("")
    for i, env in enumerate(spec.envelopes, start=1):
        hold = f"  hold={env.hold * 1000:.1f}ms" if env.hold else ""
        lines.append(
            f"Env {i}: attack={env.attack * 1000:.1f}ms{hold}  decay={env.decay:.2f}s  "
            f"sustain={env.sustain:.2f}  release={env.release:.2f}s"
        )

    active_lfos = [
        (i, lfo) for i, lfo in enumerate(spec.lfos, start=1) if lfo.rate or lfo.mode != "Free"
    ]
    if active_lfos:
        lines.append("")
        for i, lfo in active_lfos:
            sync = "  beat_sync" if lfo.beat_sync else ""
            delay = f"  delay={lfo.delay:.2f}s" if lfo.delay else ""
            lines.append(f"LFO {i}: rate={lfo.rate:.0f}  mode={lfo.mode}{sync}{delay}")

    active_macros = [(i, m) for i, m in enumerate(spec.macros, start=1) if m.value or m.name]
    if active_macros:
        lines.append("")
        for i, macro in active_macros:
            name = f' "{macro.name}"' if macro.name else ""
            lines.append(f"Macro {i}{name}: {macro.value:.0f}%")

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
    porta = (
        f"  portamento={spec.global_.portamento_time:.2f}s" if spec.global_.portamento_time else ""
    )
    lines.append(
        f"Global: master_volume={spec.global_.master_volume:.2f}  "
        f"mono={'on' if spec.global_.mono else 'off'}  "
        f"poly={spec.global_.poly_count:.0f}{porta}"
    )

    return "\n".join(lines)
