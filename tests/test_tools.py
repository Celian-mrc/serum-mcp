"""Tests for the MCP tool functions. There's no LLM call anywhere in this
package to mock out -- generate_preset/edit_preset take a structured
PresetSpec directly (built by the calling model, e.g. Claude Code itself),
so these tests just exercise the deterministic validate/merge/pack path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from serum_mcp import config
from serum_mcp.generation.spec import EnvelopeSpec, FilterSpec, OscillatorSpec, PresetSpec
from serum_mcp.preset.packer import unpack_file
from serum_mcp.tools import describe_preset as describe_preset_mod
from serum_mcp.tools import edit_preset as edit_preset_mod
from serum_mcp.tools import generate_preset as generate_preset_mod
from serum_mcp.tools.list_parameters import list_parameters


def _bass_spec(**overrides) -> PresetSpec:
    defaults = dict(
        name="BA - Simple LP Bass",
        description="Simple bass with a warm low-pass filtered oscillator.",
        oscillators=[OscillatorSpec(enabled=True, octave=-1, volume=0.8)],
        filters=[FilterSpec(enabled=True, type="lowpass_24", cutoff=0.35, resonance=15)],
        envelopes=[EnvelopeSpec(attack=0.001, decay=0.3, sustain=0.6, release=0.2)],
    )
    defaults.update(overrides)
    return PresetSpec(**defaults)


@pytest.fixture
def presets_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, str(tmp_path))
    return tmp_path


def test_generate_preset_writes_valid_file(presets_dir):
    path = generate_preset_mod.generate_preset(_bass_spec())

    written = Path(path)
    assert written.exists()
    assert written.parent == presets_dir
    preset = unpack_file(written)
    assert preset.metadata["presetName"] == "BA - Simple LP Bass"
    assert preset.data["VoiceFilter0"]["plainParams"]["kParamType"] == "L24"


def test_edit_preset_updates_in_place(presets_dir):
    path = generate_preset_mod.generate_preset(_bass_spec())

    # A partial spec: only the filter changes, everything else is left alone.
    edit_spec = PresetSpec(
        name="BA - Simple LP Bass (brighter)",
        description="",
        filters=[FilterSpec(enabled=True, type="lowpass_24", cutoff=0.9, resonance=15)],
    )
    edited_path = edit_preset_mod.edit_preset(path, edit_spec)

    assert edited_path == path
    preset = unpack_file(edited_path)
    assert preset.data["VoiceFilter0"]["plainParams"]["kParamFreq"] == 0.9
    assert preset.metadata["presetName"] == "BA - Simple LP Bass (brighter)"
    # Untouched by the edit spec (empty oscillators list):
    assert preset.data["Oscillator0"]["plainParams"]["kParamOctave"] == -1.0


def test_describe_preset_mentions_key_sections():
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    summary = describe_preset_mod.describe_preset(str(fixtures_dir / "init_preset.SerumPreset"))
    assert "Osc A" in summary
    assert "Filter 1" in summary
    assert "Env 1" in summary


def test_list_parameters_is_valid_json_with_expected_sections():
    import json

    parsed = json.loads(list_parameters())
    assert "oscillator" in parsed
    assert "voice_filter" in parsed
    assert "fx_params" in parsed
    assert "mod_source_ids" in parsed
    assert "mod_dest_targets" in parsed
    assert "kParamFreq" in parsed["voice_filter"]
