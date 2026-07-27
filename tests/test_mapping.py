from __future__ import annotations

from pathlib import Path

import pytest

from serum_mcp.generation.spec import (
    EnvelopeSpec,
    FilterSpec,
    FxUnitSpec,
    OscillatorSpec,
    PresetSpec,
)
from serum_mcp.preset.introspect import extract_spec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_bytes, unpack_bytes, unpack_file
from serum_mcp.preset.validator import ParamValidationError

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def init_data():
    return unpack_file(FIXTURES_DIR / "init_preset.SerumPreset").data


def test_simple_bass_end_to_end(init_data):
    spec = PresetSpec(
        name="BA - Test Bass",
        description="Simple low-pass filtered bass for testing.",
        oscillators=[OscillatorSpec(enabled=True, octave=-1, volume=0.8)],
        filters=[FilterSpec(enabled=True, type="lowpass_24", cutoff=0.35, resonance=15)],
        envelopes=[EnvelopeSpec(attack=0.001, decay=0.3, sustain=0.6, release=0.2)],
    )

    data = apply_spec(init_data, spec)

    assert data["Oscillator0"]["plainParams"]["kParamEnable"] is True
    assert data["Oscillator0"]["plainParams"]["kParamOctave"] == -1.0
    assert data["VoiceFilter0"]["plainParams"]["kParamType"] == "L24"
    assert data["VoiceFilter0"]["plainParams"]["kParamFreq"] == 0.35
    assert data["Env0"]["plainParams"]["kParamSustain"] == 0.6

    # The result must still be a valid, round-trippable Serum container.
    packed = SerumPreset(metadata={"presetName": spec.name}, data=data)
    again = unpack_bytes(pack_bytes(packed))
    assert again.data == data


def test_untouched_oscillators_are_left_alone(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True)],  # only Osc A
    )
    data = apply_spec(init_data, spec)
    # Osc B (Oscillator1) must be byte-for-byte identical to the base fixture.
    assert data["Oscillator1"] == init_data["Oscillator1"]


def test_fx_chain_round_trips_through_introspection(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXReverb", wet=40.0, params={"kParamSize": 60.0})],
    )
    data = apply_spec(init_data, spec)
    fx_entry = data["FXRack0"]["FX"][0]
    assert fx_entry["type"] == 6  # FXReverb id
    assert fx_entry["FXReverb"]["plainParams"]["kParamWet"] == 40.0

    extracted = extract_spec(data)
    assert extracted.fx_chain[0].type == "FXReverb"
    assert extracted.fx_chain[0].wet == 40.0
    assert extracted.fx_chain[0].params["kParamSize"] == 60.0


def test_invalid_fx_param_rejected(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXReverb", params={"kParamWet": 500.0})],
    )
    with pytest.raises(ParamValidationError):
        apply_spec(init_data, spec)


def test_extract_spec_matches_known_defaults(init_data):
    spec = extract_spec(init_data)
    assert spec.oscillators[0].enabled is True
    assert spec.oscillators[1].enabled is False
    assert spec.filters[0].enabled is False
    assert spec.envelopes[0].sustain == 1.0
