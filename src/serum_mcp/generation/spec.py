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

from typing import Literal

from pydantic import BaseModel, Field

from serum_mcp.preset.schema import (
    MULTISAMPLE_INSTRUMENTS,
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
    fine: float = Field(
        0.0,
        ge=-80.0,
        le=80.0,
        description="cents (approx.), independent of both octave and semitone -- a "
        "smaller-than-a-semitone micro-tuning control, the same 'Coarse + Fine' pattern "
        "as most synths. Found live 2026-07-29: a real preset used this on 2 of its "
        "active oscillators (-3/+4 cents) for subtle detuning/beating between layers "
        "that this project had never exposed as a settable base value (only as a mod "
        "destination, oscillator{i}.fine).",
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
    warp_amount: float = Field(
        0.0, ge=0.0, le=1.0, description="slots 0-2 only. Also applies to granular_source/"
        "spectral_source/multisample_source (GranularOsc/SpectralOsc/MultiSampleOsc share "
        "the same kParamWarp amount knob as WTOsc/SampleOsc, though SpectralOsc's warp "
        "MODE vocabulary is different -- see warp_mode)."
    )
    warp_mode: str = Field(
        "fm",
        description=f"slots 0-2 only, one of: {', '.join(sorted(SIMPLE_WARP_MODES))}. Also "
        "applies to granular_source/multisample_source. For spectral_source specifically, "
        "this curated list does NOT apply -- SpectralOsc has its own, much larger "
        "warp-mode vocabulary "
        "(spectral-domain effects like gating/robotizing/vocoding/Shepard tones, "
        "unrelated names) -- pass the raw Serum name directly instead, e.g. "
        "warp_mode='kGate', 'kSmear', 'kRobotize', 'kSpectralShift', 'kVocode_OSC', "
        "'kMask_OSC', 'kShepardFilter' (any value not in the curated list above is "
        "passed straight through unvalidated against a friendly-name table).",
    )
    granular_source: str | None = Field(
        None,
        description="slots 0-2 only. If set, uses Serum's GRANULAR engine (GranularOsc) "
        "instead of the wavetable engine: an absolute path to a WAV file that gets copied "
        "into Serum's Samples library (same mechanism as sample_playback_source) and "
        "played back through Serum's grain-based synthesis instead of straight playback "
        "-- continuously re-triggered short 'grains' sliced from the source, each with "
        "randomizable pitch/pan/length/start-offset, for an evolving/textural/'clouds of "
        "sound' character very different from both wavetable and sample_playback_source. "
        "Use for pads/textures/soundscapes built FROM a sample (a field recording, a "
        "vocal, a drone) rather than played back as itself. Takes priority over "
        "wavetable/custom_harmonics/sample_source if set, but sample_playback_source "
        "takes priority over this if BOTH are set (only one non-wavetable engine can be "
        "active per slot). Decoded 2026-07-30 via a 626-preset corpus survey and VST3 "
        "binary string mining, then confirmed live in real Serum 2 (including fixing two "
        "real unit-conversion bugs found that way, see granular_density/"
        "granular_grain_length below) -- genuinely produces a grain-cloud texture, "
        "cross-validated against a real Factory Granular preset. Only the controls below "
        "plus warp_amount/warp_mode are exposed; Serum's real GranularOsc has ~20 more "
        "params (window shape, BPM-synced density/length, unison trigger pattern, a "
        "second randomizable warp lane, a SCAN/playback-position system found live but "
        "not yet wired up, ...) this project doesn't generate yet -- see "
        "docs/PARAMETER_SCHEMA.md.",
    )
    granular_density: float = Field(
        10.0, ge=0.0, le=30.0, description="granular_source only. Grain trigger rate, on "
        "the SAME 0-30 scale as Serum's own DENS knob (higher = denser/smoother/more "
        "continuous-sounding grain cloud, lower = sparser/more rhythmic/glitchy individual "
        "grains audible) -- confirmed live 2026-07-30 by reading back real Serum-saved "
        "values (the raw storage format is a much steeper, unrelated quartic curve; this "
        "field matches the UI number, not raw storage, same convention as every other "
        "field in this project).",
    )
    granular_grain_length: float = Field(
        100.0, ge=0.0, le=10000.0, description="granular_source only. Length of each "
        "individual grain in MILLISECONDS, on the SAME scale as Serum's own LENGTH knob "
        "-- confirmed live 2026-07-30 by reading back a real Factory preset's own raw "
        "value (808 - Texture's Osc B: raw 0.1243 -> displayed 124ms, matching this "
        "formula to within rounding) in addition to the original 3-point calibration "
        "(0.05/0.3/1.0 -> 50/300/1000x smaller raw). Shorter = more textural/glitchy, "
        "longer = closer to overlapping mini-loops of the source; the real Factory "
        "reference above used 124ms for a smooth/rich texture. IMPORTANT: earlier "
        "versions of this project wrote this number directly as Serum's raw storage "
        "value AND assumed the unit was seconds, not ms -- e.g. writing 0.15 intending "
        "'150ms' actually produced 0.15ms (absurdly short) after the first fix and "
        "'150 real seconds' (absurdly long, clamped) before it. Both bugs are now fixed; "
        "this field is the literal millisecond number you'd type into Serum.",
    )
    granular_random_pitch: float = Field(
        0.0, ge=0.0, le=12.0, description="granular_source only. Random per-grain pitch "
        "variation in semitones -- adds a chorus-like/detuned-cloud thickness. 0 = every "
        "grain plays at the same pitch.",
    )
    granular_random_pan: float = Field(
        0.0, ge=0.0, le=100.0, description="granular_source only. % random per-grain stereo "
        "placement -- higher = wider/more diffuse cloud, 0 = all grains centered.",
    )
    granular_random_grain_length: float = Field(
        0.0, ge=0.0, le=100.0, description="granular_source only. % random variation in "
        "each grain's length around granular_grain_length -- adds organic irregularity to "
        "the grain cloud instead of a perfectly uniform texture.",
    )
    granular_random_offset: float = Field(
        0.0, ge=0.0, le=100.0, description="granular_source only. % random per-grain start "
        "offset within the source sample -- higher scatters each grain's read position "
        "instead of every grain starting at the exact same point, adding texture/blur. "
        "Wired 2026-08-01, always written explicitly (same low-risk pattern as "
        "granular_random_pitch/pan/grain_length above) -- confidence='observed' in "
        "schema.py (clearer real-corpus meaning than most of the other newly-wired "
        "granular_* fields below, which are 'uncertain').",
    )
    granular_loop: bool = Field(
        True, description="granular_source only. Whether each grain loops within its "
        "window instead of playing once. True is Serum's own corpus-observed default -- "
        "leave it unless deliberately going for a choppier, non-looping grain character. "
        "Wired 2026-08-01, confidence='uncertain' in schema.py (never independently "
        "confirmed live, only decoded from corpus survey + VST3 binary mining).",
    )
    granular_jump_start: bool = Field(
        False, description="granular_source only. Presumed 'each grain jump-starts "
        "mid-window rather than fading in' toggle -- not independently confirmed, "
        "confidence='uncertain' in schema.py. Rare in real content; leave False unless "
        "specifically matching a reference preset that uses it.",
    )
    granular_reverse: bool = Field(
        False, description="granular_source only. Plays grains in reverse. Plausible "
        "explanation for a real Factory reference preset ('808 - Texture', Osc B) "
        "observed playing in reverse during GranularOsc live-testing -- see "
        "docs/PARAMETER_SCHEMA.md item 3 -- but that connection was never independently "
        "confirmed (a negative granular_scan_rate, not yet wired, was an equally "
        "plausible alternate explanation at the time). confidence='uncertain' in "
        "schema.py.",
    )
    granular_length_key_track: bool = Field(
        False, description="granular_source only. Presumed 'grain length tracks the "
        "played note' toggle (shorter grains on higher notes, or similar) -- not "
        "independently confirmed, confidence='uncertain' in schema.py.",
    )
    granular_max_grains: float = Field(
        16.0, ge=1.0, le=64.0, description="granular_source only. Ceiling on simultaneous "
        "overlapping grains -- higher allows denser/thicker clouds at high "
        "granular_density at the cost of more voices/CPU. confidence='uncertain' in "
        "schema.py (real corpus range observed, exact audible effect not independently "
        "tested).",
    )
    granular_random_window_amount: float = Field(
        0.0, ge=0.0, le=100.0, description="granular_source only. % randomization of each "
        "grain's amplitude envelope/window shape -- adds organic variation to the "
        "grain-to-grain volume envelope, similar in spirit to granular_random_pan/"
        "grain_length but for the window shape itself. confidence='uncertain' in "
        "schema.py.",
    )
    granular_random_window_skew: float = Field(
        0.0, ge=0.0, le=100.0, description="granular_source only. % randomization of each "
        "grain's window skew (attack/release balance within the grain) -- 0 = every "
        "grain uses the same symmetric-ish window. confidence='uncertain' in schema.py.",
    )
    spectral_source: str | None = Field(
        None,
        description="slots 0-2 only. If set, uses Serum's SPECTRAL engine (SpectralOsc) "
        "instead of the wavetable engine: an absolute path to a WAV file, resynthesized "
        "through spectral-domain processing (FFT-based warping -- gating, robotizing, "
        "spectral shifting, vocoding against the OTHER oscillators/filters via the "
        "kMask_*/kVocode_* warp modes, Shepard-tone effects, and more, see warp_mode) "
        "instead of straight playback or granular re-triggering. Use for glitchy/robotic/"
        "vocoder/otherworldly textures specifically -- a materially different character "
        "than sample_playback_source (unprocessed) or granular_source (grain clouds). "
        "IMPORTANT LIMITATION: real SpectralOsc content commonly carries a hand-drawn "
        "spectral filter/EQ CURVE across the frequency domain (53% of real samples "
        "surveyed) that this project cannot yet generate (see "
        "docs/PARAMETER_SCHEMA.md item 4) -- a generated SpectralOsc always has a flat/"
        "neutral spectral response; only the frequency-range and warp controls below are "
        "real. Takes priority over wavetable/custom_harmonics/sample_source, but "
        "sample_playback_source/granular_source take priority over this if set. Only "
        ".wav is supported. Confirmed live 2026-07-30 in real Serum 2 (warp_mode='kGate' "
        "on a noise source produced the expected robotic/vocoder-like gated character, "
        "with warp_amount=0 correctly falling back to a clean resynthesis of the source). "
        "spectral_warp_freq_lo/freq_hi confirmed correct as literal Hz 2026-07-31 via "
        "automated audio rendering (see docs/PARAMETER_SCHEMA.md item 3) -- a 20-500Hz "
        "window and a 5000-20000Hz window on the same source produced spectral centroids "
        "of 102Hz vs 6946Hz respectively, no conversion needed. filter_shift/filter_wet "
        "remain unverified.",
    )
    spectral_warp_freq_lo: float = Field(
        20.0, ge=20.0, le=20000.0, description="spectral_source only. Hz, low edge of the "
        "frequency range warp_mode's spectral effect applies to.",
    )
    spectral_warp_freq_hi: float = Field(
        20000.0, ge=20.0, le=20000.0, description="spectral_source only. Hz, high edge of "
        "the frequency range warp_mode's spectral effect applies to -- narrow the "
        "freq_lo..freq_hi range to target just a specific band (e.g. only warping the "
        "upper harmonics while leaving the fundamental untouched).",
    )
    spectral_filter_shift: float = Field(
        0.0, ge=-100.0, le=100.0, description="spectral_source only. % shift applied to "
        "the (always-flat, see the spectral_source limitation note) spectral filter "
        "curve's effective position.",
    )
    spectral_filter_wet: float = Field(
        100.0, ge=0.0, le=100.0, description="spectral_source only. % wet/dry for the "
        "spectral filter/curve effect.",
    )
    multisample_source: str | None = Field(
        None,
        description=f"slots 0-2 only. If set, uses Serum's MULTISAMPLE engine "
        f"(MultiSampleOsc) with a CURATED real Factory multisample instrument -- one of: "
        f"{', '.join(sorted(MULTISAMPLE_INSTRUMENTS))}. Unlike granular_source/"
        f"spectral_source/sample_playback_source (an arbitrary user WAV file),  "
        f"MultiSampleOsc's real structure is a full SFZ-format keyzone mapping across many "
        f"sample files -- too complex to build from an arbitrary user file this round (see "
        f"docs/PARAMETER_SCHEMA.md item 3), so only these pre-verified real Factory "
        f"instruments are selectable, each played back with correct per-note sample "
        f"selection/pitch/looping exactly as Xfer's own sound designers configured it "
        f"(unlike a single-sample engine playing one recording across the whole keyboard). "
        f"Use for realistic multisampled instruments (choir, guitar, strings, ...) rather "
        f"than synthesized/textural sources. Decoded 2026-07-31 via a 246-preset corpus "
        f"survey -- NOT yet confirmed live for generation, treat as experimental until "
        f"tested. Takes priority over wavetable/custom_harmonics/sample_source, but "
        f"sample_playback_source/granular_source/spectral_source take priority over this "
        f"if set on the same oscillator.",
    )
    multisample_env_attack: float = Field(
        0.0, ge=0.0, le=0.4, description="multisample_source only. Seconds -- an OSC-level "
        "note-shaping attack stage layered on top of the instrument's own baked-in sample "
        "envelope, NOT the primary voice envelope (Env0-3). Real range observed is short "
        "(0-0.4s); for a longer/slower attack shape the fuller Env0-3 envelope is the "
        "right tool instead.",
    )
    multisample_env_decay: float = Field(
        0.0, ge=0.0, le=32.0, description="multisample_source only. Seconds, same "
        "OSC-level layered envelope as multisample_env_attack.",
    )
    multisample_env_release: float = Field(
        0.0, ge=0.0, le=32.0, description="multisample_source only. Seconds, same "
        "OSC-level layered envelope as multisample_env_attack.",
    )
    warp_amount2: float = Field(
        0.0, ge=0.0, le=1.0, description="amount for the SECOND warp lane, slots 0-2 only "
        "-- see warp_mode2"
    )
    warp_mode2: str | None = Field(
        None,
        description=(
            "slots 0-2 only, one of the same values as warp_mode, or None (default) for "
            "no second warp lane at all -- most oscillators only use one. A SECOND, "
            "independent warp stage applied after the first (e.g. warp_mode='fm' for an "
            "FM character, THEN warp_mode2='filter_lpf' to tame/soften it) -- found live "
            "2026-07-29: a real preset's primary oscillator used exactly this pattern "
            "(kFM_NOISE then kFilterLPF at 56%), and a recreation missing the second lane "
            "sounded harsh/aliased/'8-bit' despite the primary warp matching. If a "
            "request implies a raw/digital/FM/noise character should still sound musical "
            "rather than harsh, consider pairing it with warp_mode2='filter_lpf' or "
            "'filter_hpf' to shape it, the same way real content commonly does."
        ),
    )
    warp_var2: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="slots 0-2 only. A rarer, distinct third warp-related control -- not "
        "the same as warp_amount2. Uncertain exact role (found live 2026-07-29 only as "
        "a mod-matrix destination target, not independently understood); leave unset "
        "unless specifically matching a real reference preset's value for this field.",
    )
    noise_type: str = Field(
        "White", description="slot 3 (Noise) only, one of: White, Pink, Brown, Geiger"
    )
    sub_shape: str = Field(
        "saw",
        description=f"slot 4 (Sub) only, one of: {', '.join(sorted(SIMPLE_SUB_SHAPES))}",
    )
    filter_routing: Literal["filter", "master", "direct", "none"] | None = Field(
        None,
        description="Which path THIS oscillator's signal takes after leaving the "
        "oscillator itself, backed by RoutingSlot{index} (see "
        "docs/PARAMETER_SCHEMA.md §5 item 11 -- distinct from FilterSpec.output_routing, "
        "which is each FILTER's own output routing, not an oscillator's input routing). "
        "'filter' (Serum's real default when left unset) sends it through the enabled "
        "VoiceFilter(s) normally -- see filter_balance when both filters are in use. "
        "'master' bypasses both filters straight to the main output -- useful to keep a "
        "bright/transient layer (a noise click, a sub) out of a resonant/saturating "
        "filter chain shaping the rest of the stack. 'direct' bypasses filters AND the "
        "FX bus system entirely. 'none' sends to neither filter nor master by default. "
        "Leave unset unless deliberately routing a specific oscillator around the filter "
        "stage.",
    )
    filter_balance: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Only meaningful when filter_routing='filter' (or left unset) AND "
        "two filters are enabled -- balance of this oscillator's signal between Filter 1 "
        "and Filter 2. Exact scale not independently confirmed; higher values are "
        "believed to lean toward Filter 2 (see docs/PARAMETER_SCHEMA.md). Leave unset to "
        "use Serum's own default balance.",
    )
    fx_bus1_send: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="% of this oscillator's signal sent to FX Bus 1, independent of "
        "filter_routing's main destination -- a genuine aux send, not mutually exclusive "
        "with it. See GlobalSpec.fx_bus1_volume for the bus's own aggregate level. Leave "
        "unset for no send (Serum's real default).",
    )
    fx_bus2_send: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Same as fx_bus1_send, for FX Bus 2.",
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
    var: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="the 'Var' knob -- meaning changes per filter TYPE (e.g. comb "
        "spacing for comb filters, formant blend for formant filters). Found live "
        "2026-07-29: for `type='comb'` (or any DistComb/RMT-style raw type), this is a "
        "MAJOR contributor to the filter's character, not a minor tweak -- a real comb "
        "preset with var=65 sounded harsh/aliased/'8-bit' when this was left at the 0 "
        "default. Check a real reference preset's value for this filter type rather "
        "than assuming 0 is fine.",
    )
    key_track: bool = Field(
        False, description="cutoff tracks the played note's pitch (higher notes = brighter)"
    )
    wet: float = Field(
        100.0,
        ge=0.0,
        le=100.0,
        description="this filter's own dry/wet mix -- distinct from the fx_chain's FX "
        "wet knobs. Most filter uses want fully wet (the default); a low value "
        "approaches an all-pass/bypass character while keeping resonance/drive coloring "
        "subtle.",
    )
    level_out: float = Field(
        0.5, ge=0.0, le=1.0, description="output level trim applied after the filter"
    )
    output_routing: Literal["parallel", "series"] | None = Field(
        None,
        description="how this filter's OWN output reaches the main signal path -- "
        "'parallel' (the real Serum default: goes straight to output, independent of "
        "the other filter) or 'series' (cascades into the OTHER filter, i.e. this "
        "filter's output becomes the other filter's input). Leave unset to use "
        "Serum's real default ('parallel') rather than writing anything explicit -- "
        "found live 2026-07-29: a fixture bug had every serum-mcp preset with both "
        "filters enabled silently running them in series (now fixed at the fixture "
        "level, so 'parallel' no longer needs to be set explicitly to get it). Only "
        "set 'series' when a genuinely cascaded dual-filter chain is wanted (e.g. "
        "recreating a specific reference preset that uses it) -- setting BOTH "
        "filters[0] and filters[1] to 'series' at once creates a routing cycle and "
        "raises an error rather than producing a silently broken preset. Backed by "
        "RoutingSlot5/RoutingSlot6, a top-level structure outside VoiceFilter this "
        "project only partially understands -- see docs/PARAMETER_SCHEMA.md §5.",
    )
    fx_bus1_send: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="% of this filter's signal sent to FX Bus 1, independent of "
        "output_routing's main destination -- a genuine aux send, not mutually "
        "exclusive with it. See GlobalSpec.fx_bus1_volume for the bus's own aggregate "
        "level. Leave unset for no send (Serum's real default).",
    )
    fx_bus2_send: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Same as fx_bus1_send, for FX Bus 2.",
    )


class EnvelopeSpec(BaseModel):
    attack: float = Field(0.0005, ge=0.0, le=10.0, description="seconds")
    hold: float = Field(0.0, ge=0.0, le=5.2, description="seconds, full level before decay starts")
    decay: float = Field(1.0, ge=0.0, le=32.0, description="seconds")
    sustain: float = Field(1.0, ge=0.0, le=1.0)
    release: float = Field(0.015, ge=0.0, le=32.0, description="seconds")
    attack_curve: float = Field(
        50.0,
        ge=0.0,
        le=100.0,
        description="shape (linear/exponential/logarithmic-ish) of the attack ramp, "
        "0-100. Found live 2026-07-29 present on 97% of all real envelopes surveyed "
        "(3242/3333) -- effectively always set, not a rare/optional field, default "
        "~50 is by far the most common real value. Segment mapping (attack/decay/"
        "release, matching kParamCurve1/2/3's declaration order) is inferred, not "
        "independently confirmed.",
    )
    decay_curve: float = Field(
        66.6, ge=0.0, le=100.0, description="shape of the decay ramp, 0-100 -- see attack_curve"
    )
    release_curve: float = Field(
        66.6, ge=0.0, le=100.0, description="shape of the release ramp, 0-100 -- see attack_curve"
    )


class LfoSpec(BaseModel):
    rate: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="With mode='Free' and beat_sync=False (both required for this to "
        "mean anything -- see beat_sync's own docstring for a real bug this project "
        "shipped where free-Hz mode was silently unreachable, fixed 2026-08-01), this "
        "IS literal Hz -- confirmed via audio-rendering calibration, exact 1:1 match at "
        "raw 2/5/10/20/30 -> 2.0/5.0/10.0/20.0/30.0 Hz, and confirmed clean/glitch-free "
        "by live listening all the way to 100 too (a live-Serum cross-check first found "
        "visible 'jumps' near raw 35-40, but traced them to a per-voice LFO retriggering "
        "on each note-on, not the rate itself -- see LfoSpec.mono; with that confound "
        "removed the audio was smooth throughout, the remaining visible jumps being an "
        "inaudible screen-refresh/stroboscopic illusion, not a real glitch). Safe to use "
        "the full 0-100 range as literal-ish Hz; the exact number above ~35 just isn't "
        "independently pinned down as precisely as the 2-30 range (this project's own "
        "measurement tool has known limits at fast rates, see "
        "schema.LFO_PARAMS['kParamRate'] and docs/PARAMETER_SCHEMA.md item 6a). 0.0 "
        "(this field's own default) writes nothing at all UNLESS beat_sync is also "
        "explicitly set -- see that field's docstring -- landing on Serum's genuine "
        "absent-state default instead "
        "('1/4' BPM-synced, not 0Hz).",
    )
    mode: str = Field("Free", description="'Free', 'Retrig', or 'Envelope'")
    beat_sync: bool | None = Field(
        None,
        description="True = tempo-synced rate (BPM note values); False = free-running Hz; "
        "None (default) = leave unset, which is Serum's own genuine default and is ALSO "
        "tempo-synced, not Hz -- confirmed both by live UI probing and by audio "
        "measurement (see LFO_PARAMS['kParamRate'] notes). "
        "**Real bug, fixed 2026-08-01**: this field used to be a plain `bool` defaulting "
        "to `False`, which made explicit free-Hz mode UNREACHABLE -- `False` was "
        "indistinguishable from 'not set' and got silently omitted by mapping.py's "
        "omit-at-default logic, always falling back to Serum's real (synced) default "
        "regardless of intent. Found live by a user manually turning a calibration "
        "preset's RATE knob and noticing it read 'BPM'/a note fraction instead of Hz, "
        "which invalidated an earlier 'confirmed' free-Hz curve calibration that had "
        "silently been measuring the BPM-synced curve instead (see PARAMETER_SCHEMA.md "
        "item 6a's retraction). Pass `beat_sync=False` explicitly now to genuinely get "
        "free-Hz mode; leave unset (None) for Serum's real tempo-synced default.",
    )
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
    shape: str | None = Field(
        None,
        description=(
            "one of: random_sh, rossler, lorenz, path -- named algorithmic LFO shapes "
            "(chaotic attractors / randomization), NOT a plain sine/triangle/square/saw "
            "(those are stored as hand-drawn curve data this project can't generate yet, "
            "so leave this unset for a normal-shaped LFO -- unset keeps whatever curve "
            "the base preset already has, it does NOT mean 'off'). random_sh ('S&H' in "
            "Serum's UI) is a stepped-random hold, good for glitchy/robotic movement; "
            "rossler/lorenz are smooth-but-unpredictable organic chaotic modulation, "
            "good for 'evolving'/'alive' textures; path is unconfirmed in character. "
            "NOT yet confirmed live for generation (only confirmed reading real files) "
            "-- treat as experimental until tested."
        ),
    )
    mono: bool = Field(
        False,
        description="a single shared LFO instance running continuously, independent of "
        "note-on events, instead of a per-voice LFO that restarts its phase at every "
        "note-on. Found live 2026-07-29: matters a lot for a FAST lfo under a fast "
        "arpeggiator/sequencer -- a per-voice LFO barely completes any of its cycle "
        "before being reset by the next note, which can read as choppy/'too fast' and "
        "'frozen when nothing is playing'; mono=True keeps it running and visibly "
        "moving regardless of note activity, closer to a genuinely independent, "
        "continuously-evolving modulation source. Use for a fast/busy LFO (e.g. "
        "shape='random_sh') paired with a fast arp/sequence, where the LFO is meant to "
        "feel alive on its own rather than reset in lockstep with every note.",
    )
    swing: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="shuffle/swing amount for a stepped LFO (e.g. shape='random_sh'). "
        "Only ever observed at 1.0 in real content -- uncertain exactly what "
        "intermediate values do; leave at 0 unless specifically asked for a swung/"
        "shuffled feel.",
    )
    dotted: bool = Field(
        False,
        description="dotted-rhythm timing for the LFO's rate, mirroring the "
        "arpeggiator's identically-named field. Found live 2026-07-29, present on 16% "
        "of real LFOs surveyed.",
    )
    triplets: bool = Field(
        False, description="triplet timing for the LFO's rate -- see dotted."
    )
    rate10x: bool = Field(
        False,
        description="presumed x10 rate multiplier (not independently confirmed). Found "
        "live 2026-07-29 on real chaotic-shape LFOs (rossler/lorenz) with a very low "
        "base rate -- may matter for whether a slow chaos LFO actually reads as "
        "'moving' at a musically useful speed.",
    )


class MacroSpec(BaseModel):
    name: str = ""
    value: float = Field(0.0, ge=0.0, le=100.0)


class FxUnitSpec(BaseModel):
    type: str = Field(description="one of the FX_TYPE_IDS names, e.g. 'FXReverb'")
    wet: float = Field(50.0, ge=0.0, le=100.0)
    params: dict[str, float | str] = Field(
        default_factory=dict,
        description="Type-specific plainParams, e.g. {'kParamRate': 2.0}. Key names and "
        "ranges: see list_parameters()['fx_params'][type]. GOTCHA for FXDelay "
        "specifically: kParamTimeL/kParamTimeR only mean literal seconds when "
        "kParamBeatSync is ALSO passed here as explicit False -- e.g. "
        "{'kParamTimeL': 0.25, 'kParamTimeR': 0.25, 'kParamBeatSync': False} for a "
        "250ms delay. Omitting kParamBeatSync falls back to Serum's real (BPM-synced/"
        "note-quantized) default, silently making kParamTimeL/R NOT mean seconds at all "
        "-- confirmed live 2026-08-01 (same class of bug as LfoSpec.beat_sync). Bool "
        "values like this work fine as plain Python True/False despite this field's "
        "float|str type hint.",
    )
    rack: int = Field(
        0,
        ge=0,
        le=2,
        description="which of Serum's 3 PARALLEL fx racks this unit sits in. 0 is what "
        "nearly every preset uses (a single serial chain) -- only set 1 or 2 for a "
        "second/third independent signal path that processes in parallel with rack 0, "
        "not after it (e.g. a dry chain in rack 0 and a separate wet/send chain in rack "
        "1). Units within the same rack still process in list order. Found live "
        "2026-07-29 in a real Unmute preset (a second rack with its own EQ/comp/reverb/"
        "bode-shifter running alongside rack 0) -- this project had never read or "
        "written anything but rack 0 before that.",
    )


class GlobalSpec(BaseModel):
    master_volume: float = Field(0.5, ge=0.0, le=1.0)
    mono: bool = False
    portamento_time: float = Field(
        0.0, ge=0.0, le=3.0, description="glide time between notes, seconds"
    )
    poly_count: float = Field(8.0, ge=1.0, le=32.0, description="max simultaneous voices")
    limit_same_note_polyphony: bool = Field(
        False,
        description="limit voice-stacking when the SAME note is retriggered rapidly (e.g. "
        "under a fast arp/sequence) instead of letting overlapping voices for one note "
        "pile up. Found live 2026-07-29, present on 39% of real presets surveyed.",
    )
    fx_bus1_volume: float | None = Field(
        None,
        ge=0.0,
        description="Aggregate volume for FX Bus 1, fed by any oscillator's/filter's own "
        "fx_bus1_send. CAN exceed 1.0 (a real boost/gain stage, not just 0-100%% "
        "attenuation like most params in this schema) -- real values seen 0.26-1.75. "
        "Leave unset to use Serum's own default (unity) rather than writing it "
        "explicitly; only meaningful when at least one source has a nonzero "
        "fx_bus1_send.",
    )
    fx_bus2_volume: float | None = Field(
        None,
        ge=0.0,
        description="Same as fx_bus1_volume, for FX Bus 2.",
    )
    direct_volume: float | None = Field(
        None,
        ge=0.0,
        description="Volume for signal from any source routed with "
        "filter_routing/output_routing='direct' (bypasses both filters AND the FX bus "
        "system entirely). Real values seen 0.21-0.43 -- well below the presumed unity "
        "default, uncertain why. Leave unset unless deliberately using 'direct' routing.",
    )
    fx_bus1_destination: Literal["master", "direct"] | None = Field(
        None,
        description="Where FX Bus 1's OWN processed signal (after passing through its "
        "FX chain) rejoins the main path -- distinct from fx_bus1_volume (that bus's "
        "aggregate level) and each source's own fx_bus1_send (how much is sent INTO the "
        "bus to begin with). 'master' (straight to main output) or 'direct' (a separate "
        "bypass path, see direct_volume). Decoded 2026-07-30 from a 626-preset corpus "
        "survey: real content only ever used these two values, never routing a bus back "
        "into a filter or nowhere. Leave unset unless deliberately using the FX bus "
        "system; only meaningful when at least one source has a nonzero fx_bus1_send.",
    )
    fx_bus2_destination: Literal["master", "direct"] | None = Field(
        None,
        description="Same as fx_bus1_destination, for FX Bus 2.",
    )


class ModRouteSpec(BaseModel):
    """One mod-matrix route: ``source`` modulates ``destination`` by ``amount``.

    Supported sources -- ``lfo0``..``lfo9``, ``macro0``..``macro7``,
    ``velocity``, ``mod_wheel``, ``pitch_bend``, ``key_track`` (note number),
    ``aftertouch``, ``poly_aftertouch``, ``env0``..``env3`` (an envelope's
    own output used as a source, distinct from routing something INTO that
    envelope), three independent per-note random sources (``random1``,
    ``random2``, ``random_discrete``), and 5 per-voice/note "Note"-category
    sources -- ``release_velo``, ``active_voices``, ``voice_index``,
    ``voice_mod1``, ``voice_mod2`` -- routed to the destinations enumerated
    in ``preset.schema.MOD_DEST_TARGETS`` (oscillator volume/pan/octave/
    pitch/fine, filter cutoff/resonance/drive, envelope attack/decay/
    sustain/release). ``velocity`` is a good fit for envelope attack/decay/
    release (classic velocity-sensitivity) or filter cutoff (velocity-
    sensitive brightness); ``key_track`` for filter cutoff that opens up on
    higher notes; ``aftertouch``/``poly_aftertouch`` for post-note-on
    expressive control (e.g. pressure adding vibrato or opening the filter);
    ``random1``/``random2``/``random_discrete`` for per-note humanization
    (e.g. small pan or pitch variation); ``release_velo``/``voice_mod1``/
    ``voice_mod2``/``active_voices``/``voice_index`` exact musical meaning
    unconfirmed beyond their Serum UI name (only their source IDs were
    probed, not their live behavior) -- all IDs confirmed live 2026-07-29
    via direct probing of a real Serum 2 instance. ``fixed`` is Serum's own
    MATRIX-tab name for a CONSTANT modulation offset -- ``amount`` alone,
    with no time-varying signal at all, useful for a permanent bias on a
    destination (e.g. a fixed pitch/tuning offset) without dedicating an LFO
    or macro to it.

    Resolved 2026-08-01, closing nearly the entire remaining source list:
    ``note_on_alt``/``note_on_alt2`` (Note category, meaning unconfirmed
    beyond the UI name, same caveat as ``voice_mod1``/``2``);
    ``expr_pan``/``expr_timbre``/``expr_press`` (MPE-style per-note note
    expression -- ``mod_wheel``/``aftertouch``-style continuous control,
    only meaningful with an MPE-capable controller/DAW routing); and 7
    SELF-MODULATION sources -- ``oscillator0``..``oscillator4`` (that
    oscillator SLOT's own audio-rate output, same 0-indexed convention as
    the destination side: 0/1/2/3/4 = Osc A/B/C/Noise/Sub) and
    ``filter0``/``filter1`` (that filter's own audio-rate output) -- a
    module using its own signal to modulate something else, distinct from
    routing something INTO that module. Live audible behavior of the
    self-modulation and note-expression sources not yet independently
    tested, same "IDs confirmed, behavior not" caveat as the Note-category
    sources above.

    ``lfo1_y`` (id 40, resolved 2026-08-01) closes the last of this
    project's originally-flagged unknown source ids -- presumed to be the
    Y-axis/secondary coordinate output of LFO slot 2 (``lfo1``) when using
    a chaotic-attractor shape (Rossler/Lorenz), distinct from that LFO's
    own primary output. Confirmed for this ONE specific slot only, by
    reading a real Factory preset's own MATRIX tab directly -- whether
    other LFO slots have an analogous ``_y`` source, and what id it would
    use, is unknown; don't assume a contiguous family exists.

    ``aux_source``/``aux_inverted`` expose Serum's general "Aux"/"Via"
    system: an OPTIONAL second, independent source (same vocabulary as
    ``source``, including ``fixed``) that scales/gates how much of
    ``amount`` actually reaches ``destination``. Decoded 2026-07-30 via a
    626-preset corpus survey: 1276 real routes across nearly every source
    family use this, by far most commonly ``mod_wheel`` or ``aftertouch`` as
    the aux (e.g. "LFO1 -> pitch" scaled by the mod wheel, a classic
    controllable-vibrato pattern -- turn the wheel up to bring in an
    already-configured LFO depth rather than routing the wheel directly to
    pitch). Originally found narrowly on ``fixed`` routes and assumed to be
    a `fixed`-only mechanism; the survey showed that was just the first
    example encountered, not the whole feature. ``aux_inverted`` (rare, 2.8%
    of aux-paired routes, always literally "on" when present) flips the aux
    source before it scales ``amount``. **Combination formula confirmed
    2026-07-31** via automated audio-rendering measurement (see
    docs/PARAMETER_SCHEMA.md item 14): ``effective_amount = amount *
    (aux_value / 100)``, or with ``aux_inverted=True``, ``effective_amount =
    amount * (1 - aux_value / 100)`` -- a clean linear percentage scale,
    verified by sweeping an aux macro's own value 0/25/50/75/100 and
    measuring the resulting filter cutoff shift. A rarer curve-shaping param
    (``kParamAuxCurve``) exists but is basically never used in real content
    (0.16% of aux-paired routes) and isn't exposed here -- the linear
    formula above is what applies whenever it's absent, i.e. essentially
    always.
    """

    source: str = Field(
        description=(
            "'lfo0'..'lfo9', 'macro0'..'macro7', 'velocity', 'mod_wheel', "
            "'pitch_bend', 'key_track', 'aftertouch', 'poly_aftertouch', "
            "'env0'..'env3', 'random1', 'random2', 'random_discrete', "
            "'release_velo', 'active_voices', 'voice_index', 'voice_mod1', "
            "'voice_mod2', 'fixed' (a constant offset, see class docstring), "
            "'note_on_alt', 'note_on_alt2', 'expr_pan', 'expr_timbre', "
            "'expr_press', 'oscillator0'..'oscillator4', 'filter0'/'filter1' "
            "(self-modulation sources), or 'lfo1_y' (LFO slot 2's Y-axis output, "
            "see class docstring)"
        )
    )
    destination: str = Field(description="e.g. 'filter0.cutoff', 'oscillator0.pitch', 'env0.decay'")
    amount: float = Field(0.0, ge=-100.0, le=100.0)
    bipolar: bool = False
    aux_source: str | None = Field(
        None,
        description="Optional second source (same vocabulary as `source`) that scales/"
        "gates how much of `amount` reaches `destination` -- Serum's 'Aux'/'Via' system, "
        "see class docstring. Most commonly 'mod_wheel' or 'aftertouch' for expressive, "
        "player-controllable modulation depth. Leave unset for an ordinary route with no "
        "aux scaling (the common case).",
    )
    aux_inverted: bool = Field(
        False,
        description="Only meaningful when aux_source is set -- presumably inverts the aux "
        "source's scaling effect. Leave False unless deliberately matching a specific "
        "real reference preset's behavior.",
    )


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
        0.5,
        ge=0.0,
        le=1.0,
        description="normalized step rate -- UNCERTAIN real musical meaning (note "
        "division? Hz?). IMPORTANT, found live: for shape='pattern' specifically, low "
        "values (this field's old default of 0.25) made the pattern appear stuck/"
        "frozen on its first note -- confirmed via an isolated diagnostic that the SAME "
        "pattern only advanced through its steps once rate was raised to ~0.5. Keep "
        "rate at 0.5 or above for shape='pattern' unless you've specifically verified a "
        "lower value still steps through live; algorithmic shapes don't show this "
        "issue.",
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
        description="effects, across all 3 of Serum's fx racks -- see FxUnitSpec.rack. "
        "Almost always just rack 0 (a single serial chain); only use rack 1/2 for a "
        "genuinely separate PARALLEL signal path. Editing an existing preset: only the "
        "racks actually represented among this list's entries get replaced -- a rack "
        "with zero entries here is left untouched, so you don't need to know about "
        "(or accidentally wipe) a rack you didn't intend to touch. Mod routes address "
        "entries by their position in THIS flat list ('fx0.wet' = fx_chain[0]), "
        "regardless of which rack they're in. Cap raised from an earlier 12 after "
        "finding real third-party presets with up to 19 units in one rack; a preset "
        "using multiple racks can have more total units than that across all of them. "
        "This is a technical ceiling, not a recommendation: most good presets use far "
        "fewer, see server.py's generation guidance.",
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
