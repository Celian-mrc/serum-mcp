"""The semantic, MCP-client-facing preset schema.

This is deliberately a *simplified* view of the full raw parameter set in
:mod:`serum_mcp.preset.schema` -- friendly field names, a curated filter-type
vocabulary, seconds instead of opaque curve values where we're confident of
the unit. The calling model (see ``server.py``'s tool instructions) builds
JSON matching :class:`PresetSpec` itself; :mod:`serum_mcp.preset.mapping`
then translates a validated ``PresetSpec`` onto the raw CBOR structure.

Every field range mirrors the bounds recorded in ``preset/schema.py`` --
if you change one, change the other.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from serum_mcp.preset.schema import (
    SIMPLE_ARP_SHAPES,
    SIMPLE_FILTER_TYPES,
    SIMPLE_SUB_SHAPES,
    SIMPLE_WARP_MODES,
    SIMPLE_WAVETABLES,
)

FilterTypeName = str  # validated against SIMPLE_FILTER_TYPES keys in mapping.py


class OscillatorSpec(BaseModel):
    """Shared fields apply to all 5 oscillator slots (A/B/C/Noise/Sub).
    ``table_position``/``warp_amount`` only affect slots 0-2; ``noise_type``
    only affects slot 3; ``sub_shape`` only affects slot 4 -- mapping.py
    ignores the fields that don't apply to a given slot rather than writing
    them somewhere Serum doesn't expect. Slots 0-2 pick one of two sound-
    source engines: the wavetable engine (``wavetable``/``custom_harmonics``/
    ``sample_source``) or, if ``sample_playback_source`` is set, the sample-
    playback engine -- never both at once.
    """

    enabled: bool = True
    octave: float = Field(0.0, ge=-4.0, le=4.0)
    semitone: float = Field(
        0.0,
        ge=-12.0,
        le=12.0,
        description="static pitch offset in semitones, independent of octave -- exists "
        "mainly to align two sample_playback_source layers to the same pitch class "
        "without a full octave jump. Found live: SampleOsc has no configurable root "
        "note, so a layered one-shot's actual sounding pitch is whatever its own "
        "recorded content is; when combining pitched one-shots, check "
        "analyze_sample_file's pitch_hz on each candidate first and use this field to "
        "correct a mismatch (e.g. two layers a tritone apart) rather than assuming they "
        "already agree.",
    )
    volume: float = Field(0.75, ge=0.0, le=1.0, description="0=silent, 1=unity gain")
    pan: float = Field(0.0, ge=-50.0, le=50.0)
    unison: float = Field(
        1.0,
        ge=1.0,
        le=16.0,
        description="voice count, slots 0-2 only. Stored as a float in Serum's own "
        "format even though it's conceptually an integer -- keep it typed float here "
        "so pydantic doesn't hand back a Python int, which would encode as the wrong "
        "CBOR wire type (see docs/PARAMETER_SCHEMA.md's CBOR bool/float note).",
    )
    detune: float = Field(0.0, ge=0.0, le=1.0, description="unison detune amount, slots 0-2 only")
    wavetable: str = Field(
        "default",
        description=f"slots 0-2 only, one of: {', '.join(sorted(SIMPLE_WAVETABLES))}. "
        "Different oscillators can (and often should) use different wavetables -- "
        "using the same one for every slot limits timbral variety. Ignored if "
        "custom_harmonics, sample_source, or sample_playback_source is set. IMPORTANT: "
        "'flute' is nearly silent at the default table_position=0.0 (its frame 0 peaks "
        "at 0.004 vs a table average of 0.81, found live) -- always pair it with "
        "table_position around 130-150.",
    )
    custom_harmonics: list[list[float]] | None = Field(
        None,
        description="slots 0-2 only. If set, SYNTHESIZES a brand-new wavetable instead of "
        "using `wavetable`/`table_position`: each inner list is one frame's harmonic "
        "amplitude series (index 0 = fundamental, index 1 = 2nd harmonic, index 2 = 3rd, "
        "...), amplitudes roughly 0..1 (auto-normalized, don't worry about exact scale), "
        "additively synthesized via inverse FFT into a 2048-sample single-cycle waveform "
        "per frame. 1-256 frames; multiple frames create a wavetable that morphs in "
        "timbre as table_position scans through it -- e.g. start with just [1.0] (pure "
        "sine) and progressively add harmonics in later frames for a tone that gets "
        "brighter as table_position increases. Use this when the user wants a genuinely "
        "custom/unusual timbre that none of the curated `wavetable` options cover, not "
        "for routine sound design (the curated tables are cheaper and pre-validated).",
    )
    sample_source: str | None = Field(
        None,
        description="slots 0-2 only. If set, SYNTHESIZES a wavetable by slicing a "
        "user-provided audio file (absolute path to a WAV: 16/24/32-bit PCM or 32-bit "
        "float, any sample rate/channel count) into `sample_frames` evenly-spaced "
        "2048-sample frames that table_position scans through -- turns a one-shot (drum "
        "hit, vocal chop, foley) into an evolving/morphable synth texture derived from "
        "its own timbre. This is NOT faithful one-shot playback -- expect a synthesized, "
        "often buzzy/looped character built from slices of the source audio, not a clean "
        "reproduction of the original transient. Use ONLY when the user wants that "
        "synthesized/morphing character; if they want the one-shot to still sound "
        "recognizably like itself, use `sample_playback_source` instead. Ignored if "
        "sample_playback_source is set.",
    )
    sample_playback_source: str | None = Field(
        None,
        description="slots 0-2 only. If set, uses Serum's SAMPLE-PLAYBACK engine "
        "(SampleOsc) instead of the wavetable engine: an absolute path to a WAV file "
        "that gets copied into Serum's Samples library and played back preserving its "
        "own recorded character -- unlike sample_source (above), which resynthesizes a "
        "wavetable and loses the original transient/timbre. Use this when the user wants "
        "to recognizably keep a one-shot/sample (drum hit, vocal chop, foley) and shape "
        "it with Serum's filter/envelope/FX, alone or layered with other oscillators, "
        "rather than turn it into a synthesized texture. Takes priority over "
        "wavetable/custom_harmonics/sample_source if set. warp_amount/warp_mode still "
        "apply (this engine shares WTOsc's warp system) but table_position does not -- "
        "there's no scannable frame position, the file plays back as one continuous "
        "sample. Only .wav is supported (not .flac/.mp3/.aiff -- convert first). "
        "Confirmed live: the sample plays back at its originally-recorded pitch/speed "
        "when C5 is played -- that's the fixed reference note this engine uses (not "
        "configurable), so octave/detune/fine are the only way to shift it if the user "
        "wants a different reference. Pitch and duration are coupled with no way to "
        "decouple them (classic 'resampling' behavior, not time-stretching) -- a note "
        "played higher reads through the sample faster (shorter), lower reads slower "
        "(longer). This matters for melodic use across a wide note range (a one-shot "
        "used as a melody instrument will have a different length at each pitch); "
        "sample_loop sustains the *looped* portion regardless of pitch but not the "
        "initial attack/transient, which still speeds up or slows down with the note.",
    )
    sample_center_pan: bool = Field(
        True,
        description="slots 0-2 only, sample_playback_source only. Real one-shot "
        "recordings often have a measurable left/right level imbalance (an off-center "
        "mic placement in the original recording, not anything Serum or this project "
        "adds) -- when true (the default), a stereo file's channels are gain-balanced "
        "to the same RMS before being copied in, correcting that bias without altering "
        "either channel's actual waveform/content (not summed to mono, stereo width "
        "survives). Set false to preserve the file exactly as recorded.",
    )
    sample_loop: str = Field(
        "off",
        description="slots 0-2 only, sample_playback_source only. One of: 'off' (play "
        "through once, true one-shot -- default, use for drum hits/percussive "
        "material), 'forward' (loop sample_loop_start..sample_loop_end forward, for "
        "sustaining a pad/drone from a one-shot), 'ping_pong' (loop back and forth), "
        "'tailed' (play through once then loop the tail region -- keeps a one-shot's "
        "attack intact while sustaining its tail indefinitely).",
    )
    sample_loop_start: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="% into the sample where the loop region starts, sample_loop != 'off' only",
    )
    sample_loop_end: float = Field(
        100.0,
        ge=0.0,
        le=100.0,
        description="% into the sample where the loop region ends, sample_loop != 'off' only",
    )
    sample_loop_crossfade: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="% crossfade at the loop point, sample_loop != 'off' only",
    )
    sample_frames: int = Field(
        16,
        ge=1,
        le=256,
        description="number of frames to slice sample_source into, slots 0-2 only. "
        "Frame 0 is the sample's start (e.g. a drum hit's transient); the last frame is "
        "its tail. More frames = finer morphing resolution as table_position scans.",
    )
    table_position: float = Field(
        0.0, ge=0.0, le=256.0, description="wavetable frame position, slots 0-2 only"
    )
    warp_amount: float = Field(0.0, ge=0.0, le=1.0, description="slots 0-2 only")
    warp_mode: str = Field(
        "fm",
        description=f"slots 0-2 only, one of: {', '.join(sorted(SIMPLE_WARP_MODES))}",
    )
    noise_type: str = Field(
        "White", description="slot 3 (Noise) only, one of: White, Pink, Brown, Geiger"
    )
    sub_shape: str = Field(
        "saw",
        description=f"slot 4 (Sub) only, one of: {', '.join(sorted(SIMPLE_SUB_SHAPES))}",
    )


class FilterSpec(BaseModel):
    enabled: bool = True
    type: FilterTypeName = Field(
        "lowpass_24", description=f"one of: {', '.join(sorted(SIMPLE_FILTER_TYPES))}"
    )
    cutoff: float = Field(0.5, ge=0.0, le=1.0, description="0=closed, 1=fully open")
    resonance: float = Field(10.0, ge=0.0, le=100.0)
    drive: float = Field(0.0, ge=0.0, le=100.0)
    stereo: float = Field(
        50.0,
        ge=0.0,
        le=100.0,
        description="stereo width/spread %. 50 is centered/neutral -- confirmed live "
        "(2026-07-28, real Serum 2) that 0 is NOT neutral despite being this field's "
        "prior default: it introduces an audible, meter-visible hard-left bias on "
        "VoiceFilter's per-channel processing. Values away from 50 in either direction "
        "shift the balance.",
    )


class EnvelopeSpec(BaseModel):
    attack: float = Field(0.0005, ge=0.0, le=10.0, description="seconds")
    hold: float = Field(0.0, ge=0.0, le=5.2, description="seconds, full level before decay starts")
    decay: float = Field(1.0, ge=0.0, le=32.0, description="seconds")
    sustain: float = Field(1.0, ge=0.0, le=1.0)
    release: float = Field(0.015, ge=0.0, le=32.0, description="seconds")


class LfoSpec(BaseModel):
    rate: float = Field(0.0, ge=0.0, le=100.0, description="normalized rate, not literal Hz")
    mode: str = Field("Free", description="'Free', 'Retrig', or 'Envelope'")
    beat_sync: bool = Field(False, description="tempo-synced rate instead of free-running Hz")
    delay: float = Field(
        0.0,
        ge=0.0,
        le=3.6,
        description="seconds before the LFO starts after note-on -- use for "
        "'vibrato that kicks in after a moment' style requests, 0 = starts immediately",
    )
    rise: float = Field(0.0, ge=0.0, le=5.0, description="seconds to ramp up to full depth")
    smooth: float = Field(
        0.0, ge=0.0, le=100.0, description="% lag smoothing, higher = less steppy/more glidey"
    )


class MacroSpec(BaseModel):
    name: str = ""
    value: float = Field(0.0, ge=0.0, le=100.0)


class FxUnitSpec(BaseModel):
    type: str = Field(description="one of the FX_TYPE_IDS names, e.g. 'FXReverb'")
    wet: float = Field(50.0, ge=0.0, le=100.0)
    params: dict[str, float | str] = Field(default_factory=dict)


class GlobalSpec(BaseModel):
    master_volume: float = Field(0.5, ge=0.0, le=1.0)
    mono: bool = False
    portamento_time: float = Field(
        0.0, ge=0.0, le=3.0, description="glide time between notes, seconds"
    )
    poly_count: float = Field(8.0, ge=1.0, le=32.0, description="max simultaneous voices")


class ModRouteSpec(BaseModel):
    """One mod-matrix route: ``source`` modulates ``destination`` by ``amount``.

    Only two source families are currently supported -- ``lfo0``..``lfo9``
    and ``macro0``..``macro7`` -- and only the destinations enumerated in
    ``preset.schema.MOD_DEST_TARGETS`` (oscillator volume/pan/octave/pitch/
    fine, filter cutoff/resonance/drive, envelope attack/decay/sustain/
    release). Other mod sources (envelopes, velocity, mod wheel, aftertouch,
    ...) exist in Serum but their internal source IDs are not decoded yet --
    see docs/PARAMETER_SCHEMA.md.
    """

    source: str = Field(description="'lfo0'..'lfo9' or 'macro0'..'macro7'")
    destination: str = Field(description="e.g. 'filter0.cutoff', 'oscillator0.pitch', 'env0.decay'")
    amount: float = Field(0.0, ge=-100.0, le=100.0)
    bipolar: bool = False


class ArpPatternNoteSpec(BaseModel):
    """One note in a custom hand-drawn arp pattern (``ArpSpec.pattern``,
    ``shape='pattern'`` only). Quantized to a fixed grid (see
    ``ArpSpec.pattern_step_beats``) rather than free timing -- the real
    format supports arbitrary timestamps, but 1243 of 1507 real notes
    surveyed used exactly a 0.25-beat (16th-note) grid, so a step grid
    covers the overwhelming majority of real usage with a much simpler API.
    """

    step: int = Field(ge=0, le=1023, description="0-indexed position on the step grid")
    note_offset: int = Field(
        0,
        ge=-48,
        le=48,
        description="pitch offset from the held/played note -- can be negative. Real "
        "presets used a wide range (-26..+12 observed), not just +/-12.",
    )
    length_steps: float = Field(
        1.0,
        gt=0.0,
        le=64.0,
        description="note length in step-units; 1.0 (the default) fills exactly one "
        "step with no gap or overlap, matching the most common real value.",
    )


class ArpSpec(BaseModel):
    """Serum 2's arpeggiator. Always targets ArpClip slot 0 (the slot real
    content overwhelmingly uses).

    Reverse-engineered from real content -- first a 180-preset third-party
    bank, then widened against 844 real presets total. Two distinct pattern
    modes exist in the real format:

    - Algorithmic (``shape`` = up/down/chord/random/... -- see
      ``SIMPLE_ARP_SHAPES``): just a handful of knobs, no note data.
    - ``shape='pattern'``: a real hand-drawn note-by-note sequence, set via
      ``pattern`` (a list of ``ArpPatternNoteSpec``). Requires ``pattern`` to
      be non-empty -- selecting ``shape='pattern'`` without it raises rather
      than silently writing an empty/broken clip. Two aspects of this mode
      are simplified vs. the full real format: every note is written with
      the same fixed "attributes" vector (7 of its 8 values were constant
      across all 1507 real notes surveyed; the 8th showed real variation
      whose meaning isn't decoded, so it's not exposed here), and timing is
      quantized to a step grid rather than the free timestamps real content
      can use (see ``ArpPatternNoteSpec``).
    """

    enabled: bool = True
    shape: str = Field(
        "played",
        description=f"one of: {', '.join(sorted(SIMPLE_ARP_SHAPES))}. 'played' repeats "
        "the notes in the order/chord they were physically played (the closest to "
        "'no pattern, just retrigger'); 'chord' plays all held notes together each "
        "step; 'converge'/'diverge' sweep inward/outward from the middle of the held "
        "notes; 'down'/'thumb_up' are directional (higher note first / lowest note "
        "held as a constant 'thumb' with the pattern moving around it); "
        "'random_once'/'random_drift'/'random_no_dup' are randomized order variants. "
        "Likely more exist (e.g. an 'up' counterpart to 'down') but aren't confirmed "
        "yet -- see docs/PARAMETER_SCHEMA.md.",
    )
    rate: float = Field(
        0.25,
        ge=0.0,
        le=1.0,
        description="normalized step rate -- UNCERTAIN real musical meaning (note "
        "division? Hz?), only 2 real values seen in the source data. Adjust by ear/"
        "experimentation rather than assuming a specific note-length mapping.",
    )
    gate: float = Field(
        75.0,
        ge=0.0,
        le=200.0,
        description="% note length relative to the step -- can exceed 100 for legato "
        "overlap into the next step (observed up to ~146 in real presets).",
    )
    dotted: bool = Field(False, description="dotted-rhythm timing for the step rate")
    triplets: bool = Field(False, description="triplet timing for the step rate")
    transpose_shift: float = Field(
        0.0, ge=-24.0, le=24.0, description="semitones, static transpose of the whole pattern"
    )
    transpose_shape: str | None = Field(
        None,
        description="optional, one of the same values as `shape` -- an independent "
        "pattern for the transpose/pitch lane, so the pitch sequence can differ from "
        "the note-trigger sequence. Leave unset for a plain transpose_shift with no "
        "extra pitch pattern.",
    )
    pattern: list[ArpPatternNoteSpec] | None = Field(
        None,
        max_length=128,
        description="custom hand-drawn note sequence, shape='pattern' ONLY. Required "
        "(and must be non-empty) when shape='pattern'; ignored/must be left unset for "
        "every other shape.",
    )
    pattern_step_beats: float = Field(
        0.25,
        gt=0.0,
        le=4.0,
        description="beats per grid step for `pattern` note positions/lengths -- 0.25 "
        "(16th notes, the default) matches the most common real value, but the real "
        "format allows any grid; use 0.5 for 8th notes, 1.0 for quarter notes, etc.",
    )


class PresetSpec(BaseModel):
    """The full target state for a generated or edited preset."""

    name: str = Field(description="short preset name, Serum-style, e.g. 'BA - Acid Growl'")
    description: str = Field(description="one-sentence description of the sound design intent")
    oscillators: list[OscillatorSpec] = Field(
        default_factory=list,
        max_length=5,
        description="index 0..4 = Osc A, B, C, Noise, Sub. Omit trailing slots to leave untouched.",
    )
    filters: list[FilterSpec] = Field(
        default_factory=list,
        max_length=2,
        description="index 0..1 = Filter 1, Filter 2",
    )
    envelopes: list[EnvelopeSpec] = Field(
        default_factory=list,
        max_length=4,
        description="index 0..3; Env 1 (index 0) is conventionally the amp envelope",
    )
    lfos: list[LfoSpec] = Field(default_factory=list, max_length=10)
    macros: list[MacroSpec] = Field(default_factory=list, max_length=8)
    fx_chain: list[FxUnitSpec] = Field(
        default_factory=list,
        max_length=32,
        description="effects, in order, on FX rack 1. Cap raised from an earlier 12 after "
        "finding real third-party presets with up to 19 flattened units (their actual FX "
        "racks use parallel/multiband routing this project doesn't model yet -- see "
        "docs/PARAMETER_SCHEMA.md -- so the flat count runs higher than a simple serial "
        "chain would suggest). This is a technical ceiling, not a recommendation: most "
        "good presets use far fewer, see server.py's generation guidance.",
    )
    mod_routes: list[ModRouteSpec] = Field(
        default_factory=list,
        max_length=64,
        description="modulation matrix routes; see ModRouteSpec for supported sources/"
        "destinations. Cap matches the real mod matrix's 64 physical slots (see "
        "mapping._free_modslot_indices) -- raised from an earlier 16 after finding real "
        "third-party presets using up to 19.",
    )
    global_: GlobalSpec = Field(default_factory=GlobalSpec, alias="global")
    arp: ArpSpec | None = Field(
        None,
        description="Serum's arpeggiator, algorithmic modes only (see ArpSpec). Unset "
        "(the default) leaves the arp completely untouched -- omit it entirely rather "
        "than passing ArpSpec(enabled=False) unless you specifically want to disable "
        "an arp that's already on.",
    )

    model_config = {"populate_by_name": True}
