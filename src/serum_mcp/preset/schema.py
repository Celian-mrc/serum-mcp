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
        min=-80.0,
        max=80.0,
        unit="cents (approx.)",
        notes="Bounds widened from +/-50 after finding real presets with fine=67.2, -63.0, "
        "and 76.2.",
    ),
    "kParamCoarsePit": ParamDef(
        "kParamCoarsePit",
        "float",
        default=0.0,
        min=-72.0,
        max=72.0,
        unit="semitones",
        notes="Bounds widened from -24/48 after finding real presets with coarsePit=-64.0 "
        "and 60.26.",
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
        enum_values=("kForward", "kPingPong", "kTailed", "kReverse"),
        notes="SampleOsc only. Absent from plainParams in every factory preset that "
        "doesn't loop its sample (i.e. a true one-shot) -- there is no observed 'off' "
        "enum value, omitting the key entirely is what turns looping off. kReverse "
        "found live in real Factory content, not yet exposed via SIMPLE_SAMPLE_LOOP_MODES/"
        "OscillatorSpec.sample_loop.",
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
            "kAM_SUB",
            "kASYMNeg",
            "kASYMPos",
            "kASYMPosNeg",
            "kBendNeg",
            "kBendPos",
            "kBendPosNeg",
            "kDLM",
            "kDistAsym",
            "kDistDiode1",
            "kDistDiode2",
            "kDistHardClip",
            "kDistLinFold",
            "kDistSineShaper",
            "kDistSinFold",
            "kDistSoftClip",
            "kDistSoftSat",
            "kDistStompBox",
            "kDistTapeSat",
            "kDistTube",
            "kDistZeroSquare",
            "kEvenOdd",
            "kFMP_NOISE",
            "kFMP_OSC",
            "kFMX_NOISE",
            "kFMX_OSC",
            "kFMX_OSC2",
            "kFM_FILT1",
            "kFM_FILT2",
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
        notes="'Warp mode A'. Union of values observed across samples (expanded again "
        "after checking real Factory/third-party content: kAM_SUB, kASYMPosNeg, "
        "kDistAsym, kDistStompBox, kDistTapeSat, kDistZeroSquare, kFM_FILT1). The true "
        "full enum (from Serum's UI dropdown) may still be a superset.",
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
    # A SECOND, independent warp lane -- found live 2026-07-29 diagnosing why
    # a recreated preset ("Galaxy") kept sounding harsh/"8-bit" despite
    # every other parameter this project modeled matching the original
    # closely: Osc A's raw data had a second warp stage (kFM_NOISE primary,
    # THEN kFilterLPF secondary at 56%) taming the otherwise-raw FM-by-noise
    # character -- completely absent from the recreation since neither this
    # key nor kParamWarpMenu2 was exposed via OscillatorSpec, only
    # kParamWarp2 had a (never-wired-up) ParamDef. Surveyed across all 886
    # real presets: 193 WTOsc slots use it, with the identical raw enum
    # catalog as the primary kParamWarpMenu (same WTOSC_PARAMS["kParamWarpMenu"]
    # .enum_values) -- not a special/reduced set.
    "kParamXfadeMode": ParamDef(
        "kParamXfadeMode",
        "float",
        default=1.0,
        min=0.0,
        max=1.0,
        confidence="observed",
        notes="How the primary/secondary warp lanes combine. Only ever observed at 1.0 "
        "(46 samples) whenever a second lane is in use -- written automatically "
        "alongside kParamWarp2/kParamWarpMenu2 rather than exposed as its own "
        "OscillatorSpec field, since no other value has ever been seen.",
    ),
}
# enum_values can't reference a sibling dict entry inline above (WTOSC_PARAMS
# isn't finished building yet at that point) -- patched in immediately after.
WTOSC_PARAMS["kParamWarpMenu2"] = ParamDef(
    "kParamWarpMenu2",
    "enum",
    default="kFM_OSC",
    confidence="observed",
    enum_values=WTOSC_PARAMS["kParamWarpMenu"].enum_values,
    notes="Second warp lane's mode -- same raw enum as kParamWarpMenu (confirmed: "
    "every value observed here across 886 real presets is already in that enum).",
)
# A THIRD, separate warp-related float -- genuinely distinct from
# kParamWarp2 (confirmed: both keys co-occur in the same real WTOsc
# plainParams dict in some samples). Rarer (14 WTOsc slots observed vs 193
# for kParamWarp2) and its exact role is unconfirmed -- possibly a
# secondary-lane-specific fine control, by analogy with kParamWarp2 sharing
# a "2" suffix pattern with kParamWarpMenu2. Found live 2026-07-29 as a
# real, unreproduced mod-matrix DESTINATION on a real preset's primary
# oscillator (lfo -> kParamWarpVar2, destModuleParamID confirmed 4) even
# though that specific oscillator had no explicit BASE value for it in
# plainParams -- Serum evidently has its own internal default when the key
# is absent, same as any other engine param.
WTOSC_PARAMS["kParamWarpVar2"] = ParamDef(
    "kParamWarpVar2",
    "float",
    default=0.0,
    min=0.0,
    max=1.0,
    unit="normalized",
    confidence="uncertain",
    notes="Only 3 distinct base values observed (~0.19-0.55) across 14 WTOsc slots; "
    "exact role vs. kParamWarp2 unconfirmed.",
)

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
            # Found live checking real Factory/third-party content (not in the
            # original 66-value VST3-dump survey):
            "ADD_BASS",
            "BEQ12",
            "BP12",
            "CombHL6N",
            "CombL6N",
            "Combs",
            "DistComb1BP",
            "DistComb1LP",
            "FlangeH6P",
            "FlangeL6P",
            "HEQ12",
            "HN12",
            "LB12",
            "N12",
            "P12",
            # More found checking FXFilter usage specifically (shares this
            # same enum -- see FX_PARAMS["FXFilter"]["kParamType"] below):
            "FlangeHL6N",
            "HEQ6",
            "LPH12",
            "PN12",
            "Phase12N",
            "Phase12P",
            "SNH1",
            "ZDF_A",
            # Third pass, found via a full edit round-trip stress test across
            # 844 real presets (Factory + several third-party banks):
            "Scream3BP",
            "Phase48HL6N",
            "Phase48N",
            "FlangeHL6P",
            "Phase24N",
            "FlangeL6N",
            "SNH2",
            "CombH6P",
            "LEQ12",
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
# LFOs (LFO0..LFO9 -- 10 slots). Free-shape/curve-drawn LFOs (`curveData`,
# point-based: {curveVals, numPoints, xVals, yVals}) exist alongside these
# plain params and are still NOT modeled/generated -- most basic shapes
# (sine/triangle/square/saw/etc) are stored purely as curve points, not a
# named type, and decoding that point format is out of scope for now.
#
# `kParamType`, found live 2026-07-29 while diagnosing why a recreated
# preset ("Galaxy") sounded nothing like the real one despite every other
# parameter matching -- the real preset's busiest LFO turned out to be set
# to Sample & Hold, which the UI shows as "S&H" but the raw file calls
# `kParamType: "RandomSH"`. This is DIFFERENT from a hand-drawn curve: it's
# one of a handful of named, purely-algorithmic LFO shapes Serum computes
# procedurally (no curveData needed for most of them), so -- unlike the
# general curve-shape gap above -- these ARE cheaply generatable. Surveyed
# across all 886 real .SerumPreset files on this machine: exactly 4 named
# values appear (`Rossler`/363, `Lorenz`/337, `RandomSH`/127, `Path`/36,
# all chaotic-attractor or randomization algorithms -- Rossler/Lorenz are
# genuine strange attractors used for organic modulation, "Path" is
# unconfirmed but likely a traced-path oscillator). The key is ABSENT
# (not some other value) in the other ~3500 LFO slots sampled -- 2851 use
# curveData instead (a real hand-drawn or built-in-preset curve), 656 are
# plain/untouched defaults. `default=None` here (not a string) to preserve
# that three-way distinction -- see SIMPLE_LFO_TYPES.
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
        notes="Hz/BPM mapping depends on kParamMode and beat-sync flags; mostly not "
        "decoded, but 2026-07-29 empirical probing (real Serum, an LFO explicitly set "
        "then read back raw) DID confirm two points: with kParamBeatSync absent (its own "
        "true default, confirmed separately -- see LFO_PARAMS notes), setting the RATE "
        "knob to exactly '1/8' writes kParamRate=10.66; setting it back to '1/4' makes "
        "Serum omit the key again -- i.e. '1/4' BPM-synced IS the genuine absent-state "
        "default (not a UI placeholder), confirming mapping.py's omit-when-default fix "
        "is correct. The full Hz/BPM curve beyond these 2 points is still not decoded.",
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
    "kParamBeatSync": ParamDef(
        "kParamBeatSync",
        "bool",
        default=False,
        notes="The schema default (False/free-Hz) is NOT the genuine absent-state "
        "default -- confirmed live 2026-07-29 (real preset screenshot + empirical "
        "probing, see kParamRate above): an untouched LFO is BPM-synced by default. "
        "mapping.py omits this key when False rather than writing it explicitly, "
        "letting Serum fall back to its own (beat-synced) default correctly.",
    ),
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
    "kParamType": ParamDef(
        "kParamType",
        "enum",
        default=None,
        confidence="observed",
        enum_values=("Rossler", "Lorenz", "RandomSH", "Path"),
        notes="Named algorithmic LFO shape -- absent (None) is a real, common state "
        "(plain/curve-drawn LFO), not 'unset'/'default Rossler' or similar. See the "
        "module comment above for the 886-preset survey this came from. NOT yet "
        "confirmed live for GENERATION (only observed being read from real files) -- "
        "whether writing kParamType alone, without any curveData, is sufficient for "
        "Serum to render it correctly hasn't been tested in real Serum yet.",
    ),
    "kParamMono": ParamDef(
        "kParamMono",
        "bool",
        default=False,
        confidence="observed",
        notes="Found live 2026-07-29 diagnosing a recreated preset that still sounded "
        "'8-bit' after fixing the LFO shape/filter/warp-lane gaps: the real preset's "
        "user reported its LFO visibly kept moving even with no note held, while the "
        "recreation's didn't -- traced to this key, present (always =1.0 when present, "
        "63/4374 real LFO slots surveyed) only on that preset's busiest LFO (rate 100, "
        "RandomSH shape, driving a fast-arpeggiated oscillator). Hypothesis: a "
        "non-mono/per-voice LFO restarts its phase at every note-on, so under a fast "
        "arp it gets reset almost every step and never completes a meaningful cycle -- "
        "'mono' instead runs one shared, continuously-free-running instance "
        "independent of note-on events, which would also read as 'moving without "
        "notes' and, since it isn't constantly reset, less choppy/'faster'-feeling.",
    ),
    "kParamSwing": ParamDef(
        "kParamSwing",
        "float",
        default=0.0,
        min=0.0,
        max=1.0,
        confidence="uncertain",
        notes="Only ever observed at 1.0 (9/4374 real LFO slots). Presumed to affect "
        "timing/shuffle of a stepped (e.g. RandomSH) LFO's steps, by analogy with "
        "'swing' elsewhere in music software, but not independently confirmed.",
    ),
    # Found live 2026-07-29, same session as mono/swing above -- always 1.0
    # when present (never 0.0), same "sentinel bool" pattern. dotted/
    # triplets mirror the arpeggiator's own identically-named fields
    # (ARPCLIP_PARAMS); rate10x is LFO-specific, presumed a x10 rate
    # multiplier (unconfirmed) -- meaningful for the very-low-rate chaotic
    # LFO shapes (Rossler/Lorenz), where it could be the difference between
    # a near-static and a clearly-moving modulation.
    "kParamDotted": ParamDef("kParamDotted", "bool", default=False, confidence="observed"),
    "kParamTriplets": ParamDef("kParamTriplets", "bool", default=False, confidence="observed"),
    "kParamRate10x": ParamDef(
        "kParamRate10x", "bool", default=False, confidence="uncertain",
        notes="Presumed x10 rate multiplier, not independently confirmed. 599/4384 real "
        "LFO slots surveyed (14%), always 1.0 when present.",
    ),
}

# Friendly names -> LFO_PARAMS["kParamType"].enum_values, offered to
# generation instead of the raw "kXxx"-less raw strings (these ones happen
# to already be readable Serum-internal names, unlike most other raw enums
# in this schema, but kept lowercase/snake_case for consistency with every
# other SIMPLE_* dict).
SIMPLE_LFO_TYPES: dict[str, str] = {
    "random_sh": "RandomSH",
    "rossler": "Rossler",
    "lorenz": "Lorenz",
    "path": "Path",
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
    "kParamLimitSameNotePolyphony": ParamDef(
        "kParamLimitSameNotePolyphony",
        "bool",
        default=False,
        confidence="observed",
        notes="Found live 2026-07-29 comparing a recreated preset's Global0 against the "
        "original's -- present (always True when present) on 325/832 real Global0 slots "
        "surveyed (39%). Presumed to limit voice-stacking when the SAME note is "
        "retriggered rapidly (e.g. under a fast arp) rather than letting overlapping "
        "voices for one note pile up -- not independently confirmed.",
    ),
    # Found live 2026-07-30 via a VST3 binary string dump
    # ('kParamMasterVolume = 0, ... kParamDirectVol, kParamFXBus1Vol,
    # kParamFXBus2Vol, kNumAutomatableParams' and, from kParamPolyCount's
    # own private-param enum, 'kParamFXBus1Dest, kParamFXBus2Dest') while
    # investigating the RoutingSlot system (see docs/PARAMETER_SCHEMA.md
    # §5): these are the GLOBAL counterparts to each RoutingSlot's own
    # per-oscillator/filter kParamFXBus1Level/kParamFXBus2Level send
    # amount -- a source sends X% of its signal to a bus via its own
    # RoutingSlot, and this bus's aggregate level/destination is set once,
    # here. Confirmed real via a corpus survey (855 real Global0 slots):
    # kParamDirectVol 2.0%, kParamFXBus1Vol 6.1%, kParamFXBus2Vol 5.1%,
    # kParamFXBus1Dest 3.4%, kParamFXBus2Dest 2.1% presence. None wired
    # into GlobalSpec/generation.
    "kParamDirectVol": ParamDef(
        "kParamDirectVol", "float", default=1.0, min=0.0, max=None, confidence="observed",
        notes="Volume for signal from any source routed with "
        "RoutingSlot.kParamRoutingDest='kRoutingDestDirect' (bypasses both filters AND "
        "the FX bus system entirely). Real values seen 0.21-0.43 -- well below the "
        "presumed unity default, uncertain why.",
    ),
    "kParamFXBus1Vol": ParamDef(
        "kParamFXBus1Vol", "float", default=1.0, min=0.0, max=None, confidence="observed",
        notes="Aggregate volume for FX Bus 1 (fed by any source's "
        "RoutingSlot.kParamFXBus1Level send). Real values seen 0.26-1.75 -- CAN exceed "
        "1.0 (a real boost/gain stage, not just 0-100% attenuation like most params "
        "in this schema).",
    ),
    "kParamFXBus2Vol": ParamDef(
        "kParamFXBus2Vol", "float", default=1.0, min=0.0, max=None, confidence="observed",
        notes="Same as kParamFXBus1Vol, for FX Bus 2.",
    ),
    "kParamFXBus1Dest": ParamDef(
        "kParamFXBus1Dest", "float", default=0.0, min=0.0, max=3.0, confidence="observed",
        notes="Decoded 2026-07-30 by a full-corpus survey (626 real Factory presets, 14 "
        "with this key present): every value observed was 1.0 or 2.0, NEVER 0.0 or 3.0 "
        "-- exactly the two RoutingSlot.kParamRoutingDest ordinals that make sense as a "
        "post-FX bus return (kRoutingDestMaster=1: straight to main output; "
        "kRoutingDestDirect=2: a separate bypass path) and never the two that wouldn't "
        "(kRoutingDestFilter=0: nonsensical, already downstream of the filter stage; "
        "kRoutingDestNone=3: would silence the whole processed bus). Shares the same "
        "MEANING as RoutingSlot's kParamRoutingDest but NOT the same storage kind -- "
        "unlike RoutingSlot (which stores this enum as a literal string, e.g. "
        "'kRoutingDestFilter'), Global0 stores it as a raw float ordinal (1.0/2.0), "
        "confirmed directly against real Factory CBOR. kind stays 'float' here for that "
        "reason; GlobalSpec.fx_bus1_destination/mapping.py does the "
        "'master'/'direct'<->1.0/2.0 translation instead. default=0.0 (kRoutingDestFilter's "
        "ordinal) is assumed by that same-enum convention, NOT independently confirmed -- "
        "genuine absent-key behavior was never isolated since real content only ever "
        "writes 1.0/2.0 explicitly. Where FX Bus 1's OWN processed signal (after passing "
        "through its FX chain) rejoins the main path -- distinct from "
        "GLOBAL_PARAMS['kParamFXBus1Vol'] (that bus's aggregate level) and "
        "ROUTING_SLOT_PARAMS['kParamFXBus1Level'] (how much of a given source is SENT "
        "into the bus to begin with).",
    ),
    "kParamFXBus2Dest": ParamDef(
        "kParamFXBus2Dest", "float", default=0.0, min=0.0, max=3.0, confidence="observed",
        notes="Same as kParamFXBus1Dest, for FX Bus 2 (6 real occurrences of 1.0, 2 of "
        "2.0 in the same 626-preset survey).",
    ),
}

# RoutingSlot0-6: per-source (5 oscillators) and per-filter (2 filters)
# signal routing, discovered live 2026-07-29 recreating UN_PLACES_PL_Dreams
# (see docs/REAL_SERUM_TESTING.md and PARAMETER_SCHEMA.md §5 items 11-12)
# and expanded 2026-07-30 via a VST3 binary string dump of the module's
# full param enums. RoutingSlot0-4 = the 5 oscillators' own routing choice;
# RoutingSlot5/6 = each of the 2 filters' OWN output routing (confirmed via
# a user-provided MIX-tab screenshot: "MAIN" = kRoutingDestMaster, i.e.
# parallel/direct-to-output; "FILTER" = kRoutingDestFilter, i.e. serial,
# cascaded into the other filter). Genuine absence (both untouched) is the
# overwhelmingly common real state (450-770 of ~900 samples per slot,
# see the round-3 survey in REAL_SERUM_TESTING.md) and resolves to
# kRoutingDestFilter for oscillators, kRoutingDestMaster for filters --
# NOT the same default across the two families. Not wired into PresetSpec
# at all -- every use so far has been a one-off raw-CBOR patch reproducing
# a real preset's exact values.
ROUTING_SLOT_PARAMS: dict[str, ParamDef] = {
    "kParamRoutingDest": ParamDef(
        "kParamRoutingDest",
        "enum",
        default="kRoutingDestFilter",
        enum_values=("kRoutingDestFilter", "kRoutingDestMaster", "kRoutingDestDirect", "kRoutingDestNone"),
        confidence="observed",
        notes="Ordinal values confirmed via VST3 binary string dump: kRoutingDestFilter=0, "
        "kRoutingDestMaster=1, kRoutingDestDirect=2, kRoutingDestNone=3. For an "
        "oscillator: Filter=normal (goes through VoiceFilter0/1, see kParamFilterBalance), "
        "Master=bypasses filters straight to the main output, Direct=bypasses filters AND "
        "the FX bus system (see GLOBAL_PARAMS['kParamDirectVol']), None=goes to neither "
        "filter nor master by default (typically paired with an explicit "
        "kParamFXBus1Level/2Level send instead). For a filter's own slot (5/6): Filter="
        "cascade into the OTHER filter (serial), Master=direct to output (parallel) -- "
        "confirmed live, this was the root cause of a real preset sounding wrongly "
        "double-filtered/serial when it should have been parallel (see the fixture-bug "
        "writeup in PARAMETER_SCHEMA.md §5).",
    ),
    "kParamFilterBalance": ParamDef(
        "kParamFilterBalance", "float", default=0.0, min=0.0, max=100.0, confidence="observed",
        notes="Only meaningful when kParamRoutingDest='kRoutingDestFilter' and BOTH "
        "filters are in use -- balance between Filter 1 and Filter 2. Exact scale "
        "(0=Filter1-only vs 50/50 vs Filter2-only) not independently confirmed; a real "
        "Dreams route used 100.0 alongside Osc A+B+Noise visually confirmed feeding "
        "Filter 2 in the real UI, suggesting higher values lean toward Filter 2.",
    ),
    "kParamFXBus1Level": ParamDef(
        "kParamFXBus1Level", "float", default=0.0, min=0.0, max=100.0, confidence="observed",
        notes="% of this source's signal sent to FX Bus 1 (see "
        "GLOBAL_PARAMS['kParamFXBus1Vol']), independent of kParamRoutingDest's main "
        "destination -- a genuine aux send, not mutually exclusive with it.",
    ),
    "kParamFXBus2Level": ParamDef(
        "kParamFXBus2Level", "float", default=0.0, min=0.0, max=100.0, confidence="observed",
        notes="Same as kParamFXBus1Level, for FX Bus 2.",
    ),
    "kParamViaEnv1": ParamDef(
        "kParamViaEnv1", "bool", default=False, confidence="uncertain",
        notes="Found live 2026-07-30 via VST3 binary string dump -- presumably gates or "
        "modulates the routing choice itself via Envelope 1, but every one of 49 real "
        "occurrences surveyed had this at 0.0 (False) -- never observed actually "
        "enabled, so the presumption is unconfirmed and likely low-impact even if "
        "correct.",
    ),
}

# Serum 2's arpeggiator: a single on/off toggle (`Arp0`) plus 12 pattern
# "clip" slots (`ArpClip0..11`), only one of which is normally used
# (`Arp0.kParamActiveClipID` selects which; almost always absent/0 in real
# content). Reverse-engineered by inspecting all 180 presets in a real
# third-party bank (Unmute's "Places") -- 15 had the arp enabled. An
# unpopulated ArpClip slot has `plainParams: "default"` (same sentinel as
# VoiceFilter/FXRack when untouched) and `clip: {}`.
#
# `kParamShape` (and the separate `kParamTransposeShape`, which modulates
# transposition independently using the *same* enum) selects the pattern
# algorithm. Two DISTINCT modes exist and this project only generates one:
# - Algorithmic (Played, Chord, Converge, RandOnce, RandDrift, RandNoDup,
#   and very likely Up/Down/UpDown/ThumbUp given "Down"/"ThumbUp"/"Diverge"
#   were observed on kParamTransposeShape -- GENERATABLE, see ArpSpec.
# - "Pattern": a real hand-drawn MIDI-clip-like note list lives in this
#   clip's own `clip.notes` array (each note: noteNum/timeStamp/length/
#   channel/an 8-float "attributes" vector whose exact meaning isn't
#   decoded, always identical across every note observed here/expressionEvents).
#   Actually the single MOST COMMON shape in the real sample (9/23 populated
#   clips) -- NOT modeled yet, out of scope for this pass. Selecting
#   shape="pattern" via ArpSpec is rejected with a clear error rather than
#   silently writing an empty/broken pattern.
ARP_PARAMS: dict[str, ParamDef] = {
    "kParamEnabled": ParamDef("kParamEnabled", "bool", default=False, confidence="observed"),
    "kParamActiveClipID": ParamDef(
        "kParamActiveClipID",
        "float",
        default=0.0,
        min=0.0,
        max=11.0,
        unit="ArpClip slot index",
        confidence="observed",
        notes="Almost always absent in real content (implicitly slot 0) -- this "
        "project always writes to ArpClip0 and never sets this explicitly.",
    ),
    "kParamLaunchQuantize": ParamDef(
        "kParamLaunchQuantize",
        "float",
        default=0.0,
        min=0.0,
        max=32.0,
        unit="uncertain",
        confidence="uncertain",
        notes="Observed values 0.0/10.0/12.0 across only 4 samples -- real unit/"
        "meaning (beats? steps?) not established. Not currently exposed via ArpSpec.",
    ),
}

# Curated subset of the real (larger, per the module comment above) shape
# enum -- only values directly observed in real CBOR data, to avoid writing
# an unconfirmed string Serum might reject or silently reinterpret. Widened
# after a second pass across all 844 real presets available (Factory + 6
# third-party banks, not just the original 180-preset sample) -- turned up
# 6 more confirmed shapes, including UpDown (the 2nd most common value
# overall after Pattern). The distinction between e.g. "UpDown" and
# "DownAndUp" vs "UpAndDown" and "DownUp" (4 separate raw values, all
# observed) is NOT understood -- likely a real difference in whether the
# turnaround note at top/bottom repeats, but unverified; named as
# distinctly as possible without inventing a confident explanation.
SIMPLE_ARP_SHAPES: dict[str, str] = {
    "played": "Played",
    "chord": "Chord",
    "converge": "Converge",
    "diverge": "Diverge",
    "converge_diverge": "ConvAndDiv",
    "down": "Down",
    "up_down": "UpDown",
    "down_up": "DownUp",
    "up_and_down": "UpAndDown",
    "down_and_up": "DownAndUp",
    "thumb_up": "ThumbUp",
    "thumb_up_down": "ThumbUD",
    "random": "Rand",
    "random_once": "RandOnce",
    "random_drift": "RandDrift",
    "random_no_dup": "RandNoDup",
}

ARPCLIP_PARAMS: dict[str, ParamDef] = {
    "kParamShape": ParamDef(
        "kParamShape",
        "enum",
        default="Played",
        confidence="observed",
        enum_values=(
            "Played",
            "Pattern",
            "Chord",
            "Converge",
            "Diverge",
            "ConvAndDiv",
            "Down",
            "UpDown",
            "DownUp",
            "UpAndDown",
            "DownAndUp",
            "ThumbUp",
            "ThumbUD",
            "Rand",
            "RandOnce",
            "RandDrift",
            "RandNoDup",
        ),
        notes="Union of values observed across kParamShape AND kParamTransposeShape "
        "(same enum -- confirmed by 'Down'/'ThumbUp'/'Diverge' appearing on the "
        "latter too) across all 844 real presets available, not just the original "
        "180-preset sample. Almost certainly still a superset exists (e.g. a plain "
        "'Up', matching 'Down''s presence, never directly observed with certainty so "
        "not included). See SIMPLE_ARP_SHAPES for the curated subset ArpSpec "
        "generates; mapping.py falls back to passing an uncurated-but-otherwise-valid "
        "raw value through unchanged (same pattern as filter types/wavetables) so a "
        "round-tripped edit of a preset using a shape outside this curated list "
        "doesn't fail -- 'Pattern' is the sole deliberate exception, since it needs "
        "real note data this project doesn't generate (see ArpSpec).",
    ),
    "kParamRate": ParamDef(
        "kParamRate",
        "float",
        default=0.5,
        min=0.0,
        max=1.0,
        unit="normalized",
        confidence="uncertain",
        notes="Real musical meaning (note division? Hz?) still not established, but "
        "found live: for shape='pattern', a low value (0.25, this field's old default) "
        "made a real generated pattern appear stuck on its first note -- an isolated "
        "diagnostic confirmed raising it to a real Factory preset's value (~0.51) was "
        "the difference between stuck and correctly stepping through the pattern, "
        "holding every other field constant. Default raised to 0.5 accordingly.",
    ),
    "kParamGate": ParamDef(
        "kParamGate",
        "float",
        default=75.0,
        min=0.0,
        max=200.0,
        unit="% (approx.)",
        confidence="observed",
        notes="Observed range 0..145.6 -- can exceed 100% (legato overlap past the "
        "next step), not a simple 0-100% knob.",
    ),
    "kParamDotted": ParamDef("kParamDotted", "bool", default=False, confidence="observed"),
    "kParamTriplets": ParamDef("kParamTriplets", "bool", default=False, confidence="observed"),
    "kParamTransposeShift": ParamDef(
        "kParamTransposeShift",
        "float",
        default=0.0,
        min=-24.0,
        max=24.0,
        unit="semitones",
        confidence="observed",
    ),
}
ARPCLIP_PARAMS["kParamTransposeShape"] = ParamDef(
    "kParamTransposeShape",
    "enum",
    default="Played",
    confidence="observed",
    enum_values=ARPCLIP_PARAMS["kParamShape"].enum_values,
    notes="Same enum as kParamShape (see there) -- an independent pattern for the "
    "transpose lane, so the pitch pattern and the note-trigger pattern can differ.",
)
ARPCLIP_PARAMS["kParamNoteRetrig"] = ParamDef(
    "kParamNoteRetrig",
    "bool",
    default=False,
    confidence="observed",
    notes="CORRECTION: an earlier version of this note claimed this field alone fixed "
    "a real 'stuck on one note' Pattern-mode bug -- a later, more rigorous isolated "
    "diagnostic (holding every other field constant one at a time) found the ACTUAL "
    "cause was kParamRate (see there), not this field. This field was present in every "
    "working configuration tested but never individually proven necessary in "
    "isolation. apply_spec still writes 1.0 when arp.pattern is set, since it's "
    "present in every real working example found and never observed to cause harm, "
    "but treat its necessity as unconfirmed, not established.",
)
ARPCLIP_PARAMS["kParamWrapRange"] = ParamDef(
    "kParamWrapRange",
    "float",
    default=12.0,
    min=0.0,
    max=24.0,
    unit="semitones (approx.)",
    confidence="uncertain",
    notes="Real values observed: 1.0, 2.0, 12.0, 24.0. Likely the pitch range the "
    "pattern wraps/folds within, unconfirmed. Same status as kParamNoteRetrig: present "
    "in every working Pattern-mode configuration tested (default 12.0, one octave), "
    "never individually isolated as necessary -- kParamRate was the actual fix for the "
    "'stuck on one note' bug this was originally (incorrectly) blamed alongside.",
)
ARPCLIP_PARAMS["kParamWrapTranspose"] = ParamDef(
    "kParamWrapTranspose",
    "bool",
    default=False,
    confidence="uncertain",
    notes="Only ever observed at 1.0 across real content. Same status as "
    "kParamWrapRange/kParamNoteRetrig -- written (True) whenever arp.pattern is set, "
    "present in every working configuration tested, never individually isolated as "
    "necessary.",
)

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
# factory content). This was `observed` (statistical clustering only) until
# 2026-07-29, when two rounds of a direct-UI-probe method resolved thirteen
# more IDs: a real Serum 2 instance was used to wire up one route per known
# source by hand (round 1: Note > Velo, Mod Wheel, Pitch Bend, Note > Note#,
# Note > NoteOn Rand1/Rand2/(Discrete), Envelopes > Env 1; round 2:
# Aftertouch, Poly Aftertouch, Envelopes > Env 2/3/4) and the resulting file
# inspected raw each time. Results: Velocity=16, Mod Wheel=1 (resolving the
# earlier id-1-vs-16 ambiguity in favor of Mod Wheel, not Velocity), Env1-4
# as sources=2/3/4/5 (a contiguous block, confirming what was first just a
# guess from Env1 alone), Note#/Key Track=17, Aftertouch=18, Poly
# Aftertouch=19, NoteOn Rand1=21, NoteOn Rand2=22, Pitch Bend=33 (immediately
# after the Macro block), NoteOn Rand (Discrete)=59. All `confirmed`-
# confidence (direct probe, not statistics) -- this closes out every source
# in this project's original gap list (Envelope/Velocity/Mod Wheel/
# Aftertouch/Pitch Bend/Key Track/Random). Remaining unresolved sources
# (`Release Velo`, `Active Voices`, `Voice Index`, `Voice Mod 1`/`2`,
# `Oscillators`/`Filters`/`Note Expression` as self-mod sources) are ones
# this project only learned existed by seeing Serum 2's real source picker --
# not part of the original scope, low priority unless a use case comes up.
# See docs/PARAMETER_SCHEMA.md §6 for the full methodology, and
# CONTRIBUTING.md -- the same probe method is fast and reusable if needed.
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
    # Found live 2026-07-30 via a VST3 binary string dump of ModSlot's full
    # private param enum ('kParamCurveIn = kNumAutomatableParams,
    # kParamAuxCurve, kParamBipolar, kParamAuxInverted, kParamBypass,
    # kParamMainCurveData, kParamAuxCurveData, kParamDelayOffset,
    # kParamDelayBeatSync, kParamSmoothRise, kParamSmoothFall,
    # kParamSmoothLink, ...') -- none of the below were known to this
    # project before. A real-corpus survey (17,861 real mod slots) found
    # all of them genuinely used, just rare: kParamCurveIn 2.9%,
    # kParamMainCurveData 3.2%, kParamAuxInverted 0.9%, kParamAuxCurveData
    # 0.8%, kParamSmoothRise/Fall ~0.3% each, kParamBypass 0.3%,
    # kParamAuxCurve 0.3%, kParamSmoothLink 0.1%, kParamDelayOffset/
    # BeatSync 0.04% each (only ever seen on "LOOP"-category presets).
    # None wired into ModRouteSpec/generation -- `apply_spec` now at least
    # preserves them when editing an EXISTING route in place (previously
    # silently dropped, see `_build_modslot_entry`), but a brand-new
    # generated route still can't set any of these.
    "kParamAuxInverted": ParamDef(
        "kParamAuxInverted", "bool", default=False, confidence="observed",
        notes="Inverts the AUX source (not the main source) before it scales/gates "
        "kParamAmount -- exact combination formula not decoded.",
    ),
    "kParamAuxCurve": ParamDef(
        "kParamAuxCurve", "float", default=0.0, min=-100.0, max=100.0, confidence="observed",
        notes="A scalar curve-shape value for the AUX source, same family as the "
        "per-route kParamCurveIn (main source) -- distinct mechanism, not decoded.",
    ),
    "kParamBypass": ParamDef(
        "kParamBypass", "bool", default=False, confidence="observed",
        notes="Every real sample observed had this at 1.0 (True) when present -- "
        "unclear if 'route bypassed but kept configured' is really the common case, "
        "or if the semantics are inverted from the name.",
    ),
    "kParamCurveIn": ParamDef(
        "kParamCurveIn", "float", default=0.0, min=-100.0, max=100.0, confidence="observed",
        notes="Per-route curve-shape scalar for the MAIN source -- see the Dreams "
        "recreation write-up in docs/REAL_SERUM_TESTING.md for the discovery context.",
    ),
    "kParamMainCurveData": ParamDef(
        "kParamMainCurveData", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="A flag (observed only at 1.0), not the curve itself -- confirmed live "
        "2026-07-30 (real file inspection): the actual hand-drawn point data lives in "
        "a SIBLING 'flex' key on the ModSlot (same pattern as FX units' own 'flex'), "
        "not inside plainParams. Arbitrary points, not generatable.",
    ),
    "kParamAuxCurveData": ParamDef(
        "kParamAuxCurveData", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="Same flag-not-data pattern as kParamMainCurveData, presumably pointing "
        "at a second curve within the same sibling 'flex' structure for the AUX source "
        "-- a system this project only just found, never looked for before 2026-07-30, "
        "exact 'flex' layout when both main and aux curves are present unconfirmed.",
    ),
    "kParamDelayOffset": ParamDef(
        "kParamDelayOffset", "float", default=0.0, min=0.0, max=None, confidence="uncertain",
        notes="Per-route delay before the modulation takes effect -- only ever "
        "observed on 'LOOP'-category presets (beat-synced loop content). Real "
        "values seen ~0.3-0.8 (units unconfirmed, possibly beats).",
    ),
    "kParamDelayBeatSync": ParamDef(
        "kParamDelayBeatSync", "bool", default=False, confidence="uncertain",
        notes="Beat-syncs kParamDelayOffset -- co-occurs with it in every sample seen.",
    ),
    "kParamSmoothRise": ParamDef(
        "kParamSmoothRise", "float", default=0.0, min=0.0, max=100.0, confidence="uncertain",
        notes="Per-route smoothing time/amount for a rising modulation value, "
        "independent of the source's own smoothing (e.g. an LFO's kParamSmooth). "
        "Real values seen 5.8-92.8 -- units unconfirmed.",
    ),
    "kParamSmoothFall": ParamDef(
        "kParamSmoothFall", "float", default=0.0, min=0.0, max=100.0, confidence="uncertain",
        notes="Same as kParamSmoothRise, for a falling modulation value.",
    ),
    "kParamSmoothLink": ParamDef(
        "kParamSmoothLink", "bool", default=False, confidence="uncertain",
        notes="Presumed 'link rise and fall smoothing to one value' toggle -- every "
        "real sample seen had this at 0.0 (False) even when Rise/Fall were both set, "
        "so the presumption is unconfirmed.",
    ),
}

# source name -> ModSlot.source[0]. subIndex (source[1]) is always 0 for
# these families in every sample observed.
MOD_SOURCE_IDS: dict[str, int] = {
    **{f"lfo{i}": 6 + i for i in range(10)},
    **{f"macro{i}": 25 + i for i in range(8)},
    "velocity": 16,
    # Confirmed 2026-07-29 via the same direct-UI-probe method as velocity
    # (see the comment above MODSLOT_PARAMS and docs/PARAMETER_SCHEMA.md §6).
    "mod_wheel": 1,
    # "Env N" used AS A SOURCE (distinct from env0.decay etc as a
    # destination) -- contiguous block, directly probed for all 4, confirming
    # the contiguity guess this project originally flagged as unconfirmed.
    "env0": 2,
    "env1": 3,
    "env2": 4,
    "env3": 5,
    "key_track": 17,  # Serum's own UI calls this "Note#", not "Key Track" --
    # named key_track here for generation ergonomics; same concept.
    "aftertouch": 18,
    "poly_aftertouch": 19,
    "random1": 21,  # Serum UI: "NoteOn Rand1"
    "random2": 22,  # Serum UI: "NoteOn Rand2"
    "pitch_bend": 33,
    "random_discrete": 59,  # Serum UI: "NoteOn Rand (Discrete)"
    # Confirmed 2026-07-29 via the same direct-UI-probe method, prompted by
    # UN_PLACES_BA_Beyond using an unresolved source id (38, still not this
    # block -- see the note above MOD_SOURCE_IDS's definition) on 3 of its
    # real mod routes. Probed the 5 remaining named "Note"-category sources
    # this project had seen in Serum's picker but never identified:
    # release_velo, active_voices, voice_index, voice_mod1, voice_mod2 --
    # note these are NOT a contiguous block with each other (37, then a gap,
    # then 55-58), so don't extrapolate neighboring IDs from this range.
    "release_velo": 37,  # Serum UI: "Release Velo"
    "voice_mod1": 56,  # Serum UI: "Voice Mod 1"
    "voice_mod2": 57,  # Serum UI: "Voice Mod 2"
    "active_voices": 55,  # Serum UI: "Active Voices"
    "voice_index": 58,  # Serum UI: "Voice Index"
    # "Fixed" -- Serum's own MATRIX-tab UI name for id 38, a constant/manual
    # modulation offset (kParamAmount alone), decoded in depth 2026-07-30
    # (see docs/PARAMETER_SCHEMA.md item 14). Originally found paired with a
    # macro "Aux Source" on some real routes and assumed to be a
    # `fixed`-specific mechanism (subIndex = 25 + macro_index) -- a wider
    # 626-preset survey found that was just the first example encountered:
    # source[1]/subIndex is actually a GENERAL second/aux source id, usable
    # with ANY primary source, drawn from this exact same MOD_SOURCE_IDS
    # space (see ModRouteSpec.aux_source and mapping._build_modslot_entry).
    "fixed": 38,
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
    # destModuleParamID 4 confirmed live 2026-07-29 against a real preset's
    # raw ModSlot (see schema.WTOSC_PARAMS["kParamWarpVar2"]).
    MOD_DEST_TARGETS[f"oscillator{_i}.warp_var2"] = ModDestDef("WTOsc", _i, "kParamWarpVar2", 4)
    # destModuleParamID 3 confirmed live 2026-07-29 against UN_PLACES_BA_Beyond's
    # real raw ModSlot5 (macro4 -> WTOsc2.kParamWarp2) -- the second warp
    # lane's own amount as a mod destination, distinct from warp_amount
    # (the first lane, ID 0) and warp_var2 (ID 4).
    MOD_DEST_TARGETS[f"oscillator{_i}.warp_amount2"] = ModDestDef("WTOsc", _i, "kParamWarp2", 3)
for _i in range(10):
    MOD_DEST_TARGETS[f"lfo{_i}.rate"] = ModDestDef("LFO", _i, "kParamRate", 0)
for _i in range(8):
    MOD_DEST_TARGETS[f"macro{_i}.value"] = ModDestDef("Macro", _i, "kParamValue", 0)
del _i
# `Global` is a singleton (destModuleID always 0), unlike everything above
# which is per-slot. Confirmed live 2026-07-29 against TWO independent real
# presets (both used key_track -> Global.kParamVoiceAmp, at -61% and -52%
# respectively) -- destModuleParamID 2.
MOD_DEST_TARGETS["global.voice_amp"] = ModDestDef("Global", 0, "kParamVoiceAmp", 2)

# Non-`kParamWet` FX mod destinations -- unlike kParamWet (destModuleParamID
# 1, confirmed universal across every FX type that has a wet knob), every
# other FX-internal param's destModuleParamID is type-SPECIFIC and only
# added here once directly confirmed against a real preset's raw ModSlot,
# one at a time -- do not extrapolate an ID from one FX type to another.
# `mapping._resolve_mod_destination` looks up `fx{i}.<suffix>` against the
# fx_chain[i] type actually in use, the same way it already does for
# `fx{i}.wet`.
FX_EXTRA_MOD_DEST_PARAMS: dict[str, dict[str, tuple[str, int]]] = {
    "FXUtils": {
        # Confirmed live 2026-07-29 against a real preset's raw ModSlot
        # (lfo -> FXUtils.kParamBalance).
        "balance": ("kParamBalance", 4),
        # Confirmed live 2026-07-29 against UN_PLACES_BA_Beyond's raw
        # ModSlot0/2 (lfo0 -> FXUtils.kParamLevelOut, macro0 ->
        # FXUtils.kParamLevelOut).
        "level_out": ("kParamLevelOut", 2),
    },
}

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
                "kXShaperAsym",
                "kZeroSquare",
            ),
        ),
        "kParamDrive": ParamDef("kParamDrive", "float", default=50.0, min=0.0, max=100.0, unit="%"),
        "kParamWet": ParamDef("kParamWet", "float", default=100.0, min=0.0, max=100.0, unit="%"),
        "kParamFreq": ParamDef(
            "kParamFreq", "float", default=1.0, min=0.0, max=1.0, unit="normalized"
        ),
        "kParamNumStages": ParamDef(
            "kParamNumStages", "float", default=2.0, min=2.0, max=16.0,
            notes="Max corrected from 7.0 after finding a real preset with numStages=16.0.",
        ),
    },
    "FXChorus": {
        "kParamRate": ParamDef(
            "kParamRate", "float", default=0.5, min=0.0, max=20.0, unit="Hz (approx.)",
            notes="Max corrected from 1.4 after finding a real Factory preset with rate=20.0.",
        ),
        "kParamDepth": ParamDef(
            "kParamDepth", "float", default=10.0, min=0.0, max=26.0, unit="ms (approx.)"
        ),
        "kParamDelay": ParamDef(
            "kParamDelay", "float", default=5.0, min=0.0, max=20.0, unit="ms (approx.)",
            notes="Max corrected from 12.8 after finding real presets with delay up to 18.0.",
        ),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=0.0, min=0.0, max=75.0, unit="%",
            notes="Max corrected from 58.2 after finding a real preset with feedback=71.9.",
        ),
        "kParamFilt": ParamDef(
            "kParamFilt", "float", default=2000.0, min=50.0, max=20000.0, unit="Hz"
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=50.0, min=0.0, max=100.0, unit="%"),
    },
    "FXFlanger": {
        "kParamRate": ParamDef(
            "kParamRate", "float", default=0.5, min=0.0, max=10.0, unit="Hz (approx.)",
            notes="Max corrected from 5.1 after finding a real preset with rate=9.3.",
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
            "kParamFreq", "float", default=800.0, min=20.0, max=20000.0, unit="Hz",
            notes="Max corrected from 2563.0 after finding real presets with freq up to 18000.0.",
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
            "kParamFeedback", "float", default=30.0, min=0.0, max=90.0, unit="%",
            notes="Max corrected from 83.3 after finding a real preset with feedback=89.5.",
        ),
        "kParamFreq": ParamDef(
            "kParamFreq",
            "float",
            default=8000.0,
            min=49.5,
            max=17981.0,
            unit="Hz",
            notes="Delay tap tone filter frequency. Min nudged from 49.6 to 49.5 after "
            "finding a real preset with freq=49.56.",
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
            "kParamThresh", "float", default=0.5, min=0.0, max=1.0, unit="normalized"
        ),
        "kParamRatio": ParamDef(
            "kParamRatio",
            "float",
            default=4.0,
            min=1.0,
            max=1_000_000.0,
            unit="ratio:1",
            notes="Min corrected from 1.1 to 1.0 after finding real Factory presets with "
            "ratio=1.0 (no compression, ratio matrix's neutral position) in the raw CBOR.",
        ),
        "kParamAttack": ParamDef(
            "kParamAttack", "float", default=10.0, min=0.1, max=1000.0, unit="ms"
        ),
        "kParamRelease": ParamDef(
            "kParamRelease", "float", default=100.0, min=0.1, max=1000.0, unit="ms"
        ),
        "kParamMakeup": ParamDef(
            "kParamMakeup", "float", default=1.0, min=1.0, max=32.0, unit="gain factor",
            notes="Max corrected from 25.8 after finding a real preset with makeup=31.0.",
        ),
        "kParamWet": ParamDef("kParamWet", "float", default=100.0, min=0.0, max=100.0, unit="%"),
    },
    "FXEQ": {
        "kParamFreq1": ParamDef(
            "kParamFreq1", "float", default=200.0, min=21.5, max=10000.0, unit="Hz",
            notes="Max corrected from 9454.0 after finding a real preset with freq1=10000.0.",
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
            "kParamReso1", "float", default=0.0, min=0.0, max=100.0, unit="Q (approx.)",
            notes="Max corrected from 69.6 after finding a real preset with reso1=100.0.",
        ),
        "kParamReso2": ParamDef(
            "kParamReso2", "float", default=0.0, min=0.0, max=95.0, unit="Q (approx.)",
            notes="Max corrected from 79.0 after finding a real preset with reso2=81.3.",
        ),
    },
    "FXFilter": {
        "kParamType": ParamDef(
            "kParamType",
            "enum",
            default="L12",
            enum_values=tuple(VOICE_FILTER_PARAMS["kParamType"].enum_values),
            confidence="uncertain",
            notes="RISK, found live 2026-07-30 (user reported frequent crashes on freshly-"
            "generated presets): this enum is a straight copy of VoiceFilter's full type "
            "list, but the docstring's own claim ('minus a few voice-only variants') was "
            "NEVER actually enforced in code -- some of these ~95 raw filter-engine names "
            "were only ever confirmed present in real *VoiceFilter* data, not confirmed "
            "safe for the FXFilter (FX-chain insert) context specifically, and using one "
            "of the unconfirmed ones is a plausible crash cause. Every real preset this "
            "project has generated AND live-confirmed with an FXFilter unit (Dreams/Beyond "
            "recreations) left kParamType UNSET (Serum's own default) -- do the same until "
            "someone does the work of confirming which subset is actually FXFilter-safe.",
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
            "kParamShift", "float", default=0.0, min=-100.0, max=82.0, unit="% (approx.)",
            notes="Max corrected from 73.4 after finding a real preset with shift=80.7.",
        ),
        "kParamRange": ParamDef(
            "kParamRange", "float", default=100.0, min=0.1, max=3043.2, unit="Hz (approx.)"
        ),
        "kParamFeedback": ParamDef(
            "kParamFeedback", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamBlur": ParamDef("kParamBlur", "float", default=0.0, min=0.0, max=100.0, unit="%"),
        "kParamDelayTime": ParamDef(
            "kParamDelayTime", "float", default=0.0, min=0.0, max=1.8, unit="seconds (approx.)",
            notes="Max corrected from 1.62 after finding a real preset with delayTime=1.75.",
        ),
        "kParamOutputWidth": ParamDef(
            "kParamOutputWidth", "float", default=0.0, min=0.0, max=100.0, unit="%"
        ),
        "kParamOutputMix": ParamDef(
            "kParamOutputMix", "float", default=0.0, min=-100.0, max=100.0, unit="%"
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
        "kParamTone": ParamDef(
            "kParamTone", "float", default=0.0, min=-100.0, max=85.0, unit="%",
            notes="Max corrected from 84.2 after finding a real preset with tone=84.21.",
        ),
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
            "kParamLPF", "float", default=20000.0, min=50.0, max=20000.0, unit="Hz (approx.)",
            notes="Max corrected from 18976.0 after finding a real preset with LPF=19924.3.",
        ),
        "kParamLFXover": ParamDef(
            "kParamLFXover", "float", default=150.0, min=20.25, max=400.0, unit="Hz (approx.)",
            notes="Max corrected from 300.0 after finding a real preset with LFXover=400.0.",
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

# ---------------------------------------------------------------------------
# Role starting points -- a condensed, structured transcription of
# docs/SOUND_DESIGN_REFERENCE.md's per-role statistics (derived from
# analyzing all 180 presets in Unmute's "Places For Serum 2" commercial
# bank, broken down by role). Exists so this data reaches the calling model
# via list_parameters() -- a call server.py's guidance already establishes
# as a habitual first step before generating -- instead of depending on the
# model separately deciding to Read a markdown file each session. The full
# prose doc has more qualitative nuance and caveats (sample sizes, "treat as
# anecdotal" warnings for small categories); this is the numeric skeleton
# for quick lookup, not a replacement for it. Ranges are `min..max (median)`
# or a single median where the doc only gives one; times are seconds to
# match EnvelopeSpec's own units. `confidence` here is `observed` for all of
# it -- statistical patterns in one professional bank, not confirmed against
# Xfer documentation.
# ---------------------------------------------------------------------------

ROLE_STARTING_POINTS: dict[str, dict] = {
    "bass": {
        "sample_size": 26,
        "mono": True,  # 25/26
        "envelope": {"attack": 0.004, "release": 0.045, "sustain": 0.84},
        "filter": {"type": "moog_lowpass_12", "resonance": 7, "drive": 14},
        "oscillator_count": 2,
        "warp_mode": "fm",
        "mod_route_pattern": "macro -> oscillator / macro -> env, not LFO-driven",
        "fx_backbone": "FXComp + FXEQ ahead of character effects (reverb/delay/dist)",
        "note": "held, punchy tone (fast attack, short release, high sustain) -- not a pluck",
    },
    "pluck": {
        "sample_size": 24,
        "envelope": {"attack": 0.006, "decay": 0.232, "sustain": 0.0},
        "filter": {"type": "moog_lowpass_12", "resonance": 10},
        "warp_mode": "bend",  # not fm -- a real difference from bass/chords/synth
        "mod_route_pattern": "macro -> env (decay/release feel) then macro -> fx",
        "note": "sustain=0 is the single clearest role-defining signal in the whole "
        "dataset -- a real decaying pluck, not a held note",
    },
    "lead": {
        "sample_size": 22,
        "mono": True,  # mostly, 20/22
        "envelope": {"attack": 0.026, "decay": 1.08, "release": 0.38, "sustain": 0.74},
        "warp_mode": "bend",
        "mod_route_pattern": "macro -> fx (effect intensity) then lfo -> oscillator "
        "(vibrato/movement)",
        "note": "sustained melodic voice, not a pluck",
    },
    "pad": {
        "sample_size": 12,  # smaller sample, treat as more anecdotal than others
        "envelope": {"attack": 0.664, "decay": 1.75, "release": 1.1},
        "oscillator_count": 3,  # 8/12
        "warp_mode": "fm",
        "mod_route_pattern": "lfo -> oscillator (continuous evolving movement, not macro-driven "
        "like bass/lead)",
    },
    "chords": {
        "sample_size": 23,
        "mono": False,  # 100% polyphonic, 0/23 mono
        "filter_count": 2,  # active in 19/23 -- richer layering than most roles
        "oscillator_count": 3,  # most common, 14/23
        "warp_mode": "fm",
        "mod_route_pattern": "lfo -> oscillator, close behind macro -> oscillator",
    },
    "synth": {
        "sample_size": 28,  # largest category
        "oscillator_count": "2-3",
        "envelope": {"decay": 0.81},
        "warp_mode": "fm",
        "note": "heaviest and most evenly-spread macro usage across fx/env/oscillator/"
        "filter of any category -- the most 'built for live tweaking' role",
    },
    "arp": {
        "sample_size": 16,
        "mono": False,  # mostly polyphonic (12/16) despite the role name
        "envelope": "short attack/release",
        "warp_mode": "fm",
        "mod_route_pattern": "lfo -> oscillator",
    },
    "sequence": {
        "sample_size": 14,
        "envelope": {"attack": 0.001},
        "note": "long decay/sustain held near max -- built to be gated/retriggered "
        "rhythmically rather than shaped by its own envelope",
        "mod_route_pattern": "by far the heaviest lfo -> oscillator usage of any category "
        "-- strong rhythmic pitch/timbre modulation is a defining trait here",
    },
}

ALL_FX_TYPES: tuple[str, ...] = tuple(FX_TYPE_IDS.values())
