"""Tests for the MCP tool functions, with the LLM call mocked out (these
never hit the network / require an API key -- only :mod:`generation.llm_mapper`
does that, and it's exercised separately/manually).
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


def _fake_bass_spec(**overrides) -> PresetSpec:
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


def test_generate_preset_writes_valid_file(presets_dir, monkeypatch):
    monkeypatch.setattr(generate_preset_mod, "generate_spec", lambda description: _fake_bass_spec())

    path = generate_preset_mod.generate_preset("a simple bass with a low-pass filter")

    written = Path(path)
    assert written.exists()
    assert written.parent == presets_dir
    preset = unpack_file(written)
    assert preset.metadata["presetName"] == "BA - Simple LP Bass"
    assert preset.data["VoiceFilter0"]["plainParams"]["kParamType"] == "L24"


def test_edit_preset_updates_in_place(presets_dir, monkeypatch):
    monkeypatch.setattr(generate_preset_mod, "generate_spec", lambda description: _fake_bass_spec())
    path = generate_preset_mod.generate_preset("a simple bass")

    def fake_edit_spec(instruction, *, current_spec=None, client=None):
        updated = current_spec.model_copy(deep=True)
        updated.filters[0].cutoff = 0.9
        updated.name = "BA - Simple LP Bass (brighter)"
        return updated

    monkeypatch.setattr(edit_preset_mod, "generate_spec", fake_edit_spec)
    edited_path = edit_preset_mod.edit_preset(path, "make it brighter")

    assert edited_path == path
    preset = unpack_file(edited_path)
    assert preset.data["VoiceFilter0"]["plainParams"]["kParamFreq"] == 0.9
    assert preset.metadata["presetName"] == "BA - Simple LP Bass (brighter)"


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
    assert "kParamFreq" in parsed["voice_filter"]
