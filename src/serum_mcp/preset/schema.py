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


@dataclass(frozen=True)
class MultiSampleInstrumentDef:
    """A curated, real Factory multisample instrument for the MultiSampleOsc
    engine (slots 0-2, ``OscillatorSpec.multisample_source``) -- decoded
    2026-07-31. Unlike ``WavetableDef``/``SampleAudioDef`` (a single audio
    file's metadata), MultiSampleOsc's real structure is a full SFZ-format
    keyzone mapping across MANY sample files, too complex to synthesize from
    scratch this round (see docs/PARAMETER_SCHEMA.md item 3) -- so, mirroring
    how ``wavetable``/``sample_source`` reference curated Factory content
    rather than building a wavetable from arbitrary user data, this
    references an EXISTING real Factory instrument's structure verbatim.

    Confirmed live 2026-07-31: `embedded_sfz` and `files` are BYTE-IDENTICAL
    across every real preset observed referencing the same instrument (e.g.
    4 different presets all using ``Factory/Choir/Ah High.sfz`` produced
    identical CBOR for both fields) -- only each preset's own `plainParams`
    (envelope/warp) differ. This means it's safe to hard-code these two
    fields once per instrument and let `plainParams` stay freely settable,
    the same trust level as any other curated Factory reference in this
    project.

    `files`' own keys use a literal backslash as path separator, but the
    exact COUNT is not universal -- corrected 2026-08-01 after curating 6
    more instruments: `choir_ah`/`guitar_ac` genuinely use a literal DOUBLE
    backslash (confirmed by inspecting individual characters, e.g.
    ``"Choir Samples\\\\XFChoir Ah High A#2.flac"``, not a transcription
    artifact), but `violins` (already in this dict beforehand) and all 6
    newly-curated instruments use a single backslash instead -- a real,
    per-instrument authoring inconsistency on Xfer's own side (plausibly
    different sample-prep tooling/versions across their content library),
    not a bug in this project. Always preserve exactly what a fresh
    extraction produces; never assume/normalize the separator count.
    """

    sfz_path_relative: str
    embedded_sfz: str
    files: dict[str, dict[str, int]]


MULTISAMPLE_INSTRUMENTS: dict[str, MultiSampleInstrumentDef] = {
    'choir_ah': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Choir/Ah High.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> loop_mode=loop_continuous amp_veltrack=25.000000 ampeg_attack=0.020000 ampeg_release=1.000000\n<region> hikey=59 pitch_keycenter=58 loop_crossfade=1.062900 loop_start=104856 loop_end=274924 sample=Choir Samples//XFChoir Ah High A#2.flac\n<region> lokey=60 hikey=62 pitch_keycenter=61 loop_crossfade=0.708600 loop_start=116736 loop_end=286804 sample=Choir Samples//XFChoir Ah High C#3.flac\n<region> lokey=63 hikey=65 pitch_keycenter=64 loop_crossfade=0.644200 loop_start=133445 loop_end=288053 sample=Choir Samples//XFChoir Ah High E3.flac\n<region> lokey=66 hikey=68 pitch_keycenter=67 loop_crossfade=0.532400 loop_start=191208 loop_end=318984 sample=Choir Samples//XFChoir Ah High G3.flac\n<region> lokey=69 hikey=71 pitch_keycenter=70 loop_crossfade=1.417200 loop_start=96491 loop_end=266559 sample=Choir Samples//XFChoir Ah High A#3.flac\n<region> lokey=72 hikey=74 pitch_keycenter=73 loop_crossfade=0.532400 loop_start=79950 loop_end=207726 sample=Choir Samples//XFChoir Ah High C#4.flac\n<region> lokey=75 hikey=77 pitch_keycenter=76 loop_crossfade=0.726000 loop_start=196800 loop_end=312960 sample=Choir Samples//XFChoir Ah High E4.flac\n<region> lokey=78 hikey=80 pitch_keycenter=79 loop_crossfade=1.610500 loop_start=106912 loop_end=261520 sample=Choir Samples//XFChoir Ah High G4.flac\n<region> lokey=81 pitch_keycenter=82 loop_crossfade=0.400000 loop_start=53248 loop_end=149248 sample=Choir Samples//XFChoir Ah High A#4.flac\n',
        files={'Choir Samples\\\\XFChoir Ah High A#2.flac': {'numChannels': 2, 'numFrames': 386560, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High A#3.flac': {'numChannels': 2, 'numFrames': 390144, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High A#4.flac': {'numChannels': 2, 'numFrames': 204800, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High C#3.flac': {'numChannels': 2, 'numFrames': 391168, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High C#4.flac': {'numChannels': 2, 'numFrames': 391573, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High E3.flac': {'numChannels': 2, 'numFrames': 392192, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High E4.flac': {'numChannels': 2, 'numFrames': 395776, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High G3.flac': {'numChannels': 2, 'numFrames': 390656, 'sampleRate': 48000}, 'Choir Samples\\\\XFChoir Ah High G4.flac': {'numChannels': 2, 'numFrames': 390824, 'sampleRate': 48000}},
    ),
    'synth_sid': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Synth/SID Tarkus.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> loop_crossfade=0.012500 loop_mode=loop_continuous ampeg_attack=0.001000 ampeg_release=0.320000\n<region> hikey=31 pitch_keycenter=24 loop_start=25930 loop_end=158639 sample=../../../Samples/Factory/Synth/SID Tarkus C0.flac\n<region> lokey=32 hikey=42 pitch_keycenter=36 loop_start=73901 loop_end=159569 sample=../../../Samples/Factory/Synth/SID Tarkus C1.flac\n<region> lokey=43 hikey=55 pitch_keycenter=48 loop_start=8708 loop_end=115114 sample=../../../Samples/Factory/Synth/SID Tarkus C2.flac\n<region> lokey=56 loop_start=60622 loop_end=168389 sample=../../../Samples/Factory/Synth/SID Tarkus C3.flac\n',
        files={'C:\\Users\\brand\\BSOD_XFER Dropbox\\Serum 2 Presets\\Samples\\Factory\\Synth\\SID Tarkus C0.flac': {'numChannels': 1, 'numFrames': 174762, 'sampleRate': 44100}, 'C:\\Users\\brand\\BSOD_XFER Dropbox\\Serum 2 Presets\\Samples\\Factory\\Synth\\SID Tarkus C1.flac': {'numChannels': 1, 'numFrames': 174213, 'sampleRate': 44100}, 'C:\\Users\\brand\\BSOD_XFER Dropbox\\Serum 2 Presets\\Samples\\Factory\\Synth\\SID Tarkus C2.flac': {'numChannels': 1, 'numFrames': 162578, 'sampleRate': 44100}, 'C:\\Users\\brand\\BSOD_XFER Dropbox\\Serum 2 Presets\\Samples\\Factory\\Synth\\SID Tarkus C3.flac': {'numChannels': 1, 'numFrames': 175238, 'sampleRate': 44100}},
    ),
    'guitar_ac': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Plucked/Gtr Ac Martin Pick.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> volume=3.000000\n<region> hikey=40 pitch_keycenter=40 sample=MartinPickA Samples//XFMartin Pick E1.flac\n<region> lokey=41 hikey=43 pitch_keycenter=42 tune=-6 sample=MartinPickA Samples//XFMartin Pick F#1.flac\n<region> lokey=44 hikey=46 pitch_keycenter=45 tune=-12 sample=MartinPickA Samples//XFMartin Pick A1.flac\n<region> lokey=47 hikey=49 pitch_keycenter=48 tune=-11 sample=MartinPickA Samples//XFMartin Pick C2.flac\n<region> lokey=50 hikey=53 pitch_keycenter=53 tune=-2 sample=MartinPickA Samples//XFMartin Pick F2.flac\n<region> lokey=54 hikey=58 pitch_keycenter=54 tune=-8 sample=MartinPickA Samples//XFMartin Pick F#2.flac\n<region> lokey=59 hikey=63 pitch_keycenter=62 tune=-5 sample=MartinPickA Samples//XFMartin Pick D3.flac\n<region> lokey=64 hikey=69 pitch_keycenter=64 tune=-6 sample=MartinPickA Samples//XFMartin Pick E3.flac\n<region> lokey=70 hikey=76 pitch_keycenter=71 tune=-9 sample=MartinPickA Samples//XFMartin Pick B3.flac\n<region> lokey=77 pitch_keycenter=82 tune=-2 sample=MartinPickA Samples//XFMartin Pick A#4.flac\n',
        files={'MartinPickA Samples\\\\XFMartin Pick A#4.flac': {'numChannels': 2, 'numFrames': 104699, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick A1.flac': {'numChannels': 2, 'numFrames': 172782, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick B3.flac': {'numChannels': 2, 'numFrames': 99406, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick C2.flac': {'numChannels': 2, 'numFrames': 165284, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick D3.flac': {'numChannels': 2, 'numFrames': 133560, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick E1.flac': {'numChannels': 2, 'numFrames': 300160, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick E3.flac': {'numChannels': 2, 'numFrames': 203904, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick F#1.flac': {'numChannels': 2, 'numFrames': 195524, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick F#2.flac': {'numChannels': 2, 'numFrames': 134261, 'sampleRate': 44100}, 'MartinPickA Samples\\\\XFMartin Pick F2.flac': {'numChannels': 2, 'numFrames': 159670, 'sampleRate': 44100}},
    ),
    'violins': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Strings/Violins LE.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> loop_crossfade=0.010000 loop_mode=loop_continuous amp_veltrack=35.000000 ampeg_attack=0.010000 ampeg_release=0.700000\n<region> hikey=58 pitch_keycenter=57 loop_start=96208 loop_end=272212 tune=-4 sample=Violins Long Samples/XFviolins long 03 A2.flac\n<region> lokey=59 hikey=60 pitch_keycenter=59 loop_start=106245 loop_end=303490 sample=Violins Long Samples/XFviolins long 03 B2.flac\n<region> lokey=61 hikey=62 pitch_keycenter=61 loop_start=154108 loop_end=317805 sample=Violins Long Samples/XFviolins long-02 03 C#3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=63 loop_start=102305 loop_end=356050 tune=-4 sample=Violins Long Samples/XFviolins long-02 03 D#3.flac\n<region> lokey=65 hikey=66 pitch_keycenter=65 loop_start=160204 loop_end=370366 tune=-3 sample=Violins Long Samples/XFviolins long-02 03 F3.flac\n<region> lokey=67 hikey=68 pitch_keycenter=67 loop_start=67472 loop_end=297630 tune=-4 sample=Violins Long Samples/XFviolins long-02 03 G3.flac\n<region> lokey=69 hikey=70 pitch_keycenter=69 loop_start=122184 loop_end=325081 tune=-10 sample=Violins Long Samples/XFviolins long-02 03 A3.flac\n<region> lokey=71 hikey=72 pitch_keycenter=71 loop_start=167234 loop_end=356333 tune=-8 sample=Violins Long Samples/XFviolins long-02 03 B3.flac\n<region> lokey=73 hikey=74 pitch_keycenter=73 loop_start=116122 loop_end=342005 tune=-5 sample=Violins Long Samples/XFviolins long-02 03 C#4.flac\n<region> lokey=75 pitch_keycenter=75 loop_start=6688 loop_end=241265 tune=4 sample=Violins Long Samples/XFviolins long 03 D#4.flac\n',
        files={'Violins Long Samples\\XFviolins long 03 A2.flac': {'numChannels': 2, 'numFrames': 272740, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long 03 B2.flac': {'numChannels': 2, 'numFrames': 304018, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long 03 D#4.flac': {'numChannels': 2, 'numFrames': 241793, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 A3.flac': {'numChannels': 2, 'numFrames': 325609, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 B3.flac': {'numChannels': 2, 'numFrames': 356861, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 C#3.flac': {'numChannels': 2, 'numFrames': 318333, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 C#4.flac': {'numChannels': 2, 'numFrames': 342533, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 D#3.flac': {'numChannels': 2, 'numFrames': 356578, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 F3.flac': {'numChannels': 2, 'numFrames': 370894, 'sampleRate': 48000}, 'Violins Long Samples\\XFviolins long-02 03 G3.flac': {'numChannels': 2, 'numFrames': 298158, 'sampleRate': 48000}},
    ),
    'brass_french_horn': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Winds/French Horns.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> loop_mode=loop_continuous amp_veltrack=35.000000 ampeg_attack=0.150000\n<region> hikey=42 pitch_keycenter=41 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=44770 loop_end=215678 sample=French Horns Long Samples//XFfrench horns long-02 02 F1.flac\n<region> hikey=42 pitch_keycenter=41 lovel=101 loop_crossfade=0.100000 loop_start=97450 loop_end=176325 tune=-6 sample=French Horns Long Samples//XFfrench horns long-02 03 F1.flac\n<region> lokey=43 hikey=44 pitch_keycenter=43 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=110648 loop_end=252997 tune=-16 sample=French Horns Long Samples//XFfrench horns long-01 02 G1.flac\n<region> lokey=43 hikey=44 pitch_keycenter=43 lovel=101 loop_crossfade=0.020000 loop_start=66616 loop_end=158300 tune=-18 sample=French Horns Long Samples//XFfrench horns long-06 03 G1.flac\n<region> lokey=45 hikey=48 pitch_keycenter=47 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=116643 loop_end=292272 tune=-18 sample=French Horns Long Samples//XFfrench horns long-01 02 B1.flac\n<region> lokey=45 hikey=46 pitch_keycenter=45 lovel=101 loop_crossfade=0.020000 loop_start=42599 loop_end=199781 tune=-12 sample=French Horns Long Samples//XFfrench horns long-01 03 A1.flac\n<region> lokey=47 hikey=50 pitch_keycenter=47 lovel=101 loop_crossfade=0.020000 loop_start=146528 loop_end=262250 tune=-12 sample=French Horns Long Samples//XFfrench horns long-02 03 B1.flac\n<region> lokey=49 hikey=50 pitch_keycenter=49 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=62090 loop_end=225633 tune=-18 sample=French Horns Long Samples//XFfrench horns long-02 02 C#2.flac\n<region> lokey=51 hikey=54 pitch_keycenter=51 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=88090 loop_end=293887 tune=-22 sample=French Horns Long Samples//XFfrench horns long-01 02 D#2.flac\n<region> lokey=51 hikey=52 pitch_keycenter=51 lovel=101 loop_crossfade=0.020000 loop_start=52587 loop_end=235103 tune=-18 sample=French Horns Long Samples//XFfrench horns long-02 03 D#2.flac\n<region> lokey=53 hikey=54 pitch_keycenter=53 lovel=101 loop_crossfade=0.020000 loop_start=157794 loop_end=228432 tune=-8 sample=French Horns Long Samples//XFfrench horns long-02 03 F2.flac\n<region> lokey=55 hikey=57 pitch_keycenter=55 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=79426 loop_end=264536 tune=-22 sample=French Horns Long Samples//XFfrench horns long-02 02 G2.flac\n<region> hikey=58 pitch_keycenter=57 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=28112 loop_end=261912 tune=-20 sample=French Horns Long Samples//XFfrench horns long-02 01 A2.flac\n<region> lokey=55 hikey=58 pitch_keycenter=57 lovel=101 loop_crossfade=0.020000 loop_start=34771 loop_end=206146 tune=-8 sample=French Horns Long Samples//XFfrench horns long-02 03 A2.flac\n<region> lokey=59 hikey=60 pitch_keycenter=59 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=43694 loop_end=289419 tune=-22 sample=French Horns Long Samples//XFfrench horns long-02 01 B2.flac\n<region> lokey=58 hikey=60 pitch_keycenter=59 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=80009 loop_end=277191 tune=-20 sample=French Horns Long Samples//XFfrench horns long-02 02 B2.flac\n<region> lokey=59 hikey=62 pitch_keycenter=59 lovel=101 loop_crossfade=0.020000 loop_start=67910 loop_end=230163 tune=-16 sample=French Horns Long Samples//XFfrench horns long-02 03 B2.flac\n<region> lokey=61 hikey=62 pitch_keycenter=61 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=42984 loop_end=248352 tune=-20 sample=French Horns Long Samples//XFfrench horns long-04 01 C#3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=61 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=79267 loop_end=248833 tune=-18 sample=French Horns Long Samples//XFfrench horns long-02 02 C#3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=61 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=42984 loop_end=248352 tune=-20 sample=French Horns Long Samples//XFfrench horns long-04 01 C#3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=63 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=98585 loop_end=279723 tune=-18 sample=French Horns Long Samples//XFfrench horns long-03 02 D#3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=63 lovel=101 loop_crossfade=0.020000 loop_start=123060 loop_end=249031 tune=-10 sample=French Horns Long Samples//XFfrench horns long-06 03 D#3.flac\n<region> lokey=65 hikey=66 pitch_keycenter=65 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=44855 loop_end=271856 tune=-8 sample=French Horns Long Samples//XFfrench horns long-04 01 F3.flac\n<region> lokey=65 hikey=68 pitch_keycenter=65 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=121202 loop_end=283243 tune=-8 sample=French Horns Long Samples//XFfrench horns long-03 02 F3.flac\n<region> lokey=67 hikey=68 pitch_keycenter=67 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=52559 loop_end=281506 tune=-22 sample=French Horns Long Samples//XFfrench horns long-04 01 G3.flac\n<region> lokey=65 hikey=68 pitch_keycenter=67 lovel=101 loop_crossfade=0.020000 loop_start=75636 loop_end=283576 tune=-22 sample=French Horns Long Samples//XFfrench horns long-02 03 G3.flac\n<region> lokey=69 hikey=72 pitch_keycenter=71 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=69353 loop_end=282273 tune=-18 sample=French Horns Long Samples//XFfrench horns long-02 01 B3.flac\n<region> lokey=69 hikey=70 pitch_keycenter=69 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=72345 loop_end=283606 sample=French Horns Long Samples//XFfrench horns long-03 02 A3.flac\n<region> lokey=71 pitch_keycenter=71 lovel=41 hivel=100 loop_crossfade=0.020000 loop_start=68119 loop_end=270971 tune=-12 sample=French Horns Long Samples//XFfrench horns long-02 02 B3.flac\n<region> lokey=69 hikey=72 pitch_keycenter=71 lovel=101 loop_crossfade=0.020000 loop_start=123966 loop_end=247851 tune=-16 sample=French Horns Long Samples//XFfrench horns long-02 03 B3.flac\n<region> lokey=73 pitch_keycenter=73 lovel=1 hivel=40 loop_crossfade=0.020000 loop_start=27089 loop_end=297405 tune=-12 sample=French Horns Long Samples//XFfrench horns long-21 01 C#4.flac\n<region> lokey=73 pitch_keycenter=73 lovel=101 loop_crossfade=0.020000 loop_start=169092 loop_end=265797 tune=-16 sample=French Horns Long Samples//XFfrench horns long-09 03 C#4.flac\n',
        files={'French Horns Long Samples\\\\XFfrench horns long-01 02 B1.flac': {'numChannels': 2, 'numFrames': 292800, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-01 02 D#2.flac': {'numChannels': 2, 'numFrames': 294415, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-01 02 G1.flac': {'numChannels': 2, 'numFrames': 253525, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-01 03 A1.flac': {'numChannels': 2, 'numFrames': 200309, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 01 A2.flac': {'numChannels': 2, 'numFrames': 262440, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 01 B2.flac': {'numChannels': 2, 'numFrames': 289947, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 01 B3.flac': {'numChannels': 2, 'numFrames': 282801, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 02 B2.flac': {'numChannels': 2, 'numFrames': 277719, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 02 B3.flac': {'numChannels': 2, 'numFrames': 271499, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 02 C#2.flac': {'numChannels': 2, 'numFrames': 226161, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 02 C#3.flac': {'numChannels': 2, 'numFrames': 249361, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 02 F1.flac': {'numChannels': 2, 'numFrames': 216206, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 02 G2.flac': {'numChannels': 2, 'numFrames': 265064, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 A2.flac': {'numChannels': 2, 'numFrames': 206674, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 B1.flac': {'numChannels': 2, 'numFrames': 262778, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 B2.flac': {'numChannels': 2, 'numFrames': 230691, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 B3.flac': {'numChannels': 2, 'numFrames': 248379, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 D#2.flac': {'numChannels': 2, 'numFrames': 235631, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 F1.flac': {'numChannels': 2, 'numFrames': 218853, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 F2.flac': {'numChannels': 2, 'numFrames': 228960, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-02 03 G3.flac': {'numChannels': 2, 'numFrames': 284104, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-03 02 A3.flac': {'numChannels': 2, 'numFrames': 284134, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-03 02 D#3.flac': {'numChannels': 2, 'numFrames': 280251, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-03 02 F3.flac': {'numChannels': 2, 'numFrames': 283771, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-04 01 C#3.flac': {'numChannels': 2, 'numFrames': 248880, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-04 01 F3.flac': {'numChannels': 2, 'numFrames': 272384, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-04 01 G3.flac': {'numChannels': 2, 'numFrames': 282034, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-06 03 D#3.flac': {'numChannels': 2, 'numFrames': 249559, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-06 03 G1.flac': {'numChannels': 2, 'numFrames': 158828, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-09 03 C#4.flac': {'numChannels': 2, 'numFrames': 266325, 'sampleRate': 48000}, 'French Horns Long Samples\\\\XFfrench horns long-21 01 C#4.flac': {'numChannels': 2, 'numFrames': 297933, 'sampleRate': 48000}},
    ),
    'epiano_suitcase': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Keys/Elec.Piano Suitcase.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> amp_veltrack=0.000000 ampeg_release=0.700000\n<region> hikey=22 pitch_keycenter=21 hivel=25 sample=RDE88_V Samples//XFRde88 V1 A-1.flac\n<region> lokey=23 hikey=25 pitch_keycenter=24 hivel=25 sample=RDE88_V Samples//XFRde88 V1 C0.flac\n<region> lokey=26 hikey=28 pitch_keycenter=27 hivel=25 sample=RDE88_V Samples//XFRde88 V1 D#0.flac\n<region> lokey=29 hikey=31 pitch_keycenter=30 hivel=25 sample=RDE88_V Samples//XFRde88 V1 F#0.flac\n<region> lokey=32 hikey=34 pitch_keycenter=33 hivel=25 tune=11 sample=RDE88_V Samples//XFRde88 V1 A0.flac\n<region> lokey=35 hikey=37 pitch_keycenter=36 hivel=25 sample=RDE88_V Samples//XFRde88 V1 C1.flac\n<region> lokey=38 hikey=40 pitch_keycenter=39 hivel=25 sample=RDE88_V Samples//XFRde88 V1 D#1.flac\n<region> lokey=41 hikey=43 pitch_keycenter=42 hivel=33 sample=RDE88_V Samples//XFRde88 V1 F#1.flac\n<region> lokey=44 hikey=46 pitch_keycenter=45 hivel=46 tune=4 sample=RDE88_V Samples//XFRde88 V1 A1.flac\n<region> lokey=47 hikey=52 pitch_keycenter=48 hivel=25 tune=2 sample=RDE88_V Samples//XFRde88 V1 C2.flac\n<region> lokey=53 hikey=58 pitch_keycenter=57 hivel=25 sample=RDE88_V Samples//XFRde88 V1 A2.flac\n<region> lokey=59 hikey=61 hivel=54 sample=RDE88_V Samples//XFRde88 V1 C3.flac\n<region> lokey=62 hikey=64 pitch_keycenter=63 hivel=25 sample=RDE88_V Samples//XFRde88 V1 D#3.flac\n<region> lokey=65 hikey=67 pitch_keycenter=66 hivel=25 sample=RDE88_V Samples//XFRde88 V1 F#3.flac\n<region> lokey=68 hikey=70 pitch_keycenter=69 hivel=25 sample=RDE88_V Samples//XFRde88 V1 A3.flac\n<region> lokey=71 hikey=74 pitch_keycenter=72 hivel=25 sample=RDE88_V Samples//XFRde88 V1 C4.flac\n<region> lokey=75 hikey=79 pitch_keycenter=78 hivel=25 sample=RDE88_V Samples//XFRde88 V1 F#4.flac\n<region> lokey=80 hikey=82 pitch_keycenter=81 hivel=25 sample=RDE88_V Samples//XFRde88 V1 A4.flac\n<region> lokey=83 hikey=85 pitch_keycenter=84 hivel=25 sample=RDE88_V Samples//XFRde88 V1 C5.flac\n<region> lokey=86 hikey=88 pitch_keycenter=87 hivel=25 sample=RDE88_V Samples//XFRde88 V1 D#5.flac\n<region> lokey=89 hikey=91 pitch_keycenter=90 hivel=25 sample=RDE88_V Samples//XFRde88 V1 F#5.flac\n<region> lokey=92 hikey=94 pitch_keycenter=93 hivel=25 sample=RDE88_V Samples//XFRde88 V1 A5.flac\n<region> lokey=95 hikey=97 pitch_keycenter=96 hivel=25 sample=RDE88_V Samples//XFRde88 V1 C6.flac\n<region> lokey=98 hikey=100 pitch_keycenter=99 hivel=25 sample=RDE88_V Samples//XFRde88 V1 D#6.flac\n<region> lokey=101 hikey=103 pitch_keycenter=102 hivel=25 sample=RDE88_V Samples//XFRde88 V1 F#6.flac\n<region> lokey=104 hikey=106 pitch_keycenter=105 hivel=25 sample=RDE88_V Samples//XFRde88 V1 A6.flac\n<region> lokey=107 pitch_keycenter=108 hivel=25 sample=RDE88_V Samples//XFRde88 V1 C7.flac\n<region> hikey=22 pitch_keycenter=21 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 A-1.flac\n<region> lokey=23 hikey=25 pitch_keycenter=24 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C0.flac\n<region> lokey=26 hikey=28 pitch_keycenter=27 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 D#0.flac\n<region> lokey=29 hikey=32 pitch_keycenter=30 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 F#0.flac\n<region> lokey=33 hikey=37 pitch_keycenter=36 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C1.flac\n<region> lokey=38 hikey=40 pitch_keycenter=39 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 D#1.flac\n<region> lokey=41 hikey=43 pitch_keycenter=42 lovel=34 hivel=54 sample=RDE88_V Samples//XFRde88 V2 F#1.flac\n<region> lokey=44 hikey=46 pitch_keycenter=45 lovel=47 hivel=63 sample=RDE88_V Samples//XFRde88 V2 A1.flac\n<region> lokey=47 hikey=49 pitch_keycenter=48 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C2.flac\n<region> lokey=50 hikey=52 pitch_keycenter=51 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 D#2.flac\n<region> lokey=53 hikey=55 pitch_keycenter=54 lovel=26 hivel=75 sample=RDE88_V Samples//XFRde88 V2 F#2.flac\n<region> lokey=56 hikey=58 pitch_keycenter=57 lovel=26 hivel=67 sample=RDE88_V Samples//XFRde88 V2 A2.flac\n<region> lokey=62 hikey=64 pitch_keycenter=63 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 D#3.flac\n<region> lokey=65 hikey=67 pitch_keycenter=66 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 F#3.flac\n<region> lokey=68 hikey=70 pitch_keycenter=69 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 A3.flac\n<region> lokey=71 hikey=74 pitch_keycenter=72 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C4.flac\n<region> lokey=75 hikey=79 pitch_keycenter=78 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 F#4.flac\n<region> lokey=80 hikey=82 pitch_keycenter=81 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 A4.flac\n<region> lokey=83 hikey=85 pitch_keycenter=84 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C5.flac\n<region> lokey=86 hikey=88 pitch_keycenter=87 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 D#5.flac\n<region> lokey=89 hikey=91 pitch_keycenter=90 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 F#5.flac\n<region> lokey=92 hikey=94 pitch_keycenter=93 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 A5.flac\n<region> lokey=95 hikey=97 pitch_keycenter=96 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C6.flac\n<region> lokey=98 hikey=100 pitch_keycenter=99 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 D#6.flac\n<region> lokey=101 hikey=103 pitch_keycenter=102 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 F#6.flac\n<region> lokey=104 hikey=106 pitch_keycenter=105 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 A6.flac\n<region> lokey=107 pitch_keycenter=108 lovel=26 hivel=54 sample=RDE88_V Samples//XFRde88 V2 C7.flac\n<region> hikey=22 pitch_keycenter=21 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 A-1.flac\n<region> lokey=23 hikey=25 pitch_keycenter=24 lovel=55 hivel=83 volume=-4.000000 sample=RDE88_V Samples//XFRde88 V3 C0.flac\n<region> lokey=26 hikey=28 pitch_keycenter=27 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 D#0.flac\n<region> lokey=29 hikey=31 pitch_keycenter=30 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#0.flac\n<region> lokey=32 hikey=34 pitch_keycenter=33 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 A0.flac\n<region> lokey=35 hikey=37 pitch_keycenter=36 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C1.flac\n<region> lokey=38 hikey=40 pitch_keycenter=39 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 D#1.flac\n<region> lokey=41 hikey=43 pitch_keycenter=42 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#1.flac\n<region> lokey=44 hikey=46 pitch_keycenter=45 lovel=64 hivel=83 sample=RDE88_V Samples//XFRde88 V3 A1.flac\n<region> lokey=47 hikey=49 pitch_keycenter=48 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C2.flac\n<region> lokey=50 hikey=52 pitch_keycenter=51 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 D#2.flac\n<region> lokey=53 hikey=55 pitch_keycenter=54 lovel=76 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#2.flac\n<region> lokey=56 hikey=58 pitch_keycenter=57 lovel=68 hivel=96 sample=RDE88_V Samples//XFRde88 V3 A2.flac\n<region> lokey=59 hikey=61 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C3.flac\n<region> lokey=62 hikey=64 pitch_keycenter=63 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 D#3.flac\n<region> lokey=65 hikey=67 pitch_keycenter=66 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#3.flac\n<region> lokey=68 hikey=70 pitch_keycenter=69 lovel=55 hivel=83 volume=-1.000000 sample=RDE88_V Samples//XFRde88 V3 A3.flac\n<region> lokey=71 hikey=74 pitch_keycenter=72 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C4.flac\n<region> lokey=75 hikey=79 pitch_keycenter=78 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#4.flac\n<region> lokey=80 hikey=82 pitch_keycenter=81 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 A4.flac\n<region> lokey=83 hikey=85 pitch_keycenter=84 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C5.flac\n<region> lokey=86 hikey=88 pitch_keycenter=87 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 D#5.flac\n<region> lokey=89 hikey=91 pitch_keycenter=90 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#5.flac\n<region> lokey=92 hikey=94 pitch_keycenter=93 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 A5.flac\n<region> lokey=95 hikey=97 pitch_keycenter=96 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C6.flac\n<region> lokey=98 hikey=100 pitch_keycenter=99 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 D#6.flac\n<region> lokey=101 hikey=103 pitch_keycenter=102 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 F#6.flac\n<region> lokey=104 hikey=106 pitch_keycenter=105 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 A6.flac\n<region> lokey=107 pitch_keycenter=108 lovel=55 hivel=83 sample=RDE88_V Samples//XFRde88 V3 C7.flac\n<region> hikey=25 pitch_keycenter=24 lovel=84 sample=RDE88_V Samples//XFRde88 V4 C0.flac\n<region> lokey=26 hikey=28 pitch_keycenter=27 lovel=84 sample=RDE88_V Samples//XFRde88 V4 D#0.flac\n<region> lokey=29 hikey=31 pitch_keycenter=30 lovel=84 sample=RDE88_V Samples//XFRde88 V4 F#0.flac\n<region> lokey=32 hikey=34 pitch_keycenter=33 lovel=84 sample=RDE88_V Samples//XFRde88 V4 A0.flac\n<region> lokey=35 hikey=37 pitch_keycenter=36 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 C1.flac\n<region> lokey=38 hikey=40 pitch_keycenter=39 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 D#1.flac\n<region> lokey=41 hikey=43 pitch_keycenter=42 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 F#1.flac\n<region> lokey=44 hikey=46 pitch_keycenter=45 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 A1.flac\n<region> lokey=47 hikey=49 pitch_keycenter=48 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 C2.flac\n<region> lokey=50 hikey=52 pitch_keycenter=51 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 D#2.flac\n<region> lokey=53 hikey=55 pitch_keycenter=54 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 F#2.flac\n<region> lokey=56 hikey=58 pitch_keycenter=57 lovel=97 hivel=105 sample=RDE88_V Samples//XFRde88 V4 A2.flac\n<region> lokey=59 hikey=61 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 C3.flac\n<region> lokey=62 hikey=64 pitch_keycenter=63 lovel=84 hivel=105 volume=3.000000 sample=RDE88_V Samples//XFRde88 V4 D#3.flac\n<region> lokey=65 hikey=67 pitch_keycenter=66 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 F#3.flac\n<region> lokey=68 hikey=70 pitch_keycenter=69 lovel=84 hivel=106 volume=3.000000 sample=RDE88_V Samples//XFRde88 V4 A3.flac\n<region> lokey=71 hikey=74 pitch_keycenter=72 lovel=84 hivel=114 sample=RDE88_V Samples//XFRde88 V4 C4.flac\n<region> lokey=75 hikey=79 pitch_keycenter=78 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 F#4.flac\n<region> lokey=80 hikey=82 pitch_keycenter=81 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 A4.flac\n<region> lokey=83 hikey=85 pitch_keycenter=84 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 C5.flac\n<region> lokey=86 hikey=88 pitch_keycenter=87 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 D#5.flac\n<region> lokey=89 hikey=91 pitch_keycenter=90 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 F#5.flac\n<region> lokey=92 hikey=94 pitch_keycenter=93 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 A5.flac\n<region> lokey=95 hikey=97 pitch_keycenter=96 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 C6.flac\n<region> lokey=98 pitch_keycenter=99 lovel=84 hivel=105 sample=RDE88_V Samples//XFRde88 V4 D#6.flac\n<region> lokey=35 hikey=37 pitch_keycenter=36 lovel=106 sample=RDE88_V Samples//XFRde88 V5 C1.flac\n<region> lokey=38 hikey=40 pitch_keycenter=39 lovel=106 sample=RDE88_V Samples//XFRde88 V5 D#1.flac\n<region> lokey=41 hikey=44 pitch_keycenter=42 lovel=106 sample=RDE88_V Samples//XFRde88 V5 F#1.flac\n<region> lokey=45 hikey=49 pitch_keycenter=48 lovel=106 hivel=115 sample=RDE88_V Samples//XFRde88 V5 C2.flac\n<region> lokey=50 hikey=55 pitch_keycenter=51 lovel=106 sample=RDE88_V Samples//XFRde88 V5 D#2.flac\n<region> lokey=62 hikey=64 pitch_keycenter=63 lovel=106 hivel=115 sample=RDE88_V Samples//XFRde88 V5 D#3.flac\n<region> lokey=65 hikey=67 pitch_keycenter=66 lovel=106 sample=RDE88_V Samples//XFRde88 V5 F#3.flac\n<region> lokey=68 hikey=70 pitch_keycenter=69 lovel=106 sample=RDE88_V Samples//XFRde88 V5 A3.flac\n<region> lokey=71 hikey=77 pitch_keycenter=72 lovel=115 sample=RDE88_V Samples//XFRde88 V5 C4.flac\n<region> lokey=75 hikey=79 pitch_keycenter=78 lovel=106 hivel=115 sample=RDE88_V Samples//XFRde88 V5 F#4.flac\n<region> lokey=80 hikey=82 pitch_keycenter=81 lovel=106 hivel=115 sample=RDE88_V Samples//XFRde88 V5 A4.flac\n<region> lokey=83 hikey=85 pitch_keycenter=84 lovel=106 hivel=116 sample=RDE88_V Samples//XFRde88 V5 C5.flac\n<region> lokey=86 hikey=88 pitch_keycenter=87 lovel=106 hivel=116 sample=RDE88_V Samples//XFRde88 V5 D#5.flac\n<region> lokey=89 hikey=91 pitch_keycenter=90 lovel=106 hivel=116 sample=RDE88_V Samples//XFRde88 V5 F#5.flac\n<region> lokey=92 pitch_keycenter=93 lovel=106 hivel=116 sample=RDE88_V Samples//XFRde88 V5 A5.flac\n<region> lokey=45 hikey=49 pitch_keycenter=48 lovel=116 sample=RDE88_V Samples//XFRde88 V6 C2.flac\n<region> lokey=56 hikey=61 lovel=106 sample=RDE88_V Samples//XFRde88 V6 C3.flac\n<region> lokey=62 hikey=64 pitch_keycenter=63 lovel=116 sample=RDE88_V Samples//XFRde88 V6 D#3.flac\n<region> lokey=78 hikey=82 pitch_keycenter=81 lovel=117 sample=RDE88_V Samples//XFRde88 V7 A4.flac\n<region> lokey=83 pitch_keycenter=84 lovel=117 sample=RDE88_V Samples//XFRde88 V6 C5.flac\n',
        files={'RDE88_V Samples\\\\XFRde88 V1 A-1.flac': {'numChannels': 1, 'numFrames': 405791, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A0.flac': {'numChannels': 1, 'numFrames': 778236, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A1.flac': {'numChannels': 1, 'numFrames': 634470, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A2.flac': {'numChannels': 1, 'numFrames': 570699, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A3.flac': {'numChannels': 1, 'numFrames': 361934, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A4.flac': {'numChannels': 1, 'numFrames': 256839, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A5.flac': {'numChannels': 1, 'numFrames': 182585, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 A6.flac': {'numChannels': 1, 'numFrames': 46876, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C0.flac': {'numChannels': 1, 'numFrames': 462207, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C1.flac': {'numChannels': 1, 'numFrames': 639445, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C2.flac': {'numChannels': 1, 'numFrames': 443370, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C3.flac': {'numChannels': 1, 'numFrames': 416750, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C4.flac': {'numChannels': 1, 'numFrames': 322778, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C5.flac': {'numChannels': 1, 'numFrames': 195642, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C6.flac': {'numChannels': 1, 'numFrames': 177503, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 C7.flac': {'numChannels': 1, 'numFrames': 39099, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 D#0.flac': {'numChannels': 1, 'numFrames': 418693, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 D#1.flac': {'numChannels': 1, 'numFrames': 529001, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 D#3.flac': {'numChannels': 1, 'numFrames': 472029, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 D#5.flac': {'numChannels': 1, 'numFrames': 250431, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 D#6.flac': {'numChannels': 1, 'numFrames': 135880, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 F#0.flac': {'numChannels': 1, 'numFrames': 700658, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 F#1.flac': {'numChannels': 1, 'numFrames': 439308, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 F#3.flac': {'numChannels': 1, 'numFrames': 368280, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 F#4.flac': {'numChannels': 1, 'numFrames': 339044, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 F#5.flac': {'numChannels': 1, 'numFrames': 220234, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V1 F#6.flac': {'numChannels': 1, 'numFrames': 71511, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A-1.flac': {'numChannels': 1, 'numFrames': 295960, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A1.flac': {'numChannels': 1, 'numFrames': 862472, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A2.flac': {'numChannels': 1, 'numFrames': 569934, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A3.flac': {'numChannels': 1, 'numFrames': 371964, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A4.flac': {'numChannels': 1, 'numFrames': 285670, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A5.flac': {'numChannels': 1, 'numFrames': 200084, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 A6.flac': {'numChannels': 1, 'numFrames': 43569, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C0.flac': {'numChannels': 1, 'numFrames': 396029, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C1.flac': {'numChannels': 1, 'numFrames': 741461, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C2.flac': {'numChannels': 1, 'numFrames': 494509, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C4.flac': {'numChannels': 1, 'numFrames': 358760, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C5.flac': {'numChannels': 1, 'numFrames': 233734, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C6.flac': {'numChannels': 1, 'numFrames': 182035, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 C7.flac': {'numChannels': 1, 'numFrames': 56192, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 D#0.flac': {'numChannels': 1, 'numFrames': 344019, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 D#1.flac': {'numChannels': 1, 'numFrames': 597203, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 D#2.flac': {'numChannels': 1, 'numFrames': 680723, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 D#3.flac': {'numChannels': 1, 'numFrames': 461060, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 D#5.flac': {'numChannels': 1, 'numFrames': 286700, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 D#6.flac': {'numChannels': 1, 'numFrames': 166757, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#0.flac': {'numChannels': 1, 'numFrames': 865628, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#1.flac': {'numChannels': 1, 'numFrames': 938220, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#2.flac': {'numChannels': 1, 'numFrames': 641719, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#3.flac': {'numChannels': 1, 'numFrames': 406982, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#4.flac': {'numChannels': 1, 'numFrames': 460648, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#5.flac': {'numChannels': 1, 'numFrames': 235684, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V2 F#6.flac': {'numChannels': 1, 'numFrames': 62347, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A-1.flac': {'numChannels': 1, 'numFrames': 428764, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A0.flac': {'numChannels': 1, 'numFrames': 944262, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A1.flac': {'numChannels': 1, 'numFrames': 1006560, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A2.flac': {'numChannels': 1, 'numFrames': 678700, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A3.flac': {'numChannels': 1, 'numFrames': 371382, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A4.flac': {'numChannels': 1, 'numFrames': 313867, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A5.flac': {'numChannels': 1, 'numFrames': 220562, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 A6.flac': {'numChannels': 1, 'numFrames': 50926, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C0.flac': {'numChannels': 1, 'numFrames': 580253, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C1.flac': {'numChannels': 1, 'numFrames': 941958, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C2.flac': {'numChannels': 1, 'numFrames': 532242, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C3.flac': {'numChannels': 1, 'numFrames': 523897, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C4.flac': {'numChannels': 1, 'numFrames': 442056, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C5.flac': {'numChannels': 1, 'numFrames': 216816, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C6.flac': {'numChannels': 1, 'numFrames': 182608, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 C7.flac': {'numChannels': 1, 'numFrames': 55554, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 D#0.flac': {'numChannels': 1, 'numFrames': 418601, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 D#1.flac': {'numChannels': 1, 'numFrames': 793402, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 D#2.flac': {'numChannels': 1, 'numFrames': 694870, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 D#3.flac': {'numChannels': 1, 'numFrames': 508486, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 D#5.flac': {'numChannels': 1, 'numFrames': 293391, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 D#6.flac': {'numChannels': 1, 'numFrames': 162187, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#0.flac': {'numChannels': 1, 'numFrames': 1194763, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#1.flac': {'numChannels': 1, 'numFrames': 888775, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#2.flac': {'numChannels': 1, 'numFrames': 782735, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#3.flac': {'numChannels': 1, 'numFrames': 464663, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#4.flac': {'numChannels': 1, 'numFrames': 402188, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#5.flac': {'numChannels': 1, 'numFrames': 235358, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V3 F#6.flac': {'numChannels': 1, 'numFrames': 58749, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 A0.flac': {'numChannels': 1, 'numFrames': 962869, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 A1.flac': {'numChannels': 1, 'numFrames': 888060, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 A2.flac': {'numChannels': 1, 'numFrames': 711191, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 A3.flac': {'numChannels': 1, 'numFrames': 396349, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 A4.flac': {'numChannels': 1, 'numFrames': 321848, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 A5.flac': {'numChannels': 1, 'numFrames': 228058, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C0.flac': {'numChannels': 1, 'numFrames': 618745, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C1.flac': {'numChannels': 1, 'numFrames': 976417, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C2.flac': {'numChannels': 1, 'numFrames': 558491, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C3.flac': {'numChannels': 1, 'numFrames': 572025, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C4.flac': {'numChannels': 1, 'numFrames': 367356, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C5.flac': {'numChannels': 1, 'numFrames': 234386, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 C6.flac': {'numChannels': 1, 'numFrames': 192705, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 D#0.flac': {'numChannels': 1, 'numFrames': 624545, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 D#1.flac': {'numChannels': 1, 'numFrames': 891119, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 D#2.flac': {'numChannels': 1, 'numFrames': 687572, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 D#3.flac': {'numChannels': 1, 'numFrames': 425307, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 D#5.flac': {'numChannels': 1, 'numFrames': 275795, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 D#6.flac': {'numChannels': 1, 'numFrames': 160430, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 F#0.flac': {'numChannels': 1, 'numFrames': 1232271, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 F#1.flac': {'numChannels': 1, 'numFrames': 1035720, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 F#2.flac': {'numChannels': 1, 'numFrames': 769551, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 F#3.flac': {'numChannels': 1, 'numFrames': 463768, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 F#4.flac': {'numChannels': 1, 'numFrames': 447801, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V4 F#5.flac': {'numChannels': 1, 'numFrames': 239038, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 A3.flac': {'numChannels': 1, 'numFrames': 471450, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 A4.flac': {'numChannels': 1, 'numFrames': 313718, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 A5.flac': {'numChannels': 1, 'numFrames': 244213, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 C1.flac': {'numChannels': 1, 'numFrames': 1070573, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 C2.flac': {'numChannels': 1, 'numFrames': 615643, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 C4.flac': {'numChannels': 1, 'numFrames': 421015, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 C5.flac': {'numChannels': 1, 'numFrames': 259419, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 D#1.flac': {'numChannels': 1, 'numFrames': 917254, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 D#2.flac': {'numChannels': 1, 'numFrames': 861234, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 D#3.flac': {'numChannels': 1, 'numFrames': 508154, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 D#5.flac': {'numChannels': 1, 'numFrames': 293121, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 F#1.flac': {'numChannels': 1, 'numFrames': 942143, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 F#3.flac': {'numChannels': 1, 'numFrames': 468578, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 F#4.flac': {'numChannels': 1, 'numFrames': 397206, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V5 F#5.flac': {'numChannels': 1, 'numFrames': 221958, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V6 C2.flac': {'numChannels': 1, 'numFrames': 620167, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V6 C3.flac': {'numChannels': 1, 'numFrames': 548522, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V6 C5.flac': {'numChannels': 1, 'numFrames': 261910, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V6 D#3.flac': {'numChannels': 1, 'numFrames': 546464, 'sampleRate': 44100}, 'RDE88_V Samples\\\\XFRde88 V7 A4.flac': {'numChannels': 1, 'numFrames': 333632, 'sampleRate': 44100}},
    ),
    'synth_pad_superjx': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Synth/SuperJX 4 Chorus Pad.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> loop_mode=loop_continuous amp_veltrack=38.500000 ampeg_release=0.100000\n<region> hikey=26 pitch_keycenter=24 end=195840 loop_start=49867 loop_end=193601 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C0.flac\n<region> lokey=27 hikey=29 pitch_keycenter=28 end=198015 loop_start=88296 loop_end=193880 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E0.flac\n<region> lokey=30 hikey=33 pitch_keycenter=31 end=238588 loop_start=62289 loop_end=236232 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad G0.flac\n<region> lokey=34 hikey=35 pitch_keycenter=34 end=197162 loop_start=35097 loop_end=192673 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#0.flac\n<region> lokey=36 hikey=37 pitch_keycenter=36 end=181554 loop_start=47294 loop_end=178967 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C1.flac\n<region> lokey=38 hikey=39 pitch_keycenter=38 end=207447 loop_start=39011 loop_end=205014 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad D1.flac\n<region> key=40 end=200111 loop_start=35616 loop_end=197770 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E1.flac\n<region> lokey=41 hikey=43 pitch_keycenter=41 end=180104 loop_start=49291 loop_end=176724 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad F1.flac\n<region> lokey=44 hikey=45 pitch_keycenter=45 end=218772 loop_start=80441 loop_end=216562 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A1.flac\n<region> lokey=46 hikey=47 pitch_keycenter=46 end=204902 loop_start=27742 loop_end=201110 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#1.flac\n<region> lokey=48 hikey=50 pitch_keycenter=48 end=212993 loop_start=60860 loop_end=209081 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C2.flac\n<region> lokey=51 hikey=53 pitch_keycenter=52 end=214041 loop_start=24273 loop_end=212791 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E2.flac\n<region> lokey=54 hikey=57 pitch_keycenter=55 end=189411 loop_start=41551 loop_end=186573 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad G2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=58 end=198834 loop_start=46264 loop_end=196011 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#2.flac\n<region> lokey=60 hikey=62 end=217906 loop_start=65981 loop_end=215655 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C3.flac\n<region> lokey=63 hikey=65 pitch_keycenter=64 end=225951 loop_start=44951 loop_end=223680 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E3.flac\n<region> lokey=66 hikey=69 pitch_keycenter=67 end=204343 loop_start=46802 loop_end=200735 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad G3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=70 end=167201 loop_start=25854 loop_end=165319 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#3.flac\n<region> lokey=72 hikey=74 pitch_keycenter=72 end=213109 loop_start=47954 loop_end=208616 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C4.flac\n<region> lokey=75 hikey=77 pitch_keycenter=76 end=201533 loop_start=47611 loop_end=199588 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E4.flac\n<region> lokey=78 hikey=81 pitch_keycenter=79 end=149574 loop_start=27064 loop_end=147683 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad G4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=82 end=154188 loop_start=31191 loop_end=150404 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#4.flac\n<region> lokey=84 hikey=86 pitch_keycenter=84 end=127743 loop_start=21046 loop_end=126334 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C5.flac\n<region> lokey=87 hikey=89 pitch_keycenter=88 end=121577 loop_start=26958 loop_end=120043 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E5.flac\n<region> lokey=90 hikey=93 pitch_keycenter=91 end=176727 loop_start=41997 loop_end=170939 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad G5.flac\n<region> lokey=94 hikey=95 pitch_keycenter=94 end=102136 loop_start=24629 loop_end=100517 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#5.flac\n<region> lokey=96 hikey=98 pitch_keycenter=96 end=119672 loop_start=21745 loop_end=117700 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C6.flac\n<region> lokey=99 hikey=101 pitch_keycenter=100 end=141171 loop_start=23363 loop_end=136786 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad E6.flac\n<region> lokey=102 hikey=105 pitch_keycenter=103 end=92958 loop_start=27522 loop_end=91664 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad G6.flac\n<region> lokey=106 hikey=107 pitch_keycenter=106 end=97846 loop_start=18175 loop_end=96413 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad A#6.flac\n<region> lokey=108 pitch_keycenter=108 end=74738 loop_start=22381 loop_end=73944 sample=SuperJX 4 Osc Chorus Pad Samples/XFSuperJX4ChrsPad C7.flac\n',
        files={'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#0.flac': {'numChannels': 2, 'numFrames': 197162, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#1.flac': {'numChannels': 2, 'numFrames': 204902, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#2.flac': {'numChannels': 2, 'numFrames': 198834, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#3.flac': {'numChannels': 2, 'numFrames': 167201, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#4.flac': {'numChannels': 2, 'numFrames': 154188, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#5.flac': {'numChannels': 2, 'numFrames': 102136, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A#6.flac': {'numChannels': 2, 'numFrames': 97846, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad A1.flac': {'numChannels': 2, 'numFrames': 218772, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C0.flac': {'numChannels': 2, 'numFrames': 195840, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C1.flac': {'numChannels': 2, 'numFrames': 181554, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C2.flac': {'numChannels': 2, 'numFrames': 212993, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C3.flac': {'numChannels': 2, 'numFrames': 217906, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C4.flac': {'numChannels': 2, 'numFrames': 213109, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C5.flac': {'numChannels': 2, 'numFrames': 127743, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C6.flac': {'numChannels': 2, 'numFrames': 119672, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad C7.flac': {'numChannels': 2, 'numFrames': 74738, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad D1.flac': {'numChannels': 2, 'numFrames': 207447, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E0.flac': {'numChannels': 2, 'numFrames': 198015, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E1.flac': {'numChannels': 2, 'numFrames': 200111, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E2.flac': {'numChannels': 2, 'numFrames': 214041, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E3.flac': {'numChannels': 2, 'numFrames': 225951, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E4.flac': {'numChannels': 2, 'numFrames': 201533, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E5.flac': {'numChannels': 2, 'numFrames': 121577, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad E6.flac': {'numChannels': 2, 'numFrames': 141171, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad F1.flac': {'numChannels': 2, 'numFrames': 180104, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad G0.flac': {'numChannels': 2, 'numFrames': 238588, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad G2.flac': {'numChannels': 2, 'numFrames': 189411, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad G3.flac': {'numChannels': 2, 'numFrames': 204343, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad G4.flac': {'numChannels': 2, 'numFrames': 149574, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad G5.flac': {'numChannels': 2, 'numFrames': 176727, 'sampleRate': 44100}, 'SuperJX 4 Osc Chorus Pad Samples\\XFSuperJX4ChrsPad G6.flac': {'numChannels': 2, 'numFrames': 92958, 'sampleRate': 44100}},
    ),
    'mallet_balafon': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Mallet/Balafon.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> amp_veltrack=0.000000 ampeg_attack=0.001000\n<region> hikey=55 pitch_keycenter=55 hivel=18 loop_end=46057 sample=Balafon Samples/XFBalafon 01 G2.flac\n<region> lokey=56 hikey=57 pitch_keycenter=57 hivel=18 loop_end=70544 sample=Balafon Samples/XFBalafon 01 A2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=59 hivel=18 loop_end=38912 sample=Balafon Samples/XFBalafon 01 B2.flac\n<region> key=60 hivel=18 loop_end=46336 sample=Balafon Samples/XFBalafon 01 C3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=62 hivel=18 loop_end=63488 sample=Balafon Samples/XFBalafon 01 D3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=64 hivel=18 loop_end=43520 sample=Balafon Samples/XFBalafon 01 E3.flac\n<region> key=65 hivel=18 loop_end=47104 sample=Balafon Samples/XFBalafon 01 F3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=67 hivel=18 loop_end=43008 sample=Balafon Samples/XFBalafon 01 G3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=69 hivel=18 loop_end=37888 sample=Balafon Samples/XFBalafon 01 A3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=71 hivel=18 loop_end=29696 sample=Balafon Samples/XFBalafon 01 B3.flac\n<region> key=72 hivel=18 loop_end=33280 sample=Balafon Samples/XFBalafon 01 C4.flac\n<region> lokey=73 hikey=74 pitch_keycenter=74 hivel=18 loop_end=41984 sample=Balafon Samples/XFBalafon 01 D4.flac\n<region> lokey=75 hikey=76 pitch_keycenter=76 hivel=18 loop_end=31232 sample=Balafon Samples/XFBalafon 01 E4.flac\n<region> key=77 hivel=18 loop_end=23040 sample=Balafon Samples/XFBalafon 01 F4.flac\n<region> lokey=78 hikey=79 pitch_keycenter=79 hivel=18 loop_end=34048 sample=Balafon Samples/XFBalafon 01 G4.flac\n<region> lokey=80 hikey=81 pitch_keycenter=81 hivel=18 loop_end=23808 sample=Balafon Samples/XFBalafon 01 A4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=83 hivel=18 loop_end=29184 sample=Balafon Samples/XFBalafon 01 B4.flac\n<region> key=84 hivel=18 loop_end=21248 sample=Balafon Samples/XFBalafon 01 C5.flac\n<region> lokey=85 hikey=86 pitch_keycenter=86 hivel=18 loop_end=21760 sample=Balafon Samples/XFBalafon 01 D5.flac\n<region> lokey=87 hikey=88 pitch_keycenter=88 hivel=18 loop_end=12416 sample=Balafon Samples/XFBalafon 01 E5.flac\n<region> key=89 hivel=18 loop_end=16000 sample=Balafon Samples/XFBalafon 01 F5.flac\n<region> lokey=90 pitch_keycenter=91 hivel=18 loop_end=9408 sample=Balafon Samples/XFBalafon 01 G5.flac\n<region> hikey=55 pitch_keycenter=55 lovel=19 hivel=35 loop_end=46080 sample=Balafon Samples/XFBalafon 02 G2.flac\n<region> lokey=56 hikey=57 pitch_keycenter=57 lovel=19 hivel=35 loop_end=72816 sample=Balafon Samples/XFBalafon 02 A2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=59 lovel=19 hivel=35 loop_end=46080 sample=Balafon Samples/XFBalafon 02 B2.flac\n<region> key=60 lovel=19 hivel=35 loop_end=50176 sample=Balafon Samples/XFBalafon 02 C3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=62 lovel=19 hivel=35 loop_end=69632 sample=Balafon Samples/XFBalafon 02 D3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=64 lovel=19 hivel=35 loop_end=41472 sample=Balafon Samples/XFBalafon 02 E3.flac\n<region> key=65 lovel=19 hivel=35 loop_end=45056 sample=Balafon Samples/XFBalafon 02 F3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=67 lovel=19 hivel=35 loop_end=41472 sample=Balafon Samples/XFBalafon 02 G3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=69 lovel=19 hivel=35 loop_end=45056 sample=Balafon Samples/XFBalafon 02 A3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=71 lovel=19 hivel=35 loop_end=29056 sample=Balafon Samples/XFBalafon 02 B3.flac\n<region> key=72 lovel=19 hivel=35 loop_end=33280 sample=Balafon Samples/XFBalafon 02 C4.flac\n<region> lokey=73 hikey=74 pitch_keycenter=74 lovel=19 hivel=35 loop_end=43264 sample=Balafon Samples/XFBalafon 02 D4.flac\n<region> lokey=75 hikey=76 pitch_keycenter=76 lovel=19 hivel=35 loop_end=24832 sample=Balafon Samples/XFBalafon 02 E4.flac\n<region> key=77 lovel=19 hivel=35 loop_end=21120 sample=Balafon Samples/XFBalafon 02 F4.flac\n<region> lokey=78 hikey=79 pitch_keycenter=79 lovel=19 hivel=35 loop_end=34471 sample=Balafon Samples/XFBalafon 02 G4.flac\n<region> lokey=80 hikey=81 pitch_keycenter=81 lovel=19 hivel=35 loop_end=25856 sample=Balafon Samples/XFBalafon 02 A4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=83 lovel=19 hivel=35 loop_end=28928 sample=Balafon Samples/XFBalafon 02 B4.flac\n<region> key=84 lovel=19 hivel=35 loop_end=23296 sample=Balafon Samples/XFBalafon 02 C5.flac\n<region> lokey=85 hikey=86 pitch_keycenter=86 lovel=19 hivel=39 loop_end=21248 sample=Balafon Samples/XFBalafon 02 D5.flac\n<region> lokey=87 hikey=88 pitch_keycenter=88 lovel=19 hivel=35 loop_end=11264 sample=Balafon Samples/XFBalafon 02 E5.flac\n<region> key=89 lovel=19 hivel=35 loop_end=17024 sample=Balafon Samples/XFBalafon 02 F5.flac\n<region> lokey=90 pitch_keycenter=91 lovel=19 hivel=35 loop_end=15360 sample=Balafon Samples/XFBalafon 02 G5.flac\n<region> hikey=55 pitch_keycenter=55 lovel=36 hivel=59 loop_end=42752 sample=Balafon Samples/XFBalafon 03 G2.flac\n<region> lokey=56 hikey=57 pitch_keycenter=57 lovel=36 hivel=59 loop_end=70500 sample=Balafon Samples/XFBalafon 03 A2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=59 lovel=36 hivel=59 loop_end=44032 sample=Balafon Samples/XFBalafon 03 B2.flac\n<region> key=60 lovel=36 hivel=59 loop_end=58112 sample=Balafon Samples/XFBalafon 03 C3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=62 lovel=36 hivel=59 loop_end=68608 sample=Balafon Samples/XFBalafon 03 D3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=64 lovel=36 hivel=59 loop_end=47104 sample=Balafon Samples/XFBalafon 03 E3.flac\n<region> key=65 lovel=36 hivel=59 loop_end=47104 sample=Balafon Samples/XFBalafon 03 F3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=67 lovel=36 hivel=59 loop_end=53760 sample=Balafon Samples/XFBalafon 03 G3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=69 lovel=36 hivel=59 loop_end=46080 sample=Balafon Samples/XFBalafon 03 A3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=71 lovel=36 hivel=59 loop_end=32000 sample=Balafon Samples/XFBalafon 03 B3.flac\n<region> key=72 lovel=36 hivel=59 loop_end=30720 sample=Balafon Samples/XFBalafon 03 C4.flac\n<region> lokey=73 hikey=74 pitch_keycenter=74 lovel=36 hivel=59 loop_end=43008 sample=Balafon Samples/XFBalafon 03 D4.flac\n<region> lokey=75 hikey=76 pitch_keycenter=76 lovel=36 hivel=59 loop_end=31232 sample=Balafon Samples/XFBalafon 03 E4.flac\n<region> key=77 lovel=36 hivel=59 loop_end=22784 sample=Balafon Samples/XFBalafon 03 F4.flac\n<region> lokey=78 hikey=79 pitch_keycenter=79 lovel=36 hivel=59 loop_end=31906 sample=Balafon Samples/XFBalafon 03 G4.flac\n<region> lokey=80 hikey=81 pitch_keycenter=81 lovel=36 hivel=59 loop_end=29440 sample=Balafon Samples/XFBalafon 03 A4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=83 lovel=36 hivel=59 loop_end=29184 sample=Balafon Samples/XFBalafon 03 B4.flac\n<region> key=84 lovel=36 hivel=59 loop_end=20608 sample=Balafon Samples/XFBalafon 03 C5.flac\n<region> lokey=85 hikey=86 pitch_keycenter=86 lovel=40 hivel=59 loop_end=26624 sample=Balafon Samples/XFBalafon 03 D5.flac\n<region> lokey=87 hikey=88 pitch_keycenter=88 lovel=36 hivel=59 loop_end=12032 sample=Balafon Samples/XFBalafon 03 E5.flac\n<region> key=89 lovel=36 hivel=59 loop_end=14976 sample=Balafon Samples/XFBalafon 03 F5.flac\n<region> lokey=90 pitch_keycenter=91 lovel=36 hivel=59 loop_end=13056 sample=Balafon Samples/XFBalafon 03 G5.flac\n<region> hikey=55 pitch_keycenter=55 lovel=60 hivel=89 loop_end=41984 sample=Balafon Samples/XFBalafon 05 G2.flac\n<region> lokey=56 hikey=57 pitch_keycenter=57 lovel=60 hivel=89 loop_end=73352 sample=Balafon Samples/XFBalafon 05 A2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=59 lovel=60 hivel=89 loop_end=39936 sample=Balafon Samples/XFBalafon 05 B2.flac\n<region> key=60 lovel=60 hivel=89 loop_end=63488 sample=Balafon Samples/XFBalafon 05 C3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=62 lovel=60 hivel=89 loop_end=69632 sample=Balafon Samples/XFBalafon 05 D3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=64 lovel=60 hivel=89 loop_end=50688 sample=Balafon Samples/XFBalafon 05 E3.flac\n<region> key=65 lovel=60 hivel=89 loop_end=54272 sample=Balafon Samples/XFBalafon 05 F3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=67 lovel=60 hivel=89 loop_end=51200 sample=Balafon Samples/XFBalafon 05 G3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=69 lovel=60 hivel=89 loop_end=54272 sample=Balafon Samples/XFBalafon 05 A3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=71 lovel=60 hivel=89 loop_end=33024 sample=Balafon Samples/XFBalafon 05 B3.flac\n<region> key=72 lovel=60 hivel=89 loop_end=39168 sample=Balafon Samples/XFBalafon 05 C4.flac\n<region> lokey=73 hikey=74 pitch_keycenter=74 lovel=60 hivel=89 loop_end=48128 sample=Balafon Samples/XFBalafon 05 D4.flac\n<region> lokey=75 hikey=76 pitch_keycenter=76 lovel=60 hivel=89 loop_end=29696 sample=Balafon Samples/XFBalafon 05 E4.flac\n<region> key=77 lovel=60 hivel=89 loop_end=33646 sample=Balafon Samples/XFBalafon 05 F4.flac\n<region> lokey=78 hikey=79 pitch_keycenter=79 lovel=60 hivel=89 loop_end=39424 sample=Balafon Samples/XFBalafon 05 G4.flac\n<region> lokey=80 hikey=81 pitch_keycenter=81 lovel=60 hivel=89 loop_end=27904 sample=Balafon Samples/XFBalafon 05 A4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=83 lovel=60 hivel=89 loop_end=33792 sample=Balafon Samples/XFBalafon 05 B4.flac\n<region> key=84 lovel=60 hivel=89 loop_end=26112 sample=Balafon Samples/XFBalafon 05 C5.flac\n<region> lokey=85 hikey=86 pitch_keycenter=86 lovel=60 hivel=89 loop_end=28544 sample=Balafon Samples/XFBalafon 05 D5.flac\n<region> lokey=87 hikey=88 pitch_keycenter=88 lovel=60 hivel=89 loop_end=11680 sample=Balafon Samples/XFBalafon 05 E5.flac\n<region> key=89 lovel=60 hivel=89 loop_end=21120 sample=Balafon Samples/XFBalafon 05 F5.flac\n<region> lokey=90 pitch_keycenter=91 lovel=60 hivel=89 loop_end=13376 sample=Balafon Samples/XFBalafon 05 G5.flac\n<region> hikey=55 pitch_keycenter=55 lovel=90 hivel=118 loop_end=39936 sample=Balafon Samples/XFBalafon 07 G2.flac\n<region> lokey=56 hikey=57 pitch_keycenter=57 lovel=90 hivel=118 loop_end=66560 sample=Balafon Samples/XFBalafon 07 A2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=59 lovel=90 hivel=118 loop_end=41984 sample=Balafon Samples/XFBalafon 07 B2.flac\n<region> key=60 lovel=90 hivel=118 loop_end=73728 sample=Balafon Samples/XFBalafon 07 C3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=62 lovel=90 hivel=118 loop_end=78848 sample=Balafon Samples/XFBalafon 07 D3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=64 lovel=90 hivel=118 loop_end=50176 sample=Balafon Samples/XFBalafon 07 E3.flac\n<region> key=65 lovel=90 hivel=118 loop_end=54784 sample=Balafon Samples/XFBalafon 07 F3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=67 lovel=90 hivel=118 loop_end=54272 sample=Balafon Samples/XFBalafon 07 G3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=69 lovel=90 hivel=118 loop_end=46080 sample=Balafon Samples/XFBalafon 07 A3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=71 lovel=90 hivel=118 loop_end=37888 sample=Balafon Samples/XFBalafon 07 B3.flac\n<region> key=72 lovel=90 hivel=118 loop_end=46592 sample=Balafon Samples/XFBalafon 07 C4.flac\n<region> lokey=73 hikey=74 pitch_keycenter=74 lovel=90 hivel=118 loop_end=53248 sample=Balafon Samples/XFBalafon 07 D4.flac\n<region> lokey=75 hikey=76 pitch_keycenter=76 lovel=90 hivel=118 loop_end=30464 sample=Balafon Samples/XFBalafon 07 E4.flac\n<region> key=77 lovel=90 hivel=118 loop_end=33610 sample=Balafon Samples/XFBalafon 07 F4.flac\n<region> lokey=78 hikey=79 pitch_keycenter=79 lovel=90 hivel=118 loop_end=39424 sample=Balafon Samples/XFBalafon 07 G4.flac\n<region> lokey=80 hikey=81 pitch_keycenter=81 lovel=90 hivel=118 loop_end=30208 sample=Balafon Samples/XFBalafon 07 A4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=83 lovel=90 hivel=118 loop_end=37120 sample=Balafon Samples/XFBalafon 07 B4.flac\n<region> key=84 lovel=90 hivel=118 loop_end=24960 sample=Balafon Samples/XFBalafon 07 C5.flac\n<region> lokey=85 hikey=87 pitch_keycenter=86 lovel=90 hivel=118 loop_end=26624 sample=Balafon Samples/XFBalafon 07 D5.flac\n<region> lokey=88 hikey=89 pitch_keycenter=89 lovel=90 hivel=118 loop_end=19456 sample=Balafon Samples/XFBalafon 07 F5.flac\n<region> lokey=90 pitch_keycenter=91 lovel=90 hivel=118 loop_end=13376 sample=Balafon Samples/XFBalafon 07 G5.flac\n<region> hikey=55 pitch_keycenter=55 lovel=119 loop_end=46080 sample=Balafon Samples/XFBalafon 08 G2.flac\n<region> lokey=56 hikey=57 pitch_keycenter=57 lovel=119 loop_end=66560 sample=Balafon Samples/XFBalafon 08 A2.flac\n<region> lokey=58 hikey=59 pitch_keycenter=59 lovel=119 loop_end=43008 sample=Balafon Samples/XFBalafon 08 B2.flac\n<region> key=60 lovel=119 loop_end=73728 sample=Balafon Samples/XFBalafon 08 C3.flac\n<region> lokey=61 hikey=62 pitch_keycenter=62 lovel=119 loop_end=61440 sample=Balafon Samples/XFBalafon 08 D3.flac\n<region> lokey=63 hikey=64 pitch_keycenter=64 lovel=119 loop_end=54272 sample=Balafon Samples/XFBalafon 08 E3.flac\n<region> key=65 lovel=119 loop_end=53248 sample=Balafon Samples/XFBalafon 08 F3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=67 lovel=119 loop_end=46080 sample=Balafon Samples/XFBalafon 08 G3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=69 lovel=119 loop_end=41984 sample=Balafon Samples/XFBalafon 08 A3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=71 lovel=119 loop_end=38016 sample=Balafon Samples/XFBalafon 08 B3.flac\n<region> key=72 lovel=119 loop_end=46336 sample=Balafon Samples/XFBalafon 08 C4.flac\n<region> lokey=73 hikey=74 pitch_keycenter=74 lovel=119 loop_end=52224 sample=Balafon Samples/XFBalafon 08 D4.flac\n<region> lokey=75 hikey=76 pitch_keycenter=76 lovel=119 loop_end=31488 sample=Balafon Samples/XFBalafon 08 E4.flac\n<region> key=77 lovel=119 loop_end=28186 sample=Balafon Samples/XFBalafon 08 F4.flac\n<region> lokey=78 hikey=79 pitch_keycenter=79 lovel=119 loop_end=44800 sample=Balafon Samples/XFBalafon 08 G4.flac\n<region> lokey=80 hikey=81 pitch_keycenter=81 lovel=119 loop_end=33792 sample=Balafon Samples/XFBalafon 08 A4.flac\n<region> lokey=82 hikey=83 pitch_keycenter=83 lovel=119 loop_end=36864 sample=Balafon Samples/XFBalafon 08 B4.flac\n<region> lokey=84 hikey=86 pitch_keycenter=84 lovel=119 loop_end=25856 sample=Balafon Samples/XFBalafon 08 C5.flac\n<region> lokey=87 pitch_keycenter=89 lovel=119 loop_end=20352 sample=Balafon Samples/XFBalafon 08 F5.flac\n',
        files={'Balafon Samples\\XFBalafon 01 A2.flac': {'numChannels': 2, 'numFrames': 70544, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 A3.flac': {'numChannels': 2, 'numFrames': 37888, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 A4.flac': {'numChannels': 2, 'numFrames': 23808, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 B2.flac': {'numChannels': 2, 'numFrames': 38912, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 B3.flac': {'numChannels': 2, 'numFrames': 29696, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 B4.flac': {'numChannels': 2, 'numFrames': 29184, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 C3.flac': {'numChannels': 2, 'numFrames': 46336, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 C4.flac': {'numChannels': 2, 'numFrames': 33280, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 C5.flac': {'numChannels': 2, 'numFrames': 21248, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 D3.flac': {'numChannels': 2, 'numFrames': 63488, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 D4.flac': {'numChannels': 2, 'numFrames': 41984, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 D5.flac': {'numChannels': 2, 'numFrames': 21760, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 E3.flac': {'numChannels': 2, 'numFrames': 43520, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 E4.flac': {'numChannels': 2, 'numFrames': 31232, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 E5.flac': {'numChannels': 2, 'numFrames': 12416, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 F3.flac': {'numChannels': 2, 'numFrames': 47104, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 F4.flac': {'numChannels': 2, 'numFrames': 23040, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 F5.flac': {'numChannels': 2, 'numFrames': 16000, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 G2.flac': {'numChannels': 2, 'numFrames': 46057, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 G3.flac': {'numChannels': 2, 'numFrames': 43008, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 G4.flac': {'numChannels': 2, 'numFrames': 34048, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 01 G5.flac': {'numChannels': 2, 'numFrames': 9408, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 A2.flac': {'numChannels': 2, 'numFrames': 72816, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 A3.flac': {'numChannels': 2, 'numFrames': 45056, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 A4.flac': {'numChannels': 2, 'numFrames': 25856, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 B2.flac': {'numChannels': 2, 'numFrames': 46080, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 B3.flac': {'numChannels': 2, 'numFrames': 29056, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 B4.flac': {'numChannels': 2, 'numFrames': 28928, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 C3.flac': {'numChannels': 2, 'numFrames': 50176, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 C4.flac': {'numChannels': 2, 'numFrames': 33280, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 C5.flac': {'numChannels': 2, 'numFrames': 23296, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 D3.flac': {'numChannels': 2, 'numFrames': 69632, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 D4.flac': {'numChannels': 2, 'numFrames': 43264, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 D5.flac': {'numChannels': 2, 'numFrames': 21248, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 E3.flac': {'numChannels': 2, 'numFrames': 41472, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 E4.flac': {'numChannels': 2, 'numFrames': 24832, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 E5.flac': {'numChannels': 2, 'numFrames': 11264, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 F3.flac': {'numChannels': 2, 'numFrames': 45056, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 F4.flac': {'numChannels': 2, 'numFrames': 21120, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 F5.flac': {'numChannels': 2, 'numFrames': 17024, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 G2.flac': {'numChannels': 2, 'numFrames': 46080, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 G3.flac': {'numChannels': 2, 'numFrames': 41472, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 G4.flac': {'numChannels': 2, 'numFrames': 34471, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 02 G5.flac': {'numChannels': 2, 'numFrames': 15360, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 A2.flac': {'numChannels': 2, 'numFrames': 70500, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 A3.flac': {'numChannels': 2, 'numFrames': 46080, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 A4.flac': {'numChannels': 2, 'numFrames': 29440, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 B2.flac': {'numChannels': 2, 'numFrames': 44032, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 B3.flac': {'numChannels': 2, 'numFrames': 32000, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 B4.flac': {'numChannels': 2, 'numFrames': 29184, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 C3.flac': {'numChannels': 2, 'numFrames': 58112, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 C4.flac': {'numChannels': 2, 'numFrames': 30720, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 C5.flac': {'numChannels': 2, 'numFrames': 20608, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 D3.flac': {'numChannels': 2, 'numFrames': 68608, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 D4.flac': {'numChannels': 2, 'numFrames': 43008, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 D5.flac': {'numChannels': 2, 'numFrames': 26624, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 E3.flac': {'numChannels': 2, 'numFrames': 47104, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 E4.flac': {'numChannels': 2, 'numFrames': 31232, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 E5.flac': {'numChannels': 2, 'numFrames': 12032, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 F3.flac': {'numChannels': 2, 'numFrames': 47104, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 F4.flac': {'numChannels': 2, 'numFrames': 22784, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 F5.flac': {'numChannels': 2, 'numFrames': 14976, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 G2.flac': {'numChannels': 2, 'numFrames': 42752, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 G3.flac': {'numChannels': 2, 'numFrames': 53760, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 G4.flac': {'numChannels': 2, 'numFrames': 31906, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 03 G5.flac': {'numChannels': 2, 'numFrames': 13056, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 A2.flac': {'numChannels': 2, 'numFrames': 73352, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 A3.flac': {'numChannels': 2, 'numFrames': 54272, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 A4.flac': {'numChannels': 2, 'numFrames': 27904, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 B2.flac': {'numChannels': 2, 'numFrames': 39936, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 B3.flac': {'numChannels': 2, 'numFrames': 33024, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 B4.flac': {'numChannels': 2, 'numFrames': 33792, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 C3.flac': {'numChannels': 2, 'numFrames': 63488, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 C4.flac': {'numChannels': 2, 'numFrames': 39168, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 C5.flac': {'numChannels': 2, 'numFrames': 26112, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 D3.flac': {'numChannels': 2, 'numFrames': 69632, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 D4.flac': {'numChannels': 2, 'numFrames': 48128, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 D5.flac': {'numChannels': 2, 'numFrames': 28544, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 E3.flac': {'numChannels': 2, 'numFrames': 50688, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 E4.flac': {'numChannels': 2, 'numFrames': 29696, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 E5.flac': {'numChannels': 2, 'numFrames': 11680, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 F3.flac': {'numChannels': 2, 'numFrames': 54272, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 F4.flac': {'numChannels': 2, 'numFrames': 33646, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 F5.flac': {'numChannels': 2, 'numFrames': 21120, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 G2.flac': {'numChannels': 2, 'numFrames': 41984, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 G3.flac': {'numChannels': 2, 'numFrames': 51200, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 G4.flac': {'numChannels': 2, 'numFrames': 39424, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 05 G5.flac': {'numChannels': 2, 'numFrames': 13376, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 A2.flac': {'numChannels': 2, 'numFrames': 66560, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 A3.flac': {'numChannels': 2, 'numFrames': 46080, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 A4.flac': {'numChannels': 2, 'numFrames': 30208, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 B2.flac': {'numChannels': 2, 'numFrames': 41984, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 B3.flac': {'numChannels': 2, 'numFrames': 37888, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 B4.flac': {'numChannels': 2, 'numFrames': 37120, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 C3.flac': {'numChannels': 2, 'numFrames': 73728, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 C4.flac': {'numChannels': 2, 'numFrames': 46592, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 C5.flac': {'numChannels': 2, 'numFrames': 24960, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 D3.flac': {'numChannels': 2, 'numFrames': 78848, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 D4.flac': {'numChannels': 2, 'numFrames': 53248, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 D5.flac': {'numChannels': 2, 'numFrames': 26624, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 E3.flac': {'numChannels': 2, 'numFrames': 50176, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 E4.flac': {'numChannels': 2, 'numFrames': 30464, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 F3.flac': {'numChannels': 2, 'numFrames': 54784, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 F4.flac': {'numChannels': 2, 'numFrames': 33610, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 F5.flac': {'numChannels': 2, 'numFrames': 19456, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 G2.flac': {'numChannels': 2, 'numFrames': 39936, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 G3.flac': {'numChannels': 2, 'numFrames': 54272, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 G4.flac': {'numChannels': 2, 'numFrames': 39424, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 07 G5.flac': {'numChannels': 2, 'numFrames': 13376, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 A2.flac': {'numChannels': 2, 'numFrames': 66560, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 A3.flac': {'numChannels': 2, 'numFrames': 41984, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 A4.flac': {'numChannels': 2, 'numFrames': 33792, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 B2.flac': {'numChannels': 2, 'numFrames': 43008, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 B3.flac': {'numChannels': 2, 'numFrames': 38016, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 B4.flac': {'numChannels': 2, 'numFrames': 36864, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 C3.flac': {'numChannels': 2, 'numFrames': 73728, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 C4.flac': {'numChannels': 2, 'numFrames': 46336, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 C5.flac': {'numChannels': 2, 'numFrames': 25856, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 D3.flac': {'numChannels': 2, 'numFrames': 61440, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 D4.flac': {'numChannels': 2, 'numFrames': 52224, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 E3.flac': {'numChannels': 2, 'numFrames': 54272, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 E4.flac': {'numChannels': 2, 'numFrames': 31488, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 F3.flac': {'numChannels': 2, 'numFrames': 53248, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 F4.flac': {'numChannels': 2, 'numFrames': 28186, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 F5.flac': {'numChannels': 2, 'numFrames': 20352, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 G2.flac': {'numChannels': 2, 'numFrames': 46080, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 G3.flac': {'numChannels': 2, 'numFrames': 46080, 'sampleRate': 44100}, 'Balafon Samples\\XFBalafon 08 G4.flac': {'numChannels': 2, 'numFrames': 44800, 'sampleRate': 44100}},
    ),
    'strings_full': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Strings/Full Strings LE.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> loop_crossfade=0.020000 loop_mode=loop_continuous amp_veltrack=35.000000 ampeg_attack=0.010000 ampeg_release=0.900000\n<region> hikey=26 pitch_keycenter=24 loop_start=69417 loop_end=393658 tune=-14 sample=Full Strings Long Samples//XFfull strings long 04 C0.flac\n<region> lokey=27 hikey=29 pitch_keycenter=28 loop_start=82577 loop_end=441426 tune=-18 sample=Full Strings Long Samples//XFfull strings long 04 E0.flac\n<region> lokey=30 hikey=31 pitch_keycenter=30 loop_start=86785 loop_end=369017 tune=16 volume=-3.000000 sample=Full Strings Long Samples//XFfull strings long 04 F#0.flac\n<region> lokey=32 hikey=33 pitch_keycenter=32 loop_start=46572 loop_end=285141 tune=25 sample=Full Strings Long Samples//XFfull strings long 04 G#0.flac\n<region> lokey=34 hikey=35 pitch_keycenter=34 loop_start=53198 loop_end=324113 tune=-8 volume=-3.000000 sample=Full Strings Long Samples//XFfull strings long 04 A#0.flac\n<region> lokey=36 hikey=38 pitch_keycenter=36 loop_start=32307 loop_end=301675 sample=Full Strings Long Samples//XFfull strings long-01 04 C1.flac\n<region> lokey=39 hikey=42 pitch_keycenter=40 loop_start=166513 loop_end=307393 tune=14 sample=Full Strings Long Samples//XFfull strings long-01 04 E1.flac\n<region> lokey=43 hikey=47 pitch_keycenter=46 loop_start=31587 loop_end=257451 tune=20 sample=Full Strings Long Samples//XFfull strings long-01 04 A#1.flac\n<region> lokey=48 hikey=49 pitch_keycenter=48 loop_start=44039 loop_end=266963 sample=Full Strings Long Samples//XFfull strings long-02 04 C2.flac\n<region> lokey=50 hikey=51 pitch_keycenter=50 loop_start=40516 loop_end=292358 volume=-4.000000 sample=Full Strings Long Samples//XFfull strings long-02 04 D2.flac\n<region> lokey=52 hikey=55 pitch_keycenter=52 loop_start=51790 loop_end=280633 tune=8 sample=Full Strings Long Samples//XFfull strings long 04 E2.flac\n<region> lokey=56 hikey=60 pitch_keycenter=54 loop_start=38225 loop_end=257381 tune=12 sample=Full Strings Long Samples//XFfull strings long-03 04 F#2.flac\n<region> lokey=61 hikey=65 pitch_keycenter=64 loop_start=152086 loop_end=389795 tune=4 sample=Full Strings Long Samples//XFfull strings long-03 04 E3.flac\n<region> lokey=66 hikey=67 pitch_keycenter=66 loop_start=107568 loop_end=304687 tune=6 sample=Full Strings Long Samples//XFfull strings long 04 F#3.flac\n<region> lokey=68 hikey=69 pitch_keycenter=68 loop_start=108993 loop_end=356605 tune=4 sample=Full Strings Long Samples//XFfull strings long 04 G#3.flac\n<region> lokey=70 hikey=71 pitch_keycenter=70 loop_start=78168 loop_end=363077 tune=10 sample=Full Strings Long Samples//XFfull strings long 04 A#3.flac\n<region> lokey=72 hikey=73 pitch_keycenter=72 loop_start=100451 loop_end=364562 tune=3 sample=Full Strings Long Samples//XFfull strings long 04 C4.flac\n<region> lokey=74 hikey=75 pitch_keycenter=74 loop_start=81437 loop_end=367633 tune=4 sample=Full Strings Long Samples//XFfull strings long 04 D4.flac\n<region> lokey=76 hikey=78 pitch_keycenter=77 loop_start=204447 loop_end=396603 tune=4 sample=Full Strings Long Samples//XFfull strings long 04 F4.flac\n<region> lokey=79 hikey=80 pitch_keycenter=79 loop_start=127616 loop_end=336356 tune=-4 sample=Full Strings Long Samples//XFfull strings long 04 G4.flac\n<region> lokey=81 hikey=82 pitch_keycenter=81 loop_start=69232 loop_end=396914 tune=-10 sample=Full Strings Long Samples//XFfull strings long-02 04 A4.flac\n<region> lokey=83 hikey=84 pitch_keycenter=83 loop_start=161228 loop_end=322261 tune=-6 sample=Full Strings Long Samples//XFfull strings long 04 B4.flac\n<region> lokey=85 hikey=86 pitch_keycenter=85 loop_start=90070 loop_end=296221 tune=-6 sample=Full Strings Long Samples//XFfull strings long 04 C#5.flac\n<region> lokey=87 hikey=88 pitch_keycenter=87 loop_start=131262 loop_end=302220 tune=-8 sample=Full Strings Long Samples//XFfull strings long 04 D#5.flac\n<region> lokey=89 hikey=90 pitch_keycenter=89 loop_start=111049 loop_end=305038 tune=-8 sample=Full Strings Long Samples//XFfull strings long-02 04 F5.flac\n<region> lokey=91 hikey=92 pitch_keycenter=91 loop_start=140532 loop_end=291068 tune=-8 sample=Full Strings Long Samples//XFfull strings long 04 G5.flac\n<region> lokey=93 pitch_keycenter=93 loop_start=88694 loop_end=270768 tune=-7 sample=Full Strings Long Samples//XFfull strings long 04 A5.flac\n',
        files={'Full Strings Long Samples\\\\XFfull strings long 04 A#0.flac': {'numChannels': 2, 'numFrames': 324641, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 A#3.flac': {'numChannels': 2, 'numFrames': 363605, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 A5.flac': {'numChannels': 2, 'numFrames': 271296, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 B4.flac': {'numChannels': 2, 'numFrames': 322789, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 C#5.flac': {'numChannels': 2, 'numFrames': 296749, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 C0.flac': {'numChannels': 2, 'numFrames': 394186, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 C4.flac': {'numChannels': 2, 'numFrames': 365090, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 D#5.flac': {'numChannels': 2, 'numFrames': 302748, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 D4.flac': {'numChannels': 2, 'numFrames': 368161, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 E0.flac': {'numChannels': 2, 'numFrames': 441954, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 E2.flac': {'numChannels': 2, 'numFrames': 281161, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 F#0.flac': {'numChannels': 2, 'numFrames': 369545, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 F#3.flac': {'numChannels': 2, 'numFrames': 305215, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 F4.flac': {'numChannels': 2, 'numFrames': 397131, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 G#0.flac': {'numChannels': 2, 'numFrames': 285669, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 G#3.flac': {'numChannels': 2, 'numFrames': 357133, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 G4.flac': {'numChannels': 2, 'numFrames': 336884, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long 04 G5.flac': {'numChannels': 2, 'numFrames': 291596, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-01 04 A#1.flac': {'numChannels': 2, 'numFrames': 257979, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-01 04 C1.flac': {'numChannels': 2, 'numFrames': 302203, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-01 04 E1.flac': {'numChannels': 2, 'numFrames': 307921, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-02 04 A4.flac': {'numChannels': 2, 'numFrames': 397442, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-02 04 C2.flac': {'numChannels': 2, 'numFrames': 267491, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-02 04 D2.flac': {'numChannels': 2, 'numFrames': 292886, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-02 04 F5.flac': {'numChannels': 2, 'numFrames': 305566, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-03 04 E3.flac': {'numChannels': 2, 'numFrames': 390323, 'sampleRate': 48000}, 'Full Strings Long Samples\\\\XFfull strings long-03 04 F#2.flac': {'numChannels': 2, 'numFrames': 257909, 'sampleRate': 48000}},
    ),
    'piano_grand': MultiSampleInstrumentDef(
        sfz_path_relative='Factory/Keys/Baby Grand Piano.sfz',
        embedded_sfz='// SFZ Generated by libSFZ\n<group> amp_veltrack=0.000000 ampeg_release=0.850000\n<region> hikey=23 pitch_keycenter=21 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 A-1.flac\n<region> hikey=23 pitch_keycenter=21 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 A-1.flac\n<region> hikey=25 pitch_keycenter=21 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 A-1.flac\n<region> hikey=23 pitch_keycenter=21 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A-1.flac\n<region> lokey=24 hikey=26 pitch_keycenter=24 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C0.flac\n<region> lokey=24 hikey=26 pitch_keycenter=24 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C0.flac\n<region> lokey=24 hikey=26 pitch_keycenter=24 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C0.flac\n<region> lokey=27 hikey=29 pitch_keycenter=27 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 D#0.flac\n<region> lokey=27 hikey=29 pitch_keycenter=27 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 D#0.flac\n<region> lokey=27 hikey=29 pitch_keycenter=27 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 D#0.flac\n<region> lokey=30 hikey=32 pitch_keycenter=31 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 G0.flac\n<region> lokey=30 hikey=32 pitch_keycenter=31 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 G0.flac\n<region> lokey=26 hikey=32 pitch_keycenter=31 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 G0.flac\n<region> lokey=30 hikey=32 pitch_keycenter=31 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 G0.flac\n<region> lokey=33 hikey=35 pitch_keycenter=33 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 A0.flac\n<region> lokey=33 hikey=35 pitch_keycenter=33 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 A0.flac\n<region> lokey=33 hikey=35 pitch_keycenter=33 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 A0.flac\n<region> lokey=33 hikey=35 pitch_keycenter=33 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A0.flac\n<region> lokey=36 hikey=38 pitch_keycenter=36 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C1.flac\n<region> lokey=36 hikey=38 pitch_keycenter=36 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C1.flac\n<region> lokey=36 hikey=38 pitch_keycenter=36 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C1.flac\n<region> lokey=36 hikey=38 pitch_keycenter=36 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C1.flac\n<region> lokey=39 hikey=41 pitch_keycenter=39 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 D#1.flac\n<region> lokey=39 hikey=41 pitch_keycenter=39 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 D#1.flac\n<region> lokey=39 hikey=41 pitch_keycenter=39 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 D#1.flac\n<region> lokey=39 hikey=41 pitch_keycenter=39 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 D#1.flac\n<region> lokey=42 hikey=44 pitch_keycenter=42 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 F#1.flac\n<region> lokey=42 hikey=44 pitch_keycenter=42 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 F#1.flac\n<region> lokey=42 hikey=44 pitch_keycenter=42 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 F#1.flac\n<region> lokey=42 hikey=44 pitch_keycenter=42 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 F#1.flac\n<region> lokey=45 hikey=47 pitch_keycenter=45 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 A1.flac\n<region> lokey=45 hikey=47 pitch_keycenter=45 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 A1.flac\n<region> lokey=45 hikey=47 pitch_keycenter=45 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 A1.flac\n<region> lokey=45 hikey=47 pitch_keycenter=45 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A1.flac\n<region> lokey=48 hikey=50 pitch_keycenter=48 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C2.flac\n<region> lokey=48 hikey=50 pitch_keycenter=48 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C2.flac\n<region> lokey=48 hikey=50 pitch_keycenter=48 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C2.flac\n<region> lokey=48 hikey=50 pitch_keycenter=48 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C2.flac\n<region> lokey=51 hikey=53 pitch_keycenter=51 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 D#2.flac\n<region> lokey=51 hikey=53 pitch_keycenter=51 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 D#2.flac\n<region> lokey=51 hikey=53 pitch_keycenter=51 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 D#2.flac\n<region> lokey=51 hikey=53 pitch_keycenter=51 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 D#2.flac\n<region> lokey=54 hikey=56 pitch_keycenter=54 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 F#2.flac\n<region> lokey=54 hikey=56 pitch_keycenter=54 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 F#2.flac\n<region> lokey=54 hikey=56 pitch_keycenter=54 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 F#2.flac\n<region> lokey=54 hikey=56 pitch_keycenter=54 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 F#2.flac\n<region> lokey=57 hikey=59 pitch_keycenter=57 hivel=41 tune=4 sample=Baby Grand Samples/XFBabyGrand 04 A2.flac\n<region> lokey=57 hikey=59 pitch_keycenter=57 lovel=42 hivel=69 tune=4 sample=Baby Grand Samples/XFBabyGrand 05 A2.flac\n<region> lokey=57 hikey=59 pitch_keycenter=57 lovel=70 hivel=100 tune=4 sample=Baby Grand Samples/XFBabyGrand 06 A2.flac\n<region> lokey=57 hikey=59 pitch_keycenter=57 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A2.flac\n<region> lokey=60 hikey=62 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C3.flac\n<region> lokey=60 hikey=62 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C3.flac\n<region> lokey=60 hikey=62 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C3.flac\n<region> lokey=60 hikey=62 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C3.flac\n<region> lokey=63 hikey=65 pitch_keycenter=63 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 D#3.flac\n<region> lokey=63 hikey=65 pitch_keycenter=63 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 D#3.flac\n<region> lokey=63 hikey=65 pitch_keycenter=63 lovel=70 hivel=100 volume=-3.000000 sample=Baby Grand Samples/XFBabyGrand 06 D#3.flac\n<region> lokey=63 hikey=65 pitch_keycenter=63 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 D#3.flac\n<region> lokey=66 hikey=68 pitch_keycenter=66 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 F#3.flac\n<region> lokey=66 hikey=68 pitch_keycenter=66 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 F#3.flac\n<region> lokey=66 hikey=68 pitch_keycenter=66 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 F#3.flac\n<region> lokey=66 hikey=68 pitch_keycenter=66 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 F#3.flac\n<region> lokey=69 hikey=71 pitch_keycenter=69 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 A3.flac\n<region> lokey=69 hikey=71 pitch_keycenter=69 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 A3.flac\n<region> lokey=69 hikey=71 pitch_keycenter=69 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 A3.flac\n<region> lokey=69 hikey=71 pitch_keycenter=69 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A3.flac\n<region> lokey=72 hikey=74 pitch_keycenter=72 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C4.flac\n<region> lokey=72 hikey=74 pitch_keycenter=72 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C4.flac\n<region> lokey=72 hikey=74 pitch_keycenter=72 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C4.flac\n<region> lokey=72 hikey=74 pitch_keycenter=72 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C4.flac\n<region> lokey=75 hikey=77 pitch_keycenter=75 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 D#4.flac\n<region> lokey=75 hikey=77 pitch_keycenter=75 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 D#4.flac\n<region> lokey=75 hikey=77 pitch_keycenter=75 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 D#4.flac\n<region> lokey=75 hikey=77 pitch_keycenter=75 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 D#4.flac\n<region> lokey=78 hikey=80 pitch_keycenter=78 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 F#4.flac\n<region> lokey=78 hikey=80 pitch_keycenter=78 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 F#4.flac\n<region> lokey=78 hikey=80 pitch_keycenter=78 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 F#4.flac\n<region> lokey=78 hikey=80 pitch_keycenter=78 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 F#4.flac\n<region> lokey=81 hikey=83 pitch_keycenter=81 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 A4.flac\n<region> lokey=81 hikey=83 pitch_keycenter=81 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 A4.flac\n<region> lokey=81 hikey=83 pitch_keycenter=81 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 A4.flac\n<region> lokey=81 hikey=83 pitch_keycenter=81 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A4.flac\n<region> lokey=84 hikey=88 pitch_keycenter=84 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C5.flac\n<region> lokey=84 hikey=88 pitch_keycenter=84 lovel=42 hivel=69 volume=-3.000000 sample=Baby Grand Samples/XFBabyGrand 05 C5.flac\n<region> lokey=84 hikey=88 pitch_keycenter=84 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C5.flac\n<region> lokey=84 hikey=88 pitch_keycenter=84 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C5.flac\n<region> lokey=89 hikey=92 pitch_keycenter=90 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 F#5.flac\n<region> lokey=89 hikey=92 pitch_keycenter=90 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 F#5.flac\n<region> lokey=89 hikey=92 pitch_keycenter=90 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 F#5.flac\n<region> lokey=89 hikey=92 pitch_keycenter=90 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 F#5.flac\n<region> lokey=93 hikey=95 pitch_keycenter=93 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 A5.flac\n<region> lokey=93 hikey=95 pitch_keycenter=93 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 A5.flac\n<region> lokey=93 hikey=95 pitch_keycenter=93 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 A5.flac\n<region> lokey=93 hikey=95 pitch_keycenter=93 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 A5.flac\n<region> lokey=96 hikey=98 pitch_keycenter=96 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C6.flac\n<region> lokey=96 hikey=98 pitch_keycenter=96 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C6.flac\n<region> lokey=96 hikey=98 pitch_keycenter=96 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C6.flac\n<region> lokey=96 hikey=98 pitch_keycenter=96 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C6.flac\n<region> lokey=99 hikey=101 pitch_keycenter=99 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 D#6.flac\n<region> lokey=99 hikey=101 pitch_keycenter=99 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 D#6.flac\n<region> lokey=99 hikey=101 pitch_keycenter=99 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 D#6.flac\n<region> lokey=99 hikey=101 pitch_keycenter=99 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 D#6.flac\n<region> lokey=102 hikey=106 pitch_keycenter=102 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 F#6.flac\n<region> lokey=102 hikey=106 pitch_keycenter=102 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 F#6.flac\n<region> lokey=102 hikey=106 pitch_keycenter=102 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 F#6.flac\n<region> lokey=102 hikey=106 pitch_keycenter=102 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 F#6.flac\n<region> lokey=107 pitch_keycenter=108 hivel=41 sample=Baby Grand Samples/XFBabyGrand 04 C7.flac\n<region> lokey=107 pitch_keycenter=108 lovel=42 hivel=69 sample=Baby Grand Samples/XFBabyGrand 05 C7.flac\n<region> lokey=107 pitch_keycenter=108 lovel=70 hivel=100 sample=Baby Grand Samples/XFBabyGrand 06 C7.flac\n<region> lokey=107 pitch_keycenter=108 lovel=101 sample=Baby Grand Samples/XFBabyGrand 07 C7.flac\n',
        files={'Baby Grand Samples\\XFBabyGrand 04 A-1.flac': {'numChannels': 2, 'numFrames': 440901, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 A0.flac': {'numChannels': 2, 'numFrames': 434935, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 A1.flac': {'numChannels': 2, 'numFrames': 437875, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 A2.flac': {'numChannels': 2, 'numFrames': 440120, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 A3.flac': {'numChannels': 2, 'numFrames': 443617, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 A4.flac': {'numChannels': 2, 'numFrames': 404476, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 A5.flac': {'numChannels': 2, 'numFrames': 201915, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C0.flac': {'numChannels': 2, 'numFrames': 441605, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C1.flac': {'numChannels': 2, 'numFrames': 442627, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C2.flac': {'numChannels': 2, 'numFrames': 440868, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C3.flac': {'numChannels': 2, 'numFrames': 440808, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C4.flac': {'numChannels': 2, 'numFrames': 443805, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C5.flac': {'numChannels': 2, 'numFrames': 352220, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C6.flac': {'numChannels': 2, 'numFrames': 311500, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 C7.flac': {'numChannels': 2, 'numFrames': 77255, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 D#0.flac': {'numChannels': 2, 'numFrames': 440891, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 D#1.flac': {'numChannels': 2, 'numFrames': 442379, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 D#2.flac': {'numChannels': 2, 'numFrames': 441634, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 D#3.flac': {'numChannels': 2, 'numFrames': 440873, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 D#4.flac': {'numChannels': 2, 'numFrames': 311534, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 D#6.flac': {'numChannels': 2, 'numFrames': 128286, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 F#1.flac': {'numChannels': 2, 'numFrames': 441601, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 F#2.flac': {'numChannels': 2, 'numFrames': 440929, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 F#3.flac': {'numChannels': 2, 'numFrames': 440864, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 F#4.flac': {'numChannels': 2, 'numFrames': 520000, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 F#5.flac': {'numChannels': 2, 'numFrames': 363436, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 F#6.flac': {'numChannels': 2, 'numFrames': 124783, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 04 G0.flac': {'numChannels': 2, 'numFrames': 443501, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A-1.flac': {'numChannels': 2, 'numFrames': 440388, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A0.flac': {'numChannels': 2, 'numFrames': 428951, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A1.flac': {'numChannels': 2, 'numFrames': 437760, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A2.flac': {'numChannels': 2, 'numFrames': 440888, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A3.flac': {'numChannels': 2, 'numFrames': 446708, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A4.flac': {'numChannels': 2, 'numFrames': 432026, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 A5.flac': {'numChannels': 2, 'numFrames': 157275, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C0.flac': {'numChannels': 2, 'numFrames': 440976, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C1.flac': {'numChannels': 2, 'numFrames': 441347, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C2.flac': {'numChannels': 2, 'numFrames': 440381, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C3.flac': {'numChannels': 2, 'numFrames': 441624, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C4.flac': {'numChannels': 2, 'numFrames': 440827, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C5.flac': {'numChannels': 2, 'numFrames': 437370, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C6.flac': {'numChannels': 2, 'numFrames': 244028, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 C7.flac': {'numChannels': 2, 'numFrames': 130796, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 D#0.flac': {'numChannels': 2, 'numFrames': 440592, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 D#1.flac': {'numChannels': 2, 'numFrames': 442325, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 D#2.flac': {'numChannels': 2, 'numFrames': 443076, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 D#3.flac': {'numChannels': 2, 'numFrames': 435015, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 D#4.flac': {'numChannels': 2, 'numFrames': 434961, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 D#6.flac': {'numChannels': 2, 'numFrames': 239141, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 F#1.flac': {'numChannels': 2, 'numFrames': 440886, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 F#2.flac': {'numChannels': 2, 'numFrames': 440822, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 F#3.flac': {'numChannels': 2, 'numFrames': 437920, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 F#4.flac': {'numChannels': 2, 'numFrames': 573109, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 F#5.flac': {'numChannels': 2, 'numFrames': 438566, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 F#6.flac': {'numChannels': 2, 'numFrames': 163129, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 05 G0.flac': {'numChannels': 2, 'numFrames': 441097, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A-1.flac': {'numChannels': 2, 'numFrames': 440524, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A0.flac': {'numChannels': 2, 'numFrames': 437837, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A1.flac': {'numChannels': 2, 'numFrames': 440629, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A2.flac': {'numChannels': 2, 'numFrames': 440048, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A3.flac': {'numChannels': 2, 'numFrames': 440825, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A4.flac': {'numChannels': 2, 'numFrames': 432063, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 A5.flac': {'numChannels': 2, 'numFrames': 232234, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C1.flac': {'numChannels': 2, 'numFrames': 443009, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C2.flac': {'numChannels': 2, 'numFrames': 441538, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C3.flac': {'numChannels': 2, 'numFrames': 440122, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C4.flac': {'numChannels': 2, 'numFrames': 437997, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C5.flac': {'numChannels': 2, 'numFrames': 441906, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C6.flac': {'numChannels': 2, 'numFrames': 342420, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 C7.flac': {'numChannels': 2, 'numFrames': 123478, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 D#1.flac': {'numChannels': 2, 'numFrames': 441455, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 D#2.flac': {'numChannels': 2, 'numFrames': 442299, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 D#3.flac': {'numChannels': 2, 'numFrames': 443796, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 D#4.flac': {'numChannels': 2, 'numFrames': 440909, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 D#6.flac': {'numChannels': 2, 'numFrames': 152093, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 F#1.flac': {'numChannels': 2, 'numFrames': 449061, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 F#2.flac': {'numChannels': 2, 'numFrames': 440866, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 F#3.flac': {'numChannels': 2, 'numFrames': 429121, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 F#4.flac': {'numChannels': 2, 'numFrames': 434925, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 F#5.flac': {'numChannels': 2, 'numFrames': 435774, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 F#6.flac': {'numChannels': 2, 'numFrames': 187850, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 06 G0.flac': {'numChannels': 2, 'numFrames': 441264, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A-1.flac': {'numChannels': 2, 'numFrames': 440109, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A0.flac': {'numChannels': 2, 'numFrames': 443736, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A1.flac': {'numChannels': 2, 'numFrames': 443520, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A2.flac': {'numChannels': 2, 'numFrames': 440091, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A3.flac': {'numChannels': 2, 'numFrames': 443765, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A4.flac': {'numChannels': 2, 'numFrames': 440809, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 A5.flac': {'numChannels': 2, 'numFrames': 290338, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C0.flac': {'numChannels': 2, 'numFrames': 442028, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C1.flac': {'numChannels': 2, 'numFrames': 442259, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C2.flac': {'numChannels': 2, 'numFrames': 440794, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C3.flac': {'numChannels': 2, 'numFrames': 439361, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C4.flac': {'numChannels': 2, 'numFrames': 440808, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C5.flac': {'numChannels': 2, 'numFrames': 452158, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C6.flac': {'numChannels': 2, 'numFrames': 286617, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 C7.flac': {'numChannels': 2, 'numFrames': 97411, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 D#0.flac': {'numChannels': 2, 'numFrames': 439126, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 D#1.flac': {'numChannels': 2, 'numFrames': 440656, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 D#2.flac': {'numChannels': 2, 'numFrames': 441531, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 D#3.flac': {'numChannels': 2, 'numFrames': 437879, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 D#4.flac': {'numChannels': 2, 'numFrames': 437862, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 D#6.flac': {'numChannels': 2, 'numFrames': 214583, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 F#1.flac': {'numChannels': 2, 'numFrames': 442280, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 F#2.flac': {'numChannels': 2, 'numFrames': 440819, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 F#3.flac': {'numChannels': 2, 'numFrames': 440820, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 F#4.flac': {'numChannels': 2, 'numFrames': 440823, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 F#5.flac': {'numChannels': 2, 'numFrames': 429985, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 F#6.flac': {'numChannels': 2, 'numFrames': 139771, 'sampleRate': 44100}, 'Baby Grand Samples\\XFBabyGrand 07 G0.flac': {'numChannels': 2, 'numFrames': 441168, 'sampleRate': 44100}},
    ),
}


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

# GranularOsc (slots 0-2, an alternate engine selected via kParamType=
# "kOsc_Granular" the same way kOsc_Sample/kOsc_WT are, see mapping.py's
# oscillator loop) -- surveyed and its full automatable/private param enum
# mined from the VST3 binary's own debug strings 2026-07-30 (same technique
# used throughout this project): 22 automatable params (kParamWarp/
# WarpVar/WarpMenu/Warp2/WarpVar2/WarpMenu2 -- shared with WTOsc/SampleOsc's
# own warp system -- plus kParamDensity/GrainLength/GrainReverse/
# WindowParam/WindowSkew/WindowShape/RandomOffset/RandomDir/RandomPitch/
# RandomGrainLength/RandomPan/RandomGain/RandomWindowAmount/
# RandomWindowSkew/RandomWarp/RandomWarp2) plus 7 private ones
# (kParamLengthMode/DensityMode/MaxNumGrains/YAxisAssignment/
# UnisonTrigPattern/JumpStartGrains/DensityDotted/DensityTriplet/
# LengthDotted/LengthTriplet/LoopGrains/LengthKeyTrack -- some genuinely
# rarely used, see per-param confidence/notes below). Only the 5 highest-
# presence controls (found via a 66-sample corpus survey) plus warp_amount/
# warp_mode (shared OscillatorSpec fields, already used by WTOsc/SampleOsc)
# are wired into OscillatorSpec/mapping.py/introspect.py this round --
# window shaping, randomization-direction/gain/window-skew, BPM-synced
# density/length, unison trigger pattern, and the granular-specific warp
# lane 2 remain documented here (round-trip/edit safety via
# `_plain_params`'s allow_unknown merge) but not independently generatable.
# CONFIRMED LIVE 2026-07-30 in real Serum 2 after fixing the two
# raw<->displayed conversion bugs documented immediately below -- a
# generated GranularOsc genuinely produces a grain-cloud texture,
# cross-validated by ear against a real Factory Granular preset
# (`808 - Texture`). A SCAN/playback-position system (`kParamScanRate`/
# `kParamPosition`, on the OUTER `Oscillator{i}` container, not this table)
# was found live but remains unwired -- see docs/PARAMETER_SCHEMA.md item 3.
#
# kParamDensity/kParamGrainLength's raw<->UI-displayed relationships --
# decoded live 2026-07-30 after the FIRST real-Serum test of GranularOsc
# came back broken ("plays like a sample, extremely filtered"). Root cause:
# both params were being written as if OscillatorSpec's value WAS the raw
# CBOR value directly (matching every other already-modeled param in this
# project), but neither actually is -- confirmed by asking the user to type
# exact DENS/LENGTH-knob values into a real Serum 2 instance and reading
# back the resulting saved file's raw value for each:
#   - kParamDensity: raw = displayed**4 / 810 (a clean QUARTIC curve,
#     confirmed EXACT across 3 points: displayed 5/15/25 -> raw
#     0.7716/62.5/482.25). The knob's own confirmed display range is 0-30;
#     30**4/810 == 1000 exactly, a suspiciously round number strongly
#     suggesting 1000 is the true raw ceiling -- NOT the 850ish this
#     project had previously guessed purely from corpus min/max
#     observations (which was simply wrong, an artifact of never having
#     confirmed the curve shape).
#   - kParamGrainLength: raw = displayed / 1000 (LINEAR, confirmed exact
#     across displayed 0.05/0.3/1.0 -> raw 0.00005/0.0003/0.001). The
#     original bug in one sentence: writing OscillatorSpec.
#     granular_grain_length=0.15 (intended as "0.15 seconds") directly as
#     the raw value actually displays as 150 in Serum's own UI -- an
#     absurdly long, almost certainly clamped grain length that made the
#     engine effectively play large continuous chunks of the source
#     instead of short grains, the direct cause of "plays like a sample."
# OscillatorSpec.granular_density/granular_grain_length are the UI-
# displayed numbers (what a user would type into Serum), NOT the raw CBOR
# values -- mapping.py/introspect.py apply these conversions at the
# read/write boundary so PresetSpec stays in the same "matches what you'd
# see in Serum's own UI" convention as every other already-modeled param.
GRANULAR_DENSITY_CURVE_DIVISOR = 810.0
GRANULAR_GRAIN_LENGTH_DIVISOR = 1000.0
GRANULAROSC_PARAMS: dict[str, ParamDef] = {
    "kParamWarp": ParamDef(
        "kParamWarp", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="Shared with WTOsc/SampleOsc's own warp system -- see OscillatorSpec.warp_amount.",
    ),
    "kParamWarpMenu": ParamDef(
        "kParamWarpMenu", "enum", default="kFM_OSC", confidence="observed",
        enum_values=(
            "kFM_OSC", "kAM_OSC", "kSync", "kPWM", "kBendPos", "kDistLinFold",
            "kDistSoftClip", "kDistHardClip", "kQuantize", "kFilterLPF", "kFilterHPF",
            "kDistAsym", "kPD_OSC", "kGate",
        ),
        notes="Real corpus values included kDistAsym/kPD_OSC/kGate, NOT in "
        "SIMPLE_WARP_MODES's curated 11-value subset -- Serum's real warp-mode menu is "
        "larger than what this project exposes for generation; see OscillatorSpec.warp_mode.",
    ),
    "kParamWarp2": ParamDef(
        "kParamWarp2", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="Second warp lane's amount, same concept as WTOsc's kParamWarp2 -- NOT "
        "wired into OscillatorSpec.warp_amount2 for this engine yet.",
    ),
    "kParamWarpMenu2": ParamDef(
        "kParamWarpMenu2", "enum", default="kAM_OSC", confidence="observed",
        enum_values=(
            "kFM_OSC", "kAM_OSC", "kSync", "kPWM", "kBendPos", "kDistLinFold",
            "kDistSoftClip", "kDistHardClip", "kQuantize", "kFilterLPF", "kFilterHPF",
        ),
    ),
    "kParamWarpVar": ParamDef("kParamWarpVar", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain"),
    "kParamWarpVar2": ParamDef("kParamWarpVar2", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain"),
    "kParamDensity": ParamDef(
        "kParamDensity", "float", default=0.0247, min=0.0, max=1000.0, unit="raw (see "
        "GRANULAR_DENSITY_CURVE_DIVISOR)", confidence="confirmed",
        notes="Grain trigger rate. 89% presence (59/66 real samples), real raw range "
        "7.6e-6-800.0. THIS IS THE RAW STORAGE VALUE, not what Serum's DENS knob "
        "displays -- confirmed live 2026-07-30: raw = displayed**4 / 810 (quartic), "
        "displayed range 0-30. Interpretation depends on kParamDensityMode (Free Hz/"
        "BPM-synced/direct grain count) -- only kDensityFree confirmed as the "
        "overwhelmingly common real default (3/66 used a non-default mode).",
    ),
    "kParamGrainLength": ParamDef(
        "kParamGrainLength", "float", default=0.124, min=0.0, max=10.0, unit="raw (see "
        "GRANULAR_GRAIN_LENGTH_DIVISOR; displayed unit is MILLISECONDS)",
        confidence="confirmed",
        notes="83% presence (55/66), real raw range 0.0-10.0. THIS IS THE RAW STORAGE "
        "VALUE, not what Serum's LENGTH knob displays -- confirmed live 2026-07-30: "
        "raw = displayed_ms / 1000 (linear), confirmed via BOTH the original 3-point "
        "calibration (displayed 0.05/0.3/1.0ms) AND independently cross-validated "
        "against a real Factory preset (808 - Texture's Osc B: raw 0.1243 -> predicted "
        "displayed 124.3ms, user-reported real value 124ms -- matches to within "
        "rounding). The displayed unit is confirmed MILLISECONDS (not seconds, an "
        "earlier wrong assumption) -- so real raw=10.0 implies displayed=10000ms=10s, "
        "plausible as an extreme long-grain/pad setting, not necessarily broken. Getting "
        "the raw<->displayed conversion backwards (writing the intended displayed number "
        "directly as raw) was the root cause of GranularOsc's first live test sounding "
        "broken -- see the module comment above this table.",
    ),
    "kParamGrainReverse": ParamDef("kParamGrainReverse", "bool", default=False, confidence="uncertain"),
    "kParamRandomOffset": ParamDef(
        "kParamRandomOffset", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="observed", notes="Random start-offset within the source sample per grain.",
    ),
    "kParamRandomDir": ParamDef(
        "kParamRandomDir", "float", default=0.0, min=0.0, max=100.0, unit="%", confidence="observed",
    ),
    "kParamRandomPitch": ParamDef(
        "kParamRandomPitch", "float", default=0.0, min=0.0, max=12.0, unit="semitones",
        confidence="observed", notes="33% presence (22/66), real range ~0-12 (one octave).",
    ),
    "kParamRandomGrainLength": ParamDef(
        "kParamRandomGrainLength", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="observed", notes="61% presence (40/66), real range 1.0-100.0.",
    ),
    "kParamRandomPan": ParamDef(
        "kParamRandomPan", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="observed", notes="62% presence (41/66), real range 15.9-100.0.",
    ),
    "kParamRandomGain": ParamDef(
        "kParamRandomGain", "float", default=0.0, min=0.0, max=100.0, unit="%", confidence="observed",
    ),
    "kParamRandomWindowAmount": ParamDef(
        "kParamRandomWindowAmount", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="uncertain",
    ),
    "kParamRandomWindowSkew": ParamDef(
        "kParamRandomWindowSkew", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="uncertain",
    ),
    "kParamRandomWarp": ParamDef(
        "kParamRandomWarp", "float", default=0.0, min=0.0, max=100.0, unit="%", confidence="observed",
    ),
    "kParamRandomWarp2": ParamDef(
        "kParamRandomWarp2", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="uncertain",
    ),
    "kParamWindowParam": ParamDef(
        "kParamWindowParam", "float", default=50.0, min=0.0, max=100.0, unit="%",
        confidence="observed", notes="Shapes the grain envelope window.",
    ),
    "kParamWindowSkew": ParamDef(
        "kParamWindowSkew", "float", default=0.0, min=-100.0, max=100.0, unit="%",
        confidence="observed",
    ),
    "kParamWindowShape": ParamDef(
        "kParamWindowShape", "enum", default="kWindowHann", confidence="observed",
        enum_values=(
            "kWindowHann", "kWindowWelch", "kWindowGaussian", "kWindowBlackmanHarris",
            "kWindowSinc", "kWindowTukey", "kWindowTriangle", "kWindowTrapezoid",
            "kWindowExpDec", "kWindowExpDecRev",
        ),
        notes="Ordinals confirmed via VST3 binary string dump (declaration order 0-9).",
    ),
    "kParamDensityMode": ParamDef(
        "kParamDensityMode", "enum", default="kDensityFree", confidence="observed",
        enum_values=("kDensityFree", "kDensityBPM", "kDensityGrains"),
    ),
    "kParamLengthMode": ParamDef(
        "kParamLengthMode", "enum", default="kLengthFree", confidence="observed",
        enum_values=("kLengthFree", "kLengthBPM", "kLengthPercent"),
    ),
    "kParamUnisonTrigPattern": ParamDef(
        "kParamUnisonTrigPattern", "enum", default="kTogether", confidence="observed",
        enum_values=("kTogether", "kEven", "kExponential", "kRandom"),
    ),
    "kParamYAxisAssignment": ParamDef(
        "kParamYAxisAssignment", "enum", default="kYAxisNone", confidence="uncertain",
        enum_values=(
            "kYAxisNone", "kYAxisOscVolume", "kYAxisGranularWarp", "kYAxisGranularWarp2",
            "kYAxisGranularDensity", "kYAxisGranularGrainLength", "kYAxisGranularWindowParam",
            "kYAxisGranularWindowSkew", "kYAxisGranularRandomOffset", "kYAxisGranularRandomDir",
            "kYAxisGranularRandomPitch", "kYAxisGranularRandomGrainLength",
        ),
        notes="Only 1/66 real samples used this (assigns an XY-pad axis to a granular "
        "param) -- rare, low-priority.",
    ),
    "kParamMaxNumGrains": ParamDef("kParamMaxNumGrains", "float", default=16.0, min=1.0, max=64.0, confidence="uncertain"),
    "kParamJumpStartGrains": ParamDef("kParamJumpStartGrains", "bool", default=False, confidence="uncertain"),
    "kParamDensityDotted": ParamDef("kParamDensityDotted", "bool", default=False, confidence="uncertain"),
    "kParamDensityTriplet": ParamDef("kParamDensityTriplet", "bool", default=False, confidence="uncertain"),
    "kParamLengthDotted": ParamDef("kParamLengthDotted", "bool", default=False, confidence="uncertain"),
    "kParamLengthTriplet": ParamDef("kParamLengthTriplet", "bool", default=False, confidence="uncertain"),
    "kParamLoopGrains": ParamDef("kParamLoopGrains", "bool", default=True, confidence="uncertain"),
    "kParamLengthKeyTrack": ParamDef("kParamLengthKeyTrack", "bool", default=False, confidence="uncertain"),
}

# SpectralOsc's own warp-mode enum -- DIFFERENT from WTOsc/SampleOsc/
# GranularOsc's (see SIMPLE_WARP_MODES) and much larger: mined from the
# VST3 binary's own debug strings 2026-07-30, ~80 entries covering
# spectral-domain processing (kDetune/kSmear/kSpread/kGate/kRobotize/
# kSpectralShift/kMirror/kPeakFollow/kPeakOctave*/kPeakHarm*/kShepard*/
# kSpectral*/kMask_*/kVocode_* -- none shared with the generic warp-mode
# vocabulary) plus a shared tail (kFilterLPF/HPF, kDist*, kFM_*/kFMX_*/
# kFMP_*/kAM_*/kRM_* per-target FM/AM/RM variants). Every value observed in
# a 53-preset real corpus survey (kGate/kSmear/kAddsubharmonics/kDetune/
# kSpread/kAM_OSC/kPeakOctaveUp/kPeakOctaveDown/kMask_OSC/kMask_NOISE/
# kVocode_OSC/kVocode_NOISE/kShepardNarrow/kShepardFilter/kSpectralComb/
# kSpectralShift/kSpectralPitchShift/kFilterLPF/kFilterHPF/kDistSoftClip/
# kDistDiode1/kDistDiode2/kAddharmonics/kPeakHarmUp/kPeakHarmDown/kPD_OSC/
# kPD_OSC2/kSelfPD/kSpectralPhaseTwist/kMirror/kDistTapeSat/kDistTube) is a
# subset of this list, confirming it's complete/authoritative rather than
# guessed.
_SPECTRAL_WARP_MODES: tuple[str, ...] = (
    "kNoWarp", "kDetune", "kSmear", "kSpread", "kAddharmonics", "kAddsubharmonics",
    "kGate", "kRobotize", "kSpectralShift", "kMirror", "kPeakFollow", "kPeakOctaveUp",
    "kPeakOctaveDown", "kPeakHarmUp", "kPeakHarmDown", "kPeakHarmSweep", "kShepardNarrow",
    "kShepardFilter", "kSpectralComb", "kSpectralPitchShift", "kSpectralPitchShiftNew",
    "kSpectralPhaseTwist", "kSpectralFormantShift", "kMask_OSC", "kMask_OSC2",
    "kMask_NOISE", "kMask_SUB", "kMask_FILT1", "kMask_FILT2", "kVocode_OSC",
    "kVocode_OSC2", "kVocode_NOISE", "kVocode_SUB", "kVocode_FILT1", "kVocode_FILT2",
    "kFilterLPF", "kFilterHPF", "kDistTube", "kDistSoftClip", "kDistHardClip",
    "kDistDiode1", "kDistDiode2", "kDistLinFold", "kDistSinFold", "kDistZeroSquare",
    "kDistAsym", "kDistRectify", "kDistSineShaper", "kDistStompBox", "kDistTapeSat",
    "kDistSoftSat", "kFM_OSC", "kFM_OSC2", "kFM_NOISE", "kFM_SUB", "kFM_FILT1",
    "kFM_FILT2", "kFMX_OSC", "kFMX_OSC2", "kFMX_NOISE", "kFMX_SUB", "kFMX_FILT1",
    "kFMX_FILT2", "kFMP_OSC", "kFMP_OSC2", "kFMP_NOISE", "kFMP_SUB", "kFMP_FILT1",
    "kFMP_FILT2", "kSelfPD", "kPD_OSC", "kPD_OSC2", "kPD_NOISE", "kPD_SUB",
    "kPD_FILT1", "kPD_FILT2", "kAM_OSC", "kAM_OSC2", "kAM_NOISE", "kAM_SUB",
    "kAM_FILT1", "kAM_FILT2", "kRM_OSC", "kRM_OSC2", "kRM_NOISE", "kRM_SUB",
    "kRM_FILT1", "kRM_FILT2",
)

# SpectralOsc (slots 0-2, alternate engine kParamType="kOsc_Spectral") --
# structurally identical to SampleOsc/GranularOsc's own file-reference
# shape, plus a `flex` curve sibling (see the point-curve format decode,
# PARAMETER_SCHEMA.md item 4) applying a spectral filter/EQ-like shape
# across the frequency domain. Full automatable/private param enum mined
# from the VST3 binary 2026-07-30: kParamWarp/WarpVar/WarpMenu/Warp2/
# WarpVar2/WarpMenu2/SpecFltShift/SpecFltWetDry/FreqLo/FreqHi (automatable)
# plus kParamPhaseLock/Transients/LoHiIsPost/LoHiIsSmooth/YAxisAssignment
# (private). A 53-preset corpus survey found `flex.numPoints` is genuinely
# >1 (a real hand-drawn spectral curve) in 53% of real occurrences -- only
# the trivial single-point case (47%) is safely reproducible without a
# curve-generation feature (see item 4), so this engine is wired into
# OscillatorSpec with that caveat: a flat/neutral spectral response,
# frequency-range and warp controls are real and generatable, the CURVE
# SHAPE itself always comes out flat/untouched. NOT yet confirmed live for
# generation -- same "experimental" caveat as GranularOsc/LfoSpec.shape.
SPECTRALOSC_PARAMS: dict[str, ParamDef] = {
    "kParamWarp": ParamDef(
        "kParamWarp", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="Real range observed 0.035-1.0 across 26 samples.",
    ),
    "kParamWarpMenu": ParamDef(
        "kParamWarpMenu", "enum", default="kNoWarp", confidence="observed",
        enum_values=_SPECTRAL_WARP_MODES,
        notes="SpectralOsc's OWN warp-mode vocabulary, much larger and mostly DIFFERENT "
        "names than SIMPLE_WARP_MODES (WTOsc/SampleOsc/GranularOsc's shared one) -- see "
        "the module-level comment above this table. Not offered as curated friendly "
        "names; pass the raw 'kXxx' string directly via OscillatorSpec.warp_mode (falls "
        "through unchanged when not a SIMPLE_WARP_MODES key, same mechanism already used "
        "for any warp-capable engine).",
    ),
    "kParamWarp2": ParamDef(
        "kParamWarp2", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="Second warp lane's amount -- NOT wired into OscillatorSpec.warp_amount2 "
        "for this engine yet.",
    ),
    "kParamWarpMenu2": ParamDef(
        "kParamWarpMenu2", "enum", default="kNoWarp", confidence="observed",
        enum_values=_SPECTRAL_WARP_MODES,
    ),
    "kParamWarpVar": ParamDef("kParamWarpVar", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain"),
    "kParamWarpVar2": ParamDef("kParamWarpVar2", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain"),
    "kParamSpecFltShift": ParamDef(
        "kParamSpecFltShift", "float", default=0.0, min=-100.0, max=100.0, unit="%",
        confidence="observed", notes="Shifts the spectral filter/curve's effective "
        "position. Real range observed -100.0 to 100.0.",
    ),
    "kParamSpecFltWetDry": ParamDef(
        "kParamSpecFltWetDry", "float", default=100.0, min=0.0, max=100.0, unit="%",
        confidence="observed", notes="Wet/dry for the spectral filter/curve effect. Real "
        "range observed 0.0-98.7.",
    ),
    "kParamFreqLo": ParamDef(
        "kParamFreqLo", "float", default=20.0, min=20.0, max=20000.0, unit="Hz",
        confidence="observed", notes="Low edge of the frequency range the spectral "
        "effect applies to. Real range observed 15.9-4307.3 Hz.",
    ),
    "kParamFreqHi": ParamDef(
        "kParamFreqHi", "float", default=20000.0, min=20.0, max=20000.0, unit="Hz",
        confidence="observed", notes="High edge of the frequency range. Real range "
        "observed 371.1-17462.0 Hz.",
    ),
    "kParamPhaseLock": ParamDef("kParamPhaseLock", "bool", default=False, confidence="uncertain"),
    "kParamTransients": ParamDef("kParamTransients", "bool", default=False, confidence="uncertain"),
    "kParamLoHiIsPost": ParamDef("kParamLoHiIsPost", "bool", default=False, confidence="uncertain"),
    "kParamLoHiIsSmooth": ParamDef("kParamLoHiIsSmooth", "bool", default=False, confidence="uncertain"),
    "kParamYAxisAssignment": ParamDef(
        "kParamYAxisAssignment", "enum", default="kYAxisNone", confidence="uncertain",
        enum_values=(
            "kYAxisNone", "kYAxisOscVolume", "kYAxisSpectralWarp", "kYAxisSpectralWarp2",
            "kYAxisSpectralSpecFltShift", "kYAxisSpectralSpecFltWetDry",
            "kYAxisSpectralFreqLo", "kYAxisSpectralFreqHi",
        ),
        notes="Rare (an XY-pad axis assignment) -- low-priority, same as GranularOsc's "
        "own kParamYAxisAssignment.",
    ),
}

# MultiSampleOsc (slots 0-2, alternate engine kParamType="kOsc_MultiSample")
# -- decoded 2026-07-31 via a 246-sample corpus survey. Unlike SampleOsc/
# GranularOsc/SpectralOsc (a single audio file reference), MultiSampleOsc's
# real structure is a full SFZ-format multisample keyzone mapping across
# MANY sample files (embedded_sfz text + a files metadata dict, see
# MultiSampleInstrumentDef above) -- too complex to synthesize a NEW
# instrument from scratch this round, so only a curated set of real Factory
# instruments (MULTISAMPLE_INSTRUMENTS) are referenceable, mirroring
# `wavetable`'s curated-Factory-content approach. This table only covers
# MultiSampleOsc's own `plainParams` (its OSC-level envelope/warp controls,
# layered on top of whatever ADSR the SFZ's own regions define -- these are
# NOT the primary voice envelope, Env0-3). Only the 3 highest-presence
# controls (kParamEnvAttack 98%, kParamEnvRelease 100%, kParamEnvDecay 97%)
# plus warp_amount/warp_mode (shared with every other warp-capable engine)
# are wired into OscillatorSpec this round; kParamEnvOverride/
# VelTrackOverride/TimbreShift/RandomPhase/VelTrack/second warp lane remain
# documented here for round-trip/edit safety only.
MULTISAMPLEOSC_PARAMS: dict[str, ParamDef] = {
    "kParamEnvAttack": ParamDef(
        "kParamEnvAttack", "float", default=0.0, min=0.0, max=0.4, unit="seconds",
        confidence="observed", notes="98% presence (242/246). Real range 0.0-0.396 -- "
        "notably SHORT compared to Env0-3's own attack range, consistent with this being "
        "a separate note-shaping stage layered on the SFZ's own baked-in ampeg envelope, "
        "not the primary voice envelope.",
    ),
    "kParamEnvDecay": ParamDef(
        "kParamEnvDecay", "float", default=0.0, min=0.0, max=32.0, unit="seconds",
        confidence="observed", notes="97% presence (239/246). Real range 0.0-32.0.",
    ),
    "kParamEnvSustain": ParamDef(
        "kParamEnvSustain", "float", default=1.0, min=0.0, max=1.0, confidence="observed",
        notes="Only 11/246 real samples -- rare, most content relies on the SFZ's own "
        "loop/release behavior instead.",
    ),
    "kParamEnvRelease": ParamDef(
        "kParamEnvRelease", "float", default=0.0, min=0.0, max=32.0, unit="seconds",
        confidence="observed", notes="100% presence (245/246, effectively always set). "
        "Real range 0.0-32.0.",
    ),
    "kParamEnvHold": ParamDef(
        "kParamEnvHold", "float", default=0.0, min=0.0, max=32.0, unit="seconds",
        confidence="uncertain", notes="Rare (5/246).",
    ),
    "kParamEnvDelay": ParamDef(
        "kParamEnvDelay", "float", default=0.0, min=0.0, max=1.0, unit="seconds",
        confidence="uncertain", notes="Very rare (4/246), tiny real values observed.",
    ),
    "kParamEnvOverride": ParamDef(
        "kParamEnvOverride", "bool", default=False, confidence="uncertain",
        notes="27% presence (66/246), always 1.0/True when present. Presumed to gate "
        "whether kParamEnv* values override the SFZ's own per-region ampeg envelope "
        "vs. layering on top of it -- not independently confirmed.",
    ),
    "kParamVelTrack": ParamDef(
        "kParamVelTrack", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="uncertain", notes="Rare (33/246), real range 0.0-95.7.",
    ),
    "kParamVelTrackOverride": ParamDef(
        "kParamVelTrackOverride", "bool", default=False, confidence="uncertain",
        notes="Rare (22/246), always 1.0/True when present -- same pattern as "
        "kParamEnvOverride, presumably gating kParamVelTrack similarly.",
    ),
    "kParamTimbreShift": ParamDef(
        "kParamTimbreShift", "float", default=0.0, min=-20.0, max=65.0, confidence="uncertain",
        notes="18% presence (44/246), real range -17.0 to 64.0. Exact effect unconfirmed.",
    ),
    "kParamRandomPhase": ParamDef(
        "kParamRandomPhase", "float", default=0.0, min=0.0, max=100.0, unit="%",
        confidence="uncertain", notes="Rare (23/246).",
    ),
    "kParamWarp": ParamDef(
        "kParamWarp", "float", default=0.0, min=0.0, max=1.0, confidence="observed",
        notes="Shared with WTOsc/SampleOsc/GranularOsc/SpectralOsc's warp system -- see "
        "OscillatorSpec.warp_amount. 13% presence (31/246).",
    ),
    "kParamWarpMenu": ParamDef(
        "kParamWarpMenu", "enum", default="kFM_OSC", confidence="observed",
        enum_values=(
            "kFM_OSC", "kFM_OSC2", "kFM_NOISE", "kFM_SUB", "kAM_OSC", "kRM_OSC", "kRM_SUB",
            "kSelfPD", "kPD_OSC", "kPD_OSC2", "kPD_SUB", "kFilterLPF", "kFilterHPF",
            "kDistTube", "kDistSoftClip", "kDistHardClip", "kDistDiode1", "kDistDiode2",
            "kDistSinFold", "kDistAsym", "kDistSineShaper", "kDistStompBox", "kDistSoftSat",
            "kDistTapeSat",
        ),
        notes="30% presence (74/246) -- a curated subset of the values actually observed "
        "in real content (not necessarily exhaustive); same 'pass raw name through' "
        "convention as SpectralOsc's warp_mode.",
    ),
    "kParamWarp2": ParamDef(
        "kParamWarp2", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain",
        notes="Rare (15/246) -- NOT wired into OscillatorSpec.warp_amount2 for this "
        "engine yet.",
    ),
    "kParamWarpMenu2": ParamDef(
        "kParamWarpMenu2", "enum", default="kFM_OSC", confidence="uncertain",
        enum_values=(
            "kFM_OSC", "kFM_OSC2", "kFM_NOISE", "kFM_SUB", "kFMX_OSC", "kAM_OSC", "kAM_OSC2",
            "kAM_SUB", "kRM_OSC", "kRM_NOISE", "kSelfPD", "kPD_OSC", "kPD_NOISE", "kPD_FILT1",
            "kFilterLPF", "kDistSoftClip", "kDistTube", "kDistStompBox", "kDistSineShaper",
        ),
        notes="Rare (43/246).",
    ),
    "kParamWarpVar": ParamDef(
        "kParamWarpVar", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain",
        notes="Very rare (2/246).",
    ),
    "kParamWarpVar2": ParamDef(
        "kParamWarpVar2", "float", default=0.0, min=0.0, max=1.0, confidence="uncertain",
        notes="Very rare (1/246).",
    ),
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
        notes="0=fully closed, 1=fully open. Calibrated 2026-07-31 via the audio-"
        "rendering pipeline (see docs/PARAMETER_SCHEMA.md item 2 and "
        "reference-serum-verify-audio-pipeline): an 11-point sweep on lowpass_24 "
        "fed white noise, measuring 85%-energy spectral rolloff, gives 0.05->21.5Hz "
        "through 1.00->14427.2Hz, roughly log-linear through the middle with some "
        "flattening at both extremes. Treat as the best current reference table, not "
        "a closed-form formula (rolloff85 is a proxy for -3dB point, and the "
        "flattening at the extremes could be a real curve feature or a proxy "
        "artifact, not disambiguated). Still `uncertain` because this table is "
        "specific to lowpass_24 -- not independently confirmed for every other "
        "filter type in the enum above (comb/formant/moog/etc. plausibly use a "
        "different Freq curve or a different role for this knob entirely). Confirmed "
        "2026-08-01 via VST3 binary string mining: DistComb1BP/1LP/2BP/2LP's "
        "'COMBFRQ' UI knob (previously flagged as an unconfirmed possible 5th "
        "filter param) is THIS param under a type-specific label, not a separate "
        "one -- the binary's automatable-param enum for VoiceFilter has no "
        "separate Comb-frequency ID, and 'CombFrq'/'LP Frq'/'HP Frq' sit adjacent "
        "in the string table as per-type label variants of kParamFreq (the same "
        "pattern as kParamVar's per-type relabeling below).",
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
        confidence="observed",
        notes="Hz/BPM mapping depends on kParamMode and beat-sync flags. Two points known "
        "from 2026-07-29 live UI probing (beat-synced regime): with kParamBeatSync "
        "absent (its own true default), setting the RATE knob to exactly '1/8' writes "
        "kParamRate=10.66; setting it back to '1/4' makes Serum omit the key again -- "
        "i.e. '1/4' BPM-synced IS the genuine absent-state default (not a UI "
        "placeholder), confirming mapping.py's omit-when-default fix is correct. "
        "\n\n"
        "**RETRACTED AND CORRECTED 2026-08-01**: a 2026-07-31 attempt to calibrate the "
        "separate FREE (beat_sync=False) Hz curve produced a bogus, wildly non-monotonic "
        "'result' (a fake exponential-doubling shape at low raw values, anomalous "
        "plateaus above raw~35) -- traced to a REAL bug, not a Serum quirk: "
        "LfoSpec.beat_sync used to be a plain `bool` defaulting to `False`, which is "
        "indistinguishable from 'not set' once mapping.py's omit-at-default logic runs -- "
        "so EVERY calibration preset in that sweep silently omitted kParamBeatSync "
        "entirely and was actually measured in Serum's real absent-state default "
        "(BPM-SYNCED), not free-Hz mode at all. Found live by a user manually turning a "
        "calibration preset's RATE knob in Serum and noticing it displayed 'BPM'/a note "
        "fraction (e.g. '1/16') instead of Hz -- the automated pipeline never would have "
        "caught this on its own, since it only ever inspected the rendered AUDIO, not "
        "the loaded preset's own UI state. Fixed by making `LfoSpec.beat_sync` a 3-state "
        "`bool | None` (see its docstring) so `False` genuinely writes "
        "`kParamBeatSync=False` instead of being omitted.\n\n"
        "**Re-calibrated 2026-08-01 with the fix in place, genuine free-Hz mode "
        "confirmed this time**: raw 2/5/10/20/30 measured 2.0/5.0/10.0/20.0/30.0 Hz -- "
        "an exact 1:1 match, i.e. **raw kParamRate IS literal Hz** in free mode, no curve "
        "needed at all (trust this for raw <= ~30). raw=0 (which still omits kParamRate "
        "itself, a separate and correct omission -- see _LFO_KEYS_OMIT_AT_DEFAULT) "
        "measured 6.25Hz, presumably Serum's own genuine free-mode rate default; not "
        "independently confirmed.\n\n"
        "**The raw>=~35-40 'anomaly' -- live-Serum cross-check 2026-08-01, resolved as "
        "a measurement-pipeline limitation, NOT a real Serum DSP issue.** First live "
        "check found real visible/audible glitches -- but traced entirely to the "
        "well-known per-voice LFO phase-reset-on-note-on behavior (see "
        "LfoSpec.mono's docstring), an artifact of testing with a looping/retriggering "
        "piano-roll note, not the rate curve. Re-tested with `mono=True` (removes the "
        "retrigger confound) sweeping RATE 20-100%: STILL saw visible 'jumps' at the "
        "high end, but explicitly confirmed INAUDIBLE -- consistent with a stroboscopic/ "
        "aliasing illusion (the cyclic knob motion beating against the screen's own "
        "refresh rate), a known visual-perception effect, not a real audio glitch. "
        "**Conclusion**: no evidence of a genuine Serum DSP anomaly at any rate tested -- "
        "the real audio is smooth throughout, confirmed by ear with the retrigger "
        "confound removed. The automated pipeline's earlier non-monotonic Hz readings "
        "(raw 40/60/80 all reading an identical 21.6Hz, 50/70/90/100 giving inconsistent "
        "values) are now understood to be a limitation of `detect_modulation_rate_hz` "
        "itself at fast target rates (see its own docstring's 2 documented caveats), "
        "not a real curve kink -- don't re-litigate raw>=35 as a Serum bug going "
        "forward, but also don't trust the pipeline's own Hz number that fast, only "
        "that the underlying audio is well-behaved. See docs/PARAMETER_SCHEMA.md item "
        "6a for the full writeup and reference-serum-verify-audio-pipeline for the "
        "pipeline-side notes.",
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
    # Resolved 2026-08-01 via the direct-UI-probe method (user screenshotted
    # every source-picker submenu, then built one 12-row probe file covering
    # every name this project had never seen before -- see
    # docs/PARAMETER_SCHEMA.md §6). This closes essentially the entire
    # remaining source-id gap in one sitting; only id 40 (one of Galaxy's 3
    # original unknowns) is still unaccounted for despite every name in the
    # picker now being identified -- see the note below.
    "note_on_alt": 23,  # Serum UI: "NoteOn Alt." (Note category)
    "note_on_alt2": 24,  # Serum UI: "NoteOn Alt.2" (Note category) -- one of
    # Galaxy's original 3 unknown source ids (24, 40, 57; 57 resolved
    # earlier as voice_mod2, only 40 remains open).
    "expr_pan": 34,  # Serum UI: "Expr X (Pan)" -- MPE-style note expression,
    # contiguous right after pitch_bend (33).
    "expr_timbre": 35,  # Serum UI: "Expr Y (Timbre)"
    "expr_press": 36,  # Serum UI: "Expr Z (Press.)"
    # Self-modulation sources -- a module's own audio-rate output used to
    # modulate something else (distinct from routing something INTO that
    # module). Named with the SAME 0-indexed convention as this project's
    # destination side (oscillator{i}.*, filter{i}.*) for consistency, even
    # though Serum's own UI labels them 1-indexed ("OSC A"/"Filter 1").
    "oscillator0": 49,  # Serum UI: "OSC A"
    "oscillator1": 50,  # Serum UI: "OSC B"
    "oscillator2": 51,  # Serum UI: "OSC C"
    "oscillator4": 52,  # Serum UI: "SUB OSC" -- note oscillator3 (Noise) is
    # NOT part of this contiguous 49-52 block, see "oscillator3" below --
    # a genuine gap in Serum's own id assignment, not a probing error
    # (independently re-confirmed by row order in the probe file).
    "oscillator3": 20,  # Serum UI: "Noise OSC" -- resolves one of the
    # original "20/23" cluster gaps from the first probe rounds.
    "filter0": 53,  # Serum UI: "Filter 1"
    "filter1": 54,  # Serum UI: "Filter 2"
}
# `20` and `40` (from the *original* Galaxy-recreation gap list) deserve a
# closing note: `20` is now resolved above (`oscillator3`/"Noise OSC"). `40`
# is NOT -- and after this probe, every single named entry in Serum 2's own
# MATRIX-tab source picker (all 49 of them, across every submenu) has a
# resolved id, none of which is 40. That makes `40` very unlikely to be
# reachable via the standard UI at all -- plausibly a legacy/vestigial id
# from an earlier Serum version's source list, or something gated behind a
# state this project hasn't triggered (a specific engine/module combination
# where the picker briefly shows an extra option). Further UI probing of the
# picker itself is unlikely to resolve it; if it matters again, the more
# promising angle is finding a REAL preset that uses it and working
# backwards from context (mod-route amount curve, what it's paired with),
# the same way `38` ("Fixed") was originally noticed.


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
    # Confirmed 2026-07-30 via a 626-preset corpus survey of every real
    # ModSlot's (destModuleTypeString, destModuleParamName) -> destModuleParamID
    # pair (same method as the rest of this table): kParamWet -> 1 (152
    # samples), kParamVar -> 6 (82), kParamStereo -> 7 (14), kParamLevelOut
    # -> 8 (153) -- closing part of item 1b's "VoiceFilter.kParamWet" gap in
    # docs/PARAMETER_SCHEMA.md §5. kParamX/kParamY also appeared as real mod
    # destinations (ids 9/10) but only 4/1 samples respectively and aren't
    # even modeled as static FilterSpec fields yet -- not enough evidence to
    # add safely, left out.
    MOD_DEST_TARGETS[f"filter{_i}.wet"] = ModDestDef("VoiceFilter", _i, "kParamWet", 1)
    MOD_DEST_TARGETS[f"filter{_i}.var"] = ModDestDef("VoiceFilter", _i, "kParamVar", 6)
    MOD_DEST_TARGETS[f"filter{_i}.stereo"] = ModDestDef("VoiceFilter", _i, "kParamStereo", 7)
    MOD_DEST_TARGETS[f"filter{_i}.level_out"] = ModDestDef("VoiceFilter", _i, "kParamLevelOut", 8)
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
# NoiseOsc is a singleton submodule living only inside Oscillator3 (the
# fixed Noise slot, see OscillatorSpec.noise_type) -- destModuleID always 3
# (confirmed 2026-07-30, 64/64 samples), matching that slot's own index, the
# same convention as WTOsc's oscillator{i}.* destinations above.
# destModuleParamID confirmed via the same 626-preset survey: kParamColor ->
# 0 (53 samples). Closes part of item 1b's "NoiseOsc.kParamColor" gap.
MOD_DEST_TARGETS["oscillator3.noise_color"] = ModDestDef("NoiseOsc", 3, "kParamColor", 0)
# Closes the rest of NoiseOsc's item 1b gap -- confirmed 2026-08-01 via an
# 876-preset corpus survey (Factory + every third-party bank on this
# machine, not just the original 626): kParamInitialPhase (7 samples) and
# kParamFine (6 samples) at destModuleParamID 2/1 respectively, same
# fixed destModuleID=3 singleton as kParamColor above. kParamRandomPhase
# (1 sample) stays unwired -- too little evidence.
MOD_DEST_TARGETS["oscillator3.noise_initial_phase"] = ModDestDef(
    "NoiseOsc", 3, "kParamInitialPhase", 2
)
MOD_DEST_TARGETS["oscillator3.noise_fine"] = ModDestDef("NoiseOsc", 3, "kParamFine", 1)
del _i
# `Global` is a singleton (destModuleID always 0), unlike everything above
# which is per-slot. Confirmed live 2026-07-29 against TWO independent real
# presets (both used key_track -> Global.kParamVoiceAmp, at -61% and -52%
# respectively) -- destModuleParamID 2.
MOD_DEST_TARGETS["global.voice_amp"] = ModDestDef("Global", 0, "kParamVoiceAmp", 2)
# `Arp`/`VoicePanel` are also singletons (destModuleID always 0, confirmed
# 2026-07-30: 32/32 and 9/9 samples respectively). destModuleParamID via the
# same 626-preset survey. Arp's gate/rate are only meaningful when
# GlobalSpec/ArpSpec's own arp is actually enabled, same caveat as any other
# destination targeting a disabled module. Closes the rest of item 1b's
# "Arp params"/"VoicePanel.kParamGlobalScalingEnvTime" gaps.
MOD_DEST_TARGETS["arp.gate"] = ModDestDef("Arp", 0, "kParamGate", 6)
MOD_DEST_TARGETS["arp.rate"] = ModDestDef("Arp", 0, "kParamRate", 1)
# Closes 3 more of Galaxy's "still open" Arp routes -- confirmed 2026-08-01
# via the same 876-preset survey: kParamChance (7 samples), kParamOffset
# (7), kParamTransposeRange (6), all destModuleID 0 (Arp's own singleton).
# kParamWrapPhantomNote/kParamRetrigRate/kParamVeloTarget (1-2 samples
# each) stay unwired -- too little evidence yet.
MOD_DEST_TARGETS["arp.chance"] = ModDestDef("Arp", 0, "kParamChance", 7)
MOD_DEST_TARGETS["arp.offset"] = ModDestDef("Arp", 0, "kParamOffset", 4)
MOD_DEST_TARGETS["arp.transpose_range"] = ModDestDef("Arp", 0, "kParamTransposeRange", 3)
MOD_DEST_TARGETS["global.voice_scaling_env_time"] = ModDestDef(
    "VoicePanel", 0, "kParamGlobalScalingEnvTime", 58
)
MOD_DEST_TARGETS["global.voice_scaling_lfo_time"] = ModDestDef(
    "VoicePanel", 0, "kParamGlobalScalingLfoTime", 59
)

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
        # Closes the rest of item 1b's "FXUtils.kParamWidth/kParamLPF" gap
        # (plus HPF/LFXover, found alongside them) -- confirmed 2026-08-01
        # via an 876-preset corpus survey (Factory + every third-party bank
        # on this machine): kParamWidth (~50 samples across many
        # destModuleIDs), kParamLPF (~40), kParamHPF (~30), kParamLFXover
        # (3, rarer but still directly observed, same evidentiary bar as
        # kParamBalance's original single confirmation above).
        "width": ("kParamWidth", 3),
        "hpf": ("kParamHPF", 7),
        "lpf": ("kParamLPF", 8),
        "lf_xover": ("kParamLFXover", 6),
    },
    "FXEQ": {
        # Closes item 1b's "FXEQ.kParamFreq2" gap -- confirmed 2026-08-01,
        # same 876-preset survey (~60 samples across many destModuleIDs,
        # destModuleParamID consistently 2).
        "freq2": ("kParamFreq2", 2),
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
            notes="Max corrected from 1.4 after finding a real Factory preset with rate=20.0. "
            "Partially calibrated 2026-08-01 via the audio-rendering pipeline (same "
            "detect_modulation_rate_hz technique as LFO_PARAMS['kParamRate'], see "
            "docs/PARAMETER_SCHEMA.md item 6b): raw 15/20 measured EXACTLY 15.0/20.0 Hz "
            "-- 'approx.' can be trusted as literal Hz at the top of the range. Raw "
            "2-10 measured inconsistently 1x-2x the raw value (e.g. raw=4->4Hz but "
            "raw=3->6Hz and raw=5->10Hz) -- plausibly the analysis locking onto the "
            "2nd harmonic of the true rate (a symmetric brightness sweep can read as "
            "2x in a spectral-centroid-based measurement) rather than a real curve "
            "kink, unconfirmed. Raw 0.5/1.0 measured a fixed ~16.5/~32 Hz -- NOT a "
            "multiple of the raw value at all. NOTE: originally written up as "
            "'matching the exact same anomaly found calibrating LFO_PARAMS[\"kParamRate\"]', "
            "presented as cross-validation -- that LFO-side finding was RETRACTED "
            "2026-08-01 (it had been measuring the wrong mode entirely due to an "
            "unrelated beat_sync bug, see LFO_PARAMS['kParamRate']'s notes), so this "
            "FXChorus anomaly is back to being an independent, uncorroborated finding, "
            "not confirmed by a second source. Still real and reproducible on its own "
            "terms (unaffected by the beat_sync bug -- FXChorus has no such field), just "
            "don't cite it as cross-validated anymore. Trust raw >= ~15 only; don't "
            "trust the low end without a live Serum check.",
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
            notes="Max corrected from 5.1 after finding a real preset with rate=9.3. "
            "Calibrated 2026-08-01 via the audio-rendering pipeline (same technique as "
            "FXChorus): measured Hz was EXACTLY 2x the raw value across all 7 points "
            "tested (raw 1/2/3/5/7/9/10 -> 2/4/6/10/14/18/20 Hz), a suspiciously perfect "
            "and uniform ratio, not the erratic 1x/2x flip-flopping seen calibrating "
            "FXChorus's low range. Most likely explanation: detect_modulation_rate_hz's "
            "known 2nd-harmonic-locking limitation (see its own docstring) is unusually "
            "STRONG and consistent for a flanger's sharp, symmetric comb-filter-notch "
            "brightness sweep -- meaning the true curve is presumably raw=Hz, matching "
            "every other similarly-labeled rate param calibrated this project (LFO free "
            "rate, FXChorus's own confirmed raw>=15 range), not a genuine '2x' Serum "
            "curve. NOT independently disambiguated (would need a live Serum check or a "
            "differently-shaped destination signal) -- treat 'raw=Hz' as the working "
            "assumption, not a confirmed fact, for this specific param.",
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
            "kParamRate", "float", default=1.0, min=0.0, max=20.0, unit="Hz (approx.)",
            notes="Calibrated 2026-08-01, same technique/caveat as FXFlanger above: "
            "measured Hz was ~2x raw at most points (raw 1/2/10/15/18/20 -> 2/4/20/30/"
            "36/40 Hz) but NOT perfectly consistent -- raw=5 measured 20Hz (4x, not the "
            "expected ~10Hz/2x), an outlier that itself supports 'harmonic-locking "
            "instability' over 'genuine clean 2x curve' (a real fixed-ratio Serum curve "
            "shouldn't have produced this one inconsistent point). Same working "
            "assumption as FXFlanger: true curve presumably raw=Hz, not independently "
            "confirmed.",
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
            "kParamTimeL", "float", default=0.25, min=0.001, max=0.34, unit="seconds",
            confidence="confirmed",
            notes="CONFIRMED literal seconds 2026-08-01 via the audio-rendering pipeline "
            "(a sharp transient through the delay, feedback>0 for repeats, measuring the "
            "echo gap via onset detection) -- but ONLY when kParamBeatSync (see below) is "
            "explicitly False. Real bug found in the process, same class as "
            "LFO_PARAMS['kParamRate']'s beat_sync issue: kParamBeatSync was never "
            "catalogued in this schema at all (found via VST3 binary string mining, same "
            "technique as the COMBFRQ/RoutingSlot/ModSlot investigations), so no "
            "serum-mcp-generated FXDelay has ever set it -- meaning every one has been "
            "silently falling back to Serum's real (BPM-synced/note-quantized) default, "
            "NOT literal seconds as this label implied. Raw 0.05/0.1/0.2/0.3 measured "
            "clean note-value-like jumps (~0.255/~0.5/~2.0/~2.0/~4.0s -- doubling at "
            "irregular raw intervals, unmistakably a quantized/synced pattern, not a "
            "smooth curve) when kParamBeatSync was left absent; with kParamBeatSync=False "
            "explicitly written, the SAME raw values measured near-exact literal seconds "
            "(0.05->0.046, 0.1->0.105, 0.2->0.197, 0.3->0.302, all within onset-detection "
            "noise of the raw value itself). Pass `kParamBeatSync: False` explicitly in "
            "FxUnitSpec.params whenever kParamTimeL/R should mean literal seconds.",
        ),
        "kParamTimeR": ParamDef(
            "kParamTimeR", "float", default=0.25, min=0.001, max=0.32, unit="seconds",
            confidence="confirmed", notes="See kParamTimeL -- identical finding/fix.",
        ),
        "kParamBeatSync": ParamDef(
            "kParamBeatSync", "bool", default=False, confidence="confirmed",
            notes="Never catalogued before 2026-08-01 (found via VST3 binary string "
            "mining while investigating why kParamTimeL/R's calibration looked "
            "note-quantized instead of linear) -- see kParamTimeL's notes for the full "
            "story. Presumed genuine absent-state default is BPM-synced (True-like), "
            "mirroring LFO_PARAMS['kParamRate']'s own beat_sync default, but NOT "
            "independently confirmed via the omit-vs-explicit-True comparison that "
            "nailed that down for the LFO case -- only confirmed that explicit False "
            "unlocks literal-seconds kParamTimeL/R. Not yet exposed as a dedicated "
            "OscillatorSpec-style field -- pass `kParamBeatSync: False` directly via "
            "FxUnitSpec.params (validated fine, `_build_fx_entry` allows unknown-to-"
            "common-schema keys through for any FX type) whenever literal-second delay "
            "times are wanted.",
        ),
        "kParamMode": ParamDef(
            "kParamMode", "float", confidence="uncertain",
            notes="Found via the same 2026-08-01 binary string mining as kParamBeatSync "
            "above, never independently investigated -- likely a delay-topology enum "
            "(e.g. normal/ping-pong/dual-mono) given it sits alongside kParamLink/"
            "kParamOffsetL/kParamOffsetR in the same automatable-param group, but the "
            "real values/kind (float vs enum) aren't confirmed. Documented for "
            "round-trip safety only.",
        ),
        "kParamLink": ParamDef(
            "kParamLink", "bool", default=False, confidence="uncertain",
            notes="Found via binary string mining, presumably 'link L/R times together' "
            "given its position next to kParamTimeL/R -- not independently confirmed.",
        ),
        "kParamBW": ParamDef(
            "kParamBW", "float", confidence="uncertain",
            notes="Found via binary string mining; also independently spotted as a real, "
            "uncatalogued key surviving edit-round-trip passthrough on real third-party "
            "content during the 2026-07-28 stress test (see PARAMETER_SCHEMA.md item at "
            "the top of §5). Presumably the tone filter's bandwidth, alongside "
            "kParamFreq -- not independently confirmed.",
        ),
        "kParamOffsetL": ParamDef(
            "kParamOffsetL", "float", confidence="uncertain",
            notes="Found via binary string mining, presumably a per-channel timing "
            "offset/micro-delay alongside kParamOffsetR -- not independently confirmed.",
        ),
        "kParamOffsetR": ParamDef(
            "kParamOffsetR", "float", confidence="uncertain",
            notes="See kParamOffsetL.",
        ),
        "kParamHQ": ParamDef(
            "kParamHQ", "bool", default=False, confidence="uncertain",
            notes="Found via binary string mining, presumably a high-quality/"
            "oversampling toggle -- not independently confirmed.",
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

# FXSplit / FXSplit3 / FXSplitMS -- multi-band split/merge FX units, decoded
# 2026-07-30 via a 626-preset corpus survey (77 real occurrences: 43/19/15).
# Despite the "structurally different, needs a recursive FxUnitSpec" note
# this comment used to carry, they turned out to have an ORDINARY flat
# plainParams dict, same as every other FX type -- no nested container at
# all. What actually differs is how the SUBSEQUENT entries in that same
# rack's flat FX list are interpreted:
#   - FXSplit (2 bands): kParamModuleCount1/kParamModuleCount2 (each
#     optional, default/absent = 0) give branch 1's and branch 2's own unit
#     counts. Reading the flat list AFTER the split entry in order: the
#     first kParamModuleCount1 entries belong to band 1 (below kParamFreq),
#     the next kParamModuleCount2 entries belong to band 2 (above
#     kParamFreq) -- confirmed against 43 real examples with ZERO
#     exceptions, e.g. `BA - Dual MG Bass.SerumPreset`
#     (kParamModuleCount1=1, kParamModuleCount2=1, followed by exactly
#     [FXDistortion, FXDelay]: branch1=[FXDistortion], branch2=[FXDelay]).
#   - FXSplit3 (3 bands): same idea with kParamModuleCount1/2/3 and TWO
#     crossover frequencies (kParamFreq = low/mid boundary, kParamFreq2 =
#     mid/high boundary) -- confirmed against 19 real examples, e.g.
#     `KIT - 808 Basic Kit.SerumPreset` (all three counts=1, followed by
#     [FXComp, FXComp, FXComp, FXConv, FXComp]: 3 bands of 1 unit each,
#     then 2 more units continuing AFTER the split/remerge point).
#   - FXSplitMS (Mid/Side split, no crossover frequency -- channel-based,
#     not frequency-based): kParamModuleCount1/kParamModuleCount2 for the
#     Mid and Side branches respectively -- confirmed against 15 real
#     examples, same consumption rule.
# In every type, once all bands' counts are consumed, ANY remaining entries
# in that rack continue as ordinary SERIAL processing on the recombined
# signal (the bands implicitly remerge back into one signal after their own
# branch chains) -- e.g. the `KIT - 808 Basic Kit` example's trailing
# [FXConv, FXComp] process the merged 3-band output further. This needs NO
# special code: it's the exact same flat, ordered `fx_chain` list every
# other FX type already uses -- `FxUnitSpec(type='FXSplit', params={
# 'kParamFreq': ..., 'kParamModuleCount1': ..., 'kParamModuleCount2': ...})`
# followed by that many further `FxUnitSpec` entries in the SAME rack IS a
# correctly-formed split. The calling model is responsible for setting the
# counts to match how many entries it actually places in each band (see
# server.py's fx_chain guidance) -- nothing here validates that a count
# matches reality, the same trust level as every other free-form field.
# None of the three has a `kParamWet`/mix knob (absent from every real
# sample) -- omitted here the same way FXEQ omits it.
FX_PARAMS["FXSplit"] = {
    "kParamFreq": ParamDef(
        "kParamFreq", "float", default=1000.0, min=20.0, max=20000.0, unit="Hz",
        confidence="observed",
        notes="Crossover between band 1 (below) and band 2 (above). Real range "
        "observed 30.8-3517.9 Hz across 54 samples (shared with FXSplit3's kParamFreq).",
    ),
    "kParamModuleCount1": ParamDef(
        "kParamModuleCount1", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="How many of the flat fx_chain entries immediately following this one "
        "(within the same rack) belong to band 1 -- see the module-level comment above "
        "this table. Absent/0 means band 1 has no additional processing.",
    ),
    "kParamModuleCount2": ParamDef(
        "kParamModuleCount2", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="Same as kParamModuleCount1, for band 2 -- consumed from the flat list "
        "right after band 1's entries.",
    ),
}
FX_PARAMS["FXSplit3"] = {
    "kParamFreq": ParamDef(
        "kParamFreq", "float", default=300.0, min=20.0, max=20000.0, unit="Hz",
        confidence="observed", notes="Crossover between band 1 (low) and band 2 (mid).",
    ),
    "kParamFreq2": ParamDef(
        "kParamFreq2", "float", default=3000.0, min=20.0, max=20000.0, unit="Hz",
        confidence="observed",
        notes="Crossover between band 2 (mid) and band 3 (high). Real range observed "
        "309.5-9000.0 Hz across 17 samples.",
    ),
    "kParamModuleCount1": ParamDef(
        "kParamModuleCount1", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="Band 1 (low)'s own unit count -- see FXSplit's kParamModuleCount1 note; "
        "same consumption rule, 3 bands instead of 2.",
    ),
    "kParamModuleCount2": ParamDef(
        "kParamModuleCount2", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="Band 2 (mid)'s own unit count.",
    ),
    "kParamModuleCount3": ParamDef(
        "kParamModuleCount3", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="Band 3 (high)'s own unit count.",
    ),
}
FX_PARAMS["FXSplitMS"] = {
    "kParamModuleCount1": ParamDef(
        "kParamModuleCount1", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="Mid branch's own unit count -- no crossover frequency (channel-based "
        "split, not frequency-based); same consumption rule as FXSplit.",
    ),
    "kParamModuleCount2": ParamDef(
        "kParamModuleCount2", "float", default=0.0, min=0.0, max=16.0, confidence="observed",
        notes="Side branch's own unit count.",
    ),
}

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
