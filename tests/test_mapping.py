from __future__ import annotations

from pathlib import Path

import pytest

from serum_mcp.generation.spec import (
    EnvelopeSpec,
    FilterSpec,
    FxUnitSpec,
    ModRouteSpec,
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

    # kParamEnable is stored as a CBOR float (1.0/0.0) in real Serum
    # presets, not a native CBOR bool -- writing a real bool crashes
    # Serum's loader (confirmed against a live FL Studio install).
    assert data["Oscillator0"]["plainParams"]["kParamEnable"] == 1.0
    assert type(data["Oscillator0"]["plainParams"]["kParamEnable"]) is float
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
    assert spec.mod_routes == []


def test_mod_route_round_trips_through_introspection(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=53.2, bipolar=True),
            ModRouteSpec(source="macro2", destination="oscillator0.pan", amount=-25.0),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["source"] == [6, 0]  # lfo0
    assert data["ModSlot0"]["destModuleTypeString"] == "VoiceFilter"
    assert data["ModSlot0"]["destModuleParamName"] == "kParamFreq"
    assert data["ModSlot0"]["destModuleParamID"] == 3
    assert data["ModSlot0"]["plainParams"]["kParamAmount"] == 53.2
    assert data["ModSlot0"]["plainParams"]["kParamBipolar"] == 1.0
    assert type(data["ModSlot0"]["plainParams"]["kParamBipolar"]) is float

    assert data["ModSlot1"]["source"] == [27, 0]  # macro2

    extracted = extract_spec(data)
    routes = {r.destination: r for r in extracted.mod_routes}
    assert routes["filter0.cutoff"].source == "lfo0"
    assert routes["filter0.cutoff"].amount == 53.2
    assert routes["oscillator0.pan"].source == "macro2"
    assert routes["oscillator0.pan"].amount == -25.0


def test_mod_routes_do_not_collide_with_existing_slots(init_data):
    init_data["ModSlot0"] = {
        "source": [99, 0],
        "destModuleID": 0,
        "destModuleParamID": 1,
        "destModuleParamName": "kParamVolume",
        "destModuleTypeString": "Oscillator",
        "plainParams": {"kParamAmount": 10.0},
    }
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[ModRouteSpec(source="lfo1", destination="filter0.cutoff", amount=10.0)],
    )
    data = apply_spec(init_data, spec)
    assert data["ModSlot0"]["source"] == [99, 0]  # untouched
    assert data["ModSlot1"]["source"] == [7, 0]  # lfo1, placed in the next free slot


def test_unknown_mod_source_rejected(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[ModRouteSpec(source="env0", destination="filter0.cutoff", amount=10.0)],
    )
    with pytest.raises(ValueError, match="unknown mod source"):
        apply_spec(init_data, spec)
