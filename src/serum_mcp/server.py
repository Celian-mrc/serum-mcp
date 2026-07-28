"""MCP server entry point: exposes generate_preset, edit_preset,
list_parameters and describe_preset over stdio for Claude Code / Claude
Desktop / any MCP client.

Sound design happens in the calling model (you), not inside this server:
generate_preset/edit_preset take a structured PresetSpec, not a free-text
description. There is no LLM call anywhere in this package -- translating a
user's natural-language request into a PresetSpec is entirely your job,
guided by the docstrings below and list_parameters()/describe_preset().
This keeps the tool usable from any MCP client's existing model without a
separate, separately-billed API call.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from serum_mcp.generation.spec import PresetSpec
from serum_mcp.tools.analyze_sample_file import analyze_sample_file as _analyze_sample_file
from serum_mcp.tools.describe_preset import describe_preset as _describe_preset
from serum_mcp.tools.edit_preset import edit_preset as _edit_preset
from serum_mcp.tools.generate_preset import generate_preset as _generate_preset
from serum_mcp.tools.list_parameters import list_parameters as _list_parameters
from serum_mcp.tools.list_sample_files import list_sample_files as _list_sample_files

mcp = FastMCP(
    name="serum-mcp",
    instructions=(
        "Generate, edit and save Xfer Serum 2 (.SerumPreset) files. Presets "
        "are written directly to the user's configured Serum presets folder "
        "(see SERUM_PRESETS_PATH) as valid .SerumPreset files -- no DAW, "
        "plugin host, or audio rendering is involved at any point.\n\n"
        "You (the calling model) are responsible for sound design: turn the "
        "user's natural-language request into a PresetSpec yourself -- this "
        "server has no LLM of its own. Call list_parameters() first if "
        "you're unsure of a valid range or enum value. Guidelines:\n"
        "- Prefer Osc A (index 0) as the primary source unless the request "
        "clearly calls for layering ('fat', 'wide', 'detuned stack').\n"
        "- oscillators[] index 3 is always Noise (use noise_type, one of "
        "list_parameters()['noise_oscillator']['kParamNoiseType']['enum_values']) "
        "and index 4 is always Sub (use sub_shape, one of "
        "list_parameters()['simple_sub_shapes']); wavetable/table_position/warp_amount/"
        "warp_mode only apply to indices 0-2. IMPORTANT: when using 2+ oscillators, give "
        "them DIFFERENT wavetable values (one of list_parameters()['simple_wavetables']) "
        "-- they default to the same table ('default'), which sounds thin/undifferentiated "
        "when layered; picking different tables per layer is what makes a stack sound rich. "
        "unison/detune (indices 0-2) thicken a single oscillator -- use for 'fat', 'wide', "
        "'supersaw'-style requests. warp_mode "
        "(one of list_parameters()['simple_warp_modes']) picks the wavetable warping "
        "character -- 'fm'/'am' for classic FM/AM timbres, 'sync' for aggressive sync "
        "leads, 'pwm' for pulse-width sounds, 'fold'/'soft_clip'/'hard_clip' for "
        "distortion character, 'quantize' for lo-fi/digital, 'filter_lpf'/'filter_hpf' "
        "for a built-in tilt.\n"
        "- oscillators[].custom_harmonics (indices 0-2) SYNTHESIZES a new wavetable from "
        "scratch instead of using `wavetable`: a list of frames, each frame a list of "
        "harmonic amplitudes (index 0 = fundamental, index 1 = 2nd harmonic, ...). Use "
        "ONLY when the user wants a genuinely custom/unusual timbre the curated "
        "`wavetable` list can't cover -- it's slower and less proven than the curated "
        "tables, so don't reach for it by default.\n"
        "- If the user references their own sample bank/drumkit without naming an exact "
        "file ('use one of my kicks', 'grab a bell from my drumkits'), call "
        "list_sample_files(directory) first to see what's actually there and pick a "
        "specific path by filename/folder context (and duration, for .wav) -- don't "
        "guess a path. If they have SAMPLE_BANK_PATH configured, list_sample_files() "
        "with no directory argument uses it -- call it proactively (even without an "
        "explicit mention of their sample bank) whenever a request would clearly "
        "benefit from a real one-shot. Category folders are usually reliably named, but "
        "filenames *within* a category often aren't -- if list_sample_files leaves "
        "several plausible .wav candidates you can't distinguish by name, call "
        "analyze_sample_file(path) on a few of them (not all -- it's per-file signal "
        "processing) to get brightness/texture/pitch and pick the best fit.\n"
        "- STRONG DEFAULT, found via real user feedback across multiple banks: if a "
        "preset role NAMES A REAL ACOUSTIC INSTRUMENT OR A DEDICATED FX RECORDING "
        "(guitar, piano, violin, choir, brass, flute, mallet/music-box, riser/impact, "
        "...), PREFER a real one-shot via sample_playback_source over wavetable "
        "synthesis -- don't just check as a first step and fall back readily, actually "
        "prefer it. A user who A/B'd a whole bank reported liking every real-sample "
        "preset and disliking nearly every synthesized one (a synthesized 'guitar pluck' "
        "read as neither a guitar nor a pluck; a synthesized 'riser' was unconvincing "
        "next to an actual riser recording). Only reach for wavetable synthesis by "
        "default for roles that are genuinely ABSTRACT/ELECTRONIC in character -- pads, "
        "drones, distorted leads, arps -- where 'synthetic' is the correct character, "
        "not a compromise. If no configured sample bank exists or truly nothing "
        "plausible turns up after checking, synthesis is the fallback, not the first "
        "choice, for instrument/FX-named roles.\n"
        "- When layering oscillators (indices 0-2) as a primary+secondary pair, don't "
        "make the secondary layer's volume so low it's inaudible under the primary -- "
        "found via real user feedback: a secondary layer at 0.2 under a primary at 0.8 "
        "registered as basically silent. If it's meant to be audibly heard (adding "
        "harmonic color, a supporting texture), keep it within roughly half to two-"
        "thirds of the primary's volume; only go quieter than that for a deliberately "
        "subliminal 'harmonic dust' effect, and say so in the description if that's the "
        "intent.\n"
        "- WHEN COMBINING MULTIPLE sample_playback_source LAYERS specifically (as "
        "opposed to wavetable oscillators, which are roughly level-normalized to each "
        "other), don't set their relative volume by ear/guess -- call "
        "analyze_sample_file(path) on each candidate FIRST and check peak_dbfs/rms_dbfs. "
        "Found live: two one-shots from different sample packs measured 18dB apart in "
        "RMS despite being given similar volume values (0.55 vs 0.75) -- the quieter-"
        "recorded file was nearly inaudible even alone, let alone under the other "
        "layers. Raw one-shot libraries are NOT gain-matched to each other; a layer's "
        "OscillatorSpec.volume has to compensate for its source file's own recorded "
        "level, not just express the creative balance you want. Roughly: if two "
        "candidate files differ by Xdb in rms_dbfs, their volume values need to differ "
        "by about that same amount in the OPPOSITE direction to sound equally present "
        "before you apply any deliberate creative emphasis on top.\n"
        "- SAME CHECK FOR PITCH, not just level, when layering multiple pitched "
        "sample_playback_source one-shots meant to blend as one tone/chord (less "
        "important for a one-shot that's clearly atmospheric/unpitched FX, e.g. a riser "
        "or room tone): SampleOsc has no configurable root note, so each layer sounds "
        "at whatever pitch its own recorded content actually is when C5 is played -- "
        "there's no guarantee two one-shots from different sample packs agree. Check "
        "analyze_sample_file's pitch_hz on each candidate (don't fully trust "
        "embedded_metadata's root_note for this -- found live, 3 unrelated files in the "
        "same pack all reported the identical root_note, i.e. it was a batch default, "
        "not a per-file measurement). oscillators[].semitone gives a static +/-12 "
        "semitone correction independent of octave -- use it to align a mismatched "
        "layer to the others' pitch class instead of leaving them clashing (e.g. a "
        "tritone apart) or assuming a whole-octave shift via `octave` is precise enough.\n"
        "- CREATIVE DIFFERENTIATION, found via real user feedback: when generating "
        "multiple presets/banks in one session, especially across different genres or "
        "styles, don't reskin an earlier preset by tweaking envelope/FX wet% while "
        "reusing the same wavetable+warp_mode combination -- two 'bell' presets for two "
        "different aesthetics (e.g. an aggressive genre vs. a delicate one) should sound "
        "meaningfully different, not like the same recipe with different reverb. Before "
        "finalizing a preset that echoes an earlier one's role (bell, pad, lead, ...), "
        "actively vary the underlying palette: a different wavetable pairing, "
        "custom_harmonics for a genuinely custom spectrum, or (per the instruction above) "
        "a real sample -- not just different knob values on the same ingredients.\n"
        "- oscillators[].sample_source (indices 0-2) SYNTHESIZES a wavetable by slicing "
        "a user-provided audio file (absolute path to a WAV) into sample_frames evenly-"
        "spaced frames -- use ONLY when the user explicitly wants a synthesized/morphing "
        "texture derived from their own sample. This is NOT sample playback -- it'll "
        "sound buzzy/synthesized, not like the original one-shot played back cleanly. If "
        "the user wants the sample to still sound recognizably like itself ('use this "
        "exact drum hit', 'keep the vocal chop's character'), use "
        "oscillators[].sample_playback_source instead.\n"
        "- oscillators[].sample_playback_source (indices 0-2) uses Serum's actual "
        "SAMPLE-PLAYBACK engine (SampleOsc) instead of the wavetable engine: an absolute "
        "path to a WAV file, played back preserving its own recorded character. Use this "
        "for 'turn this one-shot/drum hit/vocal chop into a preset', 'layer this sample "
        "with a synth pad', or anything implying the sample itself should still be "
        "recognizable -- combine with other oscillator slots (WT/Noise/Sub) plus "
        "filters/envelopes/FX for a complete preset around it. sample_loop defaults to "
        "'off' (true one-shot, right for drums/percussion); set it to 'forward'/"
        "'ping_pong'/'tailed' with sample_loop_start/end if the user wants it to sustain "
        "like a held note. Only .wav is supported. Takes priority over wavetable/"
        "custom_harmonics/sample_source if set. Plays back at its original recorded "
        "pitch/speed when C5 is played (confirmed) -- mention this if the user is "
        "layering it with other oscillators and pitch/tuning matters, since C5 is the "
        "reference note, not C3/C4. IMPORTANT, found via real user question: pitch and "
        "duration are coupled with no way to decouple them (classic sampler 'resampling' "
        "behavior, not time-stretching) -- a note played higher reads through the sample "
        "faster/shorter, lower reads slower/longer, same as FL Studio's own one-shot "
        "channels in non-time-stretch mode. If the user wants to play a MELODY across "
        "several notes with this one-shot, proactively mention this up front (each note "
        "will have a different length/character) -- it's an inherent Serum engine "
        "property, not something any preset setting fixes. sample_loop only sustains the "
        "*looped* portion regardless of pitch, not the initial attack. "
        "sample_center_pan (default true) gain-balances a stereo file's channels to fix "
        "an off-center mic bias in the original recording (real one-shots often have "
        "one) without altering either channel's actual content -- leave it on unless the "
        "user specifically wants the file preserved exactly as recorded.\n"
        "- filters[].type must be one of list_parameters()['simple_filter_types']; "
        "cutoff is 0.0 (closed)..1.0 (open), not Hz.\n"
        "- fx_chain[].type must be a name from list_parameters()['fx_type_ids']; "
        "fx_chain[].params keys are raw kParam* names valid for that type.\n"
        "- mod_routes[].source is 'lfo0'..'lfo9' or 'macro0'..'macro7' only "
        "(other sources aren't wired up yet); destination is a key from "
        "list_parameters()['mod_dest_targets'] (e.g. 'filter0.cutoff', "
        "'lfo1.rate', 'macro0.value'), OR 'fx{i}.wet' where i is a 0-based index "
        "into THIS SAME CALL's fx_chain (e.g. fx_chain[0] -> 'fx0.wet'; errors if "
        "that FX type has no wet knob, e.g. FXEQ). Use for vibrato (LFO -> "
        "oscillator pitch, small amount), movement (slow LFO -> filter cutoff), "
        "or a macro/LFO fading an effect in and out (LFO/macro -> 'fx{i}.wet').\n"
        "- Envelope times are seconds; macro/resonance/wet/drive are 0-100%. "
        "envelopes[].hold is a rarely-needed extra plateau at full level before "
        "decay starts, seconds -- leave at 0 unless asked for.\n"
        "- global.portamento_time (seconds) is glide between notes -- use for "
        "'glide', 'portamento', 'slide between notes' requests; 0 = off (default). "
        "global.poly_count caps simultaneous voices (default 8) -- lower it only "
        "if asked to save CPU or force fewer overlapping notes.\n"
        "- lfos[].delay (seconds) is a fade-in before the LFO starts after note-on "
        "-- use for 'vibrato that kicks in after a moment'. lfos[].smooth (%) "
        "softens steppy/random LFO shapes into something glidey. lfos[].beat_sync "
        "ties rate to tempo instead of free Hz."
    ),
)


@mcp.tool()
def generate_preset(spec: PresetSpec, subfolder: str | None = None) -> str:
    """Write a new Serum 2 preset built from ``spec`` to the user's Serum
    presets folder.

    Build ``spec`` yourself from the user's natural-language description
    (see server instructions for the mapping guidelines). Any section left
    empty (e.g. no ``filters``) keeps that module at its default, inert
    state -- you don't need to fill in every field, only what the sound
    calls for.

    Pass ``subfolder`` (e.g. "RAGE Bank") to group a themed set of presets
    generated together into their own nested folder instead of writing them
    flat into the presets root -- call generate_preset once per preset with
    the same subfolder name. Omit for a single/one-off preset.

    Returns the absolute path of the written .SerumPreset file.
    """
    return _generate_preset(spec, subfolder=subfolder)


@mcp.tool()
def edit_preset(preset_path: str, spec: PresetSpec) -> str:
    """Apply a partial ``spec`` update to an existing .SerumPreset file, in place.

    Call describe_preset(preset_path) first to see the current state, then
    only include the sections/indices in ``spec`` that should change --
    e.g. to just brighten the filter, pass ``filters=[FilterSpec(cutoff=0.8, ...)]``
    and leave everything else empty; it will be left untouched.

    Returns the absolute path of the edited file (same as ``preset_path``).
    """
    return _edit_preset(preset_path, spec)


@mcp.tool()
def list_parameters() -> str:
    """Return the full documented Serum 2 parameter schema (modules, value
    ranges, units, enum values, and how confidently each was verified) as
    JSON.

    Call this before proposing an edit so you know what parameter names and
    ranges are actually valid.
    """
    return _list_parameters()


@mcp.tool()
def describe_preset(preset_path: str) -> str:
    """Return a human-readable summary of an existing preset's sound-shaping
    parameters (oscillators, filters, envelopes, FX chain, mod routes, globals)."""
    return _describe_preset(preset_path)


@mcp.tool()
def list_sample_files(directory: str | None = None, recursive: bool = True) -> str:
    """List audio files under ``directory`` (e.g. a drumkit/sample bank
    folder) as JSON: path, name, extension, size, and -- for ``.wav`` files
    -- duration/sample_rate/channels.

    Call this when the user references their own sample bank/drumkit
    without naming an exact file ("use one of my kicks", "grab a bell from
    my drumkits"), so you can pick a specific file by name/folder context
    (and duration, for .wav) to pass as
    ``oscillators[].sample_playback_source`` or ``sample_source``, instead
    of guessing a path.

    ``directory`` is optional: if omitted, this falls back to the user's
    configured default sample bank (the ``SAMPLE_BANK_PATH`` environment
    variable) -- if the user has that set, you can call this proactively
    (no directory argument) when a request would clearly benefit from one
    of their own one-shots even if they didn't explicitly mention their
    sample bank (e.g. "make me a bell melody" -- check whether they have a
    fitting bell one-shot before defaulting to pure synthesis). If neither
    an explicit directory nor a configured default is available, this
    raises an error -- don't guess a path.
    """
    return _list_sample_files(directory, recursive=recursive)


@mcp.tool()
def analyze_sample_file(path: str) -> str:
    """Compute lightweight acoustic descriptors for one .wav one-shot as
    JSON: peak_dbfs/rms_dbfs, brightness (dark/warm/bright/airy), texture
    (tonal/mixed/noisy), a gated pitch estimate (note name or null if
    unpitched/untrustworthy), attack time, sustain ratio, duration, and an
    embedded_metadata field.

    Call this on a handful of specific candidate files (not in bulk -- it
    does real signal processing per file) when filenames within a sample
    bank category aren't descriptive enough to pick between them by name
    alone (category folders like "Pluck"/"Bell"/"Key" are usually reliable;
    individual filenames within them often aren't). This never guesses an
    instrument name ("this is a kick") -- only report the objective
    descriptors back, and combine them with the filename/folder yourself.

    Also call this on EVERY file before combining multiple
    sample_playback_source layers in one preset: peak_dbfs/rms_dbfs exist
    specifically because raw one-shot libraries aren't gain-matched to each
    other (found live, an 18dB RMS gap between two one-shots given similar
    volume values left one nearly inaudible) -- use them to set each
    layer's volume, don't guess from the filename/description alone.

    embedded_metadata (not universal -- empty dict when absent) surfaces
    root_note/root_note_midi and, if the file's creator embedded sample-
    accurate loop points, loop_start_percent/loop_end_percent -- real
    human-authored tags read straight from the file's own RIFF chunks, a
    stronger signal than any DSP estimate above. When present, prefer
    embedded_metadata's loop_start_percent/loop_end_percent over guessing
    your own sample_loop_start/sample_loop_end, and consider its root_note
    if the user cares about the sample's original recorded pitch.
    """
    return _analyze_sample_file(path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
