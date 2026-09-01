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
from mcp.types import ToolAnnotations

from serum_mcp.generation.spec import PresetSpec
from serum_mcp.tools.analyze_sample_file import analyze_sample_file as _analyze_sample_file
from serum_mcp.tools.describe_preset import describe_preset as _describe_preset
from serum_mcp.tools.edit_preset import edit_preset as _edit_preset
from serum_mcp.tools.find_reference_presets import (
    find_reference_presets as _find_reference_presets,
)
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
        "warp_mode only apply to indices 0-2. sub_shape's own SCHEMA default is 'saw' "
        "(harmonically bright/aggressive), but leaving it unset is safe: mapping.py omits "
        "the underlying param entirely at that default rather than writing it explicitly "
        "-- found live 2026-07-30 that a real preset's Sub is essentially NEVER touched "
        "away from Serum's own true default (0% presence across an 896-preset survey), "
        "and explicitly writing 'saw' gave a layered bass harsh/piercing highs the real "
        "preset didn't have. For 'clean'/'warm'/'deep' sub-bass reinforcement (the most "
        "common ask for this slot), either leave sub_shape unset or pass 'triangle' "
        "explicitly (closest to a pure tone) -- both are clean; reserve 'saw'/'square'/"
        "'pulse' for when the user explicitly wants an aggressive/present/buzzy sub "
        "character.\n"
        "IMPORTANT: when using 2+ oscillators, give "
        "them DIFFERENT wavetable values (one of list_parameters()['simple_wavetables']) "
        "-- they default to the same table ('default'), which sounds thin/undifferentiated "
        "when layered; picking different tables per layer is what makes a stack sound rich. "
        "unison/detune (indices 0-2) thicken a single oscillator -- use for 'fat', 'wide', "
        "'supersaw'-style requests.\n"
        "- wavetable ISN'T LIMITED TO THE 12-NAME CURATED LIST -- found live 2026-08-05 "
        "after a user noticed generated banks kept reaching for the same few tables: "
        "`simple_wavetables` is a small friendly-name subset, but the real Serum install "
        "ships ~300+ actual wavetable files (this project's own Tables folder, "
        "config.get_tables_dir()), and `wavetable` accepts a real Tables-relative path "
        "DIRECTLY as a string, not just the 12 curated names (mapping.py already falls "
        "back to resolving it as a real file when it's not a curated name -- this existed "
        "for edit_preset round-tripping but was never mentioned as a generation option "
        "before). This unlocks REAL variety, including tables that sound like specific "
        "instruments/characters the curated list has no equivalent for -- e.g. "
        "'S2 Tables/Digital/Piano.wav', 'S2 Tables/Digital/RMrk1.wav' (Rhodes Mark 1), "
        "'S2 Tables/Digital/Wuuurli.wav' (Wurlitzer), 'S2 Tables/Digital/Braids Bell "
        "Pluck.wav', 'Vowel/DudaChoir.wav' (a real vowel-formant choir table -- a much "
        "more genuine vocal character than approximating one with a formant FILTER), "
        "'S2 Tables/Digital/Brass Stab.wav', 'S2 Tables/Digital/Xylo Pluck.wav'. When a "
        "request names a specific instrument/character (Rhodes, Wurlitzer, choir, bell, "
        "brass, ...), check whether a real table matches that name/character BEFORE "
        "reaching for a generic curated table + warp_mode approximation -- it's often a "
        "closer, more distinctive match and costs nothing extra to try. Exact file names "
        "aren't enumerated anywhere in this server (there are hundreds); if unsure what's "
        "available, a real Tables-relative path either resolves or raises a clear 'file "
        "not found' error naming the path it tried -- safe to attempt speculatively for a "
        "plausible name. This is also the fix for 'presets all sound similar' complaints "
        "when the curated 12 aren't cutting it: actively vary between curated names AND "
        "real Tables paths across a themed set, don't default to the same 3-4 curated "
        "tables every time.\n"
        "- warp_mode "
        "(one of list_parameters()['simple_warp_modes']) picks the wavetable warping "
        "character -- 'fm'/'am' for classic FM/AM timbres, 'sync' for aggressive sync "
        "leads, 'pwm' for pulse-width sounds, 'fold'/'soft_clip'/'hard_clip' for "
        "distortion character, 'quantize' for lo-fi/digital, 'filter_lpf'/'filter_hpf' "
        "for a built-in tilt. warp_mode2/warp_amount2 (indices 0-2, optional -- leave "
        "warp_mode2 unset for the common single-warp-lane case) add a SECOND warp stage "
        "applied after the first -- found live 2026-07-29 in real content, e.g. "
        "warp_mode='fm'/'kFM_NOISE' (raw/digital-sounding on its own) THEN "
        "warp_mode2='filter_lpf' to tame it into something musical. Use this pairing "
        "whenever a raw/FM/noise/digital primary warp shouldn't sound harsh -- an "
        "unmodeled second lane was found live to be the difference between 'harsh 8-bit "
        "noise' and the intended character for an otherwise-identical oscillator.\n"
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
        "choice, for instrument/FX-named roles. Caveat found analyzing a real "
        "professional bank (Unmüte 'Places', 180 presets, ambient/emotional style): it "
        "used real sample playback in essentially none of its presets, synthesizing "
        "convincing guitar/string-named sounds from wavetables alone -- so real-sample "
        "preference isn't a universal law, it's specifically this project's own users' "
        "consistent feedback on their own banks. Keep following it as the default here, "
        "but it's a taste/context finding, not evidence that synthesis can't work well in "
        "skilled hands. RECURRED live 2026-08-14 on the EXACT named example above: a "
        "generated 'PL - Warm Guitar Pluck' used a synthesized wavetable + custom_harmonics "
        "instead of `multisample_source='guitar_ac'` (a real curated Factory acoustic "
        "guitar multisample that was available the whole time) -- the user asked directly "
        "why a real guitar sample wasn't used, and the honest answer was an execution "
        "miss, not a tool limitation. This means checking `sample_playback_source` "
        "(user one-shots) alone isn't enough -- for an instrument-named role, ALSO check "
        "`multisample_source`'s curated list (brass_french_horn, choir_ah, "
        "epiano_suitcase, guitar_ac, mallet_balafon, piano_grand, strings_full, "
        "synth_pad_superjx, synth_sid, violins) before defaulting to synthesis, even "
        "when no user-provided sample bank exists -- it needs no external file at all. "
        "MAKE THIS AN EXPLICIT PRE-GENERATION CHECK, not just background awareness: "
        "before choosing an oscillator engine for an instrument-named role, run down "
        "BOTH lists (sample_playback_source candidates via list_sample_files, AND the "
        "multisample_source curated names above) and only fall back to wavetable/"
        "custom_harmonics synthesis once both are confirmed to have no fit.\n"
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
        "- SAME CHECK ACROSS ENGINES, not just between sample_playback_source layers: "
        "found live, a preset combining an octave-corrected sample layer (e.g. "
        "oscillators[0].octave=-1 to compensate for a one-shot's embedded root note vs "
        "SampleOsc's fixed C5 reference) with an UNCORRECTED Sub/wavetable oscillator "
        "meant to reinforce the same fundamental played a full octave apart -- the Sub "
        "sounded clearly, jarringly higher than the sample layer it was supposed to sit "
        "underneath. octave/semitone corrections only affect the oscillator they're set "
        "on; if a non-sample layer is meant to track a sample_playback_source layer's "
        "corrected pitch, apply the SAME octave/semitone offset to it too, not just to "
        "the sample layer.\n"
        "- A Sub layer (oscillators[4]) only makes sense if the preset is actually played "
        "in a low/bass register -- found live, a sample_playback_source-based preset "
        "auditioned around F#6 (a high note) still sounded shrill with the Sub matched to "
        "the sample layers' pitch, and even at octave=-4 (the most negative allowed) it "
        "only just reached true sub range while losing all rhythmic punch/relevance -- "
        "removing the Sub entirely was the right call, not chasing a 'correct' tuning for "
        "it. Before adding a Sub, check what register the preset is actually meant to be "
        "played in (ask if unclear); don't add one by default just because a bass-ish "
        "request came in if the instrument is voiced/played higher than true bass range.\n"
        "- CREATIVE DIFFERENTIATION, found via real user feedback: when generating "
        "multiple presets/banks in one session, especially across different genres or "
        "styles, don't reskin an earlier preset by tweaking envelope/FX wet% while "
        "reusing the same wavetable+warp_mode combination -- two 'bell' presets for two "
        "different aesthetics (e.g. an aggressive genre vs. a delicate one) should sound "
        "meaningfully different, not like the same recipe with different reverb. Before "
        "finalizing a preset that echoes an earlier one's role (bell, pad, lead, ...), "
        "actively vary the underlying palette: a different wavetable pairing, "
        "custom_harmonics for a genuinely custom spectrum, or (per the instruction above) "
        "a real sample -- not just different knob values on the same ingredients. THIS "
        "APPLIES ACROSS SEPARATE BANKS IN THE SAME SESSION, NOT JUST WITHIN ONE -- found "
        "live 2026-08-05: a second bank (drill-style) generated after an earlier one "
        "(Yeat-style) reused the exact same wavetable+warp_mode+distortion-mode combo on "
        "8 of 16 presets (a hard-clipped 808 on the literal same 'Filthy' table, a bell "
        "pluck on the literal same 'Xylo Pluck' table, an identical 3-oscillator "
        "semitone-stack chord recipe, ...) despite each bank's own presets being "
        "internally varied -- the repetition was invisible within either bank alone, "
        "only visible comparing across them, and 'I designed each one thinking about "
        "variety' was not enough to catch it without an active check. Before finalizing "
        "a wavetable/technique choice for a themed bank, call "
        "find_reference_presets(role or wavetable keyword) -- it already searches the "
        "user's own Presets/User folder including every prior bank this project "
        "generated (flagged via is_serum_mcp_generated) -- specifically to see if an "
        "earlier self-generated preset already used that exact table/technique, not just "
        "to find genuine external references.\n"
        "- DON'T ADD 'FX -' ROLE PRESETS (one-shot risers/impacts/sweeps/transition "
        "sounds, as opposed to fx_chain -- the EFFECTS UNITS inside every preset, a "
        "completely different thing) TO A BANK UNLESS SPECIFICALLY REQUESTED -- found "
        "live 2026-08-05, direct user feedback on a generated 20-preset bank that "
        "included 2 'FX -' one-shots unprompted: 'quand on lui demande de créer une "
        "bank il ne doit pas créer de FX à part si c'est demandé.' A request for a "
        "themed bank/set of presets in a genre or artist's style defaults to PLAYABLE "
        "INSTRUMENT roles (bass, lead, pad, pluck, chords, keys) -- a riser/impact/"
        "transition one-shot is a materially different kind of thing (not meant to be "
        "played melodically) and is its own separate ask, not a default filler category "
        "to round out a role spread. Only include one when the user's own request "
        "mentions transitions/risers/impacts/sweeps, or explicitly asks for FX-type "
        "content.\n"
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
        "- oscillators[].granular_source (indices 0-2, confirmed live 2026-07-30 in real "
        "Serum 2) uses Serum's GRANULAR engine (GranularOsc): an absolute path to a WAV "
        "file, continuously re-triggered as short randomizable 'grains' instead of played "
        "back straight -- for pads/textures/soundscapes built FROM a sample (a field "
        "recording, a vocal, a drone, an ambient texture) rather than the sample staying "
        "recognizable as itself (use sample_playback_source for that instead). "
        "granular_density (0-30, higher = denser/smoother cloud, SAME scale as Serum's "
        "own DENS knob), granular_grain_length (MILLISECONDS, e.g. 100-150ms is a "
        "musically reasonable range -- confirmed against a real Factory preset), "
        "granular_random_pitch/pan/grain_length add organic variation between grains -- 0 "
        "on all three gives a robotic/uniform-sounding cloud, real presets almost always "
        "randomize at least pan and grain length. warp_amount/warp_mode also apply "
        "(shared with sample_playback_source/wavetable). Takes priority over wavetable/"
        "custom_harmonics/sample_source, but sample_playback_source takes priority over "
        "this if both are set on the same oscillator. Only .wav is supported.\n"
        "- oscillators[].spectral_source (indices 0-2, confirmed live 2026-07-30 -- "
        "warp_mode='kGate' produced the expected robotic/gated character; "
        "freq_lo/freq_hi confirmed correct as literal Hz via automated audio rendering "
        "2026-07-31; filter_shift/filter_wet remain unverified, treat with more caution) "
        "uses Serum's SPECTRAL engine (SpectralOsc): an absolute path "
        "to a WAV file, resynthesized through FFT/spectral-domain processing (gating, "
        "robotizing, vocoding, spectral shifting, Shepard-tone effects, see warp_mode) -- "
        "for glitchy/robotic/vocoder/otherworldly textures specifically, a different "
        "character than granular_source's grain clouds or sample_playback_source's "
        "straight playback. warp_mode for this engine does NOT use the curated "
        "list_parameters() warp-mode names -- pass Serum's raw name directly, e.g. "
        "'kGate', 'kSmear', 'kRobotize', 'kSpectralShift', 'kVocode_OSC', 'kMask_OSC', "
        "'kShepardFilter'. spectral_warp_freq_lo/freq_hi (Hz) narrow which frequency "
        "band the effect applies to. IMPORTANT LIMITATION: real SpectralOsc content "
        "commonly has a hand-drawn spectral filter curve this project can't generate "
        "yet -- a generated one always has a flat/neutral spectral response, only the "
        "frequency-range and warp controls are real; mention this if the user's request "
        "implies a specific spectral shape. Takes priority over wavetable/"
        "custom_harmonics/sample_source, but sample_playback_source/granular_source take "
        "priority over this if set on the same oscillator. Only .wav is supported.\n"
        "- oscillators[].multisample_source (indices 0-2, one of "
        "list_parameters()['multisample_instruments'] -- check that call for the current "
        "list, don't assume a fixed set: 10 as of 2026-08-01 spanning choir/synth/guitar/"
        "violins/piano/full-strings/french-horns/synth-pad/balafon/electric-piano) uses "
        "Serum's MULTISAMPLE engine (MultiSampleOsc) with a CURATED real Factory "
        "multisample instrument -- for requests wanting a REALISTIC sampled instrument "
        "(choir, guitar, strings, piano, brass, ...) rather than a synthesized/textural "
        "source. Unlike sample_playback_source (one recording played across the whole "
        "keyboard), this plays the correct sample per note/keyzone with proper pitch, "
        "exactly as Xfer's own sound designers configured it -- confirmed live 2026-07-31 "
        "(rendering the same instrument an octave apart produced pitches exactly an "
        "octave apart, confirming real per-note sample selection). Only pre-curated "
        "instruments are selectable (arbitrary user sample files aren't supported for "
        "this engine -- use sample_playback_source or "
        "granular_source for a user-provided file instead). multisample_env_attack/decay/"
        "release (seconds, short range) are an OSC-level envelope layered on the "
        "instrument's own baked-in sample envelope, NOT a substitute for the main Env0-3 "
        "envelope. Takes priority over wavetable/custom_harmonics/sample_source, but "
        "sample_playback_source/granular_source/spectral_source take priority over this "
        "if set on the same oscillator. Experimental -- prefer test-in-serum before "
        "declaring a multisample preset done.\n"
        "- filters[].type must be one of list_parameters()['simple_filter_types']; "
        "cutoff is 0.0 (closed)..1.0 (open), not Hz. filters[].var ('Var' knob) means "
        "something DIFFERENT per filter type -- comb spacing for comb-family types, "
        "formant blend for formant types, etc -- and defaults to 0, which found live "
        "2026-07-29 produced a harsh/aliased/'digital' character for a comb filter "
        "specifically (a real reference preset had var=65, not 0). For 'comb', "
        "'formant', or other exotic/character filter types, don't leave var at its "
        "default without a reason -- check a real reference value if you have one, or "
        "pick something clearly nonzero and mention the uncertainty. filters[]."
        "key_track (cutoff follows the played note's pitch) and filters[].wet (this "
        "filter's own dry/wet, separate from fx_chain) are also available but usually "
        "fine left at their defaults (off / fully wet). filters[].output_routing "
        "('parallel'/'series'/unset) controls whether 2 simultaneous filters each go "
        "straight to output (parallel, Serum's real default -- leave unset, don't set "
        "'parallel' explicitly for no reason) or cascade into each other (series) -- "
        "only reach for 'series' when a genuinely cascaded dual-filter chain is wanted "
        "(e.g. matching a real reference preset that uses it); setting BOTH filters to "
        "'series' raises an error (routing cycle). oscillators[].filter_routing "
        "('filter'/'master'/'direct'/'none'/unset) is the INPUT-side counterpart -- which "
        "path a given OSCILLATOR's own signal takes, not a filter's output. Leave unset "
        "(Serum's real default, routes through the enabled filters normally) unless "
        "deliberately bypassing the filter stage for one layer (e.g. keeping a bright "
        "transient/noise layer out of a resonant/saturating filter shaping the rest of "
        "the stack -- set that oscillator's filter_routing='master'). "
        "oscillators[].filter_balance (0-100) only matters when filter_routing='filter' "
        "(or unset) and both filters are enabled; leave unset unless matching a specific "
        "real reference value. oscillators[]/filters[].fx_bus1_send/fx_bus2_send (0-100, "
        "paired with global.fx_bus1_volume/fx_bus2_volume and global.fx_bus1_destination/"
        "fx_bus2_destination -- 'master'/'direct'/unset, where that bus's OWN processed "
        "signal rejoins) are a rarely-used aux-send system independent of the main "
        "routing above -- leave unset for ordinary presets, only reach for it when a "
        "request specifically calls for a parallel send/return chain.\n"
        "- fx_chain[].type must be a name from list_parameters()['fx_type_ids']; "
        "fx_chain[].params keys are raw kParam* names valid for that type. "
        "IMPORTANT: if using type='FXFilter', do NOT set its kParamType param -- leave it "
        "unset (Serum's own default). Found live 2026-07-30: FXFilter.kParamType's enum "
        "is an unverified copy of VoiceFilter's full ~95-entry type catalog, and setting "
        "an unconfirmed one is a plausible crash cause (see schema.FX_PARAMS['FXFilter'] "
        "for the full writeup). Every live-confirmed generated preset with an FXFilter "
        "unit left this param unset; freq/reso/drive/wet are all safe to set normally.\n"
        "fx_chain[].rack (0-2, default 0) selects which of Serum's 3 PARALLEL fx racks "
        "a unit sits in -- leave at 0 for a normal single serial chain (the vast "
        "majority of requests); only use 1/2 for an explicitly separate parallel signal "
        "path (e.g. a dry chain vs a send-style wet chain processed independently, not "
        "in series). Editing: a rack with no entries in this call's fx_chain is left "
        "untouched, so omitting rack 1/2 units when editing rack 0 won't wipe them.\n"
        "- FXDelay IMPORTANT: kParamTimeL/kParamTimeR only mean literal seconds when "
        "kParamBeatSync is ALSO passed in params as explicit False -- e.g. for a 250ms "
        "delay: params={'kParamTimeL': 0.25, 'kParamTimeR': 0.25, 'kParamBeatSync': False}. "
        "Omitting kParamBeatSync silently falls back to Serum's real default (BPM-synced/"
        "note-quantized timing, NOT literal seconds) -- a real bug found live 2026-08-01, "
        "confirmed via echo-timing measurement. Every delay-time request ('300ms echo', "
        "'quarter-note delay' being the one exception -- that one WANTS beat sync, so "
        "leave kParamBeatSync unset instead) needs this explicit False or the timing will "
        "be wrong.\n"
        "- type='FXSplit'/'FXSplit3'/'FXSplitMS' (rare -- only reach for these on an "
        "explicit 'multiband' request, e.g. 'distort just the low end' or 'compress mid "
        "and side differently') are 2/3/2-band splitters. They work entirely through "
        "ORDERING in THIS SAME fx_chain list, not a nested structure: place the split "
        "unit, then immediately after it (same rack) place that many entries for band 1, "
        "then that many for band 2, etc, matching params.kParamModuleCount1/2/(3) exactly "
        "to how many units you actually placed in each band -- e.g. a 2-band split with 1 "
        "distortion unit on the low band and nothing on the high band is "
        "[FXSplit(params={'kParamFreq': 200.0, 'kParamModuleCount1': 1.0}), FXDistortion]. "
        "FXSplit/FXSplit3 crossover at params.kParamFreq (Hz, and kParamFreq2 for "
        "FXSplit3's second crossover); FXSplitMS has no frequency (Mid/Side channel "
        "split). Any fx_chain entries left over after all bands' counts are consumed "
        "continue as normal serial processing on the recombined signal. None of the "
        "three have a wet/mix knob.\n"
        "- mod_routes[].source is one of 'lfo0'..'lfo9', 'macro0'..'macro7', "
        "'velocity', 'mod_wheel', 'pitch_bend', 'key_track', 'aftertouch', "
        "'poly_aftertouch', 'env0'..'env3', 'random1', 'random2', "
        "'random_discrete', or 'fixed' (a CONSTANT offset -- amount alone, no "
        "time-varying signal -- useful for a permanent bias on a destination, e.g. a "
        "fixed detune/tuning offset, without dedicating an LFO or macro to it); "
        "destination is a key from "
        "list_parameters()['mod_dest_targets'] (e.g. 'filter0.cutoff', "
        "'lfo1.rate', 'macro0.value'), OR 'fx{i}.wet' where i is a 0-based index "
        "into THIS SAME CALL's fx_chain (e.g. fx_chain[0] -> 'fx0.wet'; errors if "
        "that FX type has no wet knob, e.g. FXEQ). Use for vibrato (LFO -> "
        "oscillator pitch, small amount), movement (slow LFO -> filter cutoff), "
        "or a macro/LFO fading an effect in and out (LFO/macro -> 'fx{i}.wet'). "
        "'velocity' -> a destination is for 'plays louder/brighter/snappier when hit "
        "harder'-style requests -- e.g. 'velocity' -> 'filter0.cutoff' for velocity-"
        "sensitive brightness, or 'velocity' -> 'env0.attack'/'env0.decay' for a "
        "classic velocity-sensitive envelope response. GOTCHA found live 2026-08-06: "
        "'-> filter{i}.cutoff' (from velocity, a macro, an LFO, anything) only means "
        "'brighter/opens up' for lowpass/highpass-family filter types. For 'bandpass', "
        "'comb', and 'notch', cutoff is the CENTER/notch frequency of a narrow band, "
        "not an open/close threshold -- pushing it up on a hard hit moves the passband "
        "AWAY from the oscillator's actual harmonic content instead of brightening it, "
        "which can silence the note almost entirely (confirmed via serum-verify: a "
        "bandpass_12 preset went from a healthy -22dBFS to -62dBFS 'effectively "
        "silent' from nothing but adding one velocity->filter0.cutoff route at a "
        "modest amount). For these 3 filter types, prefer modulating "
        "filter{i}.resonance or oscillator{i}.volume for a 'more presence when hit "
        "harder' effect instead, or keep the cutoff-mod amount very small and check "
        "the render isn't going quiet. 'key_track' -> "
        "'filter0.cutoff' opens the filter on higher notes (common on plucks/leads "
        "so high notes don't get muffled). 'mod_wheel'/'pitch_bend' are for explicit "
        "performance-control requests (mod wheel adding vibrato/filter movement, "
        "pitch bend already has its own dedicated pitch-bend range elsewhere -- only "
        "use pitch_bend as a mod SOURCE for something unusual like bending the filter "
        "or an FX wet amount). 'random1'/'random2'/'random_discrete' (three "
        "independent per-note random generators) are for humanization -- small "
        "amounts to oscillator pan or pitch/fine so repeated notes don't sound "
        "robotically identical. 'aftertouch'/'poly_aftertouch' are for explicit "
        "'pressing harder after the note starts adds X' requests (e.g. vibrato via "
        "'aftertouch' -> a small oscillator0.pitch amount, or filter opening via "
        "'aftertouch' -> 'filter0.cutoff'); poly_aftertouch is per-note, aftertouch is "
        "per-channel -- most controllers only send channel aftertouch, so default to "
        "'aftertouch' unless the user specifically asks for per-note (MPE-style) "
        "control. 'env0'..'env3' as a SOURCE reuses that envelope's own shape to "
        "modulate something else (distinct from routing INTO env{i}.attack/decay/"
        "etc) -- e.g. 'env1' -> 'oscillator0.pitch' for a pitch envelope shaped like "
        "Env 2, useful when the user wants two different modulation shapes without "
        "spending an LFO on it. mod_routes[].aux_source (same vocabulary as source, "
        "optional) scales/gates how much of amount actually reaches destination -- for "
        "'player-controllable modulation depth' requests, e.g. 'vibrato that only "
        "kicks in when the mod wheel is up': source='lfo0' -> "
        "destination='oscillator0.pitch' with aux_source='mod_wheel' (or 'aftertouch' "
        "for pressure-controlled depth instead), rather than routing the wheel/"
        "aftertouch to pitch directly. Leave unset for an ordinary route (the common "
        "case).\n"
        "- arp turns on Serum's arpeggiator -- see ArpSpec for the full field list. "
        "Leave it UNSET (the PresetSpec default) for anything that isn't explicitly "
        "meant to arpeggiate; don't set it just because a role sounds rhythmic. Only "
        "use for requests like 'make this arpeggiate', 'add an up/down arp', 'this "
        "should play as a chord arp', 'give it a custom step pattern'. Two modes: "
        "algorithmic (shape=up_down/chord/random_.../etc, just a few knobs) for "
        "'arpeggiate my chord' style requests, and shape='pattern' with a `pattern` "
        "list of ArpPatternNoteSpec (step/note_offset/length_steps on a quantized "
        "grid) for 'give it a specific rhythm/melody' style requests where the user "
        "describes an actual sequence rather than 'just arpeggiate'. pattern_step_beats "
        "sets the grid resolution (default 0.25 = 16th notes). Don't reach for "
        "shape='pattern' by default -- it needs you to actually compose a note "
        "sequence, which is more work and more failure-prone than picking an "
        "algorithmic shape; use it only when the user's request implies a specific "
        "sequence an algorithmic mode can't produce.\n"
        "- ARP IS ITS OWN PRESET CATEGORY, NOT A VARIANT OF LEAD/PLUCK -- found live "
        "2026-08-06, direct user feedback: 'ARP est une catégorie à part, et pour les "
        "ARP il faut que le système s'inspire davantage des ARP de la bank unmute qui "
        "sont très bien.' Confirmed via find_reference_presets('arp') -- Serum's own "
        "Factory library files this under a dedicated `Arp` folder, and Unmüte's real "
        "'Places' bank names its arp presets with their own prefix "
        "(`UN_PLACES_ARP_120_<name>`) distinct from lead/pluck/pad -- so when a bank "
        "includes an arp-appropriate preset (per the genre-research nuance above), name "
        "it `ARP - <name>`, not `LD -`/`PL -`. Studying 3 of Unmüte's real ARP presets "
        "(Sky/Galaxy/Cristals) directly turned up patterns this project had never used: "
        "(1) `arp.rate` landed on 0.46 (the confirmed 1/16-note tier) in ALL THREE, a "
        "strong starting default for an 'electronic arp' character rather than guessing; "
        "(2) `arp.transpose_shift=+12` (up an octave) in all three -- also a strong "
        "default, not universal but common enough to reach for first; (3) `arp.gate`, "
        "`arp.chance`, `arp.offset`, and `arp.transpose_range` are ALL valid mod-matrix "
        "destinations (confirmed present in list_parameters()['mod_dest_targets']) and "
        "real Unmüte arps route LFOs/macros into them (e.g. `lfo2 -> arp.gate` for a "
        "breathing/evolving gate length, `macro0 -> arp.chance` for a "
        "performance-controllable step-density knob) -- this project had never modulated "
        "an arp parameter at all before finding this; (4) shape variety beyond "
        "up_down/down_up: 'played' (passes the held chord through as-is, arp becomes a "
        "chord-retrigger engine), 'converge' (sweeps inward), 'random_drift' (evolving "
        "randomization) all appeared -- prefer a shape that matches the specific texture "
        "wanted over defaulting to up_down every time; (5) these presets ran noticeably "
        "quieter (`global.master_volume` 0.10-0.13 vs. this project's usual 0.5 default) -- "
        "plausibly because their own signal chains (dense oscillator/FX layering) build "
        "up gain that needs trimming at the source; consider a lower master_volume on a "
        "densely-layered arp preset rather than leaving it at default and fixing loudness "
        "only in the FX chain.\n"
        "- DON'T ARTIFICIALLY CAP FX/FILTER/MOD-ROUTE COUNT, calibrated against a real "
        "180-preset professional bank (Unmüte 'Places'): 9-12 fx_chain units per preset "
        "is the NORM there, not an outlier, and over half its presets run 2 filters "
        "simultaneously (not 1). A preset with only 2-3 FX units and 1 filter isn't "
        "automatically 'cleaner' -- it may just be underbuilt. The real skill professional "
        "presets show is giving each unit a distinct, nameable JOB rather than piling up "
        "prominent effects: several of those FX units are typically LOW-WET utility/glue "
        "stages (a corrective EQ, a gentle compressor, a filter used for tone-shaping "
        "rather than sweep) alongside a handful of obvious character effects (reverb, "
        "delay, chorus/distortion) -- not five different reverbs/phasers all fighting for "
        "attention. Multiple FXComp/FXEQ units in sequence (mastering-chain style) is "
        "normal, not redundant. Prior guidance in this project favored small FX counts "
        "after one bad hand-built preset stacked a harsh comb filter with several loud, "
        "competing wet effects -- the actual lesson there was 'give each unit a clear "
        "purpose and don't let prominent effects clash', not 'use fewer units'; don't "
        "conflate the two. CHECK list_parameters()['role_starting_points'] for concrete "
        "per-role starting values (envelope shape, filter type/resonance, dominant "
        "warp_mode, typical mod_routes) derived the same way -- e.g. a bass role is "
        "almost always mono with a ~4ms attack/~45ms release and low filter resonance, "
        "a pluck role's defining trait is zero sustain (a real decaying pluck, not a "
        "held note), a pad role has a long (~600ms+) attack, FXComp+FXEQ anchor nearly "
        "every role's FX chain ahead of reverb/delay, and modulation is often "
        "macro-driven (performance-mappable) rather than purely LFO-driven except in "
        "pad/chord/arp roles. Check it before generating a preset whose role matches "
        "one of its categories (bass, pluck, lead, pad, chords, synth, arp, sequence) "
        "instead of guessing envelope/filter/mod-route starting values from scratch --  "
        "it's part of the same list_parameters() call already needed for valid ranges/"
        "enums, so there's no extra step. docs/SOUND_DESIGN_REFERENCE.md has the fuller "
        "prose version with sample-size caveats, for deeper reading.\n"
        "- PULL LIVE UNMUTE/FACTORY REFERENCES PER ROLE, DON'T RELY ON BAKED-IN "
        "GUIDANCE ALONE -- found live 2026-08-12, direct user feedback after reviewing a "
        "generated bank: 'il faut vraiment que le système détecte et reprenne les "
        "patterns présents dans la bank unmute ainsi que dans factory pour atteindre un "
        "niveau de qualité similaire.' role_starting_points and the guidance elsewhere "
        "in this doc (FX-chain sizes, macro fanout, ARP conventions) are themselves "
        "distilled from past study sessions on Unmüte/Factory content -- genuinely "
        "useful, but a static snapshot that can miss a specific style/role combination "
        "or just get forgotten under a large system prompt. Before drafting EACH preset "
        "in a themed bank (not just once for the whole bank), call "
        "find_reference_presets for that specific role+genre, then describe_preset on "
        "1-2 of the best non-serum-mcp-generated matches (prefer Unmüte or genuine "
        "Factory content -- see is_serum_mcp_generated), and use their ACTUAL numbers "
        "as a concrete floor for the new preset: oscillator count actually enabled, "
        "filter count, fx_chain unit count, macro count assigned, mod_routes count. If "
        "the new preset falls noticeably short of what the real reference actually "
        "does on any of these axes, that's a signal to add depth, not a stylistic "
        "choice to leave alone. This is a per-preset habit, not a one-time research "
        "step at the start of a bank -- different roles within the same bank (a pad vs. "
        "a pluck) warrant checking different real references, since their own real "
        "complexity profiles differ (see role_starting_points).\n"
        "- A REAL REFERENCE'S BASE VALUE OF 0/SILENT-UNTIL-MACRO IS NOT SAFE TO COPY "
        "LITERALLY, found live 2026-08-21: a bank rebuilt around real Unmüte structural "
        "patterns (per the rule above) copied one specific pattern too literally -- "
        "several Unmüte presets studied had a texture oscillator sitting at `volume: 0` "
        "(silent by default) with a mod route ADDING to it only when a named macro was "
        "turned up (a deliberate 'latent layer, discover it yourself' choice real sound "
        "designers make for END USERS who will explore the macros as part of normal "
        "play). Reproducing that literally meant several generated presets were "
        "genuinely incomplete -- missing an intended layer entirely -- unless someone "
        "manually found and raised the right macro first, which directly contradicts "
        "this project's own requirement that a generated preset must be a finished, "
        "complete result the moment it's written, with zero required human tuning "
        "afterward. THE RULE: a preset's DEFAULT/as-generated state (every macro at "
        "whatever value it's initialized to) must always be the complete, intended "
        "sound on its own -- an oscillator central enough to the design to appear at "
        "all needs a genuinely audible base volume, never a literal 0. Macros may add "
        "MORE of a layer on top of an already-complete result (this is fine and "
        "encouraged, matches real content), but must never be the ONLY way to make a "
        "load-bearing layer audible at all. This applies to any other 'source sits at "
        "a neutral/off value, macro brings it in' pattern borrowed from real content, "
        "not just this one oscillator-volume case -- check every base value a live "
        "reference suggests copying against 'does the preset still sound complete if "
        "nobody ever touches a single macro'.\n"
        "- USE THIS PROJECT'S FULL TECHNIQUE PALETTE AS THE DEFAULT, NOT AN OPTION TO "
        "REACH FOR ONLY WHEN ASKED -- found live 2026-08-05, direct user feedback on a "
        "generated bank: 'if it's just taking a pluck wave and adding 2/3 fx on top, "
        "might as well do it by hand -- the whole point of the system is presets that "
        "are COMPLEX to reproduce by hand.' This server has no complexity/creativity "
        "DIAL -- there's no setting anywhere that controls how elaborate a generated "
        "preset is, it's entirely a function of how much of the schema you actually use "
        "per call. A single oscillator + one filter + a couple of low-effort FX is "
        "technically valid but under-uses everything this project has built: LAYER "
        "MULTIPLE ENGINES on one preset when it suits the sound (a real wavetable for "
        "core timbre + a granular_source/spectral_source layer for texture, not just "
        "multiple WTOsc layers); hand-draw LFO shapes via `curve` instead of defaulting "
        "to a plain rate+shape LFO when the modulation has a specific character in mind; "
        "use `voice_unison` for per-voice pan/detune/mod randomization (a real "
        "'expensive to dial in by hand' technique real professional presets use); build "
        "OUT the mod matrix with multiple interacting routes (velocity/random/key_track/"
        "env-as-source alongside the obvious LFO/macro routes), not just one or two "
        "obvious ones; use `aux_source` for player-controllable modulation depth; reach "
        "for `custom_harmonics` when a genuinely bespoke spectrum beats a curated table. "
        "OSCILLATOR LAYERING IS A SEPARATE CHECKLIST ITEM FROM TECHNIQUE CHOICE, found "
        "live 2026-08-06 auditing a 15-preset bank: 6/15 presets ended up genuinely "
        "single-oscillator despite an explicit 'multi-oscillator layering' request, and "
        "every single one of them was built around ONE deep technique (a "
        "`multisample_source`, a hand-synthesized `custom_harmonics` spectrum, an exotic "
        "filter type) that had apparently acted as an implicit 'this preset is already "
        "deep enough' stopping signal -- technique choice and LAYERING are orthogonal, "
        "not substitutes for each other, and this bites melodic single-voice content "
        "(leads/plucks/arps) hardest since 'one clear voice' can feel like the more "
        "'authentic'/focused choice even when it isn't (a real Factory keys preset with "
        "a curated Wuuurli table still layers a digital_fm oscillator AND a sub "
        "underneath it; a real third-party pad runs 4-5 active oscillator slots at "
        "once). After drafting `oscillators`, explicitly check 'does this have 2+ "
        "ENABLED slots contributing real (not token 0.1) volume?' as its own question, "
        "separate from 'does this use an interesting technique?'.\n"
        "- MULTI-FRAME custom_harmonics/WAVETABLES WITHOUT A table_position MOD ROUTE "
        "ARE INERT, found live 2026-08-14: a direct user question ('why does the system "
        "never create presets with dynamic/moving waves') traced to several presets this "
        "session using a 2+ frame `custom_harmonics` table (built specifically so timbre "
        "changes as `table_position` scans through it) but never actually routing "
        "anything to `oscillator{N}.table_position` -- the frames existed but nothing "
        "ever moved through them, wasting the whole point of authoring more than one "
        "frame. This is the same failure shape as the dead-mod-route-to-a-disabled-"
        "oscillator bug elsewhere in this doc, mirrored: there the destination was "
        "missing, here the SOURCE routing is missing. Real Factory/Unmuute content "
        "routes this constantly -- `macro -> oscillator0.table_position`, "
        "`lfo -> oscillator0.table_position`, even `velocity -> oscillator0.table_position` "
        "all appeared in real presets pulled this same session (Dream Keys, Dark Space, "
        "Dark Room, Gentle DX Synth Keys) without ever getting reproduced. RULE: any "
        "oscillator using a 2+ frame `custom_harmonics` list, OR a curated `wavetable` "
        "paired with a nonzero `table_position` chosen specifically for its timbral "
        "character, needs an explicit CHECK -- does something modulate table_position "
        "over the course of a note (an envelope for a one-directional brightening morph, "
        "an LFO for a wobbling/evolving texture, a macro for a performance-controllable "
        "timbre sweep)? If not, that's a real gap to fix, not a stylistic choice to leave "
        "alone -- a static table_position on a multi-frame table is strictly weaker than "
        "just picking the single best-sounding frame and using 1 frame in the first "
        "place.\n"
        "- WAVETABLE/SAMPLE FILE PORTABILITY, relevant whenever a preset or bank is "
        "meant to be shared/tested by someone else (not just used locally): "
        "`custom_harmonics`/`sample_source`/`sample_playback_source`/`granular_source`/"
        "`spectral_source` all write a SEPARATE file to the local Tables/Samples folder "
        "that the .SerumPreset only references by relative path -- this is a real Serum "
        "limitation (true of a wavetable hand-drawn in Serum's own editor too), not "
        "something to route around by avoiding these techniques altogether. "
        "`generate_preset`/`edit_preset` now surface this explicitly: check the return "
        "value for lines after the file path listing any local file dependencies, and "
        "if the user's request implies distribution (an explicit 'so people can test "
        "it', a bank meant to be shared, anything leaving this machine), proactively "
        "tell them which extra file(s) need to travel with which preset -- don't let "
        "them discover a blank/missing table only after sending the bank to someone "
        "else. This is a real tradeoff to name, not a reason to default away from these "
        "techniques -- the 'no complexity dial' guidance above still applies; just "
        "surface the dependency instead of staying silent about it.\n"
        "- MACROS SPECIFICALLY ARE UNDER-USED, found live 2026-08-05 comparing a generated "
        "20-preset bank against real hand-crafted content: 17/20 generated presets used "
        "ZERO macros (vs. real content -- e.g. a Factory `LD - Brutal` uses 8 NAMED "
        "macros with the mod wheel simultaneously driving 3 of them; `BA - Bunker` fans "
        "macros out to octave/warp_amount across multiple oscillators at once). Real "
        "presets treat the 8 macros as the PRIMARY player-facing performance surface, "
        "not a rarely-touched extra -- default to naming and assigning SEVERAL of the 8 "
        "per preset (not just 0-1), with at least some routes fanning ONE macro out to "
        "2+ destinations simultaneously (the 'one knob controls several things at once' "
        "pattern), the same way the rest of this paragraph already asks for a built-out "
        "mod matrix generally. EXPLICIT EXCEPTION: this 'default to more depth' push "
        "does NOT extend to `arp` -- found live 2026-08-05 (a user directly questioning "
        "why several bank presets had it on): unlike every other technique above, "
        "enabling `arp` changes how the "
        "instrument RESPONDS TO PLAYED NOTES, not just how it sounds -- a user loading a "
        "bell/pad/stab expecting a normal playable instrument gets every note forced "
        "through a pattern they didn't ask for and can't easily tell is on without "
        "checking. Keep following arp's own guidance below exactly (unset unless the "
        "request is explicitly about arpeggiating) -- 'this preset's role sounds "
        "rhythmic/chopped' is NOT sufficient justification, the same trap this note "
        "exists to warn against for every OTHER technique. NUANCE, found live "
        "2026-08-06: 'the request is explicitly about arpeggiating' can ALSO be "
        "satisfied by GENRE RESEARCH, not just literal wording -- a user asked for a "
        "Future-style (the rapper) bank and separately pointed out arp's total absence "
        "with 'dans la musique de Future il y a souvent des ARP très électroniques "
        "d'utiliser' (electronic arps ARE a genuinely common, recognizable technique in "
        "that specific artist/genre's production, confirmed via the same WebSearch/"
        "find_reference_presets research this project already does for every genre "
        "request). The exception is narrow: skip arp when it's a GUESS from a role's "
        "own character in isolation ('this bell sounds rhythmic'); DO use it (on at "
        "least one or two fitting lead/pluck presets, not blanket-applied) when the "
        "researched genre/artist's own real production is documented as commonly using "
        "arpeggiation as a signature element -- that's evidence, not a guess, the same "
        "standard already applied to genre-specific wavetable/FX choices elsewhere in "
        "this guidance. None of this means pad EVERY "
        "preset with every feature regardless of fit (a simple role can still have a "
        "simple, well-executed answer) -- it means the DEFAULT effort level should "
        "assume the user is asking for what a skilled sound designer would spend real "
        "time on, not the fastest valid PresetSpec that satisfies the request. If a "
        "user's request "
        "or a role's own character (see role_starting_points) doesn't call for a "
        "specific technique, that's a reason to skip it -- running out of things to add "
        "is not.\n"
        "- DON'T OVER-CORRECT AWAY FROM LFOs IN GENERAL AFTER A CHAOTIC-SHAPE BUG -- "
        "found live 2026-08-06: after fixing a real bug where `shape='lorenz'/'rossler'` "
        "made a bass sound inconsistent note-to-note (see that field's own docstring), "
        "subsequent banks nearly abandoned LFOs altogether -- 2 of 14 presets in a "
        "later bank used one at all, both the same plain default shape doing a single "
        "filter/pitch job, with random1/random2 (per-note humanization) and static "
        "macro routes substituted in even where a genuine periodic LFO (vibrato, a "
        "rhythmic filter wobble, a chorus-like pitch wander) was the more fitting tool. "
        "The bug was specifically about CHAOTIC shapes never repeating, not about LFOs "
        "being risky in general -- a plain periodic LFO (shape left unset, or `curve` "
        "for a hand-drawn shape, or `shape='random_sh'` for stepped/glitchy movement) "
        "is fully deterministic and safe to reach for as a default tool, including "
        "MULTIPLE simultaneous LFOs on one preset doing different jobs (real content "
        "routinely does this, see the dual-LFO chaotic pad example above for the "
        "pattern even though that one specific example uses chaotic shapes "
        "deliberately for an evolving pad). Don't let one shape family's real bug "
        "suppress the whole LFO toolset, including `curve` and `random_sh`, which this "
        "project has documented capability for but has barely exercised in practice.\n"
        "- LFO CURVE SHAPE: DON'T HAND-DRAW FOR GENERIC 'VARIETY' -- ONLY WHEN THE "
        "DESTINATION'S OWN CHARACTER CALLS FOR IT -- found live 2026-08-06, a two-part "
        "correction. First, a user noticed heavy triangle-shape reuse ('ça utilise "
        "très souvent le LFO en forme de triangle, c'est normal?'), CONFIRMED by "
        "inspecting raw CBOR: leaving `shape`/`curve` unset writes an empty "
        "`curveData: {}}`, and Serum's own fallback for that renders as a plain "
        "triangle. The FIRST fix attempt was wrong, though: a single generic "
        "'smoother/sine-like' `curve` was copy-pasted onto 7 different presets "
        "regardless of what each LFO actually modulated -- the same "
        "reskin-across-presets mistake this guidance already warns against elsewhere, "
        "just applied to LFO shape instead of wavetable choice. Checking real Unmute "
        "LFO curveData directly settled it: MOST of their plain (non-chaotic, "
        "non-random_sh) LFOs are explicitly-drawn plain triangles (3 points, 0.5 "
        "tension, i.e. exactly Serum's own default shape) -- triangle-via-unset is a "
        "legitimate, common professional default, not a gap to fill. The hand-drawn, "
        "structurally distinct curves that DO appear in real content are rare and "
        "purpose-built to their SPECIFIC destination: one real pad used a 16-point "
        "curve with repeated x-values (flat steps, instant jumps -- a hand-composed "
        "rhythmic gate pattern) tied to a macro literally named 'BUBBLY RATE'; one "
        "real piano-chord preset used a 4-point ASYMMETRIC curve (fast rise over 1/4 "
        "of the cycle, slow decay over the other 3/4) driving `oscillator.table_position` "
        "specifically -- an envelope-like shape that suits a one-directional timbral "
        "morph, not a symmetric back-and-forth destination. THE ACTUAL RULE: check what "
        "the LFO's own mod route destination and polarity (bipolar vs. unipolar) call "
        "for BEFORE deciding to hand-draw anything -- a bipolar route to filter cutoff "
        "or oscillator volume (a symmetric 'breathe up and down around center' job) is "
        "usually well served by the plain default triangle, same as real content; a "
        "unipolar route to something with an inherent one-directional/rhythmic "
        "character (warp_amount pulsing on each arp step, a table_position morph that "
        "should sweep one way and settle, a gate-like effect) is where a hand-drawn "
        "`curve` earns its complexity -- and the curve's shape should be DESIGNED "
        "AROUND that destination's actual job, not picked for looking different from "
        "the LFO next to it. `shape='random_sh'` remains the right tool specifically "
        "for stepped/glitchy randomization, independent of this curve-vs-default "
        "question.\n"
        "- ADDITIONAL CONCRETE PATTERNS FROM A DEEPER UNMÜTE STUDY (2026-08-06, "
        "describe_preset on UN_PLACES_BA_Beyond/LD_Haze/PD_Memories/CH_Piano_Dream, "
        "beyond the ARP-only study cited above) -- apply these as real per-role "
        "calibration, not just 'more of everything': (1) env0 is NOT the only usable "
        "envelope-as-SOURCE -- real content routinely gives env1/env2/env3 their own "
        "distinct attack/decay/sustain/release shape and routes them to oscillator "
        "volume/filter cutoff/etc. for staged secondary movement, something this "
        "project had essentially never done (always implicitly just env0 as the amp "
        "envelope); (2) `key_track` works as an explicit mod-matrix SOURCE (not just "
        "`FilterSpec.key_track=True`) routed to filter cutoff or `global.voice_amp` for "
        "an independent pitch-dependent layer of character; (3) active (non-dormant) "
        "LFO COUNT should scale with role, not be uniform -- bass presets in real "
        "content stay LFO-light (0-1 active), leads/chords moderate (2-3), PADS go "
        "furthest (one real pad used 8 of 10 LFO slots, each on a single small job -- "
        "pan, pitch, table_position, noise color...) -- calibrate LFO density to role "
        "the same way envelope/filter starting points already are via "
        "role_starting_points; (4) LFO slots 9/10 reserved for a dormant "
        "lorenz/rossler pair appeared in nearly every Unmüte preset checked but were "
        "essentially NEVER actually routed anywhere -- that's leftover template "
        "infrastructure from their own preset-building workflow, not evidence chaotic "
        "LFOs are the norm to imitate; (5) `global.master_volume` varies by role/"
        "density (0.11-0.63 across the 4 presets studied) rather than being uniformly "
        "low -- don't blanket-apply a very low master_volume, reserve it for genuinely "
        "dense/loud-signal-chain presets.\n"
        "- FXComp REQUIRES kParamMakeup TO AVOID A QUIET RESULT -- found live 2026-08-05 "
        "(user feedback: 'sounds too low' meant VOLUME, not tone): kParamMakeup's own "
        "default is 1.0 (unity, i.e. NO compensation for the gain compression just "
        "removed) -- every FXComp instance that doesn't set it explicitly comes out "
        "quieter than intended, more noticeably on short/transient material (plucks, "
        "stabs) than sustained pads. Set kParamMakeup (range 1.0-32.0, a multiplier) "
        "roughly proportional to how much gain reduction kParamRatio/kParamThresh will "
        "actually apply -- as a starting point, ratio 2-3 with a mid threshold wants "
        "roughly 1.5-2.5x makeup, ratio 4-6 with a low threshold wants roughly 2.5-3.5x -- "
        "and adjust by ear/level-check rather than treating these as exact.\n"
        "- GENRE/ARTIST-STYLE REQUESTS ('a dubstep bass', 'something in the style of "
        "Flume', 'a trance lead') OR ANY THEMED BANK NAMING A GENRE/ARTIST/STYLE: "
        "WebSearch on that genre/artist's real production character is MANDATORY "
        "before drafting specs, not a judgment call -- tightened live 2026-08-14 after "
        "the user pointed out that relying on training-data knowledge alone (even "
        "combined with find_reference_presets) had missed a real, common technique "
        "(wavetable/table_position morphing -- see below) that was sitting directly in "
        "every reference preset pulled that same session but never got reproduced, "
        "because the research step wasn't systematic enough to surface it. This applies "
        "to the genre/style/artist trigger specifically -- a bare technical request with "
        "no genre/style/artist named ('a warm pad with a resonant lowpass') does NOT "
        "need a web search; role_starting_points plus a find_reference_presets check "
        "already cover that case. Also call find_reference_presets(query) FIRST, before "
        "generating from scratch -- it searches this machine's real Serum Factory "
        "library plus the user's own installed banks by folder/filename, so you can "
        "ground the request in an actual designed preset (check its real parameters via "
        "describe_preset() on the best match) rather than working purely from "
        "parametric/training knowledge of the genre. This is a real corpus search, not a "
        "database of artist names -- an artist-name query works when a genre/style-"
        "branded pack happens to be installed, and otherwise falls back to genre-level "
        "matches; it can come back empty for an obscure or very specific artist, which "
        "isn't a failure, just a signal to fall back to the technique notes below plus "
        "your own knowledge of that artist's sound. role_starting_points (see above) "
        "already covers generic per-ROLE defaults (bass/pluck/lead/pad/...); the "
        "technique associations below are specifically about GENRE CHARACTER on top of "
        "that -- community sound-design convention, not measured from this project's own "
        "corpus the way role_starting_points is, so treat these as informed starting "
        "points to adapt, not fixed recipes: dubstep/riddim bass leans on FM/PD-style "
        "warp modes (raw/metallic) tamed with a second filter-type warp lane (see the "
        "warp_mode2 guidance above), heavy unison detune, an LFO synced to the beat "
        "grid wobbling filter cutoff, and aggressive distortion/compression late in the "
        "fx_chain; trap/hip-hop bass favors a clean sine/triangle sub layered under a "
        "shorter mid layer, punchy fast-attack/short-release envelopes, and 808-style "
        "pitch glide (portamento_time); house/deep house leans warmer -- softer warp "
        "modes, a rounder low-passed filter, groove-oriented macro-driven modulation "
        "rather than aggressive LFO wobble; trance/big-room leads favor bright "
        "supersaw-style unison stacks (high unison count, moderate detune), a resonant "
        "filter sweep (often macro- or envelope-driven), and long reverb/delay tails; "
        "lo-fi favors softer/duller filtering, subtle pitch/time instability (small "
        "amounts of random1/random2 modulation on pitch), and often benefits from a real "
        "sample layer (see the sample_playback_source guidance above) for vinyl/tape "
        "character rather than trying to synthesize noise/grit from scratch; ambient/"
        "cinematic pads want long attack/release envelopes, slow-moving LFO/macro "
        "modulation (filter cutoff, pan, table_position), and generous reverb -- often "
        "layered oscillators with DIFFERENT wavetables per the layering guidance above "
        "for an evolving/detuned texture rather than a single static tone. When a "
        "request names a genre not covered here, extend this reasoning (character/"
        "energy/typical arrangement role) rather than defaulting to a generic sound.\n"
        "- HYBRID/SIGNATURE-TECHNIQUE SOUNDS (a genre's own defining hybrid element -- "
        "amapiano's log drum, dubstep's Reese/growl, a specific vocal-chop texture -- as "
        "opposed to a generic role like 'a pad' or 'a bass') are defined by a SPECIFIC, "
        "fairly narrow measurable technique, not general principles, and generic "
        "knowledge/web research about them is often wrong in ways that only become "
        "obvious after several failed rounds of guessing (found live 2026-08-06: 8+ "
        "rounds spent on a log-drum bass guessing from web research alone -- wrong pitch-"
        "envelope sign, wrong register, wrong click mechanism -- before the user supplied "
        "a real reference sample, at which point analyzing it directly (pitch trajectory, "
        "amplitude-over-time decay curve, spectral-centroid-over-time brightness "
        "trajectory, harmonic amplitude ratios between partials) resolved most of it in "
        "1-2 rounds). PROACTIVELY ASK THE USER FOR A REFERENCE SAMPLE OR TRACK before "
        "attempting one of these sounds from scratch, rather than guessing from generic "
        "knowledge and only asking after repeated rejections -- this is the single "
        "highest-leverage thing to get right first, and costs nothing to ask for. If a "
        "reference file becomes available (dropped in the project, or the user names a "
        "path), and this session has some way to render+measure audio (this project's "
        "own dev pipeline is a separate GPL tool, `serum-verify`, not exposed as an "
        "MCP tool to arbitrary callers -- but if an equivalent capability exists in "
        "the calling session, use it), extract its objective 'timbral fingerprint' -- "
        "pitch stability/trajectory, amplitude envelope shape over time, spectral-"
        "centroid trajectory (does it start bright and darken, and over what "
        "timescale?), and harmonic content (which overtones are prominent relative to "
        "the fundamental) -- and match a candidate preset against those numbers before "
        "presenting it, the same way a human producer reverse-engineering a reference "
        "sound would EQ-sweep/solo/analyze it first rather than guess by ear alone. "
        "SEPARATE WHAT'S MEASURABLE FROM WHAT'S TASTE: pitch/timing/envelope-shape/"
        "harmonic-ratio questions have a right answer checkable against the reference "
        "and should be nailed BEFORE asking the user to listen; questions like 'how "
        "aggressive should this transient feel' or 'does this want more warmth/"
        "distortion' are genuine aesthetic judgment calls no amount of measurement "
        "against even a perfect reference can resolve alone -- expect those to need a "
        "real listening round-trip with the user regardless of how good the upfront "
        "research/measurement was, and don't mistake a string of taste-adjustment "
        "requests for the earlier measurable groundwork having been wrong.\n"
        "- DON'T APPLY A UNIFORM 'AGGRESSIVE' PROCESSING TEMPLATE ACROSS GENRES OR ROLES "
        "-- found live 2026-08-05, direct user feedback on a drill-style bank generated "
        "right after a rage-style one: 'tu utilises trop de fréquence aggressive pour ce "
        "style, il faut vraiment que tu arrives bien à analyser le style recherché.' "
        "Root cause: a corrective FXEQ template (a small HIGH-FREQUENCY BOOST, +1 to "
        "+2dB around 6-9kHz, for 'air/clarity') and an FXDistortion 'character' unit had "
        "been added near-uniformly across almost every preset regardless of role, "
        "carried over unchanged from the earlier rage/hyperpop bank's genuinely harsh "
        "aesthetic -- but drill's own researched character is DARK (rolled-off/muted "
        "highs, not brightened) and reserves grit almost entirely for the 808/bass "
        "role, with piano/string/bell/choir melodic elements kept comparatively clean "
        "(reverb/delay/chorus for atmosphere, not saturation). A high-frequency EQ "
        "BOOST and an added distortion stage are exactly backwards for a dark/moody "
        "genre's non-bass roles. Before choosing fx_chain processing (not just "
        "oscillators/filters), actively re-check it against what the SPECIFIC "
        "researched genre's real character actually calls for per ROLE -- a genre being "
        "'dark' or 'moody' should show up as restraint (EQ cuts not boosts, little to "
        "no distortion on delicate/acoustic-adjacent roles like piano/strings/choir) "
        "even if the same bank's bass/lead roles are genuinely meant to be harsh -- "
        "don't let one role's authentic aggression bleed into every other role's fx_chain "
        "template by default.\n"
        "- DON'T GENERATE BASS OR FX-ROLE PRESETS IN A THEMED BANK UNLESS EXPLICITLY "
        "REQUESTED -- SUPERSEDES an earlier, weaker 'default to fewer bass presets' "
        "rule (2026-08-05: 'ajoute au système de créer moins de basses'). Tightened "
        "live 2026-08-12 after a user reviewed an Atlanta-trap bank generated with 3 "
        "bass presets + 1 FX riser that were never asked for: 'il faut que le système "
        "arrête de faire des basses et des FX quand on lui demande de faire une bank "
        "à moins que ça soit précisé.' A bare 'make me a bank in the style of X' "
        "request defaults to melodic/textural roles ONLY (lead, pluck, pad, chords, "
        "keys, arp) -- these define a genre's musical character far more than another "
        "bass variant, and a bass/FX-riser preset is a narrower, more situational need "
        "than a full melodic palette. Only include a bass-role or FX-role (riser/"
        "impact/transition) preset when the user's own request names it directly "
        "('with some 808s', 'a bass too', 'add a riser') or the bank is explicitly "
        "ABOUT that role (e.g. 'a bank of Reese basses').\n"
        "- Envelope times are seconds; macro/resonance/wet/drive are 0-100%. "
        "envelopes[].hold is a rarely-needed extra plateau at full level before "
        "decay starts, seconds -- leave at 0 unless asked for.\n"
        "- global.portamento_time (seconds) is glide between notes -- use for "
        "'glide', 'portamento', 'slide between notes' requests; 0 = off (default). "
        "global.poly_count caps simultaneous voices (default 8) -- lower it only "
        "if asked to save CPU or force fewer overlapping notes.\n"
        "- lfos[].delay (seconds) is a fade-in before the LFO starts after note-on "
        "-- use for 'vibrato that kicks in after a moment'. lfos[].smooth (%) "
        "softens steppy/random LFO shapes into something glidey. lfos[].beat_sync IS "
        "REQUIRED EXPLICITLY (not just left unset) to get free-running Hz -- pass "
        "beat_sync=False alongside rate=<Hz> for 'a 3Hz LFO'/'free-running' requests "
        "(rate IS literal Hz once beat_sync=False is set, confirmed 2026-08-01); leave "
        "beat_sync unset (the default) for a normal tempo-synced LFO, which is what "
        "most musical requests actually want anyway. This was a real bug until "
        "2026-08-01 (beat_sync=False used to be silently indistinguishable from "
        "'unset' and always fell back to tempo-synced) -- don't assume beat_sync=False "
        "alone (without also having been a real fix) used to work.\n"
        "- lfos[].curve (generatable since 2026-08-01) draws a custom hand-drawn LFO "
        "shape as a list of {x, y, tension} points -- use for any shape request that "
        "isn't one of shape='random_sh'/'rossler'/'lorenz'/'path' (e.g. 'ramps up then "
        "snaps down', 'a slow rise with a sharp drop', custom envelope-like LFO "
        "motion). x=0.0..1.0 (first point MUST be x=0.0, last MUST be x=1.0, strictly "
        "increasing), y=0.0..1.0 in NATURAL terms (0=bottom/lowest point of the curve, "
        "1=top/highest -- describe it the way you'd say it out loud), tension=0.0..1.0 "
        "per point (0.5=linear/straight, confirmed via live ground-truth testing; below "
        "0.5 bows a rising segment concave/fast-start, above 0.5 bows it convex/"
        "slow-start). A 2-point curve MUST be rising (2nd point's y > 1st's) or it "
        "raises an error -- add a 3rd point for a falling 2-point shape. Leave `curve` "
        "unset (together with `shape`) to keep whatever curve the base preset already "
        "has, which is NOT the same as 'off'.\n"
        "lfos[].mono (found live 2026-07-29) "
        "makes the LFO a single shared instance that keeps running independent of "
        "note-on events, instead of a per-voice one that restarts its phase every "
        "note -- matters a lot for a FAST lfo (e.g. shape='random_sh') paired with a "
        "fast arp/sequence, where a per-voice LFO gets reset almost every step and "
        "barely completes a cycle (reads as choppy/'too fast'/'frozen with nothing "
        "playing'). Set mono=True whenever a fast LFO is meant to feel alive and "
        "independently evolving under rapid retriggering, not for slow/occasional LFOs."
    ),
)


@mcp.tool(
    title="Generate preset",
    annotations=ToolAnnotations(
        title="Generate preset",
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=False,
    ),
)
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

    Returns the absolute path of the written .SerumPreset file, as the
    FIRST LINE of the return value, always. If ``spec`` used
    ``custom_harmonics``/``sample_source``/``sample_playback_source``/
    ``granular_source``/``spectral_source`` on any oscillator, further
    lines list local file(s) that preset now depends on -- Serum itself
    always stores this kind of content (a synthesized/custom wavetable, a
    user-supplied sample) as a SEPARATE file on the local machine, not
    embedded in the .SerumPreset (true of Serum's own UI too, not a
    serum-mcp limitation). If the preset is going to be shared with
    someone else or copied to another machine, pass those file(s) along
    too, or the referenced table/sample will show up blank/missing on
    their end -- surface this to the user rather than treating the
    returned path as the whole deliverable.
    """
    return _generate_preset(spec, subfolder=subfolder)


@mcp.tool(
    title="Edit preset",
    annotations=ToolAnnotations(
        title="Edit preset",
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=False,
    ),
)
def edit_preset(preset_path: str, spec: PresetSpec) -> str:
    """Apply a partial ``spec`` update to an existing .SerumPreset file, in place.

    Call describe_preset(preset_path) first to see the current state, then
    only include the sections/indices in ``spec`` that should change --
    e.g. to just brighten the filter, pass ``filters=[FilterSpec(cutoff=0.8, ...)]``
    and leave everything else empty; it will be left untouched.

    Returns the absolute path of the edited file (same as ``preset_path``)
    as the FIRST LINE of the return value, always -- see
    ``generate_preset``'s own docstring for the same local-file-dependency
    note that applies here too when the edit touches a
    ``custom_harmonics``/``sample_source``/``sample_playback_source``/
    ``granular_source``/``spectral_source`` oscillator.
    """
    return _edit_preset(preset_path, spec)


@mcp.tool(
    title="List parameters",
    annotations=ToolAnnotations(
        title="List parameters",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def list_parameters() -> str:
    """Return the full documented Serum 2 parameter schema (modules, value
    ranges, units, enum values, and how confidently each was verified) as
    JSON.

    Call this before proposing an edit so you know what parameter names and
    ranges are actually valid.
    """
    return _list_parameters()


@mcp.tool(
    title="Describe preset",
    annotations=ToolAnnotations(
        title="Describe preset",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def describe_preset(preset_path: str) -> str:
    """Return a human-readable summary of an existing preset's sound-shaping
    parameters (oscillators, filters, envelopes, FX chain, mod routes, globals)."""
    return _describe_preset(preset_path)


@mcp.tool(
    title="List sample files",
    annotations=ToolAnnotations(
        title="List sample files",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
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


@mcp.tool(
    title="Find reference presets",
    annotations=ToolAnnotations(
        title="Find reference presets",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def find_reference_presets(query: str, limit: int = 8) -> str:
    """Search the real preset corpus (Serum's Factory library plus the
    user's Presets/User folder, incl. any third-party banks) by keyword
    match against folder/file names, and return the best candidates as
    JSON -- for grounding a genre/artist-style request in a real,
    already-designed preset instead of generating purely from parametric
    knowledge.

    Call this whenever a request references a GENRE or an ARTIST'S STYLE
    ("dubstep bass", "something like Flume would make", "a Reese bass")
    before generating from scratch. A genre query is automatically
    expanded against a small curated keyword table bridging genre names
    to Serum's own instrument/role-organized Factory folders (e.g.
    "dubstep" also searches "reese"/"wobble"/"growl"/"modulated") -- see
    find_reference_presets's own docstring for details and caveats.

    Results are a STARTING POINT: call describe_preset() on the most
    promising matches to see their actual parameters (filter type, FX
    chain, mod routes) before treating one as a reference or as the base
    for edit_preset(). A weak/empty result doesn't mean synthesis from
    scratch won't work -- this corpus is finite (Factory plus whatever
    this specific user has installed), so also fall back to this
    server's own genre/technique guidance and
    list_parameters()['role_starting_points'].

    Each result carries ``is_serum_mcp_generated`` -- found live
    2026-08-05 that some results are this project's OWN past output
    (metadata presetAuthor == "serum-mcp"), and using an earlier
    self-generated preset as a QUALITY/TECHNIQUE benchmark is circular
    (it's bounded by what this project already knew how to do back
    then, not by independent design merit). PREFER non-flagged
    (genuine Factory/third-party) results as the actual reference; a
    flagged one is still useful narrowly (what was already tried for
    this role/style) but not as "this is what good sounds like."
    """
    return _find_reference_presets(query, limit=limit)


@mcp.tool(
    title="Analyze sample file",
    annotations=ToolAnnotations(
        title="Analyze sample file",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
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
