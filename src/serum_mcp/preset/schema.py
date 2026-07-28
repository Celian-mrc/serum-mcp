"""Ground-truth schema for the Serum 2 CBOR parameter payload.

Nothing here is guessed. Every bound, default and enum value was either:

- **measured** empirically, by unpacking ~300 factory presets shipped with a
  real Serum 2 install (see ``docs/PARAMETER_SCHEMA.md`` for the sampling
  methodology) and recording observed min/max/values per ``kParam*`` key, or
- **confirmed authoritative**, by cross-referencing against a JSON dump of
  every VST3 parameter (with its default value) reported by a freshly loaded
  Serum 2 instance
  (https://gist.github.com/KennethWussmann/5b58e4de728680a0bf8906a8b113103d).

Where those two sources disagree, or where a parameter was only rarely
observed, that is called out in the ``notes`` field rather than silently
picking one. This schema intentionally covers the subset of Serum 2's engine
that matters for *sound design from a text description* (oscillators,
filters, envelopes, LFOs, macros, the mod matrix, and the effects chain) --
it does not attempt to model the arpeggiator/sequencer, MPE, MIDI clips or
GUI state, which round-trip through :mod:`serum_mcp.preset.packer` untouched
but are not validated or generated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Confidence = Literal["confirmed", "observed", "uncertain"]


@dataclass(frozen=True)
class ParamDef:
    """One ``kParam*`` field inside a module's ``plainParams`` dict."""

    key: str
    kind: Literal["float", "bool", "enum"]
    default: float | str | None = None
    min: float | None = None
    max: float | None = None
    unit: str = ""
    enum_values: tuple[str, ...] = ()
    confidence: Confidence = "observed"
    notes: str = ""


# ---------------------------------------------------------------------------
# Oscillators (Oscillator0..Oscillator4 in the CBOR payload -- Serum 2 calls
# these Osc A/B/C, Noise and Sub in the UI). Each slot's `plainParams` holds
# these pitch/mix controls; the *sound source* itself (wavetable, sample,
# granular, multisample or spectral) is a nested sub-object -- see
# WTOSC_PARAMS / SAMPLEOSC_PARAMS / NOISEOSC_PARAMS / SUBOSC_PARAMS below.
# GranularOsc/MultiSampleOsc/SpectralOsc were only lightly sampled (< 150
# presets used them each) so are NOT modeled in detail; WTOsc and SampleOsc
# are both modeled (selected via kParamType below), slots default to WTOsc.
# ---------------------------------------------------------------------------

OSCILLATOR_PARAMS: dict[str, ParamDef] = {
    "kParamEnable": ParamDef(
        "kParamEnable",
        "bool",
        default=False,
        confidence="confirmed",
        notes="Per-slot default, NOT uniform: confirmed via VST3 dump that only Osc A "
        "(Oscillator0) defaults On -- Osc B/C/Noise/Sub (Oscillator1..4) default Off. "
        "The `False` here is the common case; callers resolving Oscillator0 specifically "
        "must special-case it to True (see preset/introspect.py).",
    ),
    "kParamOctave": ParamDef(
        "kParamOctave",
        "float",
        default=0.0,
        min=-4.0,
        max=4.0,
        unit="octaves",
        confidence="confirmed",
    ),
    "kParamVolume": ParamDef(
        "kParamVolume",
        "float",
        default=0.75,
        min=0.0,
        max=1.0,
        unit="normalized (0=-inf dB, 1=0dB)",
        confidence="confirmed",
        notes="VST3 default is 75% (~-5.0dB) for Osc A/B.",
    ),
    "kParamPan": ParamDef(
        "kParamPan",
        "float",
        default=0.0,
        min=-50.0,
        max=50.0,
        unit="normalized pan",
    ),
    "kParamFine": ParamDef(
        "kParamFine",
        "float",
        default=0.0,
        min=-50.0,
        max=50.0,
        unit="cents (approx.)",
    ),
    "kParamCoarsePit": ParamDef(
        "kParamCoarsePit",
        "float",
        default=0.0,
        min=-24.0,
        max=48.0,
        unit="semitones",
    ),
    "kParamPitch": ParamDef(
        "kParamPitch",
        "float",
        default=0.0,
        min=-12.0,
        max=12.0,
        unit="semitones",
        notes="Only seen set when this oscillator is a mod-matrix destination.",
    ),
    "kParamDetune": ParamDef(
        "kParamDetune",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        unit="normalized unison detune",
    ),
    "kParamDetuneWid": ParamDef(
        "kParamDetuneWid",
        "float",
        default=0.0,
        min=0.0,
        max=100.0,
        unit="% unison width",
    ),
    "kParamUnison": ParamDef(
        "kParamUnison",
        "float",
        default=1.0,
        min=1.0,
        max=16.0,
        unit="voice count",
        confidence="uncertain",
        notes="VST3 default shows 1 voice; observed max in samples was 16.",
    ),
    "kParamUnisonStereo": ParamDef(
        "kParamUnisonStereo",
        "float",
        default=100.0,
        min=-100.0,
        max=100.0,
        unit="% width",
    ),
    "kParamPitchTrack": ParamDef(
        "kParamPitchTrack",
        "bool",
        default=True,
        confidence="confirmed",
    ),
    "kParamType": ParamDef(
        "kParamType",
        "enum",
        default="kOsc_WT",
        confidence="observed",
        enum_values=(
            "kOsc_WT",
            "kOsc_Sample",
            "kOsc_Granular",
            "kOsc_MultiSample",
            "kOsc_Spectral",
        ),
        notes="Selects which of the 5 sound-source engines (see module docstring above) "
        "this slot's nested Osc dict is actually driven by. Found via factory-preset "
        "survey, not the VST3 dump. Absent from plainParams == kOsc_WT (every WTOsc "
        "preset this project generates before this field existed omitted it and loaded "
        "fine) -- serum-mcp now writes it explicitly every time regardless, so a later "
        "partial edit that switches an oscillator's engine can't leave a stale value "
        "behind (see docs/PARAMETER_SCHEMA.md's mapping.py partial-edit lesson).",
    ),
    "kParamLoopMode": ParamDef(
        "kParamLoopMode",
        "enum",
        confidence="observed",
        enum_values=("kForward", "kPingPong", "kTailed"),
        notes="SampleOsc only. Absent from plainParams in every factory preset that "
        "doesn't loop its sample (i.e. a true one-shot) -- there is no observed 'off' "
        "enum value, omitting the key entirely is what turns looping off.",
    ),
    "kParamLoopStart": ParamDef(
        "kParamLoopStart",
        "float",
        default=0.0,
        min=0.0,
        max=100.0,
        unit="% into the sample",
        confidence="observed",
        notes="SampleOsc only, only meaningful when kParamLoopMode is set.",
    ),
    "kParamLoopEnd": ParamDef(
        "kParamLoopEnd",
        "float",
        default=100.0,
        min=0.0,
        max=100.0,
        unit="% into the sample",
        confidence="observed",
        notes="SampleOsc only, only meaningful when kParamLoopMode is set.",
    ),
    "kParamLoopCrossfade": ParamDef(
        "kParamLoopCrossfade",
        "float",
        default=0.0,
        min=0.0,
        max=100.0,
        unit="%",
        confidence="uncertain",
        notes="SampleOsc only. Observed range in factory presets was ~0.5-63%; the true "
        "engine-enforced ceiling isn't confirmed, treating 100 as the bound like other "
        "%-unit params in this schema.",
    ),
}

# WTOsc: the classic wavetable engine, used by default in every slot.
WTOSC_PARAMS: dict[str, ParamDef] = {
    "kParamTablePos": ParamDef(
        "kParamTablePos",
        "float",
        default=0.0,
        min=0.0,
        max=256.0,
        unit="table frame",
        notes="Range depends on the loaded wavetable's frame count; 256 is the observed ceiling.",
    ),
    "kParamWarp": ParamDef(
        "kParamWarp",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        unit="normalized",
    ),
    "kParamWarp2": ParamDef(
        "kParamWarp2",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        unit="normalized",
    ),
    "kParamWarpMenu": ParamDef(
        "kParamWarpMenu",
        "enum",
        default="kFM_OSC",
        confidence="observed",
        enum_values=(
            "kAM_OSC",
            "kASYMNeg",
            "kASYMPos",
            "kBendNeg",
            "kBendPos",
            "kBendPosNeg",
            "kDLM",
            "kDistDiode1",
            "kDistDiode2",
            "kDistHardClip",
            "kDistLinFold",
            "kDistSinFold",
            "kDistSoftClip",
            "kDistSoftSat",
            "kDistTube",
            "kEvenOdd",
            "kFMP_NOISE",
            "kFMP_OSC",
            "kFMX_NOISE",
            "kFMX_OSC",
            "kFMX_OSC2",
            "kFM_NOISE",
            "kFM_OSC",
            "kFM_OSC2",
            "kFM_SUB",
            "kFilterHPF",
            "kFilterLPF",
            "kFlip",
            "kPD_FILT1",
            "kPD_NOISE",
            "kPD_OSC",
            "kPD_OSC2",
            "kPD_SUB",
            "kPWM",
            "kQuantize",
            "kRM_FILT1",
            "kRM_FILT2",
            "kRM_NOISE",
            "kRM_OSC",
            "kRM_OSC2",
            "kRM_SUB",
            "kRemap_4",
            "kSelfPD",
            "kSync",
        ),
        notes="'Warp mode A'. Union of values observed across samples; the true full "
        "enum (from Serum's UI dropdown) may be a superset.",
    ),
    "kParamInitialPhase": ParamDef(
        "kParamInitialPhase",
        "float",
        default=0.0,
        min=0.0,
        max=360.0,
        unit="degrees",
    ),
    "kParamRandomPhase": ParamDef(
        "kParamRandomPhase",
        "float",
        default=0.0,
        min=0.0,
        max=100.0,
        unit="%",
    ),
}

# Friendly names -> WTOSC_PARAMS["kParamWarpMenu"] enum values, curated to a
# musically-distinct spread (FM/AM, sync, PWM, wavefolding/distortion
# characters, built-in filtering, bit-quantize) rather than the full ~43
# value raw enum.
SIMPLE_WARP_MODES: dict[str, str] = {
    "fm": "kFM_OSC",
    "am": "kAM_OSC",
    "sync": "kSync",
    "pwm": "kPWM",
    "bend": "kBendPos",
    "fold": "kDistLinFold",
    "soft_clip": "kDistSoftClip",
    "hard_clip": "kDistHardClip",
    "quantize": "kQuantize",
    "filter_lpf": "kFilterLPF",
    "filter_hpf": "kFilterHPF",
}


@dataclass(frozen=True)
class WavetableDef:
    """A selectable wavetable file for the WTOsc engine (slots 0-2).

    ``num_frames``/``sample_rate``/``num_channels`` describe the referenced
    .wav file itself (not a tunable synth parameter) and must match it
    exactly, or Serum may misread the table -- same risk class as the CBOR
    bool/int wire-type bugs (see docs/PARAMETER_SCHEMA.md), just for file
    metadata instead of a plainParams value. Every entry below was copied
    from real Serum-saved presets that reference that exact file, not
    guessed or computed from the .wav headers ourselves.
    """

    relative_path: str
    num_frames: int
    sample_rate: int
    num_channels: int


# Friendly names -> WavetableDef, curated from the ~40 most commonly
# referenced factory wavetables across our 400-preset sample for a spread of
# distinct characters (warm analog, PWM, digital/FM, harmonic-rich, acid).
# kParamTablePos (0..256, see WTOSC_PARAMS above) appears to already be
# normalized to a fixed slot count independent of a table's raw numFrames
# (observed range is ~0-256 across tables whose numFrames ranges from 4096
# to 524288), so no per-table position rescaling is needed when switching
# wavetables.
SIMPLE_WAVETABLES: dict[str, WavetableDef] = {
    "default": WavetableDef("S2 Tables/Default Shapes.wav", 18432, 44100, 1),
    "analog_basic": WavetableDef("Analog/Basic Shapes.wav", 14336, 44100, 1),
    "analog_warm": WavetableDef("S2 Tables/Analog/DM - OSCAR.wav", 8192, 44100, 1),
    "pwm": WavetableDef("Analog/PWM Juno.wav", 229376, 44100, 1),
    "analog_mini": WavetableDef("Analog/Basic Mini.wav", 8192, 44100, 1),
    "warm_sub": WavetableDef("S2 Tables/Analog/Warm Sub.wav", 4096, 44100, 1),
    "digital_fm": WavetableDef("S2 Tables/Digital/Basic OPL.wav", 16384, 44100, 1),
    "harmonic_smooth": WavetableDef(
        "S2 Tables/Digital/Harmonic Series Smooth.wav", 49152, 44100, 1
    ),
    "dying_sine": WavetableDef("S2 Tables/Digital/Dying Sine.wav", 524288, 44100, 1),
    "acid": WavetableDef("Analog/Acid.wav", 81920, 44100, 1),
    "fm_piano": WavetableDef("S2 Tables/Digital/FM Piano.wav", 4096, 44100, 1),
    "flute": WavetableDef("S2 Tables/Digital/JF Flute.wav", 524288, 44100, 1),
}

# SampleOsc: true one-shot/sample playback engine, selected via
# OSCILLATOR_PARAMS["kParamType"] = "kOsc_Sample". Reverse-engineered from 41
# real factory-preset oscillator slots that use it (see docs/PARAMETER_SCHEMA.md)
# -- there is no VST3-dump cross-check for this engine since the public dump
# this project otherwise relies on doesn't cover it. Shares its warp system
# (same kParamWarpMenu enum) with WTOSC_PARAMS above.
SAMPLEOSC_PARAMS: dict[str, ParamDef] = {
    "kParamWarp": ParamDef(
        "kParamWarp",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        unit="normalized",
        confidence="observed",
    ),
    "kParamWarp2": ParamDef(
        "kParamWarp2",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        unit="normalized",
        confidence="observed",
        notes="Second warp lane; not currently exposed via OscillatorSpec.",
    ),
    "kParamWarpMenu": ParamDef(
        "kParamWarpMenu",
        "enum",
        default="kFM_OSC",
        confidence="observed",
        enum_values=WTOSC_PARAMS["kParamWarpMenu"].enum_values,
        notes="Same raw enum as WTOsc's kParamWarpMenu -- confirmed by cross-referencing "
        "values observed here (kDistSoftClip, kAM_OSC, kPD_FILT1, kFM_NOISE, kFM_OSC2, "
        "kRM_OSC, ...) against WTOSC_PARAMS's already-established enum_values.",
    ),
    "kParamWarpMenu2": ParamDef(
        "kParamWarpMenu2",
        "enum",
        default="kFM_OSC",
        confidence="observed",
        enum_values=WTOSC_PARAMS["kParamWarpMenu"].enum_values,
        notes="Second warp lane's mode; not currently exposed via OscillatorSpec.",
    ),
    "kParamWarpVar2": ParamDef(
        "kParamWarpVar2",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        unit="normalized",
        confidence="uncertain",
        notes="Only 3 distinct values observed (~0.19-0.55); not currently exposed via "
        "OscillatorSpec.",
    ),
}

# Friendly names -> OSCILLATOR_PARAMS["kParamLoopMode"] enum values. "off"
# (the default) isn't in this dict on purpose -- it means omitting
# kParamLoopMode entirely, see that ParamDef's notes.
SIMPLE_SAMPLE_LOOP_MODES: dict[str, str] = {
    "forward": "kForward",
    "ping_pong": "kPingPong",
    "tailed": "kTailed",
}


@dataclass(frozen=True)
class SampleAudioDef:
    """A one-shot audio file copied into Serum's Samples library for the
    SampleOsc engine (slots 0-2, ``OscillatorSpec.sample_playback_source``).

    Structurally identical to :class:`WavetableDef` (same 4 fields Serum
    needs to correctly read a referenced audio file) but kept as a separate
    type since it's a semantically different engine/folder (``Samples/``,
    not ``Tables/``) with its own risk of the same file-metadata-mismatch
    class of bug documented on ``WavetableDef``.
    """

    relative_path: str
    num_frames: int
    sample_rate: int
    num_channels: int


NOISEOSC_PARAMS: dict[str, ParamDef] = {
    "kParamNoiseType": ParamDef(
        "kParamNoiseType",
        "enum",
        default="White",
        confidence="observed",
        enum_values=("White", "Pink", "Brown", "Geiger"),
    ),
    "kParamColor": ParamDef("kParamColor", "float", default=0.5, min=0.0, max=1.0),
    "kParamOneShot": ParamDef("kParamOneShot", "bool", default=False),
}

SUBOSC_PARAMS: dict[str, ParamDef] = {
    "kParamShape": ParamDef(
        "kParamShape",
        "enum",
        default="kSaw",
        confidence="observed",
        enum_values=("kSaw", "kSquare", "kTriangle", "kPulse", "kRoundRect"),
    ),
}

# Friendly names -> SUBOSC_PARAMS["kParamShape"] enum values, offered to
# generation instead of the raw "kXxx" strings.
SIMPLE_SUB_SHAPES: dict[str, str] = {
    "saw": "kSaw",
    "square": "kSquare",
    "triangle": "kTriangle",
    "pulse": "kPulse",
    "round_rect": "kRoundRect",
}

# ---------------------------------------------------------------------------
# Voice filters (VoiceFilter0 / VoiceFilter1 -- Serum's "Filter 1" / "Filter 2").
# `kParamType` enum below is the union of every filter model seen across our
# sample; SIMPLE_FILTER_TYPES is a curated subset of the ones whose behavior
# is unambiguous from naming alone, offered to the LLM mapper for V1.
# ---------------------------------------------------------------------------

VOICE_FILTER_PARAMS: dict[str, ParamDef] = {
    "kParamEnable": ParamDef(
        "kParamEnable",
        "bool",
        default=False,
        confidence="confirmed",
        notes="Both filter slots are OFF by default in a fresh Serum 2 instance.",
    ),
    "kParamType": ParamDef(
        "kParamType",
        "enum",
        default="MgL12",
        confidence="confirmed",
        notes="VST3 default display name is 'MG Low 12' -> CBOR enum 'MgL12'.",
        enum_values=(
            "L6",
            "L12",
            "L18",
            "L24",
            "H6",
            "H12",
            "H18",
            "H24",
            "B12",
            "B24",
            "N24",
            "BN12",
            "NN12",
            "BPN12",
            "BPN24",
            "BandReject",
            "Allpasses",
            "LH12",
            "HB12",
            "LBH12",
            "LBH24",
            "LNH12",
            "LNH24",
            "LPH24",
            "LN12",
            "PP12",
            "HP12",
            "MgL6",
            "MgL12",
            "MgL18",
            "MgL24",
            "LadderMg",
            "LadderAcid",
            "LadderEMS",
            "DirtyMg",
            "Comb2",
            "CombN",
            "CombP",
            "CombH6N",
            "CombHL6P",
            "DistComb2LP",
            "DistComb2BP",
            "FlangeN",
            "FlangeP",
            "FlangePhase12HL6P",
            "Phase24P",
            "Phase36N",
            "Phase36P",
            "Phase48H6P",
            "Phase48HL6P",
            "Phase48P",
            "FormantONE",
            "FormantTWB",
            "FormantTWO",
            "DJMixer",
            "Diffuser",
            "Exp",
            "ExpBPF",
            "PZ_SVF",
            "RM",
            "RMT",
            "Reverb1",
            "Scream",
            "Scream3LP",
            "Wsp",
        ),
    ),
    "kParamFreq": ParamDef(
        "kParamFreq",
        "float",
        default=0.5,
        min=0.0,
        max=1.0,
        unit="normalized cutoff",
        confidence="uncertain",
        notes="0=fully closed, 1=fully open. VST3 dump gives exactly one calibration "
        "point: normalized 0.5 ~= 425 Hz at default resonance. The full Hz curve "
        "(believed log/exponential, ~9 Hz to ~19 kHz) has not been reverse-engineered.",
    ),
    "kParamReso": ParamDef(
        "kParamReso",
        "float",
        default=10.0,
        min=0.0,
        max=100.0,
        unit="%",
        confidence="confirmed",
    ),
    "kParamDrive": ParamDef("kParamDrive", "float", default=0.0, min=0.0, max=100.0, unit="%"),
    "kParamVar": ParamDef(
        "kParamVar",
        "float",
        default=0.0,
        min=0.0,
        max=100.0,
        unit="%",
        notes="'Var' knob; meaning changes per filter type (e.g. comb spacing, formant blend).",
    ),
    "kParamLevelOut": ParamDef(
        "kParamLevelOut", "float", default=0.5, min=0.0, max=1.0, unit="normalized"
    ),
    "kParamStereo": ParamDef(
        "kParamStereo",
        "float",
        default=50.0,
        min=0.0,
        max=100.0,
        unit="%",
        confidence="confirmed",
        notes="50 is centered/neutral, not 0 -- confirmed live (2026-07-28, real Serum 2) "
        "via an isolated A/B test after 0 was found to cause an audible, meter-visible "
        "hard-left bias whenever a VoiceFilter is enabled.",
    ),
    "kParamWet": ParamDef("kParamWet", "float", default=100.0, min=0.0, max=100.0, unit="%"),
    "kParamKeyTrack": ParamDef("kParamKeyTrack", "bool", default=False),
}

# Curated subset with unambiguous, commonly-used semantics -- what the LLM
# mapper offers by name in V1 rather than the full 66-value raw enum above.
SIMPLE_FILTER_TYPES: dict[str, str] = {
    "lowpass_12": "L12",
    "lowpass_24": "L24",
    "highpass_12": "H12",
    "highpass_24": "H24",
    "bandpass_12": "B12",
    "bandpass_24": "B24",
    "notch": "N24",
    "moog_lowpass_12": "MgL12",
    "moog_lowpass_24": "MgL24",
    "comb": "CombN",
    "formant": "FormantONE",
}

# ---------------------------------------------------------------------------
# Envelopes (Env0..Env3). Serum 2 ships 4 general-purpose envelopes; Env0 is
# routed to amp by default in most factory content but nothing in the file
# format hardcodes that -- it's just convention.
# ---------------------------------------------------------------------------

ENV_PARAMS: dict[str, ParamDef] = {
    "kParamAttack": ParamDef(
        "kParamAttack",
        "float",
        default=0.0005,
        min=0.0,
        max=10.0,
        unit="seconds",
        confidence="confirmed",
        notes="VST3 default 0.5ms. Max corrected from 7.0 to 10.0 after finding a real "
        "Factory preset (FX - Wasp Whistle Sweep) with attack=9.46 in the raw CBOR -- "
        "same VST3-dump-undersells-the-real-range pattern as kParamRelease.",
    ),
    "kParamHold": ParamDef("kParamHold", "float", default=0.0, min=0.0, max=5.2, unit="seconds"),
    "kParamDecay": ParamDef(
        "kParamDecay",
        "float",
        default=1.0,
        min=0.0,
        max=32.0,
        unit="seconds",
        confidence="confirmed",
        notes="VST3 default 1.00s.",
    ),
    "kParamSustain": ParamDef(
        "kParamSustain",
        "float",
        default=1.0,
        min=0.0,
        max=1.0,
        unit="normalized",
        confidence="confirmed",
        notes="VST3 default full sustain (0dB).",
    ),
    "kParamRelease": ParamDef(
        "kParamRelease",
        "float",
        default=0.015,
        min=0.0,
        max=32.0,
        unit="seconds",
        confidence="confirmed",
        notes="VST3 default 15ms. Max corrected from 13.0 to 32.0 (matching kParamDecay) "
        "after finding real presets in a third-party bank with release=32.0 written "
        "directly into the CBOR data -- stronger evidence than the VST3 automation-range "
        "dump this field's earlier max came from.",
    ),
    "kParamCurve1": ParamDef(
        "kParamCurve1", "float", default=50.0, min=0.0, max=100.0, unit="curve %"
    ),
    "kParamCurve2": ParamDef(
        "kParamCurve2", "float", default=66.6, min=0.0, max=100.0, unit="curve %"
    ),
    "kParamCurve3": ParamDef(
        "kParamCurve3", "float", default=66.6, min=0.0, max=100.0, unit="curve %"
    ),
}

# ---------------------------------------------------------------------------
# LFOs (LFO0..LFO9 -- 10 slots). Free-shape/curve-drawn LFOs (`curveData`)
# exist alongside these plain params but are not modeled/generated in V1 --
# only rate/mode/basic timing are.
# ---------------------------------------------------------------------------

LFO_PARAMS: dict[str, ParamDef] = {
    "kParamRate": ParamDef(
        "kParamRate",
        "float",
        default=0.0,
        min=0.0,
        max=100.0,
        unit="normalized rate",
        confidence="uncertain",
        notes="Hz/BPM mapping depends on kParamMode and beat-sync flags; not decoded.",
    ),
    "kParamMode": ParamDef(
        "kParamMode",
        "enum",
        default="Free",
        confidence="observed",
        enum_values=("Free", "Retrig", "Envelope"),
        notes="'Retrig' recovered from the plugin binary's debug strings "
        "('Free = 0, Retrig, Envelope, kCount'); never observed in the factory sample.",
    ),
    "kParamBeatSync": ParamDef("kParamBeatSync", "bool", default=False),
    "kParamRise": ParamDef(
        "kParamRise",
        "float",
        default=0.0,
        min=0.0,
        max=5.0,
        unit="seconds",
        notes="Max corrected from 3.0 to 5.0 after finding real Factory presets with "
        "rise up to 4.0 in the raw CBOR.",
    ),
    "kParamSmooth": ParamDef("kParamSmooth", "float", default=0.0, min=0.0, max=100.0, unit="%"),
    "kParamDelay": ParamDef("kParamDelay", "float", default=0.0, min=0.0, max=3.6, unit="seconds"),
}

# ---------------------------------------------------------------------------
# Macros (Macro0..Macro7), global params, mod matrix
# ---------------------------------------------------------------------------

MACRO_PARAMS: dict[str, ParamDef] = {
    "kParamValue": ParamDef("kParamValue", "float", default=0.0, min=0.0, max=100.0, unit="%"),
}

GLOBAL_PARAMS: dict[str, ParamDef] = {
    "kParamMasterVolume": ParamDef(
        "kParamMasterVolume",
        "float",
        default=0.5,
        min=0.0,
        max=1.0,
        unit="normalized (0.5=-9dB)",
        confidence="confirmed",
    ),
    "kParamMonoToggle": ParamDef("kParamMonoToggle", "bool", default=False),
    "kParamPolyCount": ParamDef(
        "kParamPolyCount", "float", default=8.0, min=1.0, max=32.0, unit="voices"
    ),
    "kParamPortamentoTime": ParamDef(
        "kParamPortamentoTime",
        "float",
        default=0.0,
        min=0.0,
        max=3.0,
        unit="seconds",
        notes="Max corrected from 2.6 to 3.0 after finding a real Factory preset "
        "(FX - BHouse Glide - 04) with portamento_time=2.61 in the raw CBOR.",
    ),
}

# ModSlot0..ModSlot63: the mod matrix. Structurally confirmed (destModuleID /
# destModuleParamID / destModuleParamName / destModuleTypeString / source /
# plainParams.kParamAmount). destModuleParamID is CONFIRMED per (type, param)
# pair: sampling every ModSlot across all 626 factory presets, each
# (destModuleTypeString, destModuleParamName) pair maps to exactly one
# destModuleParamID with zero conflicting observations for the params we
# target below (see MOD_DEST_TARGETS) -- these numeric IDs also match the
# C++ enum declarations recovered from the plugin binary's debug strings
# (e.g. Oscillator's `kParamEnable=0, kParamVolume, kParamPan, kParamOctave,
# kParamPitch, kParamFine, kParamCoarsePit, ...`), which is independent
# cross-validation, not just internal consistency.
#
# `source: [sourceId, subIndex]` is PARTIALLY decoded. Clustering all 626
# presets' mod routes by source ID revealed two clean, high-confidence
# blocks (see MOD_SOURCE_IDS below): ids 6-15 (LFO1-10) and ids 25-32
# (Macro1-8), each a contiguous run matching Serum 2's known module count,
# with an internally consistent usage/bipolar signature and a
# monotonically-decreasing per-slot usage curve (slot 1 used most, matching
# the "reach for the first knob" convention seen everywhere else in the
# factory content). This is `observed`, not `confirmed` -- it was not
# cross-checked against Xfer's own source or docs, only statistical
# clustering. Envelope, Velocity, Mod Wheel, Aftertouch, Pitch Bend, Key
# Track and Random/S&H sources remain UNRESOLVED: several candidate IDs
# exist (1-5, 16-24, 34+) but did not cluster into an evidence-backed block.
# See docs/PARAMETER_SCHEMA.md for the full methodology and numbers.
# `subIndex` (source[1]) is not understood at all -- always written as 0.
MODSLOT_PARAMS: dict[str, ParamDef] = {
    "kParamAmount": ParamDef(
        "kParamAmount",
        "float",
        default=0.0,
        min=-100.0,
        max=100.0,
        unit="%",
        confidence="confirmed",
    ),
    "kParamBipolar": ParamDef("kParamBipolar", "bool", default=False),
}

# source name -> ModSlot.source[0]. subIndex (source[1]) is always 0 for
# these two families in every sample observed.
MOD_SOURCE_IDS: dict[str, int] = {
    **{f"lfo{i}": 6 + i for i in range(10)},
    **{f"macro{i}": 25 + i for i in range(8)},
}


@dataclass(frozen=True)
class ModDestDef:
    """A generatable mod-matrix destination: one confirmed
    (destModuleTypeString, destModuleID, destModuleParamName,
    destModuleParamID) tuple."""

    dest_type: str
    dest_id: int
    param_name: str
    param_id: int


# destination name (e.g. "filter0.cutoff") -> ModDestDef. Curated to the
# params confirmed above; the raw destModuleTypeString/destModuleParamName
# vocabulary is larger (see docs/PARAMETER_SCHEMA.md) but not all of it has
# a confirmed destModuleParamID yet.
MOD_DEST_TARGETS: dict[str, ModDestDef] = {}
for _i in range(5):
    MOD_DEST_TARGETS[f"oscillator{_i}.volume"] = ModDestDef("Oscillator", _i, "kParamVolume", 1)
    MOD_DEST_TARGETS[f"oscillator{_i}.pan"] = ModDestDef("Oscillator", _i, "kParamPan", 2)
    MOD_DEST_TARGETS[f"oscillator{_i}.octave"] = ModDestDef("Oscillator", _i, "kParamOctave", 3)
    MOD_DEST_TARGETS[f"oscillator{_i}.pitch"] = ModDestDef("Oscillator", _i, "kParamPitch", 4)
    MOD_DEST_TARGETS[f"oscillator{_i}.fine"] = ModDestDef("Oscillator", _i, "kParamFine", 5)
for _i in range(2):
    MOD_DEST_TARGETS[f"filter{_i}.cutoff"] = ModDestDef("VoiceFilter", _i, "kParamFreq", 3)
    MOD_DEST_TARGETS[f"filter{_i}.resonance"] = ModDestDef("VoiceFilter", _i, "kParamReso", 4)
    MOD_DEST_TARGETS[f"filter{_i}.drive"] = ModDestDef("VoiceFilter", _i, "kParamDrive", 5)
for _i in range(4):
    MOD_DEST_TARGETS[f"env{_i}.attack"] = ModDestDef("Env", _i, "kParamAttack", 0)
    MOD_DEST_TARGETS[f"env{_i}.decay"] = ModDestDef("Env", _i, "kParamDecay", 2)
    MOD_DEST_TARGETS[f"env{_i}.sustain"] = ModDestDef("Env", _i, "kParamSustain", 3)
    MOD_DEST_TARGETS[f"env{_i}.release"] = ModDestDef("Env", _i, "kParamRelease", 4)
for _i in range(3):
    # Wavetable-engine-only destinations (slots 0-2). destModuleTypeString
    # is "WTOsc" here, not "Oscillator" -- confirmed via the same
    # destModuleParamID survey as everything else (kParamTablePos -> 6 in
    # 512/526 samples, kParamWarp -> 0 in 562/562 samples).
    MOD_DEST_TARGETS[f"oscillator{_i}.table_position"] = ModDestDef(
        "WTOsc", _i, "kParamTablePos", 6
    )
    MOD_DEST_TARGETS[f"oscillator{_i}.warp_amount"] = ModDestDef("WTOsc", _i, "kParamWarp", 0)
for _i in range(10):
    MOD_DEST_TARGETS[f"lfo{_i}.rate"] = ModDestDef("LFO", _i, "kParamRate", 0)
for _i in range(8):
    MOD_DEST_TARGETS[f"macro{_i}.value"] = ModDestDef("Macro", _i, "kParamValue", 0)
del _i

# ---------------------------------------------------------------------------
# Effects. Each FXRack (FXRack0..FXRack2) holds an ordered `FX` list; each
# entry has an integer `type` (see FX_TYPE_IDS) selecting which of these
# sub-schemas its `plainParams` follows, plus a shared `kUIParamMixOrGain`.
# ---------------------------------------------------------------------------

FX_TYPE_IDS: dict[int, str] = {
    0: "FXDistortion",
    1: "FXFlanger",
    2: "FXPhaser",
    3: "FXChorus",
    4: "FXDelay",
    5: "FXComp",
    6: "FXReverb",
    7: "FXEQ",
    8: "FXFilter",
    9: "FXHyperD",
    10: "FXBode",
    11: "FXConv",
    12: "FXUtils",
    13: "FXSplit",
    14: "FXSplit3",
    15: "FXSplitMS",
}

FX_PARAMS: dict[str, dict[str, ParamDef]] = {
    "FXDistortion": {
        "kParamMode": ParamDef(
            "kParamMode",
            "enum",
            default="kOverdrive",
            enum_values=(
                "kAsym",
                "kDiode1",
                "kDiode2",
                "kDownsample",
                "kHardClip",
                "kLinFold",
                "kOverdrive",
                "kRectify",
                "kSinFold",
                "kSineShaper",
                "kSoftClip",
                "kSoftSat",
                "kStompBox",
                "kTapeSat",
                "kXShaper",
                "kZeroSquare",
            ),
        ),
        "kParamDrive": ParamDef("kParamDrive", "float", default=50.0, min=0.0, max=100.0, unit="%"),
        "kParamWet": ParamDef("kParamWet", "float", default=100.0, min=0.0, max=100.0, unit="%"),
        "kParamFreq": ParamDef(
            "kParamFreq", "float", default=1.0, min=0.0, max=1.0, unit="normalized"
        ),
        "kParamNumStages": ParamDef("kParamNumStages", "float", default=2.0, min=2.0, max=7.0),
    },
    "FXChorus": {
        "kParamRate": ParamDef(
            "kParamRate", "float", default=0.5, min=0.0, max=1.4, unit="Hz (approx.)"
        ),
        "kParamDepth": ParamDef(
            "kParamDepth", "float", default=10.0, min=0.0, max=25.2, unit="ms (approx.)"
        ),
        "kParamDelay": ParamDef(
            "kParamDelay", "float", default=5.0, min=0.0, max=12.8, unit="ms (approx.)"
        ),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=0.0, min=0.0, max=58.2, unit="%"
        ),
        "kParamFilt": ParamDef(
            "kParamFilt", "float", default=2000.0, min=50.0, max=20000.0, unit="Hz"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=50.0, min=0.0, max=100.0, unit="%"),
    },
    "FXFlanger": {
        "kParamRate": ParamDef(
            "kParamRate", "float", default=0.5, min=0.0, max=5.1, unit="Hz (approx.)"
        ),
        "kParamDepth": ParamDef("kParamDepth", "float", default=50.0, min=0.0, max=100.0, unit="%"),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=50.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamWidth": ParamDef(
            "kParamWidth", "float", default=180.0, min=0.0, max=360.0, unit="degrees"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=50.0, min=0.0, max=100.0, unit="%"),
    },
    "FXPhaser": {
        "kParamRate": ParamDef(
            "kParamRate", "float", default=1.0, min=0.0, max=20.0, unit="Hz (approx.)"
        ),
        "kParamDepth": ParamDef("kParamDepth", "float", default=50.0, min=0.0, max=100.0, unit="%"),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamFreq": ParamDef(
            "kParamFreq", "float", default=800.0, min=20.0, max=2563.0, unit="Hz"
        ),
        "kParamNumPoles": ParamDef("kParamNumPoles", "float", default=4.0, min=1.0, max=18.0),
        "kParamWet": ParamDef("kParamWet", "float", default=50.0, min=0.0, max=100.0, unit="%"),
    },
    "FXDelay": {
        "kParamTimeL": ParamDef(
            "kParamTimeL", "float", default=0.25, min=0.001, max=0.34, unit="seconds"
        ),
        "kParamTimeR": ParamDef(
            "kParamTimeR", "float", default=0.25, min=0.001, max=0.32, unit="seconds"
        ),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=30.0, min=0.0, max=83.3, unit="%"
        ),
        "kParamFreq": ParamDef(
            "kParamFreq",
            "float",
            default=8000.0,
            min=49.6,
            max=17981.0,
            unit="Hz",
            notes="Delay tap tone filter frequency.",
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=30.0, min=0.0, max=100.0, unit="%"),
    },
    "FXReverb": {
        "kParamType": ParamDef(
            "kParamType",
            "enum",
            default="kHall",
            enum_values=("kAbyss", "kHall", "kSpace", "kVintage"),
        ),
        "kParamSize": ParamDef("kParamSize", "float", default=50.0, min=0.0, max=100.0, unit="%"),
        "kParamDelay": ParamDef(
            "kParamDelay", "float", default=20.0, min=0.0, max=250.0, unit="ms"
        ),
        "kParamWidth": ParamDef(
            "kParamWidth", "float", default=100.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=30.0, min=0.0, max=100.0, unit="%"),
    },
    "FXComp": {
        "kParamThresh": ParamDef(
            "kParamThresh", "float", default=0.5, min=0.0, max=0.95, unit="normalized"
        ),
        "kParamRatio": ParamDef(
            "kParamRatio", "float", default=4.0, min=1.1, max=1_000_000.0, unit="ratio:1"
        ),
        "kParamAttack": ParamDef(
            "kParamAttack", "float", default=10.0, min=0.1, max=1000.0, unit="ms"
        ),
        "kParamRelease": ParamDef(
            "kParamRelease", "float", default=100.0, min=0.1, max=1000.0, unit="ms"
        ),
        "kParamMakeup": ParamDef(
            "kParamMakeup", "float", default=1.0, min=1.0, max=25.8, unit="gain factor"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=100.0, min=0.0, max=100.0, unit="%"),
    },
    "FXEQ": {
        "kParamFreq1": ParamDef(
            "kParamFreq1", "float", default=200.0, min=21.5, max=9454.0, unit="Hz"
        ),
        "kParamFreq2": ParamDef(
            "kParamFreq2", "float", default=4000.0, min=21.5, max=20000.0, unit="Hz"
        ),
        "kParamGain1": ParamDef(
            "kParamGain1", "float", default=0.0, min=-24.0, max=24.0, unit="dB"
        ),
        "kParamGain2": ParamDef(
            "kParamGain2", "float", default=0.0, min=-24.0, max=24.0, unit="dB"
        ),
        "kParamReso1": ParamDef(
            "kParamReso1", "float", default=0.0, min=0.0, max=69.6, unit="Q (approx.)"
        ),
        "kParamReso2": ParamDef(
            "kParamReso2", "float", default=0.0, min=0.0, max=79.0, unit="Q (approx.)"
        ),
    },
    "FXFilter": {
        "kParamType": ParamDef(
            "kParamType",
            "enum",
            default="L12",
            enum_values=tuple(VOICE_FILTER_PARAMS["kParamType"].enum_values),
            notes="Same filter model catalog as VoiceFilter, minus a few voice-only variants.",
        ),
        "kParamFreq": ParamDef(
            "kParamFreq", "float", default=0.5, min=0.0, max=1.0, unit="normalized cutoff"
        ),
        "kParamReso": ParamDef("kParamReso", "float", default=10.0, min=0.0, max=100.0, unit="%"),
        "kParamDrive": ParamDef("kParamDrive", "float", default=0.0, min=0.0, max=100.0, unit="%"),
        "kParamWet": ParamDef("kParamWet", "float", default=100.0, min=0.0, max=100.0, unit="%"),
    },
    # Frequency shifter ("Bode Shifter"). All bounds/defaults observed
    # empirically; destModuleParamID not confirmed for any of these (never
    # seen as a mod-matrix destination in our sample), so they aren't in
    # MOD_DEST_TARGETS.
    "FXBode": {
        "kParamShift": ParamDef(
            "kParamShift", "float", default=0.0, min=-100.0, max=73.4, unit="% (approx.)"
        ),
        "kParamRange": ParamDef(
            "kParamRange", "float", default=100.0, min=0.1, max=3043.2, unit="Hz (approx.)"
        ),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamBlur": ParamDef("kParamBlur", "float", default=0.0, min=0.0, max=100.0, unit="%"),
        "kParamDelayTime": ParamDef(
            "kParamDelayTime", "float", default=0.0, min=0.0, max=1.62, unit="seconds (approx.)"
        ),
        "kParamOutputWidth": ParamDef(
            "kParamOutputWidth", "float", default=0.0, min=0.0, max=96.5, unit="%"
        ),
        "kParamOutputMix": ParamDef(
            "kParamOutputMix", "float", default=0.0, min=-73.9, max=100.0, unit="%"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=30.0, min=0.0, max=100.0, unit="%"),
    },
    # "Hyper Dimension" stereo widener/unison-style FX.
    "FXHyperD": {
        "kParamRate": ParamDef("kParamRate", "float", default=0.0, min=0.0, max=100.0, unit="%"),
        "kParamDetune": ParamDef(
            "kParamDetune", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamUnison": ParamDef("kParamUnison", "float", default=0.0, min=0.0, max=7.0),
        "kParamDimESize": ParamDef(
            "kParamDimESize", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamDimEWet": ParamDef(
            "kParamDimEWet", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=50.0, min=0.0, max=100.0, unit="%"),
    },
    # Convolution reverb (loads an impulse response file, `relativePathToIR`
    # -- not modeled here, generation can't select an IR yet).
    "FXConv": {
        "kParamSize": ParamDef(
            "kParamSize", "float", default=100.0, min=10.0, max=1000.0, unit="% (IR stretch)"
        ),
        "kParamDecay": ParamDef(
            "kParamDecay", "float", default=1.0, min=0.0, max=40.0, unit="seconds (approx.)"
        ),
        "kParamTone": ParamDef("kParamTone", "float", default=0.0, min=-100.0, max=84.2, unit="%"),
        "kParamIpTrim": ParamDef(
            "kParamIpTrim", "float", default=0.0, min=-34.0, max=6.0, unit="dB"
        ),
        "kParamDamping": ParamDef(
            "kParamDamping", "float", default=50.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=30.0, min=0.0, max=100.0, unit="%"),
    },
    # Stereo/frequency utility (width, balance, HP/LP cleanup) -- no single
    # coherent "wet" behavior observed (only 2 samples), included for
    # completeness but low confidence.
    "FXUtils": {
        "kParamWidth": ParamDef(
            "kParamWidth", "float", default=100.0, min=0.0, max=800.0, unit="%"
        ),
        "kParamBalance": ParamDef(
            "kParamBalance", "float", default=0.0, min=-100.0, max=100.0, unit="%"
        ),
        "kParamHPF": ParamDef(
            "kParamHPF", "float", default=20.0, min=1.3, max=400.0, unit="Hz (approx.)"
        ),
        "kParamLPF": ParamDef(
            "kParamLPF", "float", default=20000.0, min=50.0, max=18976.0, unit="Hz (approx.)"
        ),
        "kParamLFXover": ParamDef(
            "kParamLFXover", "float", default=150.0, min=20.25, max=300.0, unit="Hz (approx.)"
        ),
        "kParamWet": ParamDef(
            "kParamWet",
            "float",
            default=100.0,
            min=0.0,
            max=100.0,
            unit="%",
            confidence="uncertain",
            notes="Only 2 samples observed; FXUtils may not meaningfully use a wet knob.",
        ),
    },
}

# FXSplit / FXSplit3 / FXSplitMS (band-splitter racks: each holds N nested
# sub-effect-chains, one per frequency band, via kParamModuleCount1/2/3) are
# structurally different from every other FX type -- not a flat plainParams
# effect but a container for further FX lists. Cataloged in FX_TYPE_IDS
# (round-trips fine) but NOT modeled in FX_PARAMS; generation cannot target
# them. A real implementation would need a recursive FxUnitSpec.

ALL_FX_TYPES: tuple[str, ...] = tuple(FX_TYPE_IDS.values())
