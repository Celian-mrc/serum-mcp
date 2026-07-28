from __future__ import annotations

from pathlib import Path

import pytest

from serum_mcp import config
from serum_mcp.generation.spec import (
    EnvelopeSpec,
    FilterSpec,
    FxUnitSpec,
    GlobalSpec,
    LfoSpec,
    ModRouteSpec,
    OscillatorSpec,
    PresetSpec,
)
from serum_mcp.preset.introspect import extract_spec
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
        mod_routes=[ModRouteSpec(source="env0", destination="filter0.cutoff", amount=10.0)],
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
