"""Merge a semantic :class:`~serum_mcp.generation.spec.PresetSpec` onto the
raw CBOR payload of a base preset (typically ``fixtures/init_preset.SerumPreset``).

Only the fields present on the spec are touched -- everything else in the
base preset's ``data`` dict (mod matrix, arpeggiator, GUI state, unmodeled
oscillator engines, ...) passes through unchanged, so editing an existing
preset only perturbs what the instruction actually asked for.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from serum_mcp import config
from serum_mcp.generation.spec import (
    ArpSpec,
    FxUnitSpec,
    LfoCurvePointSpec,
    ModRouteSpec,
    OscillatorSpec,
    PresetSpec,
)

from . import sample_library, schema, wavetable
from .validator import validate_params

_CUSTOM_WAVETABLE_SUBDIR = ("User", "serum-mcp")
_MAX_CUSTOM_WAVETABLE_FRAMES = 256
_CUSTOM_SAMPLE_SUBDIR = ("User", "serum-mcp")

_OSC_KEYS = {
    "octave": "kParamOctave",
    "semitone": "kParamPitch",
    "fine": "kParamFine",
    "volume": "kParamVolume",
    "pan": "kParamPan",
    "unison": "kParamUnison",
    "detune": "kParamDetune",
}
# Presence-forces-the-DSP-stage params (see the loop below), same class as
# _FILTER_KEYS_OMIT_AT_DEFAULT/_LFO_KEYS_OMIT_AT_DEFAULT -- found live
# 2026-07-30 (UN_PLACES_BA_Beyond): Osc A's real kParamVolume is absent
# entirely (Serum shows 75%/-5dB), while writing this field's own schema
# default (0.75) explicitly showed 87%/-2.5dB instead -- not the "same
# value" the raw number implies. A real-corpus survey confirmed every other
# _OSC_KEYS entry is similarly majority-absent when untouched (kParamOctave
# 66%, kParamPitch 95%, kParamFine 90%, kParamPan 91%, kParamUnison 78%,
# kParamDetune 72%). kParamEnable is deliberately NOT here -- it's a
# structural on/off assertion this project must always write explicitly,
# not a "neutral value" a knob happens to rest at.
_OSC_KEYS_OMIT_AT_DEFAULT = {
    "kParamOctave": 0.0,
    "kParamPitch": 0.0,
    "kParamFine": 0.0,
    "kParamVolume": 0.75,
    "kParamPan": 0.0,
    "kParamUnison": 1.0,
    "kParamDetune": 0.0,
}
_WTOSC_KEYS = {
    "table_position": "kParamTablePos",
    "warp_amount": "kParamWarp",
}
_SAMPLEOSC_KEYS = {
    "warp_amount": "kParamWarp",
}
# Which slot indices use which sound-source engine. Slots 0-2 (Osc A/B/C)
# default to the wavetable engine (or the sample-playback engine, if
# sample_playback_source is set); slot 3 is always Noise, slot 4 always
# Sub -- real Serum presets never have a WTOsc3/WTOsc4/SampleOsc3/SampleOsc4
# key, only NoiseOsc3/SubOsc4, so none of this must be written there (see
# docs/PARAMETER_SCHEMA.md).
_WTOSC_SLOTS = (0, 1, 2)
_NOISE_SLOT = 3
_SUB_SLOT = 4
_ENGINE_TYPE_WT = "kOsc_WT"
_ENGINE_TYPE_SAMPLE = "kOsc_Sample"
_ENGINE_TYPE_GRANULAR = "kOsc_Granular"
_GRANULAROSC_KEYS = {
    # kParamDensity/kParamGrainLength deliberately excluded -- both need a
    # nonlinear conversion from the UI-displayed number OscillatorSpec
    # exposes to the raw CBOR value Serum actually stores, see
    # _GRANULAR_DENSITY_DIVISOR/_granular_grain_length_to_raw below. Handled
    # explicitly at the call site instead of this generic 1:1 dict.
    "granular_random_pitch": "kParamRandomPitch",
    "granular_random_pan": "kParamRandomPan",
    "granular_random_grain_length": "kParamRandomGrainLength",
    # Added 2026-08-01 -- same always-write pattern as the 3 above (no
    # omit-at-default logic, so no risk of the beat_sync-class presence
    # bug found 3 times elsewhere this session). See each OscillatorSpec
    # field's own docstring for confidence notes.
    "granular_random_offset": "kParamRandomOffset",
    "granular_loop": "kParamLoopGrains",
    "granular_jump_start": "kParamJumpStartGrains",
    "granular_reverse": "kParamGrainReverse",
    "granular_length_key_track": "kParamLengthKeyTrack",
    "granular_max_grains": "kParamMaxNumGrains",
    "granular_random_window_amount": "kParamRandomWindowAmount",
    "granular_random_window_skew": "kParamRandomWindowSkew",
}
_ENGINE_TYPE_SPECTRAL = "kOsc_Spectral"
_SPECTRALOSC_KEYS = {
    "spectral_warp_freq_lo": "kParamFreqLo",
    "spectral_warp_freq_hi": "kParamFreqHi",
    "spectral_filter_shift": "kParamSpecFltShift",
    "spectral_filter_wet": "kParamSpecFltWetDry",
}
_ENGINE_TYPE_MULTISAMPLE = "kOsc_MultiSample"
_MULTISAMPLEOSC_KEYS = {
    "multisample_env_attack": "kParamEnvAttack",
    "multisample_env_decay": "kParamEnvDecay",
    "multisample_env_release": "kParamEnvRelease",
}
_FILTER_KEYS = {
    "cutoff": "kParamFreq",
    "resonance": "kParamReso",
    "drive": "kParamDrive",
    "stereo": "kParamStereo",
    "var": "kParamVar",
    "wet": "kParamWet",
    "level_out": "kParamLevelOut",
}
# Presence-forces-the-DSP-stage params (see the loop below) -- omit these
# from a filter's plainParams whenever the spec value equals the default
# on the right, matching how real Serum leaves an untouched knob out
# entirely. kParamFreq (cutoff) is deliberately NOT here: a real-corpus
# survey (2026-07-29) found it present in 1254/1302 (96%) real filters,
# the opposite skew from these -- almost always deliberately set, so
# always writing it explicitly is the behavior that matches real content.
_FILTER_KEYS_OMIT_AT_DEFAULT = {
    "kParamWet": 100.0,
    "kParamLevelOut": 0.5,
    "kParamDrive": 0.0,
    "kParamStereo": 50.0,
    "kParamReso": 10.0,
    "kParamVar": 0.0,
}
_ENV_KEYS = {
    "attack": "kParamAttack",
    "hold": "kParamHold",
    "decay": "kParamDecay",
    "sustain": "kParamSustain",
    "release": "kParamRelease",
    "attack_curve": "kParamCurve1",
    "decay_curve": "kParamCurve2",
    "release_curve": "kParamCurve3",
}
_LFO_KEYS = {
    "rate": "kParamRate",
    "beat_sync": "kParamBeatSync",
    "delay": "kParamDelay",
    "rise": "kParamRise",
    "smooth": "kParamSmooth",
    "mono": "kParamMono",
    "swing": "kParamSwing",
    "dotted": "kParamDotted",
    "triplets": "kParamTriplets",
    "rate10x": "kParamRate10x",
}
# Presence-forces-the-DSP-stage params (see the loop below) -- every
# _LFO_KEYS entry except kParamMode (see below), all confirmed by a
# real-corpus survey to be overwhelmingly absent when untouched:
# kParamRate 37%, kParamBeatSync 67%, kParamDelay 99%, kParamRise 96%,
# kParamMono 98%, kParamSwing 99%, kParamDotted/kParamTriplets/
# kParamRate10x 83-85% absent (2026-07-29 survey); kParamSmooth 94% absent
# (2026-08-01, 2652-slot survey -- originally excluded for "no evidence
# either way," now has it: found live recreating a real preset, Galaxy,
# whose untouched LFOs lacked it entirely). kParamMode is NOT omitted --
# survey found it PRESENT 63% of the time (a real majority, unlike every
# key in this dict), so stays always-explicit despite Galaxy's own
# untouched LFOs happening to lack it.
_LFO_KEYS_OMIT_AT_DEFAULT = {
    "kParamRate": 0.0,
    "kParamSmooth": 0.0,
    # kParamBeatSync deliberately NOT here -- LfoSpec.beat_sync is a 3-state
    # `bool | None` (None = omit, True/False = write explicitly) handled as
    # a special case in the write loop below, not the generic
    # value-equals-default comparison every other key here uses. A plain
    # bool couldn't distinguish "explicitly want free-Hz mode" (False) from
    # "didn't touch this" (also False, the natural Pydantic default) --
    # real bug, made explicit free-Hz mode unreachable, fixed 2026-08-01.
    # See LfoSpec.beat_sync's docstring for the full story.
    "kParamDelay": 0.0,
    "kParamRise": 0.0,
    "kParamMono": False,
    "kParamSwing": 0.0,
    "kParamDotted": False,
    "kParamTriplets": False,
    "kParamRate10x": False,
}


def _plain_params(container: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``container[key]["plainParams"]`` as a real dict, replacing the
    sentinel string ``"default"`` Serum uses for untouched modules with {}.

    Callers write specific fields onto this dict (e.g. ``kParamFreq``) but
    don't replace it outright -- so on an edit_preset call against a
    third-party/Factory preset, whatever this module's plainParams already
    had survives alongside the new fields. That's the point (unrelated
    settings must round-trip unchanged), but it also means the merged dict
    can contain real, legitimate params this project hasn't catalogued in
    `schema.py` yet -- found live editing real Factory content (a WTOsc
    with `kParamXfadeMode`, not in `WTOSC_PARAMS`). Every `validate_params`
    call on a dict returned from here should therefore pass
    ``allow_unknown=True``: those extra keys are pre-existing, already-valid
    Serum-authored data we're not touching, not something we generated and
    need to catch a typo in (that protection still applies in full to every
    key this module's own code actually writes, since validate_params still
    checks those against the schema like normal, and to sites that build a
    fresh dict from scratch, e.g. `_build_fx_entry`/`_build_modslot_entry`,
    which should stay strict).
    """
    sub = container.setdefault(key, {})
    if not isinstance(sub.get("plainParams"), dict):
        sub["plainParams"] = {}
    return sub["plainParams"]


def _unchanged_sample_reference(
    sample_container: dict[str, Any], osc: OscillatorSpec
) -> schema.SampleAudioDef | None:
    """If ``osc.sample_playback_source`` already points at exactly the file
    this SampleOsc container currently references, return its existing
    metadata instead of re-resolving from scratch. Exists specifically for
    editing real Factory/third-party content: extract_spec reconstructs
    sample_playback_source as an absolute path built from the preset's own
    samplePathRelative, and Serum's own factory sample library is almost
    entirely .flac -- a format copy_sample_to_library can't ingest (no FLAC
    decoder in this project). Without this fast path, ANY edit_preset call
    that includes an unchanged SampleOsc oscillator in its spec (needed
    just to preserve a later oscillator's list position, or because the
    edit round-tripped the whole preset through extract_spec) would fail
    trying to re-copy a file it doesn't actually need to touch -- found
    live, 75 of 844 real presets hit exactly this. Only tried for a real
    audio file whose extension copy_sample_to_library actually supports;
    a genuinely new/different reference still goes through the normal
    resolve-and-copy path below, .flac included -- this isn't a general
    FLAC workaround, just a no-op when nothing actually needs to change."""
    existing_relative = sample_container.get("samplePathRelative")
    if not existing_relative:
        return None
    try:
        samples_dir = config.get_samples_dir()
    except config.SamplesFolderNotFoundError:
        return None
    existing_absolute = (samples_dir / existing_relative).resolve()
    try:
        incoming_absolute = Path(osc.sample_playback_source).resolve()
    except (OSError, ValueError):
        return None
    if existing_absolute != incoming_absolute:
        return None
    num_frames = sample_container.get("numFrames")
    sample_rate = sample_container.get("sampleRate")
    num_channels = sample_container.get("numChannels")
    if not (isinstance(num_frames, int | float) and sample_rate and num_channels):
        return None
    return schema.SampleAudioDef(
        existing_relative, int(num_frames), int(sample_rate), int(num_channels)
    )


def _resolve_sample_playback(osc: OscillatorSpec) -> schema.SampleAudioDef:
    """Resolve an oscillator's ``sample_playback_source`` into a
    :class:`schema.SampleAudioDef`: copy the referenced WAV into Serum's
    Samples/User/serum-mcp folder (if not already there) -- pan-balanced
    per ``osc.sample_center_pan`` -- and read its header metadata, so
    ``SampleOsc{i}`` plays the file back as recorded (just re-centered, if
    requested) -- see ``preset/sample_library.py``."""
    source_path = Path(osc.sample_playback_source)
    if not source_path.is_file():
        raise ValueError(f"sample_playback_source {osc.sample_playback_source!r} does not exist")
    # Extension check first: copy_sample_to_library rejects unsupported
    # formats (e.g. .flac) with a clear message, whereas read_wav_metadata
    # would instead fail deep inside a RIFF parse with a confusing error.
    dest = sample_library.copy_sample_to_library(
        source_path,
        config.get_samples_dir(),
        _CUSTOM_SAMPLE_SUBDIR,
        center_pan=osc.sample_center_pan,
    )
    channels, sample_rate, num_frames = sample_library.read_wav_metadata(source_path)
    relative_path = "/".join((*_CUSTOM_SAMPLE_SUBDIR, dest.name))
    return schema.SampleAudioDef(relative_path, num_frames, sample_rate, channels)


def _unchanged_granular_reference(
    granular_container: dict[str, Any], osc: OscillatorSpec
) -> schema.SampleAudioDef | None:
    """Same fast path as ``_unchanged_sample_reference``, for
    ``osc.granular_source`` against a ``GranularOsc{i}`` container -- avoids
    re-copying/re-reading a file that's already correctly referenced on an
    edit_preset call that round-tripped an unchanged granular oscillator
    through extract_spec."""
    existing_relative = granular_container.get("samplePathRelative")
    if not existing_relative:
        return None
    try:
        samples_dir = config.get_samples_dir()
    except config.SamplesFolderNotFoundError:
        return None
    existing_absolute = (samples_dir / existing_relative).resolve()
    try:
        incoming_absolute = Path(osc.granular_source).resolve()
    except (OSError, ValueError):
        return None
    if existing_absolute != incoming_absolute:
        return None
    num_frames = granular_container.get("numFrames")
    sample_rate = granular_container.get("sampleRate")
    num_channels = granular_container.get("numChannels")
    if not (isinstance(num_frames, int | float) and sample_rate and num_channels):
        return None
    return schema.SampleAudioDef(
        existing_relative, int(num_frames), int(sample_rate), int(num_channels)
    )


def _resolve_granular_playback(osc: OscillatorSpec) -> schema.SampleAudioDef:
    """Resolve an oscillator's ``granular_source`` into a
    :class:`schema.SampleAudioDef`, same mechanism as
    ``_resolve_sample_playback`` (GranularOsc's file-reference shape is
    structurally identical to SampleOsc's) -- copy the referenced WAV into
    Serum's Samples/User/serum-mcp folder and read its header metadata."""
    source_path = Path(osc.granular_source)
    if not source_path.is_file():
        raise ValueError(f"granular_source {osc.granular_source!r} does not exist")
    dest = sample_library.copy_sample_to_library(
        source_path, config.get_samples_dir(), _CUSTOM_SAMPLE_SUBDIR, center_pan=False
    )
    channels, sample_rate, num_frames = sample_library.read_wav_metadata(source_path)
    relative_path = "/".join((*_CUSTOM_SAMPLE_SUBDIR, dest.name))
    return schema.SampleAudioDef(relative_path, num_frames, sample_rate, channels)


def _unchanged_spectral_reference(
    spectral_container: dict[str, Any], osc: OscillatorSpec
) -> schema.SampleAudioDef | None:
    """Same fast path as ``_unchanged_granular_reference``, for
    ``osc.spectral_source`` against a ``SpectralOsc{i}`` container."""
    existing_relative = spectral_container.get("samplePathRelative")
    if not existing_relative:
        return None
    try:
        samples_dir = config.get_samples_dir()
    except config.SamplesFolderNotFoundError:
        return None
    existing_absolute = (samples_dir / existing_relative).resolve()
    try:
        incoming_absolute = Path(osc.spectral_source).resolve()
    except (OSError, ValueError):
        return None
    if existing_absolute != incoming_absolute:
        return None
    num_frames = spectral_container.get("numFrames")
    sample_rate = spectral_container.get("sampleRate")
    num_channels = spectral_container.get("numChannels")
    if not (isinstance(num_frames, int | float) and sample_rate and num_channels):
        return None
    return schema.SampleAudioDef(
        existing_relative, int(num_frames), int(sample_rate), int(num_channels)
    )


def _resolve_spectral_playback(osc: OscillatorSpec) -> schema.SampleAudioDef:
    """Resolve an oscillator's ``spectral_source`` into a
    :class:`schema.SampleAudioDef`, same mechanism as
    ``_resolve_granular_playback`` (SpectralOsc's file-reference shape is
    also structurally identical to SampleOsc's)."""
    source_path = Path(osc.spectral_source)
    if not source_path.is_file():
        raise ValueError(f"spectral_source {osc.spectral_source!r} does not exist")
    dest = sample_library.copy_sample_to_library(
        source_path, config.get_samples_dir(), _CUSTOM_SAMPLE_SUBDIR, center_pan=False
    )
    channels, sample_rate, num_frames = sample_library.read_wav_metadata(source_path)
    relative_path = "/".join((*_CUSTOM_SAMPLE_SUBDIR, dest.name))
    return schema.SampleAudioDef(relative_path, num_frames, sample_rate, channels)


def _resolve_wavetable(osc: OscillatorSpec) -> schema.WavetableDef:
    """Resolve an oscillator's wavetable: a curated factory table
    (schema.SIMPLE_WAVETABLES), a table synthesized from ``custom_harmonics``,
    or one sliced from a user audio file via ``sample_source`` -- in that
    priority order -- written to Serum's Tables/User folder as needed."""
    if osc.sample_source:
        source_path = Path(osc.sample_source)
        if not source_path.is_file():
            raise ValueError(f"sample_source {osc.sample_source!r} does not exist")
        if osc.sample_frames > _MAX_CUSTOM_WAVETABLE_FRAMES:
            raise ValueError(
                f"sample_frames is {osc.sample_frames}; max is {_MAX_CUSTOM_WAVETABLE_FRAMES}"
            )
        filename = wavetable.sample_wavetable_filename(source_path, osc.sample_frames)
        dest = config.get_tables_dir().joinpath(*_CUSTOM_WAVETABLE_SUBDIR, filename)
        if not dest.exists():
            samples, sample_rate = wavetable.read_wav_mono(source_path)
            frames = wavetable.slice_sample_to_frames(samples, sample_rate, osc.sample_frames)
            wavetable.write_wavetable_wav(dest, frames)
        relative_path = "/".join((*_CUSTOM_WAVETABLE_SUBDIR, filename))
        num_frames = osc.sample_frames * wavetable.FRAME_SIZE
        return schema.WavetableDef(relative_path, num_frames, wavetable.SAMPLE_RATE, 1)

    if osc.custom_harmonics:
        frames_harmonics = osc.custom_harmonics
        if len(frames_harmonics) > _MAX_CUSTOM_WAVETABLE_FRAMES:
            raise ValueError(
                f"custom_harmonics has {len(frames_harmonics)} frames; "
                f"max is {_MAX_CUSTOM_WAVETABLE_FRAMES}"
            )
        filename = wavetable.wavetable_filename(frames_harmonics)
        dest = config.get_tables_dir().joinpath(*_CUSTOM_WAVETABLE_SUBDIR, filename)
        if not dest.exists():
            frames = [wavetable.synthesize_frame(h) for h in frames_harmonics]
            wavetable.write_wavetable_wav(dest, frames)
        relative_path = "/".join((*_CUSTOM_WAVETABLE_SUBDIR, filename))
        num_frames = len(frames_harmonics) * wavetable.FRAME_SIZE
        return schema.WavetableDef(relative_path, num_frames, wavetable.SAMPLE_RATE, 1)

    wt_def = schema.SIMPLE_WAVETABLES.get(osc.wavetable)
    if wt_def is not None:
        return wt_def

    # Not one of the curated names -- found live editing real third-party/
    # Factory presets (up to 56% of a real 844-preset sample): extract_spec
    # reports a non-curated table as its raw relativePathToWT (e.g. "S2
    # Tables/Analog/Saw Drift 303.wav", a real Serum 2 factory table, not
    # anything exotic), and re-submitting that value unchanged -- needed
    # just to preserve a LATER oscillator's position in the list, even when
    # that earlier oscillator isn't the one actually being edited -- used to
    # always fail here. Try it as a real relative path under Tables/ instead
    # of assuming it's a typo'd curated name: this is the same "read the
    # real file's header" approach sample_library.read_wav_metadata already
    # uses for sample_playback_source, just against Tables/ instead of
    # Samples/.
    # Some real Factory tables are referenced with a LEADING slash (e.g.
    # "/Analog/Basic Shapes.wav", confirmed live in Factory\Bass\808\808 -
    # Drill.SerumPreset's raw CBOR -- genuine Serum data, not a bug in this
    # file). pathlib's `/` operator treats a leading-slash right operand as
    # anchored to the drive root and silently DISCARDS the left side --
    # `Path("C:/Tables") / "/Analog/x.wav"` produces "C:/Analog/x.wav", not
    # "C:/Tables/Analog/x.wav" -- so the naive join below would resolve to
    # the wrong location and always report "file not found" for these.
    candidate = config.get_tables_dir() / osc.wavetable.lstrip("/\\")
    if candidate.is_file():
        channels, sample_rate, num_frames = sample_library.read_wav_metadata(candidate)
        return schema.WavetableDef(osc.wavetable, num_frames, sample_rate, channels)

    raise ValueError(
        f"unknown wavetable {osc.wavetable!r}: not one of the curated names "
        f"({sorted(schema.SIMPLE_WAVETABLES)}), and no file found at {candidate} either"
    )


def _resolve_arp_shape(shape: str) -> str:
    """Resolve a friendly ``SIMPLE_ARP_SHAPES`` name to its raw Serum enum
    value, or pass an already-raw value through unchanged if it's not in
    the curated set -- same fallback pattern as filter types/wavetables,
    needed so a round-tripped edit of a preset using a shape outside the
    curated list (the real enum is confirmed larger, see schema.py) doesn't
    fail. 'pattern' is rejected here too (checked case-insensitively) as a
    safety net for ``ArpSpec.transpose_shape`` -- the main ``shape`` field's
    pattern-vs-algorithmic branching happens one level up in ``apply_spec``,
    which has access to ``arp.pattern`` to build real note data; this
    function alone has no way to write that, so it must never silently
    write the raw 'Pattern' string for a lane that has no note data behind
    it."""
    if shape.lower() == "pattern":
        raise ValueError(
            "arp shape 'pattern' needs real note-by-note clip data this project "
            "doesn't generate yet -- use one of the algorithmic shapes instead: "
            f"{sorted(schema.SIMPLE_ARP_SHAPES)}"
        )
    return schema.SIMPLE_ARP_SHAPES.get(shape, shape)


# 7 of these 8 values were constant across all 1507 real Pattern-mode notes
# surveyed (Factory + 6 third-party banks); only index 6 showed real
# variation whose meaning isn't decoded (index 7's precise value, 64/127,
# suggests a MIDI-CC-style 0-127 range normalized to 0..1 with 64 as a
# "centered" default -- consistent with several of these being per-note
# expression lanes left untouched). Not exposed as configurable in
# ArpPatternNoteSpec yet -- every generated note uses this same vector.
_DEFAULT_ARP_NOTE_ATTRIBUTES: tuple[float, ...] = (
    0.5,
    1.0,
    0.0,
    0.0,
    0.0,
    0.5,
    0.0,
    0.5039370078740157,
)


def _build_arp_clip(arp: ArpSpec) -> dict[str, Any]:
    """Build the ``ArpClip0.clip`` dict for ``shape='pattern'``: a real
    note list on a quantized step grid (see ``ArpPatternNoteSpec`` -- the
    real format supports free timestamps, this project only generates a
    grid-quantized subset of it).

    Deliberately does NOT write ``regionEndBeats``, despite it being
    present in 81% of real Pattern clips surveyed -- found live: a real,
    directly-confirmed-working Factory preset's ArpClip0 (ARP - Acid101)
    omits it entirely, and a generated preset that included it (computed
    as the pattern's own last note-end time) failed to arpeggiate at all
    in real Serum, while an otherwise-identical preset with that same real
    ArpClip0 grafted in worked. Not fully isolated from the kParamDotted/
    kParamTriplets fix made at the same time (see apply_spec), but omitting
    it matches the one directly-verified-working example, so there's no
    reason to keep it as an unverified guess."""
    notes = []
    for note in arp.pattern:
        time_stamp = note.step * arp.pattern_step_beats
        length = note.length_steps * arp.pattern_step_beats
        notes.append(
            {
                "noteNum": note.note_offset,
                "timeStamp": time_stamp,
                "length": length,
                "channel": 0,
                "attributes": list(_DEFAULT_ARP_NOTE_ATTRIBUTES),
                "expressionEvents": [None] * 5,
            }
        )
    notes.sort(key=lambda n: n["timeStamp"])
    return {"notes": notes}


def _build_lfo_curve_data(curve: list[LfoCurvePointSpec], *, lfo_index: int) -> dict[str, Any]:
    """Convert ``LfoSpec.curve`` (natural y, 0=bottom/1=top) into Serum's own
    raw ``curveData`` storage (Y-axis INVERTED: 0=top, 1=bottom) -- see
    ``LfoCurvePointSpec``'s docstring and docs/PARAMETER_SCHEMA.md item 4
    for the ground-truth-calibration story behind this inversion.

    Enforces the invariants a 3051-sample real-corpus survey found
    (``xVals[0] == 0.0``, ``xVals[-1] == 1.0``, non-decreasing) and a
    real, confirmed Serum-side rendering bug for exactly-2-point curves
    (a curve whose 2nd point is LOWER than its 1st -- i.e. Serum's own
    inverted storage ends up ASCENDING -- renders as a blank/inert graph;
    only descending-in-storage-terms, i.e. rising-in-natural-terms, 2-point
    curves work). Raises rather than silently shipping a preset that loads
    fine but renders as a dead flat/default LFO.

    NON-decreasing, not strictly increasing: found live 2026-08-01
    recreating a real preset (Galaxy) that this project's own docstring
    once called an edge case (99.7% of a 3051-sample survey are strictly
    increasing) -- a DUPLICATE x is a real, deliberate construct, not
    corruption: two points at the same x with different y draws an
    instant vertical step (used to build a stepped/square-ish shape from
    otherwise-flat segments). Only truly out-of-order x (going backwards)
    is rejected.
    """
    if len(curve) < 2:
        raise ValueError(f"LFO{lfo_index}.curve needs at least 2 points, got {len(curve)}")
    if curve[0].x != 0.0:
        raise ValueError(f"LFO{lfo_index}.curve[0].x must be 0.0, got {curve[0].x}")
    if curve[-1].x != 1.0:
        raise ValueError(f"LFO{lfo_index}.curve[-1].x must be 1.0, got {curve[-1].x}")
    for prev, nxt in zip(curve, curve[1:]):
        if nxt.x < prev.x:
            raise ValueError(
                f"LFO{lfo_index}.curve x values must be non-decreasing, "
                f"got {prev.x} then {nxt.x}"
            )
    if len(curve) == 2 and curve[1].y <= curve[0].y:
        raise ValueError(
            f"LFO{lfo_index}.curve: a 2-point curve must be RISING (curve[1].y > "
            f"curve[0].y) -- a falling 2-point curve is a confirmed Serum rendering "
            "bug (renders as a blank/inert graph, see docs/PARAMETER_SCHEMA.md item "
            "4). Add a 3rd point (even a redundant midpoint) for a falling shape."
        )

    return {
        "numPoints": len(curve) - 1,
        "xVals": [p.x for p in curve],
        "yVals": [1.0 - p.y for p in curve],
        "curveVals": [p.tension for p in curve],
    }


def _build_fx_entry(fx: FxUnitSpec) -> dict[str, Any]:
    fx_module_key = fx.type
    if fx_module_key not in schema.FX_PARAMS:
        raise ValueError(f"unknown FX type {fx.type!r}; expected one of {sorted(schema.FX_PARAMS)}")
    fx_schema = schema.FX_PARAMS[fx_module_key]
    # Not every FX type has a wet/mix knob (FXEQ doesn't) -- forcing one in
    # unconditionally made FXEQ impossible to generate at all.
    plain_params: dict[str, Any] = {}
    if "kParamWet" in fx_schema and fx.wet != 100.0:
        # Found live 2026-07-29 tracking down a persistent "distorted/
        # saturated" character on an isolated oscillator: across all 11 FX
        # units in a real preset, kParamWet was ABSENT whenever it would be
        # 100 (fully wet) and explicit ONLY for other values (60.4, 0, 0) --
        # a 100% consistent pattern, not per-type. Writing an explicit
        # kParamWet=100.0 (mathematically "the same") audibly differed from
        # leaving it out -- Serum likely skips the wet/dry crossfade stage
        # entirely when the key is absent, vs. actually running a 100/0 mix
        # when it's explicitly present, which apparently isn't fully
        # transparent. Each FX_PARAMS type's own `kParamWet` default (e.g.
        # FXDelay's 30.0) is what's typically OBSERVED when present, not
        # confirmed as this true absent-state value -- 100.0 is.
        plain_params["kParamWet"] = fx.wet
    plain_params.update(fx.params)
    # allow_unknown=True: fx.params often isn't calling-model-authored from
    # scratch -- the normal edit_preset flow for fx_chain (whole-list
    # replace, no per-unit patch) is read the current chain via
    # extract_spec/describe_preset, tweak one thing, resubmit the lot, so
    # fx.params can legitimately carry real, uncatalogued params straight
    # through from a third-party file's plainParams (found live: FXEQ's
    # kParamType1, FXDelay's kParamBW, neither in FX_PARAMS). Same reasoning
    # as _plain_params's docstring.
    validate_params(fx_module_key, plain_params, fx_schema, allow_unknown=True)

    type_id = next(i for i, name in schema.FX_TYPE_IDS.items() if name == fx_module_key)
    entry: dict[str, Any] = {
        "type": type_id,
        "kUIParamMixOrGain": 0.0,
        fx_module_key: {"plainParams": plain_params},
    }
    if fx.flex is not None:
        # Opaque passthrough -- see FxUnitSpec.flex's docstring. Written
        # verbatim, no interpretation/validation of the curve shape itself
        # (unlike LfoSpec.curve, this format's semantics for FX units
        # aren't independently confirmed).
        entry["flex"] = fx.flex
    return entry


def _fx_dest_module_id(fx_chain: list[FxUnitSpec], index: int) -> int:
    """Serum encodes an FX unit's ``destModuleID`` (for mod-matrix routing)
    as ``rack * 100 + position_within_that_rack`` -- confirmed live
    2026-07-29 against a real preset with units in rack 1 (e.g. an FXBode at
    rack-1 position 4 had destModuleID 104). ``index`` is the unit's
    position in the flat ``fx_chain`` list (spans all racks); this counts
    how many earlier entries share its rack to get the position within that
    specific rack."""
    rack = fx_chain[index].rack
    position_in_rack = sum(1 for fx in fx_chain[:index] if fx.rack == rack)
    return rack * 100 + position_in_rack


def _resolve_mod_destination(destination: str, fx_chain: list[FxUnitSpec]) -> schema.ModDestDef:
    """Resolve a mod-matrix destination name.

    Most destinations are static (fixed module type + slot index), looked
    up directly in ``schema.MOD_DEST_TARGETS``. FX destinations are the
    exception: an FX rack slot's ``destModuleTypeString`` is whichever FX
    type actually sits there (e.g. "FXReverb"), which is only known once
    ``fx_chain`` has been built -- so ``fx{i}.wet`` is resolved dynamically
    against ``fx_chain[i]`` instead of being a fixed table entry.
    """
    if destination in schema.MOD_DEST_TARGETS:
        return schema.MOD_DEST_TARGETS[destination]

    if destination.startswith("fx") and destination.endswith(".wet"):
        index_part = destination[len("fx") : -len(".wet")]
        if index_part.isdigit():
            index = int(index_part)
            if index >= len(fx_chain):
                raise ValueError(
                    f"mod destination {destination!r} references fx_chain[{index}], "
                    f"but fx_chain only has {len(fx_chain)} entries"
                )
            fx_type = fx_chain[index].type
            if fx_type not in schema.FX_PARAMS or "kParamWet" not in schema.FX_PARAMS[fx_type]:
                raise ValueError(f"{fx_type!r} (fx_chain[{index}]) has no kParamWet to modulate")
            # kParamWet -> destModuleParamID 1 is confirmed for every FX
            # type that has a wet knob at all (see docs/PARAMETER_SCHEMA.md).
            return schema.ModDestDef(fx_type, _fx_dest_module_id(fx_chain, index), "kParamWet", 1)

    if destination.startswith("fx") and "." in destination:
        index_part, _, suffix = destination[len("fx") :].partition(".")
        if index_part.isdigit():
            index = int(index_part)
            if index >= len(fx_chain):
                raise ValueError(
                    f"mod destination {destination!r} references fx_chain[{index}], "
                    f"but fx_chain only has {len(fx_chain)} entries"
                )
            fx_type = fx_chain[index].type
            extra = schema.FX_EXTRA_MOD_DEST_PARAMS.get(fx_type, {}).get(suffix)
            if extra is not None:
                param_name, param_id = extra
                return schema.ModDestDef(
                    fx_type, _fx_dest_module_id(fx_chain, index), param_name, param_id
                )

    raise ValueError(
        f"unknown mod destination {destination!r}; expected one of "
        f"{sorted(schema.MOD_DEST_TARGETS)}, 'fx{{i}}.wet', or one of "
        f"{sorted({s for d in schema.FX_EXTRA_MOD_DEST_PARAMS.values() for s in d})} "
        "for an FX type that supports it"
    )


def _resolve_source_id(name: str, *, field_label: str) -> int:
    if name not in schema.MOD_SOURCE_IDS:
        raise ValueError(
            f"unknown {field_label} {name!r}; expected one of {sorted(schema.MOD_SOURCE_IDS)}"
        )
    return schema.MOD_SOURCE_IDS[name]


def _resolve_route_source(route: ModRouteSpec) -> int:
    return _resolve_source_id(route.source, field_label="mod source")


def _build_modslot_entry(
    route: ModRouteSpec,
    fx_chain: list[FxUnitSpec],
    existing_plain_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build (or update in place) one ModSlot entry. When
    ``existing_plain_params`` is given (this route is reusing an already-
    matching slot, see ``_find_existing_modslot_index``), merge onto it
    rather than replacing wholesale -- found live 2026-07-30 via a VST3
    binary string dump revealing ModSlot's full private param list
    (kParamSmoothRise/Fall/Link, kParamDelayOffset/BeatSync, kParamAuxCurve/
    AuxCurveData, kParamBypass, kParamCurveIn, kParamMainCurveData -- none
    previously known to this project, none exposed via ModRouteSpec): a
    real-corpus survey found these present on 0.04-3.2% of real mod routes,
    rare but real. Building the dict fresh (the old behavior) silently
    discarded any of these on a route being edited in place, even for an
    edit_preset call that only meant to nudge that route's amount."""
    source_id = _resolve_route_source(route)
    dest = _resolve_mod_destination(route.destination, fx_chain)
    # source[1] (subIndex) is a SECOND, independent source id from the SAME
    # MOD_SOURCE_IDS space -- Serum's "Aux"/"Via" system, decoded 2026-07-30
    # via a 626-preset corpus survey: 1276 real routes across nearly every
    # source family pair a primary source with an aux one that scales/gates
    # it (e.g. "LFO1 -> pitch" scaled by mod_wheel or aftertouch for
    # expressive vibrato -- by far the two most common aux picks). Originally
    # discovered narrowly on "Fixed" (id 38) routes specifically and assumed
    # to be a special case (subIndex = 25 + macro_index); this survey showed
    # that was just the first example found, not the whole mechanism -- ANY
    # source can be an aux source for ANY primary source, using the exact
    # same ids as MOD_SOURCE_IDS. 0 (no valid source has this id) is the
    # "no aux" sentinel. See docs/PARAMETER_SCHEMA.md item 14.
    aux_source_id = 0
    if route.aux_source is not None:
        aux_source_id = _resolve_source_id(route.aux_source, field_label="mod aux_source")
    plain_params: dict[str, Any] = dict(existing_plain_params or {})
    plain_params["kParamAmount"] = route.amount
    plain_params.pop("kParamBipolar", None)
    if route.bipolar:
        plain_params["kParamBipolar"] = True
    plain_params.pop("kParamAuxInverted", None)
    if route.aux_inverted:
        plain_params["kParamAuxInverted"] = True
    validate_params("ModSlot", plain_params, schema.MODSLOT_PARAMS, allow_unknown=True)

    return {
        "source": [source_id, aux_source_id],
        "destModuleID": dest.dest_id,
        "destModuleParamID": dest.param_id,
        "destModuleParamName": dest.param_name,
        "destModuleTypeString": dest.dest_type,
        "plainParams": plain_params,
    }


def _find_existing_modslot_index(
    data: dict[str, Any], source_id: int, dest: schema.ModDestDef
) -> int | None:
    """Find a ModSlot already routing from ``source_id`` to ``dest``, so an
    edit_preset call that updates that route's amount/bipolar overwrites it
    in place instead of accumulating a second, additive route in a
    different slot -- found live: editing a route's amount on an
    already-generated preset left both the old and new route active,
    silently doubling up the modulation."""
    for key, entry in data.items():
        if not (
            isinstance(key, str) and key.startswith("ModSlot") and key[len("ModSlot") :].isdigit()
        ):
            continue
        if not isinstance(entry, dict):
            continue
        src = entry.get("source")
        if not (isinstance(src, list) and len(src) == 2 and src[0] == source_id):
            continue
        if (
            entry.get("destModuleTypeString") == dest.dest_type
            and entry.get("destModuleID") == dest.dest_id
            and entry.get("destModuleParamName") == dest.param_name
        ):
            return int(key[len("ModSlot") :])
    return None


def _resolve_modslot_indices(
    data: dict[str, Any], routes: list[ModRouteSpec], fx_chain: list[FxUnitSpec]
) -> list[int]:
    """Assign a ModSlot index to each route in ``routes``: reuse an
    existing slot already routing the same (source, destination) pair if
    one exists, otherwise allocate a free slot (see
    ``_find_existing_modslot_index``)."""
    assignments: list[int | None] = []
    for route in routes:
        source_id = _resolve_route_source(route)
        dest = _resolve_mod_destination(route.destination, fx_chain)
        assignments.append(_find_existing_modslot_index(data, source_id, dest))

    free = iter(_free_modslot_indices(data, assignments.count(None)))
    return [idx if idx is not None else next(free) for idx in assignments]


def _free_modslot_indices(data: dict[str, Any], count: int) -> list[int]:
    used = {
        int(k[len("ModSlot") :])
        for k in data
        if isinstance(k, str) and k.startswith("ModSlot") and k[len("ModSlot") :].isdigit()
    }
    free = [i for i in range(64) if i not in used]
    if len(free) < count:
        raise ValueError(
            f"not enough free mod matrix slots: need {count}, only {len(free)} of 64 free"
        )
    return free[:count]


def apply_spec(base_data: dict[str, Any], spec: PresetSpec) -> dict[str, Any]:
    """Return a new raw ``data`` dict with ``spec`` merged onto ``base_data``."""
    data = copy.deepcopy(base_data)

    # Oscillator's own plainParams live directly on the Oscillator{i} dict,
    # not nested -- handled separately from the generic _plain_params helper
    # (which is for the sub-modules keyed *inside* Oscillator{i}, e.g. WTOsc{i}).
    for i, osc in enumerate(spec.oscillators):
        osc_container = data.setdefault(f"Oscillator{i}", {})
        if not isinstance(osc_container.get("plainParams"), dict):
            osc_container["plainParams"] = {}
        osc_params = osc_container["plainParams"]
        osc_params["kParamEnable"] = osc.enabled
        for spec_key, param_key in _OSC_KEYS.items():
            value = getattr(osc, spec_key)
            if param_key in _OSC_KEYS_OMIT_AT_DEFAULT and value == _OSC_KEYS_OMIT_AT_DEFAULT[param_key]:
                continue
            osc_params[param_key] = value

        if i in _WTOSC_SLOTS:
            if osc.sample_playback_source:
                # kParamType is written explicitly on every call (not just
                # when switching TO sample playback) so a later partial edit
                # that switches this slot back to WT can't leave a stale
                # kOsc_Sample selector behind -- the same staleness risk
                # class documented on schema.OSCILLATOR_PARAMS["kParamType"].
                osc_params["kParamType"] = _ENGINE_TYPE_SAMPLE

                sample_key = f"SampleOsc{i}"
                sample_container = osc_container.setdefault(sample_key, {})
                sample_def = _unchanged_sample_reference(
                    sample_container, osc
                ) or _resolve_sample_playback(osc)
                # File metadata, not a plainParams knob -- must match the
                # referenced audio file exactly or Serum may misread it (same
                # risk class as the CBOR bool/int wire-type bugs, see
                # docs/PARAMETER_SCHEMA.md).
                sample_container["samplePathRelative"] = sample_def.relative_path
                sample_container["numFrames"] = sample_def.num_frames
                sample_container["sampleRate"] = sample_def.sample_rate
                sample_container["numChannels"] = sample_def.num_channels

                sample_params = _plain_params(osc_container, sample_key)
                for spec_key, param_key in _SAMPLEOSC_KEYS.items():
                    sample_params[param_key] = getattr(osc, spec_key)
                sample_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                validate_params(sample_key, sample_params, schema.SAMPLEOSC_PARAMS, allow_unknown=True)

                if osc.sample_loop != "off":
                    loop_mode = schema.SIMPLE_SAMPLE_LOOP_MODES.get(osc.sample_loop)
                    if loop_mode is None:
                        raise ValueError(
                            f"unknown sample_loop {osc.sample_loop!r}; expected 'off' or "
                            f"one of {sorted(schema.SIMPLE_SAMPLE_LOOP_MODES)}"
                        )
                    osc_params["kParamLoopMode"] = loop_mode
                    osc_params["kParamLoopStart"] = osc.sample_loop_start
                    osc_params["kParamLoopEnd"] = osc.sample_loop_end
                    osc_params["kParamLoopCrossfade"] = osc.sample_loop_crossfade
            elif osc.granular_source:
                # kParamType written explicitly every call, same staleness
                # reasoning as the kOsc_Sample branch above.
                osc_params["kParamType"] = _ENGINE_TYPE_GRANULAR

                granular_key = f"GranularOsc{i}"
                granular_container = osc_container.setdefault(granular_key, {})
                granular_def = _unchanged_granular_reference(
                    granular_container, osc
                ) or _resolve_granular_playback(osc)
                granular_container["samplePathRelative"] = granular_def.relative_path
                granular_container["numFrames"] = granular_def.num_frames
                granular_container["sampleRate"] = granular_def.sample_rate
                granular_container["numChannels"] = granular_def.num_channels

                granular_params = _plain_params(osc_container, granular_key)
                for spec_key, param_key in _GRANULAROSC_KEYS.items():
                    granular_params[param_key] = getattr(osc, spec_key)
                granular_params["kParamDensity"] = (
                    osc.granular_density**4 / schema.GRANULAR_DENSITY_CURVE_DIVISOR
                )
                granular_params["kParamGrainLength"] = (
                    osc.granular_grain_length / schema.GRANULAR_GRAIN_LENGTH_DIVISOR
                )
                granular_params["kParamWarp"] = osc.warp_amount
                granular_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                validate_params(
                    granular_key, granular_params, schema.GRANULAROSC_PARAMS, allow_unknown=True
                )
            elif osc.spectral_source:
                # kParamType written explicitly every call, same staleness
                # reasoning as the kOsc_Sample branch above.
                osc_params["kParamType"] = _ENGINE_TYPE_SPECTRAL

                spectral_key = f"SpectralOsc{i}"
                spectral_container = osc_container.setdefault(spectral_key, {})
                spectral_def = _unchanged_spectral_reference(
                    spectral_container, osc
                ) or _resolve_spectral_playback(osc)
                spectral_container["samplePathRelative"] = spectral_def.relative_path
                spectral_container["numFrames"] = spectral_def.num_frames
                spectral_container["sampleRate"] = spectral_def.sample_rate
                spectral_container["numChannels"] = spectral_def.num_channels
                # Not just left absent: 24/25 real SpectralOsc instances with
                # no custom spectral-filter curve use this EXACT flat/neutral
                # sentinel (a genuinely canonical value, not just "close
                # enough"), confirmed 2026-07-30 via a corpus survey.
                # Whether Serum tolerates a genuinely ABSENT `flex` key was
                # never tested -- writing the real content's own convention
                # avoids that unverified risk (same reasoning as every other
                # "match the real absent/neutral state exactly" finding in
                # this project). Curve GENERATION (a real, non-flat shape)
                # isn't implemented yet -- see docs/PARAMETER_SCHEMA.md item 4.
                if not isinstance(spectral_container.get("flex"), dict):
                    spectral_container["flex"] = {
                        "numPoints": 1,
                        "xVals": [0.0, 1.0],
                        "yVals": [0.5, 0.5],
                        "curveVals": [0.5, 0.5],
                    }

                spectral_params = _plain_params(osc_container, spectral_key)
                for spec_key, param_key in _SPECTRALOSC_KEYS.items():
                    spectral_params[param_key] = getattr(osc, spec_key)
                spectral_params["kParamWarp"] = osc.warp_amount
                spectral_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                validate_params(
                    spectral_key, spectral_params, schema.SPECTRALOSC_PARAMS, allow_unknown=True
                )
            elif osc.multisample_source:
                if osc.multisample_source not in schema.MULTISAMPLE_INSTRUMENTS:
                    raise ValueError(
                        f"unknown multisample_source {osc.multisample_source!r}; expected "
                        f"one of {sorted(schema.MULTISAMPLE_INSTRUMENTS)}"
                    )
                # kParamType written explicitly every call, same staleness
                # reasoning as the kOsc_Sample branch above.
                osc_params["kParamType"] = _ENGINE_TYPE_MULTISAMPLE

                instrument = schema.MULTISAMPLE_INSTRUMENTS[osc.multisample_source]
                multisample_key = f"MultiSampleOsc{i}"
                multisample_container = osc_container.setdefault(multisample_key, {})
                # No file to copy/resolve -- embedded_sfz/files are curated,
                # fixed real-Factory-instrument data, confirmed byte-identical
                # across every real preset referencing the same instrument
                # (see schema.MultiSampleInstrumentDef's docstring). Written
                # verbatim every call, same "always write explicitly, don't
                # trust a stale value surviving an engine switch" reasoning
                # as every other file-reference engine above.
                multisample_container["sfzPathRelative"] = instrument.sfz_path_relative
                multisample_container["embedded_sfz"] = instrument.embedded_sfz
                multisample_container["files"] = dict(instrument.files)

                multisample_params = _plain_params(osc_container, multisample_key)
                for spec_key, param_key in _MULTISAMPLEOSC_KEYS.items():
                    multisample_params[param_key] = getattr(osc, spec_key)
                multisample_params["kParamWarp"] = osc.warp_amount
                multisample_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                validate_params(
                    multisample_key,
                    multisample_params,
                    schema.MULTISAMPLEOSC_PARAMS,
                    allow_unknown=True,
                )
            else:
                osc_params["kParamType"] = _ENGINE_TYPE_WT

                wt_key = f"WTOsc{i}"
                wt_def = _resolve_wavetable(osc)
                wtosc_container = osc_container.setdefault(wt_key, {})
                # File metadata, not a plainParams knob -- must match the
                # referenced .wav exactly or Serum may misread the table (same
                # risk class as the CBOR bool/int wire-type bugs, see
                # docs/PARAMETER_SCHEMA.md). Real ints, not floats -- confirmed
                # against real Serum-saved presets.
                wtosc_container["relativePathToWT"] = wt_def.relative_path
                wtosc_container["numFrames"] = wt_def.num_frames
                wtosc_container["sampleRate"] = wt_def.sample_rate
                wtosc_container["numChannels"] = wt_def.num_channels

                wtosc_params = _plain_params(osc_container, wt_key)
                for spec_key, param_key in _WTOSC_KEYS.items():
                    wtosc_params[param_key] = getattr(osc, spec_key)
                wtosc_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                if osc.warp_mode2 is not None:
                    wtosc_params["kParamWarp2"] = osc.warp_amount2
                    wtosc_params["kParamWarpMenu2"] = schema.SIMPLE_WARP_MODES.get(
                        osc.warp_mode2, osc.warp_mode2
                    )
                    # Only ever observed at 1.0 across 46 real samples
                    # whenever a second warp lane is in use -- see
                    # schema.WTOSC_PARAMS["kParamXfadeMode"].
                    wtosc_params["kParamXfadeMode"] = 1.0
                if osc.warp_var2 is not None:
                    wtosc_params["kParamWarpVar2"] = osc.warp_var2
                validate_params(f"WTOsc{i}", wtosc_params, schema.WTOSC_PARAMS, allow_unknown=True)
        elif i == _NOISE_SLOT:
            noise_params = _plain_params(osc_container, f"NoiseOsc{i}")
            noise_params["kParamNoiseType"] = osc.noise_type
            validate_params(f"NoiseOsc{i}", noise_params, schema.NOISEOSC_PARAMS, allow_unknown=True)
        elif i == _SUB_SLOT:
            sub_params = _plain_params(osc_container, f"SubOsc{i}")
            if osc.sub_shape != "saw":
                # Same presence-forces-the-DSP-stage pattern as VoiceFilter/LFO
                # above, found live 2026-07-29 (UN_PLACES_BA_Beyond): a
                # real-corpus survey found kParamShape absent in EVERY single
                # one of 896 real SubOsc4 modules (0% presence, the most
                # extreme skew found this session) -- Serum's Sub is
                # essentially never touched away from its true default.
                # Explicitly writing "saw" (this field's own schema default)
                # gave the Sub layer harsh/piercing highs not present in the
                # real (untouched) preset. Only write this key at all when a
                # caller deliberately requests a non-default shape.
                sub_params["kParamShape"] = schema.SIMPLE_SUB_SHAPES.get(
                    osc.sub_shape, osc.sub_shape
                )
            validate_params(f"SubOsc{i}", sub_params, schema.SUBOSC_PARAMS, allow_unknown=True)
        validate_params(f"Oscillator{i}", osc_params, schema.OSCILLATOR_PARAMS, allow_unknown=True)

        if (
            osc.filter_routing is not None
            or osc.filter_balance is not None
            or osc.fx_bus1_send is not None
            or osc.fx_bus2_send is not None
        ):
            # RoutingSlot0-4 -- this oscillator's own INPUT routing choice
            # (distinct from RoutingSlot5/6, each filter's OWN output
            # routing, see FilterSpec.output_routing below). Only written
            # when explicitly requested; leaving all fields unset matches
            # Serum's real default (through the filters, kRoutingDestFilter,
            # no aux sends) without writing anything.
            routing_params: dict[str, Any] = {}
            if osc.filter_routing is not None:
                routing_params["kParamRoutingDest"] = {
                    "filter": "kRoutingDestFilter",
                    "master": "kRoutingDestMaster",
                    "direct": "kRoutingDestDirect",
                    "none": "kRoutingDestNone",
                }[osc.filter_routing]
            if osc.filter_balance is not None:
                routing_params["kParamFilterBalance"] = osc.filter_balance
            if osc.fx_bus1_send is not None:
                routing_params["kParamFXBus1Level"] = osc.fx_bus1_send
            if osc.fx_bus2_send is not None:
                routing_params["kParamFXBus2Level"] = osc.fx_bus2_send
            validate_params(
                f"RoutingSlot{i}", routing_params, schema.ROUTING_SLOT_PARAMS, allow_unknown=True
            )
            data.setdefault(f"RoutingSlot{i}", {})["plainParams"] = routing_params

    if (
        len(spec.filters) == 2
        and spec.filters[0].output_routing == "series"
        and spec.filters[1].output_routing == "series"
    ):
        raise ValueError(
            "filters[0].output_routing and filters[1].output_routing can't both be "
            "'series' -- each filter would cascade into the other, a routing cycle "
            "Serum has no defined behavior for. Set at most one filter to 'series'."
        )

    for i, flt in enumerate(spec.filters):
        filter_params = _plain_params(data, f"VoiceFilter{i}")
        filter_params["kParamEnable"] = flt.enabled
        filter_params["kParamKeyTrack"] = flt.key_track
        filter_params["kParamType"] = schema.SIMPLE_FILTER_TYPES.get(flt.type, flt.type)
        for spec_key, param_key in _FILTER_KEYS.items():
            value = getattr(flt, spec_key)
            if param_key in _FILTER_KEYS_OMIT_AT_DEFAULT and value == _FILTER_KEYS_OMIT_AT_DEFAULT[param_key]:
                # Presence, not just value, changes the sound: real presets
                # leave a filter param key out entirely whenever it was never
                # touched, and the untouched value happens to equal this
                # param's own documented default -- writing it explicitly
                # anyway (mathematically "the same") was measurably audible
                # in real Serum (2026-07-29, chasing UN_PLACES_PL_Dreams's
                # fuzzy/buzzy character then a separate loudness regression;
                # confirmed for wet/level_out/drive/stereo by ear, and for
                # resonance/var by the SAME absent-at-default pattern showing
                # up again on a second real preset, UN_PLACES_BA_Beyond,
                # 2026-07-29). Likely cause: Serum skips the relevant DSP
                # stage entirely when the key is absent, vs. actually
                # computing it at a "neutral" value when present.
                continue
            filter_params[param_key] = value
        validate_params(
            f"VoiceFilter{i}", filter_params, schema.VOICE_FILTER_PARAMS, allow_unknown=True
        )
        if (
            (flt.output_routing is not None or flt.fx_bus1_send is not None or flt.fx_bus2_send is not None)
            and i < 2
        ):
            # RoutingSlot5/RoutingSlot6 -- each filter's OWN output routing
            # (distinct from RoutingSlot0-4, the 5 oscillators' routing
            # INTO the filters). Found live 2026-07-29 recreating two real
            # presets that used opposite directions of this -- see
            # docs/PARAMETER_SCHEMA.md §5 items 11-12. Only written when
            # explicitly requested; leaving all fields unset matches Serum's
            # real default (parallel/kRoutingDestMaster, no aux sends)
            # without writing anything, now that fixtures/init_preset.
            # SerumPreset's own fixture bug (RoutingSlot5 stuck on the
            # cascade value) is fixed.
            filter_routing_params: dict[str, Any] = {}
            if flt.output_routing is not None:
                filter_routing_params["kParamRoutingDest"] = (
                    "kRoutingDestMaster" if flt.output_routing == "parallel" else "kRoutingDestFilter"
                )
            if flt.fx_bus1_send is not None:
                filter_routing_params["kParamFXBus1Level"] = flt.fx_bus1_send
            if flt.fx_bus2_send is not None:
                filter_routing_params["kParamFXBus2Level"] = flt.fx_bus2_send
            validate_params(
                f"RoutingSlot{5 + i}",
                filter_routing_params,
                schema.ROUTING_SLOT_PARAMS,
                allow_unknown=True,
            )
            data.setdefault(f"RoutingSlot{5 + i}", {})["plainParams"] = filter_routing_params

    for i, env in enumerate(spec.envelopes):
        env_params = _plain_params(data, f"Env{i}")
        for spec_key, param_key in _ENV_KEYS.items():
            value = getattr(env, spec_key)
            # kParamHold specifically: a 2504-slot corpus survey found it
            # present only 4% of the time (vs 37-52% for the other 4 ADSR
            # keys, too ambiguous to touch without more evidence) -- found
            # live 2026-08-01 recreating a real preset (Galaxy) whose
            # unused envelopes lacked it entirely.
            if param_key == "kParamHold" and value == 0.0:
                continue
            env_params[param_key] = value
        validate_params(f"Env{i}", env_params, schema.ENV_PARAMS, allow_unknown=True)

    for i, lfo in enumerate(spec.lfos):
        lfo_params = _plain_params(data, f"LFO{i}")
        if lfo.beat_sync is not None:
            lfo_params["kParamBeatSync"] = lfo.beat_sync
        # else: leave whatever's already there untouched (e.g. an
        # edit_preset call against an existing preset that already had this
        # set) -- same "don't write, don't delete" convention every other
        # omitted _LFO_KEYS entry follows via the `continue` below.
        for spec_key, param_key in _LFO_KEYS.items():
            if spec_key == "beat_sync":
                continue  # handled above -- 3-state, not a plain omit-at-default key
            value = getattr(lfo, spec_key)
            if param_key in _LFO_KEYS_OMIT_AT_DEFAULT and value == _LFO_KEYS_OMIT_AT_DEFAULT[param_key]:
                # Same presence-forces-the-DSP-stage pattern as the
                # VoiceFilter fix above. Found live 2026-07-29
                # (UN_PLACES_BA_Beyond): kParamRate=0.0 (LfoSpec's own
                # default) is a literal 0Hz freeze, not a neutral value --
                # the real LFO0 has neither kParamRate nor kParamBeatSync at
                # all, yet a user-provided screenshot (note held) showed it
                # visibly running in BPM-synced mode ("1/4" readout). A
                # follow-up real-corpus survey found the SAME overwhelming
                # absent-when-default skew on every other _LFO_KEYS entry
                # (kParamDelay 99%, kParamRise 96%, kParamMono 98%,
                # kParamSwing 99%, kParamDotted/kParamTriplets/kParamRate10x
                # 83-85% absent) -- generalized rather than fixed one at a
                # time. The exact Hz/BPM rate encoding remains undecoded
                # (LFO_PARAMS["kParamRate"]) -- omitting sidesteps needing
                # it, by letting Serum fall back to its own real default.
                continue
            lfo_params[param_key] = value
        lfo_params["kParamMode"] = lfo.mode
        if lfo.shape is not None:
            lfo_params["kParamType"] = schema.SIMPLE_LFO_TYPES.get(lfo.shape, lfo.shape)
        if lfo.curve is not None:
            lfo_container = data.setdefault(f"LFO{i}", {})
            lfo_container["curveData"] = _build_lfo_curve_data(lfo.curve, lfo_index=i)
            # Required alongside curveData or Serum silently ignores it and
            # shows "Default"/an empty graph instead -- found live
            # 2026-08-01 comparing a real preset's full raw LFO dict
            # against what this project was writing (see
            # docs/PARAMETER_SCHEMA.md item 4).
            lfo_container["curveDisplayName"] = "Custom"
            lfo_container.setdefault("pathData", {})
        validate_params(f"LFO{i}", lfo_params, schema.LFO_PARAMS, allow_unknown=True)

    for i, macro in enumerate(spec.macros):
        macro_container = data.setdefault(f"Macro{i}", {})
        if macro.name:
            macro_container["name"] = macro.name
        macro_params = _plain_params(data, f"Macro{i}")
        macro_params["kParamValue"] = macro.value
        validate_params(f"Macro{i}", macro_params, schema.MACRO_PARAMS, allow_unknown=True)

    if spec.fx_chain:
        # Group by rack (0-2) instead of always writing FXRack0 -- Serum can
        # run up to 3 FX racks in PARALLEL (found live 2026-07-29 in a real
        # preset with a second, independent chain including a reverb and a
        # bode shifter, entirely invisible to this project before that). A
        # rack with zero entries in spec.fx_chain is left untouched (not
        # cleared) -- most callers don't know rack 1/2 exist at all, and
        # silently wiping one just because an edit only mentioned rack 0
        # would be a surprising, hard-to-notice destructive side effect.
        by_rack: dict[int, list[FxUnitSpec]] = {}
        for fx in spec.fx_chain:
            by_rack.setdefault(fx.rack, []).append(fx)
        for rack, units in by_rack.items():
            fx_rack = data.setdefault(f"FXRack{rack}", {})
            fx_rack["FX"] = [_build_fx_entry(fx) for fx in units]

    if spec.mod_routes:
        indices = _resolve_modslot_indices(data, spec.mod_routes, spec.fx_chain)
        for idx, route in zip(indices, spec.mod_routes, strict=True):
            existing = data.get(f"ModSlot{idx}", {}).get("plainParams")
            existing = existing if isinstance(existing, dict) else None
            data[f"ModSlot{idx}"] = _build_modslot_entry(route, spec.fx_chain, existing)

    # Unlike oscillators/filters/envelopes/etc. (lists, only touched per
    # index when present), `global` is a single nested object that always
    # has a value -- PresetSpec() with no "global" key still gets a
    # default-valued GlobalSpec(). Without this check, every edit_preset
    # call that didn't explicitly repeat the current global settings would
    # silently reset them to defaults, breaking the "only change what you
    # specify" contract every other section honors.
    if "global_" in spec.model_fields_set:
        global_params = _plain_params(data, "Global0")
        # kParamMasterVolume stays always-explicit (91%/626 real presence,
        # see the survey below) -- the other 4 are majority-ABSENT in real
        # content, same "presence forces the DSP stage" pattern as every
        # other module in this file. Found live 2026-08-01 recreating a
        # real preset (Galaxy): its 6 untouched/default Global fields were
        # genuinely absent, but this project always wrote them explicitly
        # at the GlobalSpec schema default. A 626-preset corpus survey
        # confirmed the skew: kParamMonoToggle 33%, kParamPolyCount 31%,
        # kParamLimitSameNotePolyphony 27%, kParamPortamentoTime 19%
        # present (vs kParamMasterVolume's 91%).
        global_params["kParamMasterVolume"] = spec.global_.master_volume
        if spec.global_.mono is not False:
            global_params["kParamMonoToggle"] = spec.global_.mono
        if spec.global_.portamento_time != 0.0:
            global_params["kParamPortamentoTime"] = spec.global_.portamento_time
        if spec.global_.poly_count != 8.0:
            global_params["kParamPolyCount"] = spec.global_.poly_count
        if spec.global_.limit_same_note_polyphony is not False:
            global_params["kParamLimitSameNotePolyphony"] = spec.global_.limit_same_note_polyphony
        if spec.global_.fx_bus1_volume is not None:
            global_params["kParamFXBus1Vol"] = spec.global_.fx_bus1_volume
        if spec.global_.fx_bus2_volume is not None:
            global_params["kParamFXBus2Vol"] = spec.global_.fx_bus2_volume
        if spec.global_.direct_volume is not None:
            global_params["kParamDirectVol"] = spec.global_.direct_volume
        if spec.global_.fx_bus1_destination is not None:
            # Stored as a raw float ordinal in Global0 (1.0/2.0), NOT the
            # string enum RoutingSlot uses for the same meaning -- confirmed
            # against real Factory CBOR, see schema.GLOBAL_PARAMS['kParamFXBus1Dest'].
            global_params["kParamFXBus1Dest"] = (
                1.0 if spec.global_.fx_bus1_destination == "master" else 2.0
            )
        if spec.global_.fx_bus2_destination is not None:
            global_params["kParamFXBus2Dest"] = (
                1.0 if spec.global_.fx_bus2_destination == "master" else 2.0
            )
        if spec.global_.bend_range_up is not None:
            global_params["kParamBendRangeUp"] = spec.global_.bend_range_up
        if spec.global_.bend_range_down is not None:
            global_params["kParamBendRangeDn"] = spec.global_.bend_range_down
        if spec.global_.legato is not None:
            global_params["kParamLegato"] = spec.global_.legato
        if spec.global_.porta_always is not None:
            global_params["kParamPortaAlways"] = spec.global_.porta_always
        if spec.global_.porta_scaled is not None:
            global_params["kParamPortaScaled"] = spec.global_.porta_scaled
        if spec.global_.portamento_curve is not None:
            global_params["kParamPortamentoCurve"] = spec.global_.portamento_curve
        if spec.global_.swing is not None:
            global_params["kParamSwing"] = spec.global_.swing
        if spec.global_.swing_div is not None:
            global_params["kParamSwingDiv"] = spec.global_.swing_div
        if spec.global_.transpose is not None:
            global_params["kParamTranspose"] = spec.global_.transpose
        if spec.global_.global_tuning is not None:
            global_params["kParamGlobalTuning"] = spec.global_.global_tuning
        if spec.global_.oversampling is not None:
            global_params["kParamOversampling"] = spec.global_.oversampling
        if spec.global_.s1_compatibility is not None:
            global_params["kParamS1Compatibility"] = spec.global_.s1_compatibility
        if spec.global_.use_ultra_on_render is not None:
            global_params["kParamUseUltraOnRender"] = spec.global_.use_ultra_on_render
        if spec.global_.note_latch is not None:
            global_params["kParamNoteLatch"] = spec.global_.note_latch
        if spec.global_.voice_amp is not None:
            global_params["kParamVoiceAmp"] = spec.global_.voice_amp
        validate_params("Global0", global_params, schema.GLOBAL_PARAMS, allow_unknown=True)
        # kParamVoicePriority has no GLOBAL_PARAMS entry (see the schema.py
        # comment above it, same reasoning as ARPCLIP_PARAMS's uncatalogued
        # string-enum fields) -- written after validation so it's never
        # typechecked against an incomplete enum guess.
        if spec.global_.voice_priority is not None:
            global_params["kParamVoicePriority"] = spec.global_.voice_priority

    # Like `global`, arp is a single nested object (not a list), and unset
    # (spec.arp is None, the default) must leave Arp0/ArpClip0 completely
    # untouched -- ArpSpec's own default (enabled=True) exists for when the
    # caller DOES provide one, not to imply "no arp key present" means
    # "turn the arp on."
    if spec.arp is not None:
        arp = spec.arp
        arp_params = _plain_params(data, "Arp0")
        arp_params["kParamEnabled"] = arp.enabled
        if arp.key_zone_min is not None:
            arp_params["kParamKeyZoneMin"] = arp.key_zone_min
        if arp.key_zone_max is not None:
            arp_params["kParamKeyZoneMax"] = arp.key_zone_max
        if arp.midi_select_octave is not None:
            arp_params["kParamMidiSelectOctave"] = arp.midi_select_octave
        validate_params("Arp0", arp_params, schema.ARP_PARAMS, allow_unknown=True)

        clip_key = "ArpClip0"
        clip_container = data.setdefault(clip_key, {})
        clip_params = _plain_params(data, clip_key)

        is_pattern_shape = arp.shape.lower() == "pattern"
        if is_pattern_shape and not arp.pattern:
            raise ValueError(
                "arp.shape='pattern' needs arp.pattern set with real note data -- "
                "use one of the algorithmic shapes instead, or provide arp.pattern."
            )
        if arp.pattern and not is_pattern_shape:
            raise ValueError(
                "arp.pattern is set but arp.shape is not 'pattern' -- set "
                "shape='pattern' explicitly to use a custom pattern."
            )

        if arp.pattern:
            # kParamShape must be the exact raw "Pattern" string here (not run
            # through _resolve_arp_shape's friendly-name lookup) since it's
            # matched case-insensitively above and SIMPLE_ARP_SHAPES doesn't
            # curate it (see ArpSpec).
            clip_params["kParamShape"] = "Pattern"
            clip_container["clip"] = _build_arp_clip(arp)
            # Present in every real working Pattern-mode configuration found
            # during diagnosis (see schema.ARPCLIP_PARAMS's kParamNoteRetrig/
            # kParamWrapRange/kParamWrapTranspose notes) -- none individually
            # proven necessary (kParamRate, written below via the normal
            # arp.rate field, was the field actually isolated as the real
            # fix for a live "stuck on one note" bug), but consistent with
            # every working example and never observed to cause harm.
            clip_params["kParamNoteRetrig"] = arp.note_retrig if arp.note_retrig is not None else True
            clip_params["kParamWrapRange"] = arp.wrap_range if arp.wrap_range is not None else 12.0
            clip_params["kParamWrapTranspose"] = True
        else:
            clip_params["kParamShape"] = _resolve_arp_shape(arp.shape)
            # Always explicitly reset to {} (not just "if missing") -- an
            # edit_preset call switching this preset's arp AWAY from a
            # previous Pattern-mode note list must not leave stale notes
            # behind now that kParamShape no longer says "Pattern".
            clip_container["clip"] = {}
            if arp.note_retrig is not None:
                clip_params["kParamNoteRetrig"] = arp.note_retrig
            if arp.wrap_range is not None:
                clip_params["kParamWrapRange"] = arp.wrap_range

        clip_params["kParamRate"] = arp.rate
        clip_params["kParamGate"] = arp.gate
        # Found live: kParamDotted/kParamTriplets=0.0 was never observed in
        # any of 844 real presets (only 1.0, or the key absent entirely) --
        # a real Pattern-mode preset with these written explicitly (even at
        # 0.0) failed to arpeggiate at all in Serum, while an otherwise-
        # identical preset with a real, unmodified ArpClip0 grafted in
        # (which never writes these keys when off) worked. Matches the same
        # "omission means off" convention already established for
        # kParamLoopMode.
        if arp.dotted:
            clip_params["kParamDotted"] = True
        else:
            clip_params.pop("kParamDotted", None)
        if arp.triplets:
            clip_params["kParamTriplets"] = True
        else:
            clip_params.pop("kParamTriplets", None)
        clip_params["kParamTransposeShift"] = arp.transpose_shift
        if arp.transpose_shape is not None:
            clip_params["kParamTransposeShape"] = _resolve_arp_shape(arp.transpose_shape)
        if arp.chance is not None:
            clip_params["kParamChance"] = arp.chance
        if arp.offset is not None:
            clip_params["kParamOffset"] = arp.offset
        if arp.transpose_range is not None:
            clip_params["kParamTransposeRange"] = arp.transpose_range
        if arp.retrig_rate is not None:
            clip_params["kParamRetrigRate"] = arp.retrig_rate
        if arp.first_note_retrig is not None:
            clip_params["kParamFirstNoteRetrig"] = arp.first_note_retrig
        if arp.velo_enabled is not None:
            clip_params["kParamVeloEnabled"] = arp.velo_enabled
        if arp.velo_target is not None:
            clip_params["kParamVeloTarget"] = arp.velo_target
        if arp.wrap_phantom_note is not None:
            clip_params["kParamWrapPhantomNote"] = arp.wrap_phantom_note
        if arp.beat_retrig is not None:
            clip_params["kParamBeatRetrig"] = arp.beat_retrig
        if arp.launch_retrig is not None:
            clip_params["kParamLaunchRetrig"] = arp.launch_retrig
        if arp.velo_retrig is not None:
            clip_params["kParamVeloRetrig"] = arp.velo_retrig
        if arp.velo_decay is not None:
            clip_params["kParamVeloDecay"] = arp.velo_decay
        if arp.repeats is not None:
            clip_params["kParamRepeats"] = arp.repeats
        if arp.transpose_step is not None:
            clip_params["kParamTranspose"] = arp.transpose_step
        if arp.thru is not None:
            clip_params["kParamThru"] = arp.thru
        if arp.playback_mode_time is not None:
            clip_params["kParamPlaybackModeTime"] = arp.playback_mode_time
        validate_params(clip_key, clip_params, schema.ARPCLIP_PARAMS, allow_unknown=True)
        # Deliberately written AFTER validate_params, not before -- these 3
        # have no ARPCLIP_PARAMS entry at all (see the schema.py comment
        # above kParamRangeWrapMode: too few distinct observed values to
        # trust as a complete enum), so writing them post-validation avoids
        # ever needing to touch this call site again if they're catalogued
        # later.
        if arp.range_wrap_mode is not None:
            clip_params["kParamRangeWrapMode"] = arp.range_wrap_mode
        if arp.playback_mode is not None:
            clip_params["kParamPlaybackMode"] = arp.playback_mode
        if arp.step_action is not None:
            clip_params["kParamStepAction"] = arp.step_action

    if spec.voice_panel is not None:
        # Opaque passthrough -- see PresetSpec.voice_panel's docstring. Written
        # verbatim, same convention as FxUnitSpec.flex.
        voice_panel_container = data.setdefault("VoicePanel0", {})
        voice_panel_container["plainParams"] = dict(spec.voice_panel)

    return data
