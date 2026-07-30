from __future__ import annotations

import copy
from pathlib import Path

import pytest

from serum_mcp import config
from serum_mcp.generation.spec import (
    ArpPatternNoteSpec,
    ArpSpec,
    EnvelopeSpec,
    FilterSpec,
    FxUnitSpec,
    GlobalSpec,
    LfoSpec,
    ModRouteSpec,
    OscillatorSpec,
    PresetSpec,
)
from serum_mcp.preset.introspect import count_unmodeled_fx_units, extract_spec
from serum_mcp.preset.mapping import apply_spec
from serum_mcp.preset.packer import SerumPreset, pack_bytes, unpack_bytes, unpack_file
from serum_mcp.preset.safety import scan_wire_types
from serum_mcp.preset.validator import ParamValidationError

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def init_data():
    return unpack_file(FIXTURES_DIR / "init_preset.SerumPreset").data


@pytest.fixture
def tables_dir(tmp_path, monkeypatch):
    """Redirect config.get_tables_dir() to a throwaway directory so tests
    that synthesize custom wavetables don't write into the user's real
    Serum Tables folder."""
    monkeypatch.setenv(config.TABLES_ENV_VAR, str(tmp_path))
    return tmp_path


@pytest.fixture
def samples_dir(tmp_path, monkeypatch):
    """Redirect config.get_samples_dir() to a throwaway directory so tests
    that copy one-shots for SampleOsc playback don't write into the user's
    real Serum Samples folder."""
    dest = tmp_path / "Samples"
    dest.mkdir()
    monkeypatch.setenv(config.SAMPLES_ENV_VAR, str(dest))
    return dest


def _write_wav_fixture(path: Path, *, num_samples: int = 4410, sample_rate: int = 44100) -> None:
    """Minimal real WAV file for sample_playback_source tests -- 16-bit PCM
    mono, small enough to keep tests fast."""
    import struct as _struct

    import numpy as _np

    t = _np.linspace(0, 1, num_samples, endpoint=False)
    tone = (0.5 * _np.sin(2 * _np.pi * 440 * t) * 32767).astype("<i2")
    data = tone.tobytes()
    fmt_chunk = _struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    body = bytearray()
    body += b"fmt " + _struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + _struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += _struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def _write_stereo_wav_fixture(
    path: Path,
    *,
    left_amp: float = 0.8,
    right_amp: float = 0.4,
    num_samples: int = 4410,
    sample_rate: int = 44100,
) -> None:
    """A stereo WAV fixture with a deliberate left/right level imbalance,
    for sample_center_pan tests."""
    import struct as _struct

    import numpy as _np

    t = _np.linspace(0, 1, num_samples, endpoint=False)
    left = (left_amp * _np.sin(2 * _np.pi * 440 * t) * 32767).astype("<i2")
    right = (right_amp * _np.sin(2 * _np.pi * 440 * t) * 32767).astype("<i2")
    interleaved = _np.empty(num_samples * 2, dtype="<i2")
    interleaved[0::2] = left
    interleaved[1::2] = right
    data = interleaved.tobytes()
    fmt_chunk = _struct.pack("<HHIIHH", 1, 2, sample_rate, sample_rate * 4, 4, 16)
    body = bytearray()
    body += b"fmt " + _struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + _struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += _struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


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


@pytest.mark.parametrize(
    ("fx_type", "extra_params"),
    [
        ("FXBode", {"kParamShift": 20.0, "kParamRange": 500.0}),
        ("FXHyperD", {"kParamUnison": 4.0, "kParamDetune": 30.0}),
        ("FXConv", {"kParamSize": 200.0}),
        ("FXUtils", {"kParamWidth": 150.0}),
    ],
)
def test_previously_uncovered_fx_types(init_data, fx_type, extra_params):
    spec = PresetSpec(
        name="X", description="", fx_chain=[FxUnitSpec(type=fx_type, params=extra_params)]
    )
    data = apply_spec(init_data, spec)
    entry = data["FXRack0"]["FX"][0]
    for key, value in extra_params.items():
        assert entry[fx_type]["plainParams"][key] == value


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
            ModRouteSpec(source="velocity", destination="env0.decay", amount=30.0),
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
    assert data["ModSlot2"]["source"] == [16, 0]  # velocity

    extracted = extract_spec(data)
    routes = {r.destination: r for r in extracted.mod_routes}
    assert routes["filter0.cutoff"].source == "lfo0"
    assert routes["filter0.cutoff"].amount == 53.2
    assert routes["oscillator0.pan"].source == "macro2"
    assert routes["oscillator0.pan"].amount == -25.0
    assert routes["env0.decay"].source == "velocity"
    assert routes["env0.decay"].amount == 30.0


def test_mod_route_2026_07_29_probe_sources_round_trip(init_data):
    """mod_wheel/pitch_bend/key_track/env0/random1/random2/random_discrete --
    all confirmed live 2026-07-29 via direct probing of a real Serum 2
    instance (see docs/PARAMETER_SCHEMA.md §6)."""
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="mod_wheel", destination="filter0.cutoff", amount=10.0),
            ModRouteSpec(source="pitch_bend", destination="filter0.cutoff", amount=11.0),
            ModRouteSpec(source="key_track", destination="filter0.cutoff", amount=12.0),
            ModRouteSpec(source="env0", destination="filter0.cutoff", amount=13.0),
            ModRouteSpec(source="random1", destination="filter0.cutoff", amount=14.0),
            ModRouteSpec(source="random2", destination="filter0.cutoff", amount=15.0),
            ModRouteSpec(source="random_discrete", destination="filter0.cutoff", amount=16.0),
            ModRouteSpec(source="aftertouch", destination="filter0.cutoff", amount=17.0),
            ModRouteSpec(source="poly_aftertouch", destination="filter0.cutoff", amount=18.0),
            ModRouteSpec(source="env1", destination="filter0.cutoff", amount=19.0),
            ModRouteSpec(source="env2", destination="filter0.cutoff", amount=20.0),
            ModRouteSpec(source="env3", destination="filter0.cutoff", amount=21.0),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["source"] == [1, 0]  # mod_wheel
    assert data["ModSlot1"]["source"] == [33, 0]  # pitch_bend
    assert data["ModSlot2"]["source"] == [17, 0]  # key_track
    assert data["ModSlot3"]["source"] == [2, 0]  # env0
    assert data["ModSlot4"]["source"] == [21, 0]  # random1
    assert data["ModSlot5"]["source"] == [22, 0]  # random2
    assert data["ModSlot6"]["source"] == [59, 0]  # random_discrete
    assert data["ModSlot7"]["source"] == [18, 0]  # aftertouch
    assert data["ModSlot8"]["source"] == [19, 0]  # poly_aftertouch
    assert data["ModSlot9"]["source"] == [3, 0]  # env1
    assert data["ModSlot10"]["source"] == [4, 0]  # env2
    assert data["ModSlot11"]["source"] == [5, 0]  # env3

    extracted = extract_spec(data)
    sources = {r.amount: r.source for r in extracted.mod_routes}
    assert sources[10.0] == "mod_wheel"
    assert sources[11.0] == "pitch_bend"
    assert sources[12.0] == "key_track"
    assert sources[17.0] == "aftertouch"
    assert sources[18.0] == "poly_aftertouch"
    assert sources[19.0] == "env1"
    assert sources[20.0] == "env2"
    assert sources[21.0] == "env3"
    assert sources[13.0] == "env0"
    assert sources[14.0] == "random1"
    assert sources[15.0] == "random2"
    assert sources[16.0] == "random_discrete"


def test_mod_route_2026_07_29_note_family_probe_sources_round_trip(init_data):
    """release_velo/active_voices/voice_index/voice_mod1/voice_mod2 -- the 5
    remaining named "Note"-category sources this project had only ever seen
    in Serum's own source picker, confirmed live 2026-07-29 via the same
    direct-probe method (prompted by UN_PLACES_BA_Beyond using an
    unresolved source id, 38, on 3 of its real routes -- still not
    identified, NOT one of these 5, see docs/PARAMETER_SCHEMA.md §6)."""
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="release_velo", destination="filter0.cutoff", amount=22.0),
            ModRouteSpec(source="active_voices", destination="filter0.cutoff", amount=23.0),
            ModRouteSpec(source="voice_index", destination="filter0.cutoff", amount=24.0),
            ModRouteSpec(source="voice_mod1", destination="filter0.cutoff", amount=25.0),
            ModRouteSpec(source="voice_mod2", destination="filter0.cutoff", amount=26.0),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["source"] == [37, 0]  # release_velo
    assert data["ModSlot1"]["source"] == [55, 0]  # active_voices
    assert data["ModSlot2"]["source"] == [58, 0]  # voice_index
    assert data["ModSlot3"]["source"] == [56, 0]  # voice_mod1
    assert data["ModSlot4"]["source"] == [57, 0]  # voice_mod2

    extracted = extract_spec(data)
    sources = {r.amount: r.source for r in extracted.mod_routes}
    assert sources[22.0] == "release_velo"
    assert sources[23.0] == "active_voices"
    assert sources[24.0] == "voice_index"
    assert sources[25.0] == "voice_mod1"
    assert sources[26.0] == "voice_mod2"


def test_mod_route_fixed_source_round_trip(init_data):
    """'fixed' -- Serum's own MATRIX-tab name for source id 38, decoded in
    depth 2026-07-30 (see docs/PARAMETER_SCHEMA.md item 14). A constant
    modulation offset with no aux-macro pairing (subIndex=0) -- a full
    corpus survey found this is the overwhelmingly common real case (18/23,
    78%), matching what this write path always produces."""
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="fixed", destination="oscillator0.pitch", amount=-9.375),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["source"] == [38, 0]

    extracted = extract_spec(data)
    assert extracted.mod_routes[0].source == "fixed"
    assert extracted.mod_routes[0].amount == -9.375


def test_mod_route_aux_source_round_trip(init_data):
    """ModRouteSpec.aux_source/aux_inverted -- Serum's general 'Aux'/'Via'
    system, decoded 2026-07-30 via a 626-preset corpus survey (1276 real
    aux-paired routes across nearly every source family, not just 'fixed').
    source[1]/subIndex is a second, independent source id drawn from the
    exact same MOD_SOURCE_IDS space as the primary source."""
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(
                source="lfo0",
                destination="oscillator0.pitch",
                amount=51.0,
                bipolar=True,
                aux_source="mod_wheel",
            ),
            ModRouteSpec(
                source="env1",
                destination="filter0.cutoff",
                amount=64.0,
                aux_source="macro0",
                aux_inverted=True,
            ),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["source"] == [6, 1]  # lfo0 aux mod_wheel
    assert data["ModSlot1"]["source"] == [3, 25]  # env1 aux macro0
    assert data["ModSlot1"]["plainParams"]["kParamAuxInverted"] == 1.0

    extracted = extract_spec(data)
    routes_by_dest = {r.destination: r for r in extracted.mod_routes}
    assert routes_by_dest["oscillator0.pitch"].aux_source == "mod_wheel"
    assert routes_by_dest["oscillator0.pitch"].aux_inverted is False
    assert routes_by_dest["filter0.cutoff"].aux_source == "macro0"
    assert routes_by_dest["filter0.cutoff"].aux_inverted is True


def test_mod_route_no_aux_source_writes_zero_subindex(init_data):
    """aux_source=None (the default) must write subIndex=0, matching the
    'no aux' sentinel every ordinary (non-aux-paired) real route uses --
    no valid MOD_SOURCE_IDS value is 0, so this is unambiguous."""
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[ModRouteSpec(source="velocity", destination="filter0.cutoff", amount=30.0)],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["source"] == [16, 0]
    extracted = extract_spec(data)
    assert extracted.mod_routes[0].aux_source is None
    assert extracted.mod_routes[0].aux_inverted is False


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


def test_editing_a_mod_route_updates_it_in_place(init_data):
    """Regression test found live: editing an already-generated preset's
    route (same source+destination, new amount) must overwrite the
    existing ModSlot, not accumulate a second, additive one in a different
    free slot."""
    spec1 = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=15.0, bipolar=True)
        ],
    )
    data = apply_spec(init_data, spec1)

    spec2 = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=4.0, bipolar=True)
        ],
    )
    data = apply_spec(data, spec2)

    mod_slots = [
        (k, v)
        for k, v in data.items()
        if isinstance(k, str) and k.startswith("ModSlot") and isinstance(v, dict)
    ]
    routes_to_filter_cutoff = [
        v
        for _, v in mod_slots
        if v.get("destModuleTypeString") == "VoiceFilter"
        and v.get("destModuleParamName") == "kParamFreq"
    ]
    assert len(routes_to_filter_cutoff) == 1
    assert routes_to_filter_cutoff[0]["plainParams"]["kParamAmount"] == 4.0


def test_editing_a_mod_route_in_place_preserves_unmodeled_exotic_fields(init_data):
    """Found live 2026-07-30 via a VST3 binary string dump of ModSlot's
    full private param list: real mod routes can carry fields this project
    doesn't model at all (kParamSmoothRise/Fall, kParamAuxCurve,
    kParamCurveIn, etc, 0.04-3.2% of real routes per corpus survey).
    _build_modslot_entry used to build each ModSlot's plainParams fresh
    from scratch, silently discarding any such fields whenever
    edit_preset touched that exact route (even just to nudge its amount) --
    fixed to merge onto the existing slot instead, matching how every
    other module's plainParams already round-trips unmodeled real keys."""
    data = copy.deepcopy(init_data)
    data["ModSlot0"] = {
        "source": [6, 0],
        "destModuleID": 0,
        "destModuleParamID": 3,
        "destModuleParamName": "kParamFreq",
        "destModuleTypeString": "VoiceFilter",
        "plainParams": {
            "kParamAmount": 15.0,
            "kParamSmoothRise": 42.0,
            "kParamCurveIn": -12.5,
        },
    }

    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=4.0)],
    )
    data = apply_spec(data, spec)

    fp = data["ModSlot0"]["plainParams"]
    assert fp["kParamAmount"] == 4.0
    assert fp["kParamSmoothRise"] == 42.0
    assert fp["kParamCurveIn"] == -12.5


def test_editing_one_route_does_not_disturb_a_different_existing_route(init_data):
    spec1 = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=15.0),
            ModRouteSpec(source="lfo1", destination="oscillator0.pan", amount=20.0),
        ],
    )
    data = apply_spec(init_data, spec1)

    spec2 = PresetSpec(
        name="X",
        description="",
        mod_routes=[ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=4.0)],
    )
    data = apply_spec(data, spec2)

    extracted = extract_spec(data)
    routes = {r.destination: r for r in extracted.mod_routes}
    assert routes["filter0.cutoff"].amount == 4.0
    assert routes["oscillator0.pan"].amount == 20.0  # untouched by the second edit


def test_unknown_mod_source_rejected(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[
            ModRouteSpec(source="release_velocity", destination="filter0.cutoff", amount=10.0)
        ],
    )
    with pytest.raises(ValueError, match="unknown mod source"):
        apply_spec(init_data, spec)


def test_unison_and_detune_are_applied(init_data):
    """Regression test: unison/detune were defined on OscillatorSpec but
    silently dropped by apply_spec (missing from _OSC_KEYS)."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, unison=6.0, detune=0.4)],
    )
    data = apply_spec(init_data, spec)
    params = data["Oscillator0"]["plainParams"]
    assert params["kParamUnison"] == 6.0
    assert type(params["kParamUnison"]) is float  # not a Python int -- see validator.py
    assert params["kParamDetune"] == 0.4


def test_noise_and_sub_slots_use_their_own_engine(init_data):
    """Regression test: slots 3 (Noise) and 4 (Sub) don't have a WTOsc
    sub-key in real Serum presets -- writing table_position/warp_amount
    there would inject a key Serum never produces."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(enabled=True),
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(enabled=True, noise_type="Pink"),
            OscillatorSpec(enabled=True, sub_shape="triangle"),
        ],
    )
    data = apply_spec(init_data, spec)

    assert "WTOsc3" not in data["Oscillator3"]
    assert data["Oscillator3"]["NoiseOsc3"]["plainParams"]["kParamNoiseType"] == "Pink"

    assert "WTOsc4" not in data["Oscillator4"]
    assert data["Oscillator4"]["SubOsc4"]["plainParams"]["kParamShape"] == "kTriangle"

    extracted = extract_spec(data)
    assert extracted.oscillators[3].noise_type == "Pink"
    assert extracted.oscillators[4].sub_shape == "triangle"


def test_no_int_leaks_into_any_plain_params(init_data):
    """Broader regression test for the whole class of bug behind the two
    tests above: every value written into a plainParams dict by apply_spec
    must be a float (or str/bool-as-float via validate_params), never a
    raw Python int -- Serum's CBOR parser needs doubles even for
    conceptually-integer fields."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(enabled=True, unison=6.0, octave=-2.0),
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(enabled=True, noise_type="White"),
            OscillatorSpec(enabled=True, sub_shape="saw"),
        ],
        filters=[FilterSpec(enabled=True, cutoff=0.5, resonance=20)],
        envelopes=[EnvelopeSpec(attack=0.1, decay=1, sustain=1, release=1)],
        fx_chain=[FxUnitSpec(type="FXDistortion", params={"kParamNumStages": 4})],
        mod_routes=[ModRouteSpec(source="lfo0", destination="filter0.cutoff", amount=10)],
    )
    data = apply_spec(init_data, spec)

    issues = scan_wire_types(data)
    assert not issues, "\n".join(str(i) for i in issues)


def test_warp_mode_and_wtosc_mod_destinations(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, warp_mode="sync", warp_amount=0.6)],
        mod_routes=[
            ModRouteSpec(
                source="lfo0", destination="oscillator0.table_position", amount=40.0, bipolar=True
            ),
            ModRouteSpec(source="macro0", destination="oscillator0.warp_amount", amount=20.0),
        ],
    )
    data = apply_spec(init_data, spec)

    wtosc_params = data["Oscillator0"]["WTOsc0"]["plainParams"]
    assert wtosc_params["kParamWarpMenu"] == "kSync"
    assert wtosc_params["kParamWarp"] == 0.6

    assert data["ModSlot0"]["destModuleTypeString"] == "WTOsc"
    assert data["ModSlot0"]["destModuleParamName"] == "kParamTablePos"
    assert data["ModSlot1"]["destModuleParamName"] == "kParamWarp"

    extracted = extract_spec(data)
    assert extracted.oscillators[0].warp_mode == "sync"
    routes = {r.destination: r for r in extracted.mod_routes}
    assert routes["oscillator0.table_position"].source == "lfo0"
    assert routes["oscillator0.warp_amount"].source == "macro0"


def test_second_warp_lane_round_trips(init_data):
    """warp_mode2/warp_amount2 -- a SECOND warp stage found live 2026-07-29:
    a real preset's primary oscillator used kFM_NOISE (primary) then
    kFilterLPF (secondary, taming it) -- missing this entirely made a
    recreation sound harsh/'8-bit' despite the primary warp matching. Unset
    (None) must not write kParamWarpMenu2 at all -- most oscillators only
    use one warp lane."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                warp_mode="kFM_NOISE",
                warp_amount=0.16,
                warp_mode2="filter_lpf",
                warp_amount2=0.56,
            ),
            OscillatorSpec(enabled=True),  # no second lane
        ],
    )
    data = apply_spec(init_data, spec)

    wt0 = data["Oscillator0"]["WTOsc0"]["plainParams"]
    assert wt0["kParamWarpMenu"] == "kFM_NOISE"
    assert wt0["kParamWarp"] == 0.16
    assert wt0["kParamWarpMenu2"] == "kFilterLPF"
    assert wt0["kParamWarp2"] == 0.56
    assert wt0["kParamXfadeMode"] == 1.0

    wt1 = data["Oscillator1"]["WTOsc1"]["plainParams"]
    assert "kParamWarpMenu2" not in wt1
    assert "kParamWarp2" not in wt1

    extracted = extract_spec(data)
    assert extracted.oscillators[0].warp_mode2 == "filter_lpf"
    assert extracted.oscillators[0].warp_amount2 == 0.56
    assert extracted.oscillators[1].warp_mode2 is None


def test_warp_var2_round_trips_and_is_a_mod_destination(init_data):
    """kParamWarpVar2 -- a THIRD, separate warp-related float, distinct
    from kParamWarp2. Found live 2026-07-29 as a real, previously-invisible
    mod-matrix destination (lfo -> oscillator0.warp_var2) on the same real
    preset's primary oscillator -- confirmed destModuleParamID=4."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(enabled=True, warp_var2=0.5),
            OscillatorSpec(enabled=True),  # no warp_var2 at all
        ],
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="oscillator0.warp_var2", amount=-28.0)
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["Oscillator0"]["WTOsc0"]["plainParams"]["kParamWarpVar2"] == 0.5
    assert "kParamWarpVar2" not in data["Oscillator1"]["WTOsc1"]["plainParams"]
    assert data["ModSlot0"]["destModuleTypeString"] == "WTOsc"
    assert data["ModSlot0"]["destModuleParamName"] == "kParamWarpVar2"
    assert data["ModSlot0"]["destModuleParamID"] == 4

    extracted = extract_spec(data)
    assert extracted.oscillators[0].warp_var2 == 0.5
    assert extracted.oscillators[1].warp_var2 is None
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["oscillator0.warp_var2"] == "lfo0"


def test_filter_stereo_env_hold_global_portamento(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(enabled=True, stereo=40.0)],
        envelopes=[EnvelopeSpec(attack=0.01, hold=0.2, decay=1, sustain=1, release=1)],
        **{"global": GlobalSpec(portamento_time=0.3)},
    )
    data = apply_spec(init_data, spec)

    assert data["VoiceFilter0"]["plainParams"]["kParamStereo"] == 40.0
    assert data["Env0"]["plainParams"]["kParamHold"] == 0.2
    assert data["Global0"]["plainParams"]["kParamPortamentoTime"] == 0.3

    extracted = extract_spec(data)
    assert extracted.filters[0].stereo == 40.0
    assert extracted.envelopes[0].hold == 0.2
    assert extracted.global_.portamento_time == 0.3


def test_filter_var_key_track_wet_level_out_round_trip(init_data):
    """kParamVar/kParamKeyTrack/kParamWet/kParamLevelOut -- documented in
    schema.py but never wired into FilterSpec until found live 2026-07-29:
    a real comb-filter preset (var=65, key_track=on) sounded harsh/aliased
    when recreated with these left at 0/off, since 'Var' is comb spacing
    for that filter type -- not a minor knob."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[
            FilterSpec(
                enabled=True,
                type="comb",
                var=65.0,
                key_track=True,
                wet=80.0,
                level_out=0.6,
            )
        ],
    )
    data = apply_spec(init_data, spec)

    fp = data["VoiceFilter0"]["plainParams"]
    assert fp["kParamVar"] == 65.0
    assert fp["kParamKeyTrack"] == 1.0
    assert type(fp["kParamKeyTrack"]) is float
    assert fp["kParamWet"] == 80.0
    assert fp["kParamLevelOut"] == 0.6

    extracted = extract_spec(data)
    assert extracted.filters[0].var == 65.0
    assert extracted.filters[0].key_track is True
    assert extracted.filters[0].wet == 80.0
    assert extracted.filters[0].level_out == 0.6


def test_filter_default_wet_omitted_not_written_explicitly(init_data):
    """Same absent-means-100 pattern as FX units (see
    test_extract_spec_treats_absent_fx_wet_as_100_regardless_of_type) --
    confirmed live 2026-07-29 against UN_PLACES_PL_Dreams's real
    VoiceFilter0/1, neither of which has a kParamWet key at all despite
    both being fully wet. Writing it explicitly at 100.0 was the likely
    remaining cause of a persistent fuzzy/buzzy character."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(type="comb", var=65.0)],
    )
    data = apply_spec(init_data, spec)

    fp = data["VoiceFilter0"]["plainParams"]
    assert "kParamWet" not in fp

    extracted = extract_spec(data)
    assert extracted.filters[0].wet == 100.0


def test_filter_default_level_out_omitted_not_written_explicitly(init_data):
    """Same presence-forces-the-DSP-stage pattern as kParamWet (see
    test_filter_default_wet_omitted_not_written_explicitly) -- found live
    2026-07-29 chasing a loudness (not tone) regression that survived the
    wet fix: UN_PLACES_PL_Dreams's real VoiceFilter0 has no kParamLevelOut
    key at all. Writing the schema default (0.5) explicitly measurably
    quieted that filter's output vs leaving it untouched."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(type="comb", var=65.0)],
    )
    data = apply_spec(init_data, spec)

    fp = data["VoiceFilter0"]["plainParams"]
    assert "kParamLevelOut" not in fp

    extracted = extract_spec(data)
    assert extracted.filters[0].level_out == 0.5


def test_filter_default_drive_and_stereo_omitted_not_written_explicitly(init_data):
    """Same presence-forces-the-DSP-stage pattern as kParamWet/kParamLevelOut
    (see the two tests above) -- found live 2026-07-29 continuing the same
    loudness-regression hunt: UN_PLACES_PL_Dreams's real VoiceFilter0/1 never
    have kParamDrive or kParamStereo at all. A real-corpus survey found
    kParamStereo absent in 1162/1300 (89%) real filters -- the strongest skew
    of any VoiceFilter param besides wet/level_out."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(type="comb", var=65.0)],
    )
    data = apply_spec(init_data, spec)

    fp = data["VoiceFilter0"]["plainParams"]
    assert "kParamDrive" not in fp
    assert "kParamStereo" not in fp

    extracted = extract_spec(data)
    assert extracted.filters[0].drive == 0.0
    assert extracted.filters[0].stereo == 50.0


def test_filter_default_resonance_and_var_omitted_not_written_explicitly(init_data):
    """Same presence-forces-the-DSP-stage pattern, found again 2026-07-29 on
    a SECOND real preset (UN_PLACES_BA_Beyond, generated one-shot to test
    whether the earlier Dreams fixes generalize): its real VoiceFilter1 has
    no kParamReso at all despite the extracted value matching the schema
    default (10.0) exactly. A real-corpus survey found kParamVar present in
    only 526/1302 (40%) real filters, and virtually never AT its own default
    (0.0) when present (2/526) -- unlike kParamFreq (cutoff), deliberately
    NOT included in this fix since it's present in 96% of real filters."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(type="comb", stereo=30.0)],
    )
    data = apply_spec(init_data, spec)

    fp = data["VoiceFilter0"]["plainParams"]
    assert "kParamReso" not in fp
    assert "kParamVar" not in fp
    assert "kParamFreq" in fp

    extracted = extract_spec(data)
    assert extracted.filters[0].resonance == 10.0
    assert extracted.filters[0].var == 0.0


def test_filter_output_routing_unset_writes_no_routing_slot(init_data):
    """FilterSpec.output_routing=None (the default) must not touch
    RoutingSlot5/6 at all -- Serum's real default (parallel) is reached by
    absence, not by explicitly writing kRoutingDestMaster, now that
    fixtures/init_preset.SerumPreset's own fixture bug (RoutingSlot5 stuck
    on the cascade/'series' value) is fixed."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(), FilterSpec()],
    )
    data = apply_spec(init_data, spec)

    assert data["RoutingSlot5"]["plainParams"] == "default"
    assert data["RoutingSlot6"]["plainParams"] == "default"

    extracted = extract_spec(data)
    assert extracted.filters[0].output_routing is None
    assert extracted.filters[1].output_routing is None


def test_filter_output_routing_series_and_parallel_round_trip(init_data):
    """RoutingSlot5/6 -- found live 2026-07-29 recreating two real presets
    that used opposite directions of this (Dreams: parallel; Beyond:
    series). filters[0]='series' cascades Filter 1 into Filter 2;
    filters[1]='parallel' keeps Filter 2 direct-to-output."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[
            FilterSpec(output_routing="series"),
            FilterSpec(output_routing="parallel"),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["RoutingSlot5"]["plainParams"] == {"kParamRoutingDest": "kRoutingDestFilter"}
    assert data["RoutingSlot6"]["plainParams"] == {"kParamRoutingDest": "kRoutingDestMaster"}

    extracted = extract_spec(data)
    assert extracted.filters[0].output_routing == "series"
    assert extracted.filters[1].output_routing == "parallel"


def test_filter_output_routing_both_series_rejected(init_data):
    """Both filters cascading into each other is a routing cycle Serum has
    no defined behavior for -- reject it outright rather than writing a
    silently broken preset."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[
            FilterSpec(output_routing="series"),
            FilterSpec(output_routing="series"),
        ],
    )
    with pytest.raises(ValueError, match="both.*'series'"):
        apply_spec(init_data, spec)


def test_oscillator_filter_routing_unset_writes_no_routing_slot(init_data):
    """OscillatorSpec.filter_routing/filter_balance=None (the default) must
    not touch RoutingSlot0-4 at all -- Serum's real default (through the
    filters) is reached by absence, matching the real Dreams/Beyond
    recreations' own RoutingSlot0 ('default')."""
    spec = PresetSpec(
        name="X", description="", oscillators=[OscillatorSpec(enabled=True)]
    )
    data = apply_spec(init_data, spec)

    assert data["RoutingSlot0"]["plainParams"] == "default"

    extracted = extract_spec(data)
    assert extracted.oscillators[0].filter_routing is None
    assert extracted.oscillators[0].filter_balance is None


def test_oscillator_filter_routing_and_balance_round_trip(init_data):
    """RoutingSlot0-4 -- this oscillator's own routing choice, distinct from
    RoutingSlot5/6 (each filter's own output routing). Mirrors a real
    RoutingSlot2 patch used recreating UN_PLACES_PL_Dreams
    (kParamRoutingDest='kRoutingDestFilter', kParamFilterBalance=100.0)."""
    oscillators = [OscillatorSpec(enabled=True) for _ in range(5)]
    oscillators[1].filter_routing = "master"
    oscillators[2].filter_routing = "filter"
    oscillators[2].filter_balance = 100.0
    spec = PresetSpec(name="X", description="", oscillators=oscillators)
    data = apply_spec(init_data, spec)

    assert data["RoutingSlot0"]["plainParams"] == "default"
    assert data["RoutingSlot1"]["plainParams"] == {"kParamRoutingDest": "kRoutingDestMaster"}
    assert data["RoutingSlot2"]["plainParams"] == {
        "kParamRoutingDest": "kRoutingDestFilter",
        "kParamFilterBalance": 100.0,
    }

    extracted = extract_spec(data)
    assert extracted.oscillators[0].filter_routing is None
    assert extracted.oscillators[1].filter_routing == "master"
    assert extracted.oscillators[2].filter_routing == "filter"
    assert extracted.oscillators[2].filter_balance == 100.0


def test_fx_bus_sends_unset_write_no_routing_slot(init_data):
    """oscillators[].fx_bus1_send/fx_bus2_send and filters[].fx_bus1_send/
    fx_bus2_send=None (the default) must not touch RoutingSlot0-4/5-6 at
    all -- a genuine aux send, independent of filter_routing/output_routing,
    that's absent unless explicitly requested."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True)],
        filters=[FilterSpec()],
    )
    data = apply_spec(init_data, spec)

    assert data["RoutingSlot0"]["plainParams"] == "default"
    assert data["RoutingSlot5"]["plainParams"] == "default"


def test_fx_bus_sends_round_trip_on_oscillator_and_filter(init_data):
    """kParamFXBus1Level/kParamFXBus2Level on RoutingSlot0-4 (oscillator aux
    send) and RoutingSlot5/6 (filter aux send) -- distinct from
    kParamRoutingDest's main destination, see GLOBAL_PARAMS['kParamFXBus1Vol']
    for the bus's own aggregate level."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, fx_bus1_send=25.0, fx_bus2_send=10.0)],
        filters=[FilterSpec(fx_bus1_send=50.0)],
    )
    data = apply_spec(init_data, spec)

    assert data["RoutingSlot0"]["plainParams"] == {
        "kParamFXBus1Level": 25.0,
        "kParamFXBus2Level": 10.0,
    }
    assert data["RoutingSlot5"]["plainParams"] == {"kParamFXBus1Level": 50.0}

    extracted = extract_spec(data)
    assert extracted.oscillators[0].fx_bus1_send == 25.0
    assert extracted.oscillators[0].fx_bus2_send == 10.0
    assert extracted.filters[0].fx_bus1_send == 50.0
    assert extracted.filters[0].fx_bus2_send is None


def test_global_fx_bus_volumes_and_direct_volume_round_trip(init_data):
    """GlobalSpec.fx_bus1_volume/fx_bus2_volume/direct_volume -- the
    aggregate-level counterparts to each RoutingSlot's own per-source aux
    send, found live 2026-07-30 via a VST3 binary string dump. Unset (the
    default) writes nothing, matching Serum's real absent-state default."""
    spec = PresetSpec(
        name="X",
        description="",
        **{
            "global": GlobalSpec(
                fx_bus1_volume=1.5, fx_bus2_volume=0.8, direct_volume=0.3
            )
        },
    )
    data = apply_spec(init_data, spec)

    global_pp = data["Global0"]["plainParams"]
    assert global_pp["kParamFXBus1Vol"] == 1.5
    assert global_pp["kParamFXBus2Vol"] == 0.8
    assert global_pp["kParamDirectVol"] == 0.3

    extracted = extract_spec(data)
    assert extracted.global_.fx_bus1_volume == 1.5
    assert extracted.global_.fx_bus2_volume == 0.8
    assert extracted.global_.direct_volume == 0.3


def test_global_fx_bus_destinations_round_trip(init_data):
    """GlobalSpec.fx_bus1_destination/fx_bus2_destination -- decoded
    2026-07-30 via a 626-preset corpus survey: kParamFXBus1Dest/2Dest only
    ever took values 1.0 or 2.0 in real content, the same meaning as
    RoutingSlot's kParamRoutingDest (Master/Direct) but stored as a raw
    float ordinal here, NOT the string enum RoutingSlot uses -- confirmed
    directly against real Factory CBOR. Unset (the default) writes nothing."""
    spec = PresetSpec(
        name="X",
        description="",
        **{
            "global": GlobalSpec(
                fx_bus1_destination="master", fx_bus2_destination="direct"
            )
        },
    )
    data = apply_spec(init_data, spec)

    global_pp = data["Global0"]["plainParams"]
    assert global_pp["kParamFXBus1Dest"] == 1.0
    assert global_pp["kParamFXBus2Dest"] == 2.0

    extracted = extract_spec(data)
    assert extracted.global_.fx_bus1_destination == "master"
    assert extracted.global_.fx_bus2_destination == "direct"


def test_lfo_default_rate_and_beat_sync_omitted_not_written_explicitly(init_data):
    """kParamRate=0.0 is a literal 0Hz freeze, not a neutral value -- found
    live 2026-07-29 (UN_PLACES_BA_Beyond): its real LFO0 has neither
    kParamRate nor kParamBeatSync at all, yet a user-provided screenshot
    (note held) showed it visibly moving in BPM-synced mode ("1/4"). The
    generated version, with both explicitly written at their LfoSpec
    defaults (rate=0.0, beat_sync=False), was frozen in free-Hz mode
    instead. Omitting both when at those defaults lets Serum fall back to
    its own real (beat-synced) default -- the exact Hz/BPM rate encoding
    remains undecoded (see LFO_PARAMS["kParamRate"]), sidestepped rather
    than guessed."""
    spec = PresetSpec(
        name="X",
        description="",
        lfos=[LfoSpec(smooth=1.5)],
    )
    data = apply_spec(init_data, spec)

    fp = data["LFO0"]["plainParams"]
    assert "kParamRate" not in fp
    assert "kParamBeatSync" not in fp
    assert fp["kParamSmooth"] == 1.5

    extracted = extract_spec(data)
    assert extracted.lfos[0].rate == 0.0
    assert extracted.lfos[0].beat_sync is False


def test_lfo_default_delay_rise_mono_swing_dotted_triplets_rate10x_omitted(init_data):
    """Same pattern, generalized to the rest of _LFO_KEYS -- found live
    2026-07-29 continuing the same investigation (the LFO still wasn't
    right after the rate/beat_sync fix alone): a real-corpus survey found
    every other _LFO_KEYS entry overwhelmingly absent when untouched too
    (kParamDelay 99%, kParamRise 96%, kParamMono 98%, kParamSwing 99%,
    kParamDotted/kParamTriplets/kParamRate10x 83-85%), so this project was
    still forcing 7 more DSP-stage computations at their own defaults."""
    spec = PresetSpec(
        name="X",
        description="",
        lfos=[LfoSpec(smooth=1.5)],
    )
    data = apply_spec(init_data, spec)

    fp = data["LFO0"]["plainParams"]
    for key in (
        "kParamDelay",
        "kParamRise",
        "kParamMono",
        "kParamSwing",
        "kParamDotted",
        "kParamTriplets",
        "kParamRate10x",
    ):
        assert key not in fp, key
    assert fp["kParamSmooth"] == 1.5
    assert fp["kParamMode"] == "Free"

    extracted = extract_spec(data)
    lfo = extracted.lfos[0]
    assert lfo.delay == 0.0
    assert lfo.rise == 0.0
    assert lfo.mono is False
    assert lfo.swing == 0.0
    assert lfo.dotted is False
    assert lfo.triplets is False
    assert lfo.rate10x is False


def test_sub_osc_default_shape_omitted_not_written_explicitly(init_data):
    """kParamShape (SubOsc4) -- found live 2026-07-30 isolating oscillators
    solo on UN_PLACES_BA_Beyond: the Sub layer had harsh/piercing highs not
    present in the real preset. Its real SubOsc4 has no kParamShape at all;
    a real-corpus survey found this key absent in ALL 896 real SubOsc4
    modules surveyed (0% presence -- the most extreme skew found this
    session), yet `serum-mcp` always wrote the schema default ('saw',
    harmonically bright) explicitly. Only an explicit non-default request
    (e.g. 'square') should still write the key."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(enabled=True, sub_shape="saw"),
        ],
    )
    data = apply_spec(init_data, spec)

    sp = data["Oscillator4"]["SubOsc4"]["plainParams"]
    assert "kParamShape" not in sp

    extracted = extract_spec(data)
    assert extracted.oscillators[4].sub_shape == "saw"

    spec2 = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(),
            OscillatorSpec(enabled=True, sub_shape="square"),
        ],
    )
    data2 = apply_spec(init_data, spec2)
    sp2 = data2["Oscillator4"]["SubOsc4"]["plainParams"]
    assert sp2["kParamShape"] == "kSquare"


def test_oscillator_default_octave_pitch_fine_volume_pan_unison_detune_omitted(init_data):
    """Same presence-forces-the-DSP-stage pattern, generalized to the rest
    of _OSC_KEYS -- found live 2026-07-30 continuing the same investigation
    (user noticed Osc A's LEVEL knob read 75%/-5dB on the real preset vs
    87%/-2.5dB on the recreation): Osc A's real kParamVolume is absent
    entirely, not just at this field's own schema default (0.75) -- writing
    it explicitly is NOT the audibly-transparent "same value" the raw
    number implies. A real-corpus survey found every other _OSC_KEYS entry
    similarly majority-absent when untouched (kParamOctave 66%, kParamPitch
    95%, kParamFine 90%, kParamPan 91%, kParamUnison 78%, kParamDetune
    72%)."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True)],
    )
    data = apply_spec(init_data, spec)

    op = data["Oscillator0"]["plainParams"]
    for key in (
        "kParamOctave",
        "kParamPitch",
        "kParamFine",
        "kParamVolume",
        "kParamPan",
        "kParamUnison",
        "kParamDetune",
    ):
        assert key not in op, key
    assert op["kParamEnable"] == 1.0

    extracted = extract_spec(data)
    osc = extracted.oscillators[0]
    assert osc.octave == 0.0
    assert osc.semitone == 0.0
    assert osc.fine == 0.0
    assert osc.volume == 0.75
    assert osc.pan == 0.0
    assert osc.unison == 1.0
    assert osc.detune == 0.0


def test_oscillator_semitone_round_trips(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, semitone=-7.0)],
    )
    data = apply_spec(init_data, spec)

    assert data["Oscillator0"]["plainParams"]["kParamPitch"] == -7.0

    extracted = extract_spec(data)
    assert extracted.oscillators[0].semitone == -7.0


def test_oscillator_fine_round_trips(init_data):
    """kParamFine -- cents-level micro-tuning, distinct from both octave and
    semitone. Found live 2026-07-29 comparing a recreation's Osc A/B
    byte-for-byte against a real preset: both used this (-3/+4 cents) and
    it had never been exposed as a settable base value, only as a mod
    destination."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, fine=-3.08)],
    )
    data = apply_spec(init_data, spec)

    assert data["Oscillator0"]["plainParams"]["kParamFine"] == -3.08

    extracted = extract_spec(data)
    assert extracted.oscillators[0].fine == -3.08


def test_envelope_curve_shapes_round_trip(init_data):
    """kParamCurve1/2/3 -- found live 2026-07-29, present on 97% of all
    real envelopes surveyed (3242/3333) -- effectively always set, not an
    optional/rare field."""
    spec = PresetSpec(
        name="X",
        description="",
        envelopes=[
            EnvelopeSpec(
                attack=0.01, decay=1, sustain=1, release=1,
                attack_curve=40.0, decay_curve=60.0, release_curve=58.1,
            )
        ],
    )
    data = apply_spec(init_data, spec)

    ep = data["Env0"]["plainParams"]
    assert ep["kParamCurve1"] == 40.0
    assert ep["kParamCurve2"] == 60.0
    assert ep["kParamCurve3"] == 58.1

    extracted = extract_spec(data)
    assert extracted.envelopes[0].attack_curve == 40.0
    assert extracted.envelopes[0].decay_curve == 60.0
    assert extracted.envelopes[0].release_curve == 58.1


def test_global_limit_same_note_polyphony_round_trips(init_data):
    """kParamLimitSameNotePolyphony -- found live 2026-07-29, present on
    39% of real Global0 slots surveyed (always True when present)."""
    spec = PresetSpec(
        name="X",
        description="",
        **{"global": GlobalSpec(limit_same_note_polyphony=True)},
    )
    data = apply_spec(init_data, spec)

    gp = data["Global0"]["plainParams"]
    assert gp["kParamLimitSameNotePolyphony"] == 1.0
    assert type(gp["kParamLimitSameNotePolyphony"]) is float

    extracted = extract_spec(data)
    assert extracted.global_.limit_same_note_polyphony is True


def test_extract_spec_skips_unmodeled_fx_routing_types_without_crashing(init_data):
    data = copy.deepcopy(init_data)
    data["FXRack0"] = {
        "FX": [
            {"FXEQ": {"plainParams": {"kParamWet": 100.0}}, "type": 7},
            # FXSplit has no kParamWet/param schema at all -- this used to
            # raise a raw KeyError from extract_spec (found live against a
            # real third-party bank where most presets use this).
            {"FXSplit": {"plainParams": {"kParamModuleCount2": 3.0}}, "type": 13},
            {"FXDelay": {"plainParams": {"kParamWet": 25.0}}, "type": 4},
        ]
    }

    spec = extract_spec(data)

    assert [fx.type for fx in spec.fx_chain] == ["FXEQ", "FXDelay"]
    assert count_unmodeled_fx_units(data) == 1


def test_extract_spec_treats_absent_fx_wet_as_100_regardless_of_type(init_data):
    """Found live 2026-07-29: kParamWet absent means fully wet (100.0) for
    every FX type -- a 100% consistent pattern, not per-type. extract_spec
    used to fall back to each FX_PARAMS type's own schema default (e.g.
    FXDelay's 30.0, only what's typically OBSERVED when present) instead,
    silently misreporting untouched wet knobs on round-trip."""
    data = copy.deepcopy(init_data)
    data["FXRack0"] = {
        "FX": [
            {"FXDelay": {"plainParams": {"kParamFeedback": 10.0}}, "type": 4},
        ]
    }

    spec = extract_spec(data)

    assert spec.fx_chain[0].type == "FXDelay"
    assert spec.fx_chain[0].wet == 100.0


def test_count_unmodeled_fx_units_zero_for_a_normal_preset(init_data):
    assert count_unmodeled_fx_units(init_data) == 0


def test_extract_spec_handles_modslot_with_default_sentinel_plainparams(init_data):
    data = copy.deepcopy(init_data)
    # Same "default" string sentinel pattern as VoiceFilter0/1 and the FX
    # crash above, found live on a real Factory preset's ModSlot -- must not
    # crash (it used to, with a raw AttributeError), and should fall back
    # to amount=0.0/bipolar=False rather than fabricating anything else.
    data["ModSlot0"] = {
        "source": [6, 0],  # lfo0
        "destModuleTypeString": "VoiceFilter",
        "destModuleID": 0,
        "destModuleParamName": "kParamFreq",
        "plainParams": "default",
    }

    spec = extract_spec(data)

    assert len(spec.mod_routes) == 1
    assert spec.mod_routes[0].source == "lfo0"
    assert spec.mod_routes[0].destination == "filter0.cutoff"
    assert spec.mod_routes[0].amount == 0.0
    assert spec.mod_routes[0].bipolar is False


def test_arp_writes_arp0_and_arpclip0(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        arp=ArpSpec(
            shape="chord",
            rate=0.3,
            gate=90.0,
            dotted=True,
            transpose_shift=12.0,
            transpose_shape="converge",
        ),
    )
    data = apply_spec(init_data, spec)

    assert data["Arp0"]["plainParams"]["kParamEnabled"] == 1.0
    clip = data["ArpClip0"]["plainParams"]
    assert clip["kParamShape"] == "Chord"
    assert clip["kParamRate"] == 0.3
    assert clip["kParamGate"] == 90.0
    assert clip["kParamDotted"] == 1.0
    assert "kParamTriplets" not in clip  # False -- omitted, matching real content
    assert clip["kParamTransposeShift"] == 12.0
    assert clip["kParamTransposeShape"] == "Converge"

    extracted = extract_spec(data)
    assert extracted.arp is not None
    assert extracted.arp.enabled is True
    assert extracted.arp.shape == "chord"
    assert extracted.arp.rate == 0.3
    assert extracted.arp.gate == 90.0
    assert extracted.arp.dotted is True
    assert extracted.arp.triplets is False
    assert extracted.arp.transpose_shift == 12.0
    assert extracted.arp.transpose_shape == "converge"


def test_arp_unset_leaves_existing_arp_untouched(init_data):
    """Same 'None means don't touch' contract as `global` -- an edit that
    doesn't mention arp at all must not silently disable/reset an arp the
    preset already had."""
    data = copy.deepcopy(init_data)
    data["Arp0"] = {"plainParams": {"kParamEnabled": 1.0}}
    data["ArpClip0"] = {"clip": {}, "plainParams": {"kParamShape": "Played", "kParamRate": 0.5}}

    spec = PresetSpec(name="X", description="", filters=[FilterSpec(enabled=True)])
    new_data = apply_spec(data, spec)

    assert new_data["Arp0"]["plainParams"]["kParamEnabled"] == 1.0
    assert new_data["ArpClip0"]["plainParams"]["kParamShape"] == "Played"


def test_arp_can_be_explicitly_disabled(init_data):
    data = copy.deepcopy(init_data)
    data["Arp0"] = {"plainParams": {"kParamEnabled": 1.0}}

    spec = PresetSpec(name="X", description="", arp=ArpSpec(enabled=False))
    new_data = apply_spec(data, spec)

    assert new_data["Arp0"]["plainParams"]["kParamEnabled"] == 0.0


def test_arp_pattern_shape_rejected_with_clear_error(init_data):
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="pattern"))
    with pytest.raises(ValueError, match="needs arp.pattern set"):
        apply_spec(init_data, spec)


def test_arp_raw_pattern_shape_also_rejected(init_data):
    """The raw capitalized 'Pattern' (as it'd appear round-tripped from a
    real preset via extract_spec) must be caught too, not just the
    friendly lowercase 'pattern' name."""
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="Pattern"))
    with pytest.raises(ValueError, match="needs arp.pattern set"):
        apply_spec(init_data, spec)


def test_arp_unknown_shape_rejected(init_data):
    """A shape that's neither a curated friendly name nor a raw value in
    the confirmed real enum is caught by validate_params's enum check."""
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="not_a_real_shape"))
    with pytest.raises(ValueError, match="is not one of"):
        apply_spec(init_data, spec)


def test_arp_uncurated_raw_shape_passes_through(init_data):
    """Found live stress-testing against real content: the confirmed real
    shape enum is larger than the curated SIMPLE_ARP_SHAPES set (e.g.
    'UpDown', the 2nd most common value across 844 real presets after
    Pattern) -- a round-tripped edit that includes an oscillator's raw,
    uncurated-but-valid shape must not fail the way a genuinely unknown
    string does."""
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="UpDown"))
    data = apply_spec(init_data, spec)
    assert data["ArpClip0"]["plainParams"]["kParamShape"] == "UpDown"


def test_arp_passes_wire_type_scan(init_data):
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="random_drift", dotted=True))
    data = apply_spec(init_data, spec)
    assert scan_wire_types(data) == []


def test_arp_pattern_writes_real_note_list(init_data):
    notes = [
        ArpPatternNoteSpec(step=0, note_offset=0),
        ArpPatternNoteSpec(step=1, note_offset=3),
        ArpPatternNoteSpec(step=2, note_offset=7),
        ArpPatternNoteSpec(step=3, note_offset=0, length_steps=2.0),
    ]
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="pattern", pattern=notes))
    data = apply_spec(init_data, spec)

    assert data["ArpClip0"]["plainParams"]["kParamShape"] == "Pattern"
    clip_notes = data["ArpClip0"]["clip"]["notes"]
    assert len(clip_notes) == 4
    by_offset = {n["noteNum"]: n for n in clip_notes}
    assert by_offset[0]["timeStamp"] in (0.0, 0.75)  # two note_offset=0 notes, steps 0 and 3
    assert by_offset[3]["timeStamp"] == pytest.approx(0.25)
    assert by_offset[3]["length"] == pytest.approx(0.25)
    assert by_offset[7]["length"] == pytest.approx(0.25)
    # regionEndBeats deliberately NOT written -- found live, a real
    # confirmed-working Factory preset's ArpClip0 (ARP - Acid101) omits it.
    assert "regionEndBeats" not in data["ArpClip0"]["clip"]
    assert scan_wire_types(data) == []


def test_arp_pattern_requires_pattern_notes(init_data):
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="pattern", pattern=[]))
    with pytest.raises(ValueError, match="needs arp.pattern set"):
        apply_spec(init_data, spec)


def test_arp_pattern_without_shape_pattern_rejected(init_data):
    """arp.pattern is set but shape wasn't explicitly changed to 'pattern' --
    a likely caller mistake, not something to silently override."""
    spec = PresetSpec(
        name="X",
        description="",
        arp=ArpSpec(shape="played", pattern=[ArpPatternNoteSpec(step=0, note_offset=0)]),
    )
    with pytest.raises(ValueError, match="shape is not 'pattern'"):
        apply_spec(init_data, spec)


def test_arp_pattern_round_trips_through_introspection(init_data):
    notes = [
        ArpPatternNoteSpec(step=0, note_offset=0),
        ArpPatternNoteSpec(step=2, note_offset=5, length_steps=2.0),
    ]
    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="pattern", pattern=notes))
    data = apply_spec(init_data, spec)

    extracted = extract_spec(data)
    assert extracted.arp.shape == "Pattern"
    assert extracted.arp.pattern_step_beats == pytest.approx(0.25)
    assert len(extracted.arp.pattern) == 2
    by_offset = {n.note_offset: n for n in extracted.arp.pattern}
    assert by_offset[0].step == 0
    assert by_offset[5].step == 2
    assert by_offset[5].length_steps == pytest.approx(2.0)

    # A full extract-then-reapply must not fail or alter the note data --
    # the natural edit_preset workflow of tweaking one unrelated field.
    extracted.global_.master_volume = 0.6
    new_data = apply_spec(data, extracted)
    assert new_data["ArpClip0"]["clip"]["notes"] == data["ArpClip0"]["clip"]["notes"]


def test_arp_switching_away_from_pattern_clears_stale_notes(init_data):
    data = copy.deepcopy(init_data)
    data["ArpClip0"] = {
        "clip": {"notes": [{"noteNum": 0, "timeStamp": 0.0, "length": 0.25, "channel": 0}]},
        "plainParams": {"kParamShape": "Pattern"},
    }

    spec = PresetSpec(name="X", description="", arp=ArpSpec(shape="played"))
    new_data = apply_spec(data, spec)

    assert new_data["ArpClip0"]["clip"] == {}
    assert new_data["ArpClip0"]["plainParams"]["kParamShape"] == "Played"


def test_lfo_extras_and_poly_count(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        lfos=[LfoSpec(rate=5.0, mode="Free", beat_sync=True, delay=0.5, rise=0.3, smooth=20.0)],
        **{"global": GlobalSpec(poly_count=4.0)},
    )
    data = apply_spec(init_data, spec)

    lfo_params = data["LFO0"]["plainParams"]
    assert lfo_params["kParamBeatSync"] == 1.0
    assert type(lfo_params["kParamBeatSync"]) is float
    assert lfo_params["kParamDelay"] == 0.5
    assert lfo_params["kParamRise"] == 0.3
    assert lfo_params["kParamSmooth"] == 20.0
    assert data["Global0"]["plainParams"]["kParamPolyCount"] == 4.0

    extracted = extract_spec(data)
    assert extracted.lfos[0].beat_sync is True
    assert extracted.lfos[0].delay == 0.5
    assert extracted.global_.poly_count == 4.0


def test_lfo_shape_round_trips(init_data):
    """kParamType -- named algorithmic LFO shapes (random_sh/rossler/lorenz/
    path), found live 2026-07-29 diagnosing why a recreated preset sounded
    nothing like the real one (its busiest LFO was Sample & Hold, not a
    plain curve). Unset (None) must stay absent from plainParams -- it's a
    real, common state (plain/curve-drawn LFO), not a value to default."""
    spec = PresetSpec(
        name="X",
        description="",
        lfos=[
            LfoSpec(rate=100.0, shape="random_sh"),
            LfoSpec(rate=10.0, shape="rossler"),
            LfoSpec(rate=5.0),  # unset -- must not write kParamType at all
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["LFO0"]["plainParams"]["kParamType"] == "RandomSH"
    assert data["LFO1"]["plainParams"]["kParamType"] == "Rossler"
    assert "kParamType" not in data["LFO2"]["plainParams"]

    extracted = extract_spec(data)
    assert extracted.lfos[0].shape == "random_sh"
    assert extracted.lfos[1].shape == "rossler"
    assert extracted.lfos[2].shape is None


def test_lfo_mono_and_swing_round_trip(init_data):
    """kParamMono -- found live 2026-07-29 diagnosing the same recreated
    preset: a real fast LFO stayed visibly moving even with no note held
    (kParamMono=1.0), while the recreation's LFO appeared frozen -- a
    per-voice (non-mono) LFO restarts its phase at every note-on, so under
    a fast arpeggiator it barely completes any cycle before being reset."""
    spec = PresetSpec(
        name="X",
        description="",
        lfos=[LfoSpec(rate=100.0, mono=True, swing=1.0)],
    )
    data = apply_spec(init_data, spec)

    lfo0 = data["LFO0"]["plainParams"]
    assert lfo0["kParamMono"] == 1.0
    assert type(lfo0["kParamMono"]) is float
    assert lfo0["kParamSwing"] == 1.0

    extracted = extract_spec(data)
    assert extracted.lfos[0].mono is True
    assert extracted.lfos[0].swing == 1.0


def test_lfo_dotted_triplets_rate10x_round_trip(init_data):
    """kParamDotted/kParamTriplets/kParamRate10x -- found live 2026-07-29
    diffing every module's raw plainParams against a real preset. dotted/
    triplets mirror the arpeggiator's identically-named fields; rate10x is
    LFO-specific, presumed a x10 multiplier."""
    spec = PresetSpec(
        name="X",
        description="",
        lfos=[LfoSpec(rate=0.1, shape="rossler", dotted=True, triplets=True, rate10x=True)],
    )
    data = apply_spec(init_data, spec)

    lfo0 = data["LFO0"]["plainParams"]
    assert lfo0["kParamDotted"] == 1.0
    assert lfo0["kParamTriplets"] == 1.0
    assert lfo0["kParamRate10x"] == 1.0

    extracted = extract_spec(data)
    assert extracted.lfos[0].dotted is True
    assert extracted.lfos[0].triplets is True
    assert extracted.lfos[0].rate10x is True


def test_fxeq_can_be_generated(init_data):
    """Regression test: FXEQ has no kParamWet, but _build_fx_entry used to
    force one into every FX type's plainParams unconditionally, so FXEQ
    could never be generated at all (always failed validation)."""
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXEQ", params={"kParamGain1": 3.0})],
    )
    data = apply_spec(init_data, spec)
    fx_params = data["FXRack0"]["FX"][0]["FXEQ"]["plainParams"]
    assert "kParamWet" not in fx_params
    assert fx_params["kParamGain1"] == 3.0

    extracted = extract_spec(data)
    assert extracted.fx_chain[0].type == "FXEQ"
    assert extracted.fx_chain[0].params["kParamGain1"] == 3.0


def test_fx_wet_and_lfo_macro_mod_destinations(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXReverb", wet=0.0), FxUnitSpec(type="FXDelay", wet=20.0)],
        mod_routes=[
            ModRouteSpec(source="macro0", destination="fx0.wet", amount=50.0),
            ModRouteSpec(source="lfo0", destination="lfo1.rate", amount=30.0),
            ModRouteSpec(source="macro1", destination="macro0.value", amount=10.0),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["destModuleTypeString"] == "FXReverb"
    assert data["ModSlot0"]["destModuleID"] == 0
    assert data["ModSlot0"]["destModuleParamName"] == "kParamWet"
    assert data["ModSlot0"]["destModuleParamID"] == 1

    assert data["ModSlot1"]["destModuleTypeString"] == "LFO"
    assert data["ModSlot1"]["destModuleID"] == 1
    assert data["ModSlot1"]["destModuleParamName"] == "kParamRate"

    assert data["ModSlot2"]["destModuleTypeString"] == "Macro"
    assert data["ModSlot2"]["destModuleID"] == 0

    extracted = extract_spec(data)
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["fx0.wet"] == "macro0"
    assert routes["lfo1.rate"] == "lfo0"
    assert routes["macro0.value"] == "macro1"


def test_fx_chain_across_multiple_racks(init_data):
    """Serum can run up to 3 FX racks in PARALLEL -- found live 2026-07-29
    in a real Unmute preset with a second, independent chain (incl. a
    reverb and a bode shifter) this project had never read or written
    before. destModuleID for an FX unit is rack*100 + position-within-rack
    (confirmed against that real preset's raw ModSlot data)."""
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[
            FxUnitSpec(type="FXComp", wet=100.0),  # rack 0, position 0
            FxUnitSpec(type="FXEQ", wet=100.0),  # rack 0, position 1
            FxUnitSpec(type="FXReverb", wet=25.0, rack=1),  # rack 1, position 0
            FxUnitSpec(type="FXDelay", wet=30.0, rack=1),  # rack 1, position 1
        ],
        mod_routes=[
            ModRouteSpec(source="macro0", destination="fx0.wet", amount=10.0),  # FXComp, rack0
            ModRouteSpec(source="macro1", destination="fx2.wet", amount=20.0),  # FXReverb, rack1
            ModRouteSpec(source="macro2", destination="fx3.wet", amount=30.0),  # FXDelay, rack1
        ],
    )
    data = apply_spec(init_data, spec)

    assert [fx["type"] for fx in data["FXRack0"]["FX"]] == [5, 7]  # FXComp, FXEQ
    assert [fx["type"] for fx in data["FXRack1"]["FX"]] == [6, 4]  # FXReverb, FXDelay

    # fx0 (FXComp, rack0 pos0) -> destModuleID 0; fx2 (FXReverb, rack1 pos0)
    # -> destModuleID 100; fx3 (FXDelay, rack1 pos1) -> destModuleID 101.
    dest_by_source = {
        tuple(v["source"]): (v["destModuleTypeString"], v["destModuleID"])
        for k, v in data.items()
        if isinstance(k, str) and k.startswith("ModSlot") and v.get("source")
    }
    assert dest_by_source[(25, 0)] == ("FXComp", 0)  # macro0
    assert dest_by_source[(26, 0)] == ("FXReverb", 100)  # macro1
    assert dest_by_source[(27, 0)] == ("FXDelay", 101)  # macro2

    extracted = extract_spec(data)
    assert [(fx.type, fx.rack) for fx in extracted.fx_chain] == [
        ("FXComp", 0),
        ("FXEQ", 0),
        ("FXReverb", 1),
        ("FXDelay", 1),
    ]
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["fx0.wet"] == "macro0"
    assert routes["fx2.wet"] == "macro1"
    assert routes["fx3.wet"] == "macro2"


def test_global_voice_amp_and_fx_balance_mod_destinations(init_data):
    """Global.kParamVoiceAmp and FXUtils.kParamBalance -- found live
    2026-07-29 recreating two different real Unmute presets (both used
    key_track -> Global.kParamVoiceAmp; one also used lfo -> FXUtils.
    kParamBalance), the last 2 of Dreams's 14 real mod routes this project
    couldn't reproduce until now (14/14 after this fix)."""
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXUtils", wet=100.0)],
        mod_routes=[
            ModRouteSpec(source="key_track", destination="global.voice_amp", amount=-51.9),
            ModRouteSpec(source="lfo2", destination="fx0.balance", amount=39.7),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["destModuleTypeString"] == "Global"
    assert data["ModSlot0"]["destModuleID"] == 0
    assert data["ModSlot0"]["destModuleParamName"] == "kParamVoiceAmp"
    assert data["ModSlot0"]["destModuleParamID"] == 2

    assert data["ModSlot1"]["destModuleTypeString"] == "FXUtils"
    assert data["ModSlot1"]["destModuleParamName"] == "kParamBalance"
    assert data["ModSlot1"]["destModuleParamID"] == 4

    extracted = extract_spec(data)
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["global.voice_amp"] == "key_track"
    assert routes["fx0.balance"] == "lfo2"


def test_fxutils_level_out_mod_destination(init_data):
    """FXUtils.kParamLevelOut -- found live 2026-07-29 recreating
    UN_PLACES_BA_Beyond in one shot: its real ModSlot0/2 both route into
    this (lfo0 and macro0 respectively), previously unmapped and silently
    dropped -- the missing lfo0 route was also why that LFO looked inert
    (not actually driving anything) in the recreation."""
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXUtils", wet=100.0)],
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="fx0.level_out", amount=-100.0),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["destModuleTypeString"] == "FXUtils"
    assert data["ModSlot0"]["destModuleParamName"] == "kParamLevelOut"
    assert data["ModSlot0"]["destModuleParamID"] == 2

    extracted = extract_spec(data)
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["fx0.level_out"] == "lfo0"


def test_oscillator_warp_amount2_mod_destination(init_data):
    """WTOsc.kParamWarp2 (destModuleParamID 3) -- the second warp lane's own
    amount as a mod destination, distinct from warp_amount (ID 0) and
    warp_var2 (ID 4). Found live 2026-07-29 recreating UN_PLACES_BA_Beyond:
    its real ModSlot5 (macro4 -> WTOsc2.kParamWarp2) was previously unmapped
    and silently dropped -- the missing 9th of 9 real active mod routes."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(warp_mode2="filter_lpf", warp_amount2=0.5)],
        mod_routes=[
            ModRouteSpec(source="macro4", destination="oscillator0.warp_amount2", amount=28.05),
        ],
    )
    data = apply_spec(init_data, spec)

    assert data["ModSlot0"]["destModuleTypeString"] == "WTOsc"
    assert data["ModSlot0"]["destModuleParamName"] == "kParamWarp2"
    assert data["ModSlot0"]["destModuleParamID"] == 3

    extracted = extract_spec(data)
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["oscillator0.warp_amount2"] == "macro4"


def test_new_mod_destinations_2026_07_30_survey_round_trip(init_data):
    """filter{i}.wet/var/stereo/level_out, oscillator3.noise_color, arp.gate/
    rate, global.voice_scaling_env_time/lfo_time -- confirmed via a
    626-preset corpus survey of every real ModSlot's destModuleParamID,
    closing out item 1b's remaining destination gaps in
    docs/PARAMETER_SCHEMA.md §5 (VoiceFilter.kParamWet, NoiseOsc.kParamColor,
    Arp params, VoicePanel.kParamGlobalScalingEnvTime/LfoTime)."""
    spec = PresetSpec(
        name="X",
        description="",
        filters=[FilterSpec(), FilterSpec()],
        mod_routes=[
            ModRouteSpec(source="lfo0", destination="filter0.wet", amount=10.0),
            ModRouteSpec(source="lfo1", destination="filter1.var", amount=11.0),
            ModRouteSpec(source="lfo2", destination="filter0.stereo", amount=12.0),
            ModRouteSpec(source="lfo3", destination="filter1.level_out", amount=13.0),
            ModRouteSpec(source="macro0", destination="oscillator3.noise_color", amount=14.0),
            ModRouteSpec(source="macro1", destination="arp.gate", amount=15.0),
            ModRouteSpec(source="macro2", destination="arp.rate", amount=16.0),
            ModRouteSpec(source="macro3", destination="global.voice_scaling_env_time", amount=17.0),
            ModRouteSpec(source="macro4", destination="global.voice_scaling_lfo_time", amount=18.0),
        ],
    )
    data = apply_spec(init_data, spec)

    expected = {
        "ModSlot0": ("VoiceFilter", "kParamWet", 1),
        "ModSlot1": ("VoiceFilter", "kParamVar", 6),
        "ModSlot2": ("VoiceFilter", "kParamStereo", 7),
        "ModSlot3": ("VoiceFilter", "kParamLevelOut", 8),
        "ModSlot4": ("NoiseOsc", "kParamColor", 0),
        "ModSlot5": ("Arp", "kParamGate", 6),
        "ModSlot6": ("Arp", "kParamRate", 1),
        "ModSlot7": ("VoicePanel", "kParamGlobalScalingEnvTime", 58),
        "ModSlot8": ("VoicePanel", "kParamGlobalScalingLfoTime", 59),
    }
    for slot, (dest_type, param_name, param_id) in expected.items():
        assert data[slot]["destModuleTypeString"] == dest_type
        assert data[slot]["destModuleParamName"] == param_name
        assert data[slot]["destModuleParamID"] == param_id

    extracted = extract_spec(data)
    routes = {r.destination: r.source for r in extracted.mod_routes}
    assert routes["filter0.wet"] == "lfo0"
    assert routes["filter1.var"] == "lfo1"
    assert routes["filter0.stereo"] == "lfo2"
    assert routes["filter1.level_out"] == "lfo3"
    assert routes["oscillator3.noise_color"] == "macro0"
    assert routes["arp.gate"] == "macro1"
    assert routes["arp.rate"] == "macro2"
    assert routes["global.voice_scaling_env_time"] == "macro3"
    assert routes["global.voice_scaling_lfo_time"] == "macro4"


def test_fx_chain_edit_only_touches_racks_present(init_data):
    """A rack with zero entries in spec.fx_chain must be left untouched --
    most callers don't know rack 1/2 exist, so an edit that only mentions
    rack 0 must not silently wipe a real rack-1 chain that was already
    there."""
    init_data["FXRack1"] = {
        "FX": [{"type": 6, "kUIParamMixOrGain": 0.0, "FXReverb": {"plainParams": {}}}]
    }
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXComp", wet=100.0)],  # rack 0 only
    )
    data = apply_spec(init_data, spec)

    assert [fx["type"] for fx in data["FXRack0"]["FX"]] == [5]
    assert [fx["type"] for fx in data["FXRack1"]["FX"]] == [6]  # untouched


def test_fx_wet_mod_destination_errors(init_data):
    # References a slot that doesn't exist in fx_chain.
    spec = PresetSpec(
        name="X",
        description="",
        mod_routes=[ModRouteSpec(source="lfo0", destination="fx0.wet", amount=10.0)],
    )
    with pytest.raises(ValueError, match="fx_chain\\[0\\]"):
        apply_spec(init_data, spec)

    # FXEQ has no wet knob to modulate.
    spec = PresetSpec(
        name="X",
        description="",
        fx_chain=[FxUnitSpec(type="FXEQ")],
        mod_routes=[ModRouteSpec(source="lfo0", destination="fx0.wet", amount=10.0)],
    )
    with pytest.raises(ValueError, match="no kParamWet"):
        apply_spec(init_data, spec)


def test_omitting_global_does_not_reset_it(init_data):
    """Regression test (found via real-world use, not a unit test): unlike
    oscillators/filters/envelopes/etc. -- lists only touched per index when
    present -- `global` is a single nested object that always has a value,
    since PresetSpec() with no "global" key still gets a default-valued
    GlobalSpec(). apply_spec used to write it unconditionally, so an
    edit_preset call that didn't repeat the current global settings would
    silently reset master_volume/mono/portamento/poly_count to defaults --
    breaking the "only change what you specify" contract every other
    section honors. Caught when poly_count silently dropped from 6 to 8
    (the default) after an edit that only touched oscillators/filters."""
    first = PresetSpec(
        name="X", description="", **{"global": GlobalSpec(poly_count=6.0, mono=True)}
    )
    data = apply_spec(init_data, first)
    assert data["Global0"]["plainParams"]["kParamPolyCount"] == 6.0

    second = PresetSpec(name="X", description="", filters=[FilterSpec(enabled=True, cutoff=0.9)])
    data = apply_spec(data, second)
    assert data["Global0"]["plainParams"]["kParamPolyCount"] == 6.0
    assert data["Global0"]["plainParams"]["kParamMonoToggle"] == 1.0


def test_different_oscillators_can_use_different_wavetables(init_data):
    """Regression test: the init fixture assigns the same wavetable file to
    every WTOsc slot, and apply_spec never touched that file reference, so
    every generated preset used the identical table for every oscillator
    (found via real-world use -- a pad's two layers sounded thin because
    both were literally the same wavetable at different octaves)."""
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(enabled=True, wavetable="pwm", table_position=30.0),
            OscillatorSpec(enabled=True, wavetable="harmonic_smooth", table_position=100.0),
        ],
    )
    data = apply_spec(init_data, spec)

    wt0 = data["Oscillator0"]["WTOsc0"]
    assert wt0["relativePathToWT"] == "Analog/PWM Juno.wav"
    assert wt0["numFrames"] == 229376
    assert type(wt0["numFrames"]) is int  # not a float -- real Serum presets use int here
    wt1 = data["Oscillator1"]["WTOsc1"]
    assert wt1["relativePathToWT"] == "S2 Tables/Digital/Harmonic Series Smooth.wav"
    assert wt0["relativePathToWT"] != wt1["relativePathToWT"]

    extracted = extract_spec(data)
    assert extracted.oscillators[0].wavetable == "pwm"
    assert extracted.oscillators[1].wavetable == "harmonic_smooth"


def test_unknown_wavetable_rejected(init_data):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, wavetable="not_a_real_table")],
    )
    with pytest.raises(ValueError, match="unknown wavetable"):
        apply_spec(init_data, spec)


def _write_minimal_wav(path: Path, num_samples: int = 2048) -> None:
    """A minimal valid mono 16-bit PCM WAV, just enough for
    sample_library.read_wav_metadata to read a real header from."""
    import struct as _struct

    data = b"\x00\x00" * num_samples
    fmt_chunk = _struct.pack("<HHIIHH", 1, 1, 44100, 44100 * 2, 2, 16)
    body = bytearray()
    body += b"fmt " + _struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + _struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += _struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def test_noncurated_wavetable_falls_back_to_reading_the_real_file(init_data, tables_dir):
    """Found live editing real Factory/third-party presets: a non-curated
    table (e.g. a genuine Serum 2 factory table not in SIMPLE_WAVETABLES)
    used to always raise "unknown wavetable", even though the file is real
    -- 56% of a real 844-preset sample referenced at least one. Falls back
    to reading the actual file's header instead of assuming a typo."""
    nested = tables_dir / "Analog"
    nested.mkdir(parents=True, exist_ok=True)
    _write_minimal_wav(nested / "Custom Table.wav")

    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, wavetable="Analog/Custom Table.wav")],
    )
    data = apply_spec(init_data, spec)
    assert data["Oscillator0"]["WTOsc0"]["relativePathToWT"] == "Analog/Custom Table.wav"
    assert data["Oscillator0"]["WTOsc0"]["numFrames"] == 2048


def test_noncurated_wavetable_leading_slash_path_resolves_correctly(init_data, tables_dir):
    """Found live in real Factory CBOR data: some tables are referenced with
    a LEADING slash (e.g. "/Analog/Basic Shapes.wav", confirmed in
    Factory/Bass/808/808 - Drill.SerumPreset -- genuine Serum data, not
    malformed). pathlib's `/` operator treats a leading-slash right operand
    as anchored to the drive root and silently discards the left side --
    `Path("C:/Tables") / "/Analog/x.wav"` resolves to "C:/Analog/x.wav", not
    "C:/Tables/Analog/x.wav" -- so a naive join always reported "file not
    found" for these."""
    nested = tables_dir / "Analog"
    nested.mkdir(parents=True, exist_ok=True)
    _write_minimal_wav(nested / "Basic Shapes.wav")

    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, wavetable="/Analog/Basic Shapes.wav")],
    )
    data = apply_spec(init_data, spec)
    assert data["Oscillator0"]["WTOsc0"]["relativePathToWT"] == "/Analog/Basic Shapes.wav"
    assert data["Oscillator0"]["WTOsc0"]["numFrames"] == 2048


def test_custom_harmonics_synthesizes_and_writes_a_wavetable(init_data, tables_dir):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                custom_harmonics=[[1.0], [1.0, 0.5, 0.0, 0.25], [1.0, 0.7, 0.5, 0.35, 0.25, 0.2]],
            )
        ],
    )
    data = apply_spec(init_data, spec)

    wt0 = data["Oscillator0"]["WTOsc0"]
    assert wt0["numFrames"] == 3 * 2048
    assert wt0["sampleRate"] == 44100
    assert wt0["numChannels"] == 1
    assert wt0["relativePathToWT"].startswith("User/serum-mcp/wt_")
    assert wt0["relativePathToWT"].endswith(".wav")

    written_file = tables_dir / wt0["relativePathToWT"]
    assert written_file.exists()
    assert written_file.read_bytes()[:4] == b"RIFF"

    extracted = extract_spec(data)
    assert extracted.oscillators[0].wavetable == wt0["relativePathToWT"]


def test_custom_harmonics_deterministic_filename_reused(init_data, tables_dir):
    """Identical harmonic content should reuse the same file rather than
    writing a duplicate every time."""
    harmonics = [[1.0, 0.3]]
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, custom_harmonics=harmonics)],
    )
    data1 = apply_spec(init_data, spec)
    path1 = data1["Oscillator0"]["WTOsc0"]["relativePathToWT"]

    data2 = apply_spec(init_data, spec)
    path2 = data2["Oscillator0"]["WTOsc0"]["relativePathToWT"]

    assert path1 == path2
    assert len(list((tables_dir / "User" / "serum-mcp").iterdir())) == 1


def test_custom_harmonics_too_many_frames_rejected(init_data, tables_dir):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, custom_harmonics=[[1.0]] * 300)],
    )
    with pytest.raises(ValueError, match="max is 256"):
        apply_spec(init_data, spec)


def test_default_wt_oscillator_writes_kparamtype_wt(init_data, tables_dir):
    """Every WT-engine oscillator must explicitly declare kOsc_WT now (not
    just rely on it being the implicit default), so a later partial edit
    that switches this slot to SampleOsc and back can't leave a stale
    engine selector behind."""
    spec = PresetSpec(name="X", description="", oscillators=[OscillatorSpec(enabled=True)])
    data = apply_spec(init_data, spec)
    assert data["Oscillator0"]["plainParams"]["kParamType"] == "kOsc_WT"


def test_sample_playback_source_writes_sampleosc_and_engine_selector(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "kick.wav"
    _write_wav_fixture(source)

    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                sample_playback_source=str(source),
                warp_amount=0.4,
                warp_mode="soft_clip",
            )
        ],
    )
    data = apply_spec(init_data, spec)

    osc0 = data["Oscillator0"]
    assert osc0["plainParams"]["kParamType"] == "kOsc_Sample"
    # No loop requested -- must not appear at all (absence == one-shot,
    # per the factory-preset survey; there's no observed "off" enum value).
    assert "kParamLoopMode" not in osc0["plainParams"]

    sample0 = osc0["SampleOsc0"]
    assert sample0["numChannels"] == 1
    assert sample0["sampleRate"] == 44100
    assert sample0["numFrames"] == 4410
    assert sample0["samplePathRelative"].startswith("User/serum-mcp/smp_")
    assert sample0["samplePathRelative"].endswith(".wav")
    assert sample0["plainParams"]["kParamWarp"] == 0.4
    assert sample0["plainParams"]["kParamWarpMenu"] == "kDistSoftClip"

    written_file = samples_dir / sample0["samplePathRelative"]
    assert written_file.exists()
    assert written_file.read_bytes() == source.read_bytes()

    # WTOsc0 must be left alone (still the base fixture's inert sentinel),
    # not populated alongside the now-inactive-engine data.
    assert osc0["WTOsc0"] == init_data["Oscillator0"]["WTOsc0"]


def test_sample_playback_source_centers_imbalanced_stereo_by_default(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "guitar.wav"
    _write_stereo_wav_fixture(source, left_amp=0.8, right_amp=0.4)

    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, sample_playback_source=str(source))],
    )
    data = apply_spec(init_data, spec)

    sample0 = data["Oscillator0"]["SampleOsc0"]
    written_file = samples_dir / sample0["samplePathRelative"]
    assert written_file.exists()
    # Re-encoded/corrected, not a verbatim copy of the imbalanced source.
    assert written_file.read_bytes() != source.read_bytes()


def test_sample_playback_source_center_pan_false_copies_verbatim(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "guitar.wav"
    _write_stereo_wav_fixture(source, left_amp=0.8, right_amp=0.4)

    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True, sample_playback_source=str(source), sample_center_pan=False
            )
        ],
    )
    data = apply_spec(init_data, spec)

    sample0 = data["Oscillator0"]["SampleOsc0"]
    written_file = samples_dir / sample0["samplePathRelative"]
    assert written_file.read_bytes() == source.read_bytes()


def test_sample_playback_source_dedup_reuses_copy(init_data, tables_dir, samples_dir, tmp_path):
    source = tmp_path / "kick.wav"
    _write_wav_fixture(source)
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, sample_playback_source=str(source))],
    )

    data1 = apply_spec(init_data, spec)
    data2 = apply_spec(init_data, spec)

    path1 = data1["Oscillator0"]["SampleOsc0"]["samplePathRelative"]
    path2 = data2["Oscillator0"]["SampleOsc0"]["samplePathRelative"]
    assert path1 == path2
    assert len(list((samples_dir / "User" / "serum-mcp").iterdir())) == 1


def test_sample_playback_source_loop_forward_writes_loop_params(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "pad.wav"
    _write_wav_fixture(source)
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                sample_playback_source=str(source),
                sample_loop="forward",
                sample_loop_start=10.0,
                sample_loop_end=90.0,
                sample_loop_crossfade=5.0,
            )
        ],
    )
    data = apply_spec(init_data, spec)
    pp = data["Oscillator0"]["plainParams"]
    assert pp["kParamLoopMode"] == "kForward"
    assert pp["kParamLoopStart"] == 10.0
    assert pp["kParamLoopEnd"] == 90.0
    assert pp["kParamLoopCrossfade"] == 5.0


def test_sample_playback_source_missing_file_rejected(init_data, tables_dir, samples_dir):
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, sample_playback_source="/no/such/file.wav")],
    )
    with pytest.raises(ValueError, match="does not exist"):
        apply_spec(init_data, spec)


def test_sample_playback_source_rejects_unsupported_extension(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "kick.flac"
    source.write_bytes(b"fLaC not a real flac but has the right extension")
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, sample_playback_source=str(source))],
    )
    with pytest.raises(ValueError, match="unsupported extension"):
        apply_spec(init_data, spec)


def test_sample_playback_source_unchanged_reference_skips_reprocessing(
    init_data, tables_dir, samples_dir
):
    """Found live editing real Factory content: Serum's own factory sample
    library is almost entirely .flac, which copy_sample_to_library can't
    ingest (no FLAC decoder in this project). extract_spec reconstructs
    sample_playback_source as an absolute path built from the preset's own
    existing samplePathRelative -- so ANY apply_spec call that includes an
    oscillator whose sample reference hasn't actually changed (e.g. just to
    preserve a later oscillator's list position during an edit) must not
    try to re-copy/re-validate that file. A .flac reference that's already
    the existing SampleOsc0 content must round-trip untouched instead of
    raising "unsupported extension"."""
    existing_relative = "Factory/Bass/Clean 808.flac"
    absolute = samples_dir / existing_relative
    data = copy.deepcopy(init_data)
    data["Oscillator0"] = {
        "plainParams": {"kParamType": "kOsc_Sample"},
        "SampleOsc0": {
            "samplePathRelative": existing_relative,
            "numFrames": 44100,
            "sampleRate": 44100,
            "numChannels": 1,
            "plainParams": {"kParamWarp": 0.0, "kParamWarpMenu": "kFM_OSC"},
        },
    }

    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[OscillatorSpec(enabled=True, sample_playback_source=str(absolute))],
    )
    new_data = apply_spec(data, spec)

    sample_osc = new_data["Oscillator0"]["SampleOsc0"]
    assert sample_osc["samplePathRelative"] == existing_relative
    assert sample_osc["numFrames"] == 44100
    assert sample_osc["sampleRate"] == 44100
    assert sample_osc["numChannels"] == 1


def test_sample_playback_source_takes_priority_over_wavetable_fields(
    init_data, tables_dir, samples_dir, tmp_path
):
    """sample_playback_source + custom_harmonics/wavetable both set at once
    must use the sample engine and never touch the wavetable-synthesis path
    (which would otherwise raise/write unnecessarily)."""
    source = tmp_path / "kick.wav"
    _write_wav_fixture(source)
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                sample_playback_source=str(source),
                wavetable="acid",
                custom_harmonics=[[1.0]],
            )
        ],
    )
    data = apply_spec(init_data, spec)
    assert data["Oscillator0"]["plainParams"]["kParamType"] == "kOsc_Sample"
    assert "SampleOsc0" in data["Oscillator0"]


def test_sample_playback_source_round_trips_through_introspection(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "kick.wav"
    _write_wav_fixture(source)
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                sample_playback_source=str(source),
                warp_amount=0.4,
                warp_mode="soft_clip",
            )
        ],
    )
    data = apply_spec(init_data, spec)

    extracted = extract_spec(data)
    osc0 = extracted.oscillators[0]
    assert osc0.sample_playback_source is not None
    written_path = Path(osc0.sample_playback_source)
    assert written_path.is_file()
    assert written_path.read_bytes() == source.read_bytes()
    assert osc0.warp_amount == 0.4
    assert osc0.warp_mode == "soft_clip"
    assert osc0.sample_loop == "off"
    # WT-only field must not leak a stale/misleading value.
    assert osc0.wavetable == "default"


def test_sample_playback_source_loop_round_trips_through_introspection(
    init_data, tables_dir, samples_dir, tmp_path
):
    source = tmp_path / "pad.wav"
    _write_wav_fixture(source)
    spec = PresetSpec(
        name="X",
        description="",
        oscillators=[
            OscillatorSpec(
                enabled=True,
                sample_playback_source=str(source),
                sample_loop="ping_pong",
                sample_loop_start=15.0,
                sample_loop_end=85.0,
                sample_loop_crossfade=8.0,
            )
        ],
    )
    data = apply_spec(init_data, spec)

    extracted = extract_spec(data)
    osc0 = extracted.oscillators[0]
    assert osc0.sample_loop == "ping_pong"
    assert osc0.sample_loop_start == 15.0
    assert osc0.sample_loop_end == 85.0
    assert osc0.sample_loop_crossfade == 8.0
