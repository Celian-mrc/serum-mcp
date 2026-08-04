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
        "'supersaw'-style requests. warp_mode "
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
        "skilled hands.\n"
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
        "classic velocity-sensitive envelope response. 'key_track' -> "
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
