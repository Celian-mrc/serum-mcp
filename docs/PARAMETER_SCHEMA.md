# Serum 2 parameter schema

This document explains the `.SerumPreset` file format and the parameter
schema `serum-mcp` uses to generate and edit presets, and — just as
importantly — what is **not** known or modeled yet.

Xfer Records does not publish a SDK or file format spec for Serum 2. Nothing
in this document comes from Xfer. It was reverse-engineered by the
community and cross-checked empirically against a real Serum 2 install for
this project. Treat it as a best-effort snapshot of Serum 2.0.11 behavior
that may break on any future Serum update.

## 1. Container format

A `.SerumPreset` (and `.XferArpBank`) file is:

```
b"XferJson\x00"                              9-byte magic
uint32_le(metadata_len)  uint32_le(0)         header
<metadata_len> bytes of UTF-8 JSON            human-readable metadata
uint32_le(payload_len)   uint32_le(2)         header (payload_len = size *after* decompression)
zstandard frame                               compresses CBOR-encoded engine state
```

Credit for the initial reverse-engineering goes to
[@0xdevalias](https://gist.github.com/0xdevalias/5a06349b376d01b2a76ad27a86b08c1b)
and [KennethWussmann/serum-preset-packager](https://github.com/KennethWussmann/serum-preset-packager),
which independently confirmed and shipped a working CLI for this layout.
`serum_mcp.preset.packer` is a clean-room reimplementation (that reference
repo carries no LICENSE file, so we did not copy its code) — same format,
own code, verified byte-for-byte against real presets exported by Serum 2.0.11
(`pack(unpack(x)) == x` on every preset in our sample, see `tests/test_packer.py`).

The **metadata** JSON is small and self-explanatory: `presetName`,
`presetAuthor`, `presetDescription`, `tags`, `product`/`productVersion`,
`vendor`, `url`, `hash`, `version`.

The **CBOR payload** (`data` in this codebase) is the actual engine state,
and is what the rest of this document covers.

**A CBOR wire-type gotcha, confirmed the hard way**: inside `plainParams`
dicts, every numeric field is stored as a CBOR **double**, including ones
that are conceptually integer or boolean (`kParamEnable`, `kParamBipolar`,
`kParamMonoToggle`, `kParamUnison`, ...) — *never* as a native CBOR boolean
or CBOR integer, even though e.g. `kParamEnable` only ever holds `0.0`/`1.0`
and `kParamUnison` only ever holds whole numbers. Writing a real CBOR bool
or CBOR int there (e.g. naively serializing a Python `bool`, or a
strictly-`int`-typed field) produces a structurally different wire type —
confirmed to reliably crash Serum's native loader for the bool case (FL
Studio closed ~2 seconds after selecting a preset built this way, no error
dialog). `serum_mcp.preset.validator.validate_params` normalizes both cases
automatically (bool → `1.0`/`0.0`, any `int` → `float`) for every field it
validates, so nothing above that layer needs to think about it — but if
you're writing CBOR by hand outside this codebase, don't assume Python's
natural bool/int → CBOR mapping is safe here. Note this is scoped to
`plainParams` fields specifically: a few *top-level* flags outside
`plainParams` (`mpeEnabled`, `lockOversampling`, `lockTuning`) genuinely are
native CBOR booleans in real presets, and `destModuleID`/`destModuleParamID`/
`ModSlot.source`/FX `type` genuinely are native CBOR integers — don't "fix"
those. `preset/safety.py::scan_wire_types` (`scripts/check_preset.py`)
independently re-scans a packed preset's output for exactly this class of
issue, as a belt-and-suspenders check that doesn't trust every code path
went through `validate_params` correctly.

## 2. Methodology

Two independent sources were used, and cross-checked against each other:

1. **Empirical sampling**: 300 factory presets (out of 626 shipped with
   Serum 2.0.11) were unpacked and every `plainParams` dict encountered was
   aggregated by owning module type, recording the observed min/max (for
   numbers) or the set of distinct values (for enum/string params). This
   tells us what values *occur in the wild* — a lower bound on the true
   range, and strong evidence for enum vocabularies, but not authoritative
   for exact default values (a parameter absent from every sampled preset's
   `plainParams` dict just means nobody happened to touch it away from
   Serum's built-in default).
2. **Authoritative defaults**: a JSON dump of all ~2,622 VST3 parameters
   (with default values) reported by a *freshly loaded* Serum 2 instance
   ([source](https://gist.github.com/KennethWussmann/5b58e4de728680a0bf8906a8b113103d)).
   This is the ground truth for default values, and was used to resolve
   several cases where the empirical sample alone was ambiguous or
   misleading (see §5).

The original Serum **1** parameter table
([gist](https://gist.github.com/0xdevalias/135a18e979ac8e302ebbc700a50a8d74))
was consulted for context but **not used directly** — Serum 2's actual CBOR
key names (`kParamFreq`, `kParamReso`, ...), module layout, and value ranges
were re-derived from the two sources above, since Serum 2 added an entire
oscillator engine layer (granular/multisample/spectral/sample, on top of the
Serum 1-era wavetable engine), tripled the FX rack count, expanded the mod
matrix from 32 to 64 slots, and expanded LFOs from 8 to 10. Reusing the
Serum 1 table as-is would have been actively misleading.

A third technique, used specifically to resolve `destModuleParamID` (§6):
**extracting printable strings from the installed Serum 2 plugin binary**
(`Serum2.vst3\Contents\x86_64-win\Serum2.vst3`). The binary's debug/RTTI
info includes literal C++ enum declarations (e.g. `kParamEnable=0,
kParamVolume, kParamPan, kParamOctave, ...`), which is an independent
confirmation source, not just internal consistency within our own samples.
This only reads plaintext already embedded in a legally-owned, installed
binary (the same category of technique the community used to find the
container format in the first place) — no decompilation, no bypassing any
protection.

## 3. Top-level module map

A decompressed CBOR payload's top-level keys, as observed:

| Key(s) | What it is | Modeled in V1? |
|---|---|---|
| `Oscillator0`..`Oscillator4` | Osc A, B, C, Noise, Sub | Yes (core params) |
| `Osc` | per-slot GUI state (zoom/markers) | No — GUI only |
| `WTOsc`, `GranularOsc`, `MultiSampleOsc`, `SampleOsc`, `SpectralOsc` | *type* placeholders (empty) — actual per-slot data lives nested inside `Oscillator{i}` as `WTOsc{i}` etc. | Partially (WTOsc and SampleOsc) |
| `VoiceFilter0`, `VoiceFilter1` | Filter 1, Filter 2 | Yes |
| `Filter` | shared filter section UI mix knob | No |
| `Env0`..`Env3` | the 4 envelopes | Yes |
| `LFO0`..`LFO9` | the 10 LFOs | Partially (rate/mode only, not curve-drawn shapes) |
| `LFOPointModBus0`..`LFOPointModBus15` | point-editor LFO mod busses | No |
| `Macro0`..`Macro7` | the 8 macro knobs | Yes |
| `Global0` | master volume, mono, portamento, poly count, ... | Partially |
| `ModSlot0`..`ModSlot63` | the 64-slot mod matrix | Partially — all destinations + LFO/Macro sources, see §6 |
| `FXRack0`..`FXRack2` | 3 independent, PARALLEL effects racks, each an ordered `FX` list | Yes, all 3 (since 2026-07-29 — see §4) |
| `Arp0`, `ArpClip0`..`ArpClip11`, `arpBankDisplayName` | arpeggiator | No — round-trips untouched |
| `MidiClip0`..`MidiClip11`, `ClipPlayer`, `ClipPlayer0`, `clipBankDisplayName` | MIDI clip player | No — round-trips untouched |
| `PitchQuantizer0` | scale/quantizer | No — round-trips untouched |
| `RetriggerState0` | legato/retrigger config | No — round-trips untouched |
| `RoutingSlot0`..`RoutingSlot6` | FX bus routing | No — round-trips untouched |
| `VoicePanel0` | voice-level scaling options | No — round-trips untouched |
| `SerumGUI` | window/panel layout | No — round-trips untouched |
| `mpeEnabled`, `mpeConfig`, `mpePitchBendRange` | MPE settings | No — round-trips untouched |
| `lockOversampling`, `lockTuning`, `scalars` | misc engine flags | No — round-trips untouched |

"Round-trips untouched" means: `serum_mcp` never reads or writes these keys,
but because `apply_spec` starts from a deep copy of the base preset and only
mutates the keys it knows about, they survive edits unchanged.

## 4. Per-module parameters

Full detail — every `kParam*` key, its type, bounds, unit, default and
confidence level — lives in code, not duplicated here, since code is what
actually gets validated against: see
[`src/serum_mcp/preset/schema.py`](../src/serum_mcp/preset/schema.py).
Call the `list_parameters` MCP tool to get the same data as JSON at runtime.

Every `ParamDef` carries a `confidence` field:

- `confirmed` — cross-checked against the authoritative VST3 default dump.
- `observed` — seen consistently across the empirical sample, but not
  independently confirmed (e.g. most enum vocabularies).
- `uncertain` — best guess from limited or conflicting evidence; treat with
  suspicion, and please open a PR if you can pin it down further.

### Oscillators

5 slots (`Oscillator0..4` = Osc A/B/C/Noise/Sub in Serum's UI). Only **Osc A
is enabled by default** — this is a *per-slot* default, not a shared one
(confirmed via the VST3 dump), which is why `preset/introspect.py`
special-cases slot 0 rather than encoding it in the shared param table. The
shared params (`kParamEnable`, `kParamOctave`, `kParamPitch`, `kParamFine`,
`kParamVolume`, `kParamPan`, `kParamUnison`, `kParamDetune`) apply to all 5
slots identically and are fully generatable via `OscillatorSpec`.
`kParamPitch` (`OscillatorSpec.semitone`, ±12 semitones) is a static offset
independent of `kParamOctave` — added specifically to align two
`sample_playback_source` one-shots to the same pitch class, since
`SampleOsc` has no configurable root note and each layer otherwise sounds
at whatever pitch its own recorded content actually is. `kParamFine`
(`OscillatorSpec.fine`, cents, ±80) is a THIRD, independent tuning
control — the standard "Coarse + Fine" pattern — found live 2026-07-29
comparing a recreation's oscillators byte-for-byte against a real preset
(both used it, -3/+4 cents); had been documented in `schema.py` and usable
as a mod destination for a while, but never exposed as a settable base
value until then.

**Slots 0-2 (Osc A/B/C)** each have a sound source that's one of 5 engines,
keyed as `WTOsc{i}`, `GranularOsc{i}`, `MultiSampleOsc{i}`, `SampleOsc{i}`,
`SpectralOsc{i}` inside `Oscillator{i}`, and selected by
`Oscillator{i}.plainParams.kParamType` (`kOsc_WT`/`kOsc_Sample`/
`kOsc_Granular`/`kOsc_MultiSample`/`kOsc_Spectral` — found via factory-preset
survey, not the VST3 dump; see §8). **`WTOsc` and `SampleOsc` are both
modeled**; Granular/MultiSample/Spectral exist in the format and round-trip
fine but `serum-mcp` cannot currently generate or target them (`kOsc_WT` is
the default/most common engine — the one every factory bass/lead/pad preset
we sampled that wasn't a multisample instrument used;
`OscillatorSpec.table_position`/`warp_amount`/`warp_mode` control it — the
last picks the wavetable warping character via a curated subset of the raw
`kParamWarpMenu` enum, `schema.SIMPLE_WARP_MODES`: FM/AM, sync, PWM,
wavefolding/clipping distortion, quantize, and two built-in filter warps).
`oscillator{i}.table_position` and `oscillator{i}.warp_amount` (slots 0-2)
are also valid mod-matrix destinations — a classic use is an LFO scanning
through the wavetable, or a macro morphing the warp amount. `SampleOsc` (true
one-shot/sample playback, `OscillatorSpec.sample_playback_source`) is covered
in §8, reverse-engineered separately and more recently than the rest of this
section.

**`kParamWarpMenu`'s `FM_*`/`RM_*`/`PD_*` values are cross-oscillator
modulation, not self-contained distortion** (`observed`-confidence, found
live — not in `SIMPLE_WARP_MODES`'s curated set, which only exposes
self-contained warps like `fm`→`kFM_OSC` was assumed to be one of, before
this). The naming (`kFM_OSC`, `kFM_OSC2`, `kFM_SUB`, `kFM_NOISE`, and the
matching `kRM_*`/`kPD_*` families) means this oscillator is
frequency-/ring-/phase-modulated *by* another module (`OSC`/`OSC2` = the
other WT oscillator slots, `SUB`/`NOISE` = those slots directly) — not a
self-modulating distortion the way `kSync`/`kDistLinFold`/`kPWM` etc. are.
Confirmed by surveying 8 factory presets using these modes: every one kept
the referenced modulator oscillator (`Sub`, or another WT oscillator slot)
enabled alongside the modulated one. Practical consequence hit live: a
preset with Osc A's `warp_mode` set to `fm` (`kFM_OSC`) sounded dramatically
different with Osc B enabled vs. disabled — not just "Osc B's layer is
missing" but Osc A's *own* timbre changing, because Osc A was being
FM'd by Osc B the whole time. `SIMPLE_WARP_MODES`'s `fm`/`am` entries
(`kFM_OSC`/`kAM_OSC`) inherit this — picking them for one oscillator makes
its sound depend on a *different* oscillator's enabled state, which is easy
to reach for by mistake if you want two independent layers rather than an
intentional 2-operator FM/RM pair. The exact `OSC`/`OSC2` slot-index mapping
(does `OSC` always mean "the next slot", with wraparound?) isn't nailed
down — the survey confirms modulator-presence correlation, not the precise
routing table.

`OscillatorSpec.wavetable` (slots 0-2) selects *which* wavetable file the
WTOsc engine loads — found missing via real-world use: every generated
preset used the same file (`fixtures/init_preset.SerumPreset`'s default,
`"S2 Tables/Default Shapes.wav"`) for every oscillator regardless of what
was asked for, since `apply_spec` only ever touched `kParamTablePos`/
`kParamWarp`/`kParamWarpMenu` inside `WTOsc{i}`, never the file reference
itself. A wavetable file's `relativePathToWT`/`numFrames`/`sampleRate`/
`numChannels` (siblings of `plainParams` inside `WTOsc{i}`, not `kParam*`
values) must match the actual referenced `.wav` exactly, or Serum may
misread the table — same risk class as the CBOR bool/int wire-type bugs.
`schema.SIMPLE_WAVETABLES` curates 12 factory tables (warm analog, PWM,
digital/FM, harmonic-rich, acid, ...) picked from the ~40 most commonly
referenced tables across a 400-preset sample, with their exact metadata
copied from real Serum-saved presets that reference each file (not computed
from the `.wav` headers ourselves) — see `preset/mapping.py`'s `WTOSC_SLOTS`
branch. `kParamTablePos`'s range appears to already be normalized to a
fixed ~0-256 slot count independent of a table's raw `numFrames` (observed
consistently across tables whose `numFrames` ranges from 4,096 to 524,288),
so switching wavetables doesn't require rescaling `table_position`.

**Known trap: `flute` is silent at the default `table_position=0.0`** (found
live -- a generated preset using it was reported as "almost no sound, the
waveform looks completely flat"). Measured directly from the `.wav` file:
frame 0's peak amplitude is `0.0039` against a table-wide average of `0.81`
across all 256 frames (peak amplitude hits ~1.0 around frame 134) -- this
table is evidently designed to start near-silent and swell in as
`table_position` increases (a reasonable design for an breathy/organic
instrument table, less reasonable as a default when nothing else sets
`table_position`). Checked all 12 curated tables the same way: every other
one starts at or near full amplitude (frame 0 within ~86-101% of that
table's mean peak) -- `flute` is the only outlier, not a systemic issue with
defaulting `table_position` to 0. **Always set `table_position` to a
non-zero value (e.g. ~130-150) when using `flute`.**

Beyond selecting a curated factory table, `OscillatorSpec.custom_harmonics`
can *synthesize a brand-new wavetable* from a harmonic amplitude series, and
`OscillatorSpec.sample_source` can build one by **slicing a user-provided
audio file** (e.g. a one-shot drum/foley/vocal sample) into evenly-spaced
frames — see §7 for the wavetable `.wav` file format itself and the slicing
approach (both reverse-engineered/built this session, separately from the
CBOR preset format). This is a different thing from true `SampleOsc`
playback: the source audio becomes loop-buzzy wavetable material scanned by
the WTOsc engine, not a faithfully reproduced one-shot.

**Slots 3 and 4 are not the same engine family** — this is structural, not
a modeling gap: slot 3 is *always* `NoiseOsc3` (white/pink/brown/geiger
noise, `OscillatorSpec.noise_type`) and slot 4 is *always* `SubOsc4` (a
single basic waveform — saw/square/triangle/pulse/round-rect,
`OscillatorSpec.sub_shape`) in every preset we've seen; real Serum presets
never have a `WTOsc3`/`WTOsc4` key. `table_position`/`warp_amount` are
ignored by `apply_spec` for these two slots rather than being (wrongly)
written into a `WTOsc` key Serum never produces there.

### Filters

2 slots (`VoiceFilter0`/`VoiceFilter1` = Filter 1/2). **Both off by default**
(confirmed). The raw `kParamType` enum has 66 observed values (ladder, SVF,
comb, phaser-as-filter, formant, "Scream" distortion-filter hybrids, etc.);
`SIMPLE_FILTER_TYPES` in `schema.py` curates 11 of them with unambiguous
names (`lowpass_12`, `lowpass_24`, `highpass_12`, ...) for generation to
target (via `FilterSpec.type`). The raw enum remains fully valid for
`edit_preset`/`list_parameters` consumers who want the rest. `FilterSpec`
also generates `stereo` (`kParamStereo`, width/spread %), `var`
(`kParamVar`), `key_track` (`kParamKeyTrack`), `wet` (`kParamWet`, this
filter's own dry/wet — separate from `fx_chain`), and `level_out`
(`kParamLevelOut`) alongside cutoff/resonance/drive.

**`kParamVar` ("Var")** was documented in `schema.py` since early in this
project (`notes="'Var' knob; meaning changes per filter type (e.g. comb
spacing, formant blend)."`) but never wired into `FilterSpec`/generation
until found live 2026-07-29 to matter a lot in practice, not just in
theory: recreating a real preset that used `DistComb1BP` (a comb filter
variant) with `var` silently left at 0 (`FilterSpec`'s old implicit
default) produced a harsh, aliased, "8-bit"-sounding result — the real
preset had `var=65.1`. For comb-family (and likely formant-family) filter
types, `var` is a primary character control, not a minor tweak; check a
real reference value before assuming 0 is safe. `key_track` (cutoff
follows note pitch) was also found unwired at the same time — the same
real preset had it `True` on both filter slots.

`kParamStereo`'s neutral/centered value is **50**, not 0 — confirmed live
(2026-07-28, real Serum 2 in FL Studio 21) after a user reported a
persistent, meter-visible hard-left bias on sample-based presets that traced
back to this field defaulting to 0. Isolated A/B preset tests (bare
oscillator vs. +filter with `stereo=0.0` vs. +filter with `stereo=50.0`)
confirmed 0 introduces the bias and 50 is centered. Both `FilterSpec.stereo`
(`spec.py`) and `kParamStereo`'s `ParamDef` default (`schema.py`) now read
50; any preset generated before this fix with a filter enabled and `stereo`
left unset was written with the old, wrong 0 default and should be
regenerated.

`kParamFreq` (cutoff) is the biggest known gap: it's a normalized `0.0..1.0`
value, and we have exactly **one** calibration point (`0.5 ≈ 425 Hz` at
default resonance, from the VST3 dump) — not enough to reconstruct the true
Hz curve (believed logarithmic, roughly 9 Hz–19 kHz). Treat `cutoff` as a
perceptual position, not a literal frequency, until someone samples enough
points to fit the curve.

### Envelopes

4 slots (`Env0..3`), all identical schema. Env 1 (`Env0`) is *conventionally*
the amp envelope in factory content, but nothing in the format enforces
that — it's just how presets are usually built. `EnvelopeSpec` generates
`attack`/`hold`/`decay`/`sustain`/`release`/`attack_curve`/`decay_curve`/
`release_curve`; `hold` (a plateau at full level before decay starts)
defaults to 0 and is rarely needed. The three `*_curve` fields
(`kParamCurve1/2/3`, 0-100, shaping how linear/exponential each ramp is)
were found live 2026-07-29 present on **97% of all real envelopes
surveyed** (3242/3333) — effectively always set, not an optional/rare
field, and had gone completely unmodeled until diffing a recreation's
`Env0..3` byte-for-byte against a real preset. Defaults (`50`/`66.6`/`66.6`)
match the overwhelmingly most common real values, presumed to be Serum's
own defaults for an untouched envelope. The attack/decay/release segment
mapping (matching `kParamAttack`/`kParamDecay`/`kParamRelease`'s
declaration order) is inferred, not independently confirmed.

`kParamRelease`'s max was `13.0` ("confirmed" from a VST3 automation-range
dump) until a real third-party bank (Unmüte's "Places") turned up multiple
presets with `release=32.0` written directly into the CBOR — corrected to
`32.0`, matching `kParamDecay`. The VST3 dump apparently reports a narrower
range than what the plugin actually accepts when loading a saved preset;
direct evidence from real files now overrides it.

### LFOs

10 slots (`LFO0..9`). `LfoSpec` generates `rate`, `mode` (`Free`/`Retrig`/
`Envelope` — `Retrig` recovered from the plugin binary's debug strings,
never observed in the factory sample), `beat_sync`, `delay` (fade-in before
the LFO starts after note-on), `rise` (ramp-up time), `smooth` (lag
smoothing, for less steppy random/S&H shapes), `shape` (named algorithmic
shapes — S&H/Rossler/Lorenz/Path, see §5 item 4-adjacent finding above),
`mono`, `swing`, `dotted`, `triplets`, and `rate10x`. Free-hand curve-drawn
LFO shapes (`curveData`: `xVals`/`yVals`/`curveVals`) exist and round-trip,
but generating them is out of scope for V1 (no natural-language mapping for
"draw this LFO shape" yet).

`kParamDotted`/`kParamTriplets` (found live 2026-07-29, same
byte-for-byte-diff pass that found `kParamFine`/envelope curves) mirror the
arpeggiator's identically-named fields — dotted/triplet rhythm timing for
the LFO's own rate, present on 16%/15% of 4,384 real LFO slots surveyed
(always `1.0` when present). `kParamRate10x` (14%) is presumed a ×10 rate
multiplier, not independently confirmed — found specifically alongside a
chaotic-shape (Rossler/Lorenz) LFO with a very low base rate, where it may
be the difference between a near-static and a clearly-moving modulation.

**`kParamMono`**, found live 2026-07-29 in the same Galaxy investigation as
the warp-lane fix (§ above/below): the real preset's busiest LFO (rate 100,
`RandomSH` shape, driving a fast-arpeggiated oscillator) visibly kept
moving with no note held; the recreation's, without this field, appeared
frozen and was reported as feeling "too fast"/choppy. `kParamMono=1.0`
makes the LFO a single shared instance running continuously, independent
of note-on events, instead of a per-voice one that restarts its phase at
every note — under a fast arpeggiator, a per-voice LFO barely completes any
of its cycle before the next note resets it, plausibly explaining both
symptoms with one cause. Surveyed across 4,374 real LFO slots: only ever
`1.0` when present (63 slots) — absence is the common/default case, not
`0.0`. `kParamSwing` was found alongside it (only ever `1.0`, 9/4,374
slots) — presumed to affect a stepped LFO's shuffle/timing by analogy with
"swing" elsewhere, not independently confirmed.

### Macros & Global

8 macros (`Macro0..7`, each `{name, plainParams.kParamValue}`). `Global0`
covers master volume (confirmed default `0.5` = -9dB), mono toggle,
portamento time (`kParamPortamentoTime`, seconds — glide between notes),
poly count, and `limit_same_note_polyphony`
(`kParamLimitSameNotePolyphony`, found live 2026-07-29, present on 39% of
832 real `Global0` slots surveyed, always `True` when present — presumed
to cap voice-stacking when the same note retriggers rapidly, e.g. under a
fast arp, rather than letting overlapping voices for one note pile up),
all generatable via `GlobalSpec`; a handful of rarer global params
(`kParamS1Compatibility` — a legacy Serum-1-porting flag, deliberately not
generalized since it's not relevant to freshly-generated content — voice
count, tuning, MPE bend range, FX bus routing) are documented in
`schema.py` but not yet wired into generation.

### Effects

3 independent, PARALLEL racks (`FXRack0..2`) — **all 3 supported since
2026-07-29**, found live diagnosing why a from-scratch recreation of a real,
complex Unmute preset ("Galaxy") sounded nothing like the original despite
every other parameter matching closely: the real preset ran a second,
entirely independent 5-unit chain (incl. a real `FXReverb` and `FXBode`
frequency shifter) in `FXRack1`, alongside `FXRack0`'s 8 units — 100%
invisible to `extract_spec` before this fix, since it only ever read
`FXRack0`. Racks run in PARALLEL, not series — rack 1 is a second signal
path, not "what happens after rack 0". `FxUnitSpec.rack` (0-2, default 0)
selects which rack a generated unit lives in; editing a preset only
replaces the racks actually represented in the new `fx_chain` list, leaving
others (that the caller may not even know exist) untouched.

An FX unit's `destModuleID` (used when a mod-matrix route targets it, e.g.
`fx{i}.wet`) is **not** its position in a flat merged list — it's
`rack * 100 + position_within_that_rack`, confirmed against Galaxy's real
raw `ModSlot` data (e.g. an `FXBode` at rack-1 position 4 had
`destModuleID` 104; rack 0's own IDs are just `0 + position`, i.e. `0-99`
as before). `serum-mcp`'s own `fx{i}.wet` NAMING still addresses units by
their position in the flat `PresetSpec.fx_chain` list (spans all racks, in
rack-0-then-1-then-2 order) — only the internal raw `destModuleID` uses the
rack-encoded scheme; see `mapping._fx_dest_module_id`.

Each rack holds an ordered `FX` list; each entry has an integer
`type` selecting one of 16 effect kinds (`FX_TYPE_IDS` in `schema.py`) and a
`plainParams` dict specific to that type. 13 of the 16 are modeled with full
param schemas (`FXDistortion`, `FXChorus`, `FXFlanger`, `FXPhaser`,
`FXDelay`, `FXReverb`, `FXComp`, `FXEQ`, `FXFilter`, `FXBode` (frequency
shifter), `FXHyperD` ("hyper dimension" widener), `FXConv`
(convolution/IR — the IR file itself, `relativePathToIR`, isn't selectable
by generation, only its processing params), `FXUtils` (width/balance/HP-LP
cleanup; its `kParamWet` is `uncertain`-confidence, only 2 samples observed
using one).

The remaining 3 — `FXSplit`, `FXSplit3`, `FXSplitMS` — are structurally
different from every other FX type: instead of a flat `plainParams` dict,
they're band-splitter containers holding N nested sub-effect-chains (one per
frequency band, via `kParamModuleCount1/2/3`). They're cataloged in
`FX_TYPE_IDS` and round-trip fine, but aren't modeled in `FX_PARAMS` —
targeting them would need a recursive `FxUnitSpec` (an FX chain that itself
contains FX chains), which is a bigger feature than a flat param schema.

Found live against a real third-party bank (Unmüte's "Places", 180
presets): 90 of them (50%) use at least one of these split types, and
`extract_spec` used to raise a raw `KeyError` on every one (no `FX_PARAMS`
entry to look up a default `kParamWet` from) — `describe_preset`/
`edit_preset` were completely broken on roughly half of a real professional
bank. Fixed by skipping split-type entries during extraction instead of
crashing; `introspect.count_unmodeled_fx_units` lets a caller report how
many were skipped rather than silently under-representing the FX chain.
The branch-boundary semantics of `kParamModuleCount1/2/3` are still not
reverse-engineered with confidence — observed so far: `FXSplit` (2-way) with
only `kParamModuleCount2` set (e.g. `3.0`); `FXSplit3` (3-way) with
`kParamModuleCount2`/`kParamModuleCount3` both set (e.g. `1.0`/`2.0`);
`FXSplitMS` (mid/side) with `kParamModuleCount1` alone or paired with
`kParamModuleCount2`. Consistent with "how many of the following flat FX-
list entries belong to this branch," but not verified across enough
examples to build a recursive `FxUnitSpec` from with confidence yet.

We also confirmed empirically that an FX entry's `destModuleID` in the mod
matrix encodes *which rack* an FX unit lives in: `0-11` for rack 0 slots,
`100-111` for rack 1, `200-211` for rack 2 (e.g. `FXComp` destinations
`0, 1, ..., 9, 14` alongside `101, 102` and `205 `in our sample).

### Arpeggiator (`Arp0` / `ArpClip0..11`)

Previously explicitly out of scope (see the exclusions list in this file's
intro); reverse-engineered and wired up as `ArpSpec` (2026-07-28) after a
direct request to see whether it could be recreated at all.

Structure: `Arp0` is just an on/off toggle (`kParamEnabled`) plus which of
12 `ArpClip{i}` pattern slots is active (`kParamActiveClipID`, almost
always absent → implicitly slot 0). Real content overwhelmingly uses only
slot 0; `ArpSpec` always targets it and never sets `kParamActiveClipID`.
An unpopulated `ArpClip` slot has `plainParams: "default"` (same sentinel
as `VoiceFilter`/FX) and `clip: {}`.

Two structurally distinct pattern modes share `kParamShape` (and the
independent `kParamTransposeShape`, which modulates transposition using
the *same* enum on its own schedule):

- **Algorithmic** (Played, Chord, Converge/Diverge/ConvAndDiv, Down/UpDown/
  DownUp/UpAndDown/DownAndUp, ThumbUp/ThumbUD, Rand/RandOnce/RandDrift/
  RandNoDup — 16 confirmed values excluding Pattern) — just a handful of
  knobs (`kParamRate`, `kParamGate`, `kParamDotted`, `kParamTriplets`,
  `kParamTransposeShift`), no note data. **Generatable** via `ArpSpec`.
  The distinction between e.g. `UpDown`/`DownUp`/`UpAndDown`/`DownAndUp`
  (4 separate confirmed raw values) isn't understood — likely whether the
  turnaround note at the top/bottom repeats, unverified.
- **`Pattern`**: a real hand-drawn MIDI-clip-like note list in the same
  clip's own `clip.notes` array (`noteNum`/`timeStamp`/`length`/`channel`,
  plus an 8-float `attributes` vector and `expressionEvents`). The single
  MOST COMMON shape value in real content (101/844 presets' populated
  clips). **Generatable** via `ArpSpec.pattern` (a list of
  `ArpPatternNoteSpec`), added 2026-07-28 in a second pass after the
  algorithmic modes, with two deliberate simplifications vs. the full real
  format:
  - **Fixed attributes vector.** Surveying 1507 real notes across all 844
    presets found 283 *distinct* attribute vectors, not one constant one as
    a single earlier example suggested — but 7 of the 8 values were
    constant throughout (`[0.5, 1.0, 0.0, 0.0, 0.0, 0.5, ?, 0.5039...]`);
    only index 6 varied, meaning unknown. Index 7's precise value
    (`0.5039370078740157` = 64/127) suggests a MIDI-CC-style 0-127 range
    normalized to 0..1 with 64 ("centered") as the default. Every generated
    note uses the same constant vector; index 6 isn't exposed.
    `expressionEvents` (per-note automation curves on one of 5 lanes) was
    non-`None` on only 6 of 1507 real notes — always written as
    `[None]*5`.
  - **Grid-quantized timing**, not the free timestamps the real format
    supports. `ArpPatternNoteSpec.step`/`length_steps` are integers/simple
    multiples of `ArpSpec.pattern_step_beats` (default 0.25 = 16th notes).
    On read-back, `introspect._infer_step_beats` picks the COARSEST musical
    grid (whole notes down to 64th notes, straight and triplet) that
    explains every real timestamp/length within a small tolerance, rather
    than assuming 0.25 or computing an exact GCD — found live, real timing
    data mixes genuine floating-point serialization noise around a clean
    value (e.g. `0.49999999999999734`/`0.5000000000000027` both meaning
    "half a beat") with occasional genuinely non-gridded/"humanized"
    timestamps (`0.4411764705882355`, no clean musical fraction) in the
    *same* clip — an exact-GCD approach is far too sensitive to either and
    can infer an absurdly fine step size (one real preset's GCD blew up to
    62500 step-units for a single note). Verified round-trip-exact
    (extract → reapply, notes byte-identical) against all 15 real presets
    surveyed whose `ArpClip0` itself uses `Pattern` shape.

`kParamRate`'s real musical meaning (note division? Hz?) is **uncertain**
— only 2 distinct values seen across 844 presets; most enabled clips don't
set it explicitly at all. `kParamGate` can exceed 100% (observed up to
~146, legato overlap into the next step). Two more `Arp0`/`ArpClip` fields
(`kParamLaunchQuantize`, note-level velocity/retrig/chance humanization
params) are cataloged in `schema.py` but not exposed via `ArpSpec` yet.

**Confirmed live** (2026-07-29, real Serum 2 in FL Studio 21), both modes:
the original `_ArpTest/` presets (`up_down` and `chord` shapes, algorithmic
mode) loaded and arpeggiated correctly on a held chord. `Pattern` mode took
7 rounds of live testing to get right — worth recording the actual
debugging path since it's a real methodology lesson, not just a result:

1. First attempt (all fields as initially guessed) failed silently: loaded
   fine, played only a single continuous note, chords included.
2. Grafting a real, confirmed-working Factory preset's ArpClip0 (`ARP -
   Acid101`) onto our own generation pipeline worked, isolating the bug to
   what values we generate, not the base pipeline.
3. Two guessed fixes (kParamDotted/kParamTriplets never written at 0.0;
   dropping `regionEndBeats`, which a working real example omits) were
   both plausible from the evidence at the time, applied together, and
   **did not fix it** -- still stuck on one note.
4. A proper 3-way isolated diagnostic (swap ONLY the notes, ONLY the
   plainParams, or ONLY the attributes vector between our generated data
   and Acid101's real data, keeping everything else from the known-working
   side) found: our note values were fine, our attributes vector was fine,
   but Acid101's plainParams were required -- narrowing the real cause to
   *something* in kParamRate/kParamGate/kParamNoteRetrig/kParamWrapRange/
   kParamWrapTranspose collectively, still not one field.
5. Adding just kParamNoteRetrig (the most plausible-*sounding* name) was
   tried next and **did not fix it either** -- still stuck.
6. A genuinely single-variable isolation (two presets, each swapping in
   Acid101's real value for exactly one of kParamRate or kParamGate,
   nothing else) finally found it: kParamRate's value alone was the cause.
   kParamGate made no difference.

**Actual root cause**: `kParamRate`'s default of 0.25 froze a real
generated Pattern-mode clip on its first note; raising it to ~0.5 (a real
Factory preset's value) fixed it with every other field held identical.
kParamNoteRetrig/kParamWrapRange/kParamWrapTranspose were never
individually proven necessary -- they're still written (present in every
real working example, never observed to cause harm) but their `schema.py`
notes say so honestly rather than repeating the disproven claim that they
were "the fix." The lesson worth keeping: when multiple fields differ
between a working and a broken example, changing several plausible-looking
ones at once and testing live doesn't actually tell you which one mattered
-- only a true single-variable swap does, and steps 3 and 5 above cost two
extra full live-test round-trips by skipping that discipline.

The exact meaning of `kParamRate` beyond "must not be too low for
`Pattern`", the `UpDown`/`DownUp`/`UpAndDown`/`DownAndUp` distinction, and
Pattern mode's attribute-vector index 6 remain unverified specifics either
way.

## 5. Known gaps and open questions

**Edit round-trip stress test (2026-07-28)**: `extract_spec` then `apply_spec`
was run against all 844 real `.SerumPreset` files installed on a real
machine — all 626 official Xfer Factory presets plus 6 third-party banks
(Unmute's "Places" 180-preset pack, PNL, RAGE x2, Starcore, plus this
project's own 21 Savage Bank), as a stand-in for "can `edit_preset` handle
real-world content, not just our own fixtures." Found and fixed, across
several passes: two `"default"`-sentinel-string crashes (FX and mod-route
`plainParams`, same class as the earlier `VoiceFilter` one), `FXSplit`/
`FXSplit3`/`FXSplitMS` crashing `extract_spec` entirely (see §4), roughly 30
undersized min/max bounds and incomplete enum catalogs (kParamRelease,
kParamAttack, kParamRise, kParamPortamentoTime, kParamCoarsePit, kParamFine,
several FX params, and the `VoiceFilter`/`FXFilter` filter-type and
`WTOsc`/`SampleOsc` warp-mode enums — all corrected with the real observed
value in the `notes` field), a `Path.__truediv__` bug where a leading-slash
raw wavetable reference (e.g. `"/Analog/Basic Shapes.wav"`, genuine Factory
data) silently resolved to the wrong location, `validate_params`'s
`allow_unknown` not being applied at 10 of 12 call sites (letting real,
uncatalogued-but-legitimate params from third-party content block an edit
that never touched them), and the bool-kind check rejecting an
already-CBOR-safe float pass-through value. Also added a fast path
(`_unchanged_sample_reference`) so an oscillator whose `sample_playback_source`
hasn't actually changed skips re-copying/re-validating its file — needed
because Serum's own Factory sample library is almost entirely `.flac`,
which this project can't ingest (no FLAC decoder), and without the fast
path *any* edit touching a later oscillator in the list would fail trying
to re-process an untouched `.flac` reference just to preserve position.

**Galaxy recreation investigation (2026-07-29)**: attempting to recreate a
single real, complex Unmute preset (`UN_PLACES_ARP_120_Galaxy`) from
scratch via `generate_preset` surfaced two significant gaps at once, found
by comparing `extract_spec`'s output against the preset's *raw* CBOR
directly rather than trusting the extracted `PresetSpec` was complete:

1. **Multi-rack FX (fixed, see §4)** — `extract_spec`/`apply_spec` only
   ever touched `FXRack0`; a real second, parallel rack (`FXRack1`, 5 units
   incl. `FXReverb`/`FXBode`) was invisible. Now fully supported.
2. **Mod-route destination coverage is narrower than it looks.** The raw
   file had **27** active `ModSlot`s; `extract_spec` surfaced only 11
   (14 after the FX-rack fix) — the rest silently dropped because their
   *destination* isn't in `MOD_DEST_TARGETS`, not because their source is
   unresolved. Newly-observed destination categories with zero coverage:
   `Arp` params (`kParamGate`, `kParamChance` — modulating the arpeggiator
   itself), a `WTOsc` secondary warp control (`kParamWarpVar2`, distinct
   from the modeled `kParamWarp`), `NoiseOsc.kParamColor`, non-wet FX
   params (e.g. `FXEQ.kParamFreq2`, `FXUtils.kParamWidth`/`kParamLPF` —
   currently only each FX unit's `kParamWet` is a valid mod destination),
   `VoiceFilter.kParamWet`/`kParamReso` via some routes, `Global.
   kParamVoiceAmp`, and `VoicePanel.kParamGlobalScalingEnvTime`. None of
   these are wired into `MOD_DEST_TARGETS` or generatable yet. Also found:
   3 more unresolved mod **source** IDs beyond §6's list — `24`, `40`, `57`
   — each seen exactly once in this file, not enough on their own to
   identify via the direct-probe method (which needs a real Serum UI
   session, not passive observation) — flagged for a future probe round.
3. **`FilterSpec` was missing `var`/`key_track`/`wet`/`level_out` (fixed,
   see the Filters section above)** — found by a byte-for-byte comparison
   of Osc A's raw data between the recreation and the original (which
   matched almost exactly at the time, ruling out the oscillator as the
   cause *given what was checked*) followed by the same comparison for
   `VoiceFilter0`, which didn't match: `var` (already documented in
   `schema.py` as meaningful-per-filter-type, e.g. comb spacing) was
   silently 0 instead of the real preset's `65.1`. Plausible contributor
   for the `DistComb1BP` filter type this preset uses, but fixing it alone
   did NOT resolve the reported "8-bit" character — see item 4.
4. **`OscillatorSpec` was missing a second warp lane entirely (fixed, see
   the Oscillators §8 note above)** — after item 3's fix
   still didn't help, a FULL (not partial) byte-for-byte comparison of Osc
   A's raw `WTOsc0` `plainParams` (every key, not just the ones this
   project already modeled) found `kParamWarp2`/`kParamWarpMenu2`: a
   second, independent warp stage (`kFilterLPF` at 56%) taming the primary
   `kFM_NOISE` warp's otherwise-raw/digital character. This had a
   `ParamDef` in `schema.py` since early in the project but was never
   exposed via `OscillatorSpec` or written by `apply_spec` — the earlier
   "matched almost exactly" comparison in item 3 had only checked the
   fields this project already knew to look for, not the full raw dict.
   Lesson for future investigations of this kind: compare *every* raw key,
   not just the modeled subset, or a real gap looks like a match.
5. **`LfoSpec` was missing `mono`/`swing` (fixed, see the LFOs section
   above)** — after item 4's fix still didn't resolve it, the user reported
   a specific, concrete symptom (the real preset's LFO visibly moves with
   no note held; the recreation's doesn't) rather than just "still sounds
   wrong" — a much more actionable bug report, and the direct lead to
   `kParamMono`. Also fixed `kParamSwing` at the same time (lower
   confidence, found alongside it).
6. **`kParamWarpVar2` — a mod-matrix destination on Osc A specifically,
   still unmodeled after item 4 (fixed, see the WTOsc note in the
   Oscillators §8 section above)** — asked directly "can you fully
   analyze this preset, or are there real technical holes", which prompted
   an exact count: 27 raw mod
   routes, 14 reproduced at the time. Of the 13 gaps, this one stood out as
   the most likely to matter for TONE specifically (the others are mostly
   `Arp`/`Global`/`VoicePanel`/non-wet-FX-param destinations, or blocked by
   3 still-unresolved source IDs) because it targets Osc A, the oscillator
   repeatedly flagged as sounding wrong. `destModuleParamID` confirmed 4
   directly from the real preset's raw `ModSlot4`. Fixed
   (`OscillatorSpec.warp_var2`, `oscillator{i}.warp_var2` mod destination)
   — 15/27 routes now reproduced.
7. **A second, deliberately-chosen recreation (`UN_PLACES_PL_Dreams`)
   surfaced a different kind of gap: a whole unmodeled oscillator
   engine.** Asked to drop the Galaxy-specific arp gaps and instead pick a
   preset entirely within scope — surveyed all 180 Unmute presets for
   single-rack FX, no sample oscillators, and the fewest silently-dropped
   mod routes; `Dreams` had only 2 of 14. Its Osc C turned out to be a real
   `SpectralOsc` (`kOsc_Spectral`, referencing a genuine Factory `.flac`,
   confirmed independently by a macro literally named "SPECTRAL SAND") —
   see item 3 above (Unmodeled oscillator engines) for the full raw
   structure and why this wasn't generalized into a feature, just patched
   in as a one-off for this single recreation.
8. **`Global.kParamVoiceAmp` and `FXUtils.kParamBalance` (fixed, see §6 and
   the Effects section in §4)** — Dreams's other 2 unreproduced routes.
   `Global.kParamVoiceAmp` had already appeared in Galaxy too (both real
   presets used `key_track -> Global.kParamVoiceAmp`, independently
   confirming both the destination and its `destModuleParamID`, 2) —
   strong enough evidence to add as a proper, reusable `MOD_DEST_TARGETS`
   entry (`global.voice_amp`) rather than a one-off patch.
   `FXUtils.kParamBalance` (`destModuleParamID` 4) is type-specific,
   confirmed once — added via a new, deliberately-scoped
   `FX_EXTRA_MOD_DEST_PARAMS` mechanism (`fx{i}.balance`) that only
   applies to FX types where a param has actually been confirmed, rather
   than assuming any non-wet FX param can be addressed generically.
   Result: **14/14** of Dreams's real mod routes now reproduced, and
   Galaxy went from 15 to 16/27 for free (same fix, independent
   confirmation).
9. **Per-instrument-module fields never checked at all, found by a
   systematic FULL raw-`plainParams` diff** (fixed where general, patched
   where one-off — see the Oscillators/Envelopes/LFOs/Macros & Global
   sections above) — user asked to check for "other small things" after
   catching `kParamFine` by eye (comparing Serum's own UI); rather than
   keep chasing individual fields, every module's *complete* raw
   `plainParams` dict was diffed against the original at once. Found:
   `kParamFine` (oscillators, on 2 of 3 active slots), `kParamCurve1/2/3`
   (envelopes, on literally every envelope — 97% corpus prevalence),
   `kParamLimitSameNotePolyphony` (global), `kParamDotted`/`kParamTriplets`/
   `kParamRate10x` (LFOs). All fixed generally. Also found, and left as
   one-off patches (see item 7, §6's curve-shaping note, and the Global
   section above): `SpectralOsc`'s extra `kParamPosition`/`kParamScanRate`/
   `kParamManualPositionMode`, `Global.kParamS1Compatibility`, and
   per-route curve shaping on 2 mod routes. Result: **zero remaining raw
   `plainParams` differences** across every oscillator/filter/envelope/LFO/
   global module for this specific recreation (`kParamDefaultMode`
   excepted — always `0.0` everywhere, confirmed inert).
10. **Presence of a param, not just its value, can change the sound —
    confirmed on 4 params, fixed generally (see the Filters section and
    `mapping.build_fx_unit`).** After item 9's "zero diff" result, Dreams
    still had a persistent fuzzy/buzzy character. A real-preset FX unit's
    `kParamWet` is ABSENT whenever it would be 100 (fully wet), explicit
    only for other values — writing an explicit `kParamWet=100.0`
    (mathematically "the same") was audibly non-transparent, most likely
    because Serum skips the wet/dry crossfade computation entirely when the
    key is absent vs. actually running a 100/0 mix when it's present. The
    same pattern held for `VoiceFilter.kParamWet`/`kParamLevelOut`/
    `kParamDrive`/`kParamStereo` — all four confirmed absent on Dreams's
    real `VoiceFilter0`/`1` despite `FilterSpec` always writing them at
    their schema-documented neutral defaults (100/0.5/0.0/50.0). A
    real-corpus survey confirmed `kParamStereo` absent in 1162/1300 (89%)
    real filters — not a one-off. Fixed by omitting each of these params
    from the written `plainParams` whenever the spec value equals its
    neutral default, both on write (`mapping.py`) and on the FX read side
    (`introspect.py` previously fell back to each FX type's own
    schema-documented default when absent, e.g. FXDelay's 30.0, instead of
    the universal true absent-state value of 100.0).
11. **A whole unmodeled oscillator-to-filter/filter-to-output routing
    system (`RoutingSlot0-6`), plus a real bug in the shared generation
    fixture (fixed, both — see the note after this list).** Even after item
    10's fix, Dreams was still fuzzy, then (once that resolved) still
    noticeably quieter than the original on an isolated oscillator. A full
    recursive diff (same technique as item 9 but on the whole data tree,
    not just `plainParams`) turned up 7 top-level `RoutingSlot` nodes never
    looked at before. Confirmed via user-provided screenshots (OSC-tab
    per-filter routing toggles, then the MIX tab): `RoutingSlot0-4` are the
    5 oscillators' filter-routing choice (which of Filter 1/Filter 2/both/
    neither/an FX bus each one feeds — real preset: Osc A + Osc B + Noise
    feed Filter 2, not just Osc A as this project had been silently
    defaulting to); `RoutingSlot5`/`RoutingSlot6` are each FILTER's own
    output-routing choice (`"MAIN"` = direct to output, i.e. parallel dual
    filters, vs `"FILTER"` = cascade into the other filter, i.e. serial —
    the real preset uses `"MAIN"` for Filter 1). The quieter-oscillator
    symptom was explained by arithmetic, not guesswork: bisecting by
    toggling each filter's power button while soloing one oscillator showed
    either filter ALONE cost only 1-2dB, but BOTH together cost 8dB more
    than the real preset's both-on state — additive/serial loss, not
    parallel. Not generalized into `PresetSpec` this session (still a
    one-off raw-CBOR patch reproducing the real preset's exact
    `RoutingSlot` values) — full enum/semantics (`kRoutingDestFilter`/
    `kRoutingDestNone`/`kRoutingDestDirect`/`kRoutingDestMaster`,
    `kParamFilterBalance`, `kParamFXBus1Level`/`kParamFXBus2Level`) surveyed
    across the real corpus but not yet wired into a spec field.

12. **A third real preset (`UN_PLACES_BA_Beyond`), recreated one-shot to
    test whether items 10-11's fixes generalize (fixed further, mostly —
    see the open item below).** Deliberately picked for using SERIAL
    filter routing (Filter 2 → Filter 1), the opposite direction from
    Dreams' parallel setup. Built directly from `extract_spec(real_file)`
    and generated with zero errors on the first attempt. A pre-emptive full
    diff (before even asking the user to listen) found 2 more
    `VoiceFilter` params following item 10's exact pattern —
    `kParamReso`/`kParamVar` absent-at-default in the real file, always
    written by `serum-mcp` — generalized into a single
    `_FILTER_KEYS_OMIT_AT_DEFAULT` table (`kParamFreq`/cutoff deliberately
    excluded: present in 96% of real filters, the opposite skew). Then the
    SAME pattern again on `LFO` — `kParamRate=0.0` is a literal 0Hz freeze,
    not a neutral value, so an untouched LFO sat frozen instead of running
    at Serum's real default; a user screenshot (note held) showed the real
    LFO's RATE readout in BPM-synced mode ("1/4") despite the file having
    neither `kParamRate` nor `kParamBeatSync` — generalized to the entire
    `_LFO_KEYS` set (delay/rise/mono/swing/dotted/triplets/rate10x all
    similarly 83-99% absent by survey) via `_LFO_KEYS_OMIT_AT_DEFAULT`.
    Also added `FXUtils.kParamLevelOut` as a confirmed mod destination
    (`FX_EXTRA_MOD_DEST_PARAMS`), and resolved 5 more mod **source** IDs via
    a 3rd direct-UI-probe round: `release_velo=37`, `active_voices=55`,
    `voice_mod1=56`, `voice_mod2=57`, `voice_index=58` (see §6) —
    `voice_mod2` also incidentally closes one of Galaxy's 3 long-standing
    unknown source IDs. Empirically confirmed (not guessed) that Serum's
    genuine absent-state LFO rate default really is "1/4" BPM-synced, via
    live probing of a real Serum instance (`kParamRate=10.66` reads back
    for an explicit `1/8`; returning to `1/4` makes Serum omit the key
    again) — ruling out rate/beat_sync as the cause of the remaining open
    item below.

13. **RESOLVED (was "still open" above): the LFO curve mystery was a
    completely unmodeled structural link, not a rendering fluke.** A
    top-level key this project had never looked at, `lfoPointModAssignments`
    (a small array: `[{busID, lfoID, lfoType, pointID, target}]`), declares
    that a SPECIFIC POINT on an LFO's hand-drawn curve (`pointID`, indexing
    into `curveData`'s own point list) is live-modulatable via a dedicated
    `LFOPointModBus{N}` module + a `ModSlot` targeting it
    (`destModuleTypeString: "LFOPointModBus"`, `destModuleID` = busID).
    Real Beyond preset: `lfoPointModAssignments=[{busID:0, lfoID:0,
    lfoType:0, pointID:1, target:0}]` plus a `ModSlot` routing the (then-
    unidentified) source `38` into `LFOPointModBus0`. `serum-mcp` wrote
    neither the assignment array nor the ModSlot at all, so LFO0's point #1
    was static in the recreation while the real preset's genuinely animated
    in real time — this, not any curveData/rate difference, was the entire
    "renders differently" mystery. Fixed as a one-off raw-CBOR patch
    (assignment array + ModSlot copied verbatim); confirmed live ("ça bouge
    comme sur l'original"). Not generalized into `PresetSpec` — see item 14.

14. **The "Fixed" mod source (id `38`) and its "Aux Source" mechanism,
    investigated in depth 2026-07-30.** Serum's own MATRIX-tab UI names
    source `38` literally "Fixed" (a constant/manual base amount,
    `kParamAmount`), paired with an independent AUX SOURCE (visible as its
    own MATRIX-tab column) that scales or gates it — confirmed via a
    user-provided screenshot showing 3 real "Fixed" rows, each with a
    DIFFERENT macro as its AUX SOURCE. `source[1]` (subIndex, "always 0,
    unresolved" everywhere else in this schema) turned out to encode WHICH
    macro is the aux source for `source[0]=38` specifically: `subIndex =
    25 + macro_index` (i.e. the same numbering as `MOD_SOURCE_IDS`'s own
    macro block) — confirmed exactly against 3 independent real routes.
    Empirically confirmed the mechanism itself works (built a minimal probe
    preset, `kParamAmount=80` gated by a macro at 0 → silent, same macro at
    100 → audible). **Still unresolved**: the exact DSP formula combining
    `kParamAmount` with the aux macro's value (simple `amount * aux/100`?
    something curve-shaped via `kParamAuxCurve`? inverted via
    `kParamAuxInverted`?) — not decoded, and the AUX-PAIRED case remains a
    one-off raw-CBOR copy only.

    **Update 2026-07-30, the common (no-aux) case wired up first**: a
    23-route "Fixed"-only survey found 78% (18/23) use no aux-macro pairing
    at all — bare `subIndex=0`. Since `mapping._build_modslot_entry` already
    always wrote `subIndex=0` (every mod source worked this way), adding
    `source='fixed'` (id 38) to `MOD_SOURCE_IDS` made this majority case
    generatable with no other code changes. Verified round-trip against
    `LOOP - Breakwave.SerumPreset` (2 real bare "Fixed" routes on
    `oscillator1.octave`/`oscillator1.pitch`).

    **Update 2026-07-30, reframed and generalized**: a wider survey (every
    `ModSlot` across all 626 Factory presets, not just `source[0]=38`) found
    the "Aux Source" mechanism was never `fixed`-specific at all — it was
    just the first example noticed. **1276 real routes** (a huge fraction of
    all mod routes surveyed) pair a primary source with a second, aux one,
    spanning nearly every source family (LFOs, envelopes, macros,
    `random_discrete`, `fixed` itself, ...). `source[1]`/subIndex is simply
    a SECOND id from the exact same `MOD_SOURCE_IDS` space as `source[0]` —
    the earlier "`subIndex = 25 + macro_index`" finding was correct but only
    because the 3 originally-probed examples happened to use a macro as
    their aux; `subIndex` values matching `mod_wheel` (1), `aftertouch`
    (18), and other non-macro sources are just as common (by far the two
    most popular aux picks: `mod_wheel` and `aftertouch` — a classic
    "player-controllable modulation depth" pattern, e.g. an LFO's vibrato
    depth wired to the mod wheel or aftertouch instead of being routed to
    pitch directly). `0` never collides with a real source id, so it
    remains an unambiguous "no aux" sentinel across every source family.

    Now generalized into `ModRouteSpec.aux_source`/`aux_inverted`, usable
    with ANY `source`/`destination` pair, not just `fixed`. Verified
    round-trip by extracting real routes from multiple Factory presets
    (`ARP - Acid101.SerumPreset`: `env1 -> filter1.cutoff` aux `macro0`;
    `ARP - Blossom Tree Sprites.SerumPreset`: `lfo3 -> oscillator0.fine` aux
    `mod_wheel`; `ARP - Altar.SerumPreset`: `random_discrete ->
    oscillator0.pan` aux `macro7`; several more). `kParamAuxInverted`
    presence rate confirmed at 2.8% of aux-paired routes (36/1276, always
    literally "on" when present, never explicitly "off") and
    `kParamAuxCurve` at 0.16% (2/1276) — curve-shaping is essentially never
    used in real content, so it stays unexposed.

    **RESOLVED 2026-07-31, via the automated audio-rendering pipeline** (see
    [[reference-serum-verify-audio-pipeline]]) — the DSP combination formula
    that resisted every static-analysis attempt turned out to be exactly the
    simplest hypothesis: **`effective_amount = kParamAmount × (aux_value /
    100)`**, and with `kParamAuxInverted=True`, **`effective_amount =
    kParamAmount × (1 − aux_value / 100)`**. Confirmed by routing
    `source='fixed'` (`amount=50.0`) at `filter0.cutoff` with `aux_source=
    'macro0'`, sweeping the macro's own value 0/25/50/75/100, and measuring
    the RESULTING cutoff via spectral rolloff against the freshly-calibrated
    filter cutoff curve (item 2) — a clean, monotonic, near-exactly-linear
    relationship (aux=0 → 0% of the full shift, exactly matching the
    unmodulated base; aux=50 → 50.0% of the full shift, landing exactly on
    the cutoff=0.75 calibration point; aux=100 → 100%, exactly matching the
    same result as no aux source at all). `aux_inverted=True` at aux=0/100
    produced the exact mirror image (100%/0% respectively), confirming both
    directions. This closes the very first item on this project's original
    "biggest remaining gaps" list — years (well, days) of static analysis
    couldn't crack it, but a handful of rendered-audio measurements did in
    one pass. `ModRouteSpec.aux_source`/`aux_inverted`'s docstrings no
    longer need to hedge on this.

15. **RoutingSlot and ModSlot's full private param lists, mined from the
    VST3 binary's own debug strings 2026-07-30** (the same technique that
    cracked the LFO rate encoding). `RoutingSlot`'s automatable enum is
    confirmed complete: `kParamFilterBalance, kParamFXBus1Level,
    kParamFXBus2Level` (nothing hidden) plus one private param never seen
    before, `kParamViaEnv1` — presumably gates the routing choice via
    Envelope 1, but every one of 49 real occurrences surveyed was `0.0`
    (never observed enabled), so low-priority. `kRoutingDestFilter/Master/
    Direct/None`'s exact ordinal values (0/1/2/3) are now confirmed. Also
    found `Global0`'s complementary bus-level controls, never looked for
    before: `kParamDirectVol` (volume for `kRoutingDestDirect`-routed
    signal), `kParamFXBus1Vol`/`kParamFXBus2Vol` (each bus's aggregate
    volume — confirmed real values EXCEED 1.0, a genuine boost stage, not
    just 0-100% attenuation like most params in this schema), and
    `kParamFXBus1Dest`/`kParamFXBus2Dest` (small-integer enum, meaning per
    integer not decoded). All added to `schema.py` (`GLOBAL_PARAMS`,
    the new `ROUTING_SLOT_PARAMS`) for documentation/round-trip safety;
    none wired into `PresetSpec`. Separately, mining `ModSlot`'s own private
    param enum found SEVEN more never-before-seen per-route fields:
    `kParamSmoothRise`/`kParamSmoothFall`/`kParamSmoothLink` (a mod route's
    OWN rise/fall smoothing, independent of the source's own smoothing),
    `kParamDelayOffset`/`kParamDelayBeatSync` (a per-route delay before the
    modulation kicks in — real corpus use is 100% confined to "LOOP"-
    category presets), `kParamAuxCurveData` (a curve-shape flag for the AUX
    source, sibling to the already-known `kParamMainCurveData` for the main
    source — confirmed BOTH are flags whose real point data lives in a
    sibling `flex` key, not the value itself), and `kParamBypass`. All rare
    (0.04-3.2% of 17,861 real mod slots surveyed) but genuinely real, now
    documented in `MODSLOT_PARAMS`. Found and fixed a real, live bug this
    surfaced: `_build_modslot_entry` built each `ModSlot`'s `plainParams`
    fresh from scratch, so any `edit_preset` call touching a route carrying
    one of these fields (even just nudging its amount) silently discarded
    it. Fixed to merge onto the existing slot instead when reusing one (see
    `_find_existing_modslot_index`); verified against the real corpus
    (423/450 real routes using an exotic field round-tripped with zero
    loss; the other 27 hit already-known, unrelated `extract_spec`/
    `apply_spec` gaps unrelated to this fix, e.g. FXDelay range/wavetable-
    path issues).

16. **`FilterSpec.output_routing` -- RoutingSlot5/6's parallel-vs-series
    piece is now a real `PresetSpec` field, not a one-off patch only.**
    The best-understood, highest-confidence slice of the RoutingSlot system
    (confirmed live on two independent real presets, opposite directions)
    is now generatable directly: `filters[i].output_routing = "parallel"`
    (explicit `kRoutingDestMaster`) or `"series"` (explicit
    `kRoutingDestFilter`, cascades into the OTHER filter). Left unset (the
    default) writes nothing, matching Serum's real absent-state default
    (parallel) rather than writing it explicitly. Setting both filters to
    `"series"` at once (a routing cycle) raises `ValueError` instead of
    silently producing a broken preset. `extract_spec` reads it back the
    same way, confirmed against both real files: Dreams' Filter 1 is
    genuinely absent (extracts `None`, not `"parallel"` -- the earlier
    write-up's "explicit MAIN" phrasing was about the FIXTURE bug being
    fixed to genuine absence, not the real file itself being explicit);
    Beyond's Filter 2 extracts `"series"` exactly as expected. The rest of
    RoutingSlot (oscillator-to-filter assignment via `RoutingSlot0-4`,
    `kParamFilterBalance`'s exact scale, the FX-bus send system) remains
    unwired -- lower confidence, not attempted this round.

17. **`OscillatorSpec.filter_routing`/`filter_balance` -- RoutingSlot0-4,
    each oscillator's own INPUT routing choice, is now also a real
    `PresetSpec` field.** Distinct from item 16 above (which is each
    FILTER's own OUTPUT routing): `oscillators[i].filter_routing` is one of
    `"filter"` (default when unset, normal path through the enabled
    VoiceFilter(s)), `"master"` (bypasses both filters straight to the main
    output), `"direct"` (bypasses filters AND the FX bus system), or
    `"none"`. `filter_balance` (0-100) sets `kParamFilterBalance` when both
    filters are in use and this oscillator routes through them; exact scale
    still not independently confirmed (see item 11), only that a real
    Dreams route used 100.0 while visually routed toward Filter 2. Left
    unset, nothing is written, matching the real absent-state default
    (`kRoutingDestFilter`) rather than writing it explicitly. Verified by
    extracting both fields back out of the real one-off `RoutingSlot0-4`
    patches made recreating Dreams (`RoutingSlot2`:
    `kParamFilterBalance=100.0` + `kParamRoutingDest='kRoutingDestFilter'`
    round-trips to `filter_routing="filter"`, `filter_balance=100.0`) and
    Beyond.

18. **The FX-bus send system is now wired end-to-end, closing out the last
    open piece of items 16/17.** `oscillators[i].fx_bus1_send`/
    `fx_bus2_send` and `filters[i].fx_bus1_send`/`fx_bus2_send` (0-100) set
    `kParamFXBus1Level`/`kParamFXBus2Level` on that source's own
    `RoutingSlot` -- a genuine aux send, independent of and not mutually
    exclusive with `filter_routing`/`output_routing`'s main destination.
    `GlobalSpec.fx_bus1_volume`/`fx_bus2_volume` set the bus's own aggregate
    level (`kParamFXBus1Vol`/`kParamFXBus2Vol` on `Global0`, CAN exceed 1.0 —
    a real boost stage, real values seen 0.26-1.75) and
    `GlobalSpec.direct_volume` sets `kParamDirectVol` (the level for any
    source routed with `filter_routing`/`output_routing='direct'`, real
    values seen well below unity, 0.21-0.43, reason unconfirmed). All four
    are `None` by default and write nothing unless explicitly set, matching
    Serum's real absent-state default.

19. **`kParamFXBus1Dest`/`kParamFXBus2Dest` decoded and wired up, closing the
    very last open piece of the RoutingSlot/FX-bus system.** A full
    626-preset Factory corpus survey (2026-07-30) found only two raw values
    ever appear: `1.0` (14 occurrences on bus 1, 6 on bus 2) and `2.0` (5 on
    bus 1, 2 on bus 2) — never `0.0` or `3.0`. That's exactly
    `RoutingSlot.kParamRoutingDest`'s own `kRoutingDestMaster`/
    `kRoutingDestDirect` ordinals, and never its `kRoutingDestFilter`/
    `kRoutingDestNone` ones — which makes sense (a post-FX-chain bus return
    routing "into a filter" that's already been passed, or "nowhere",
    would be nonsensical). **Caught mid-implementation**: unlike
    `RoutingSlot`, which stores this same enum as a literal string (e.g.
    `'kRoutingDestFilter'`), `Global0` stores `kParamFXBus1Dest`/
    `kParamFXBus2Dest` as a raw float ordinal (`1.0`/`2.0`) — confirmed
    directly against real Factory CBOR after an initial string-based
    implementation would have written the wrong CBOR value (the same class
    of bug as the historic bool/int wire-type crashes). `schema.py` keeps
    `kind="float"` for both keys for that reason; `GlobalSpec.
    fx_bus1_destination`/`fx_bus2_destination` (`"master"`/`"direct"`/
    `None`) do the string↔ordinal translation in `mapping.py`/
    `introspect.py` instead. Verified round-trip against 5 real Factory
    presets spanning all 4 combinations of set/unset per bus.

**Fixture bug, not a schema gap** (fixed): `fixtures/init_preset.SerumPreset`
— the blank template every `generate_preset`/`edit_preset` call starts
from — was built (`scripts/build_fixture.py`, one-off) by resetting most
modules from a real donor preset (`BA - Sub Sustain - mids`) to blank
defaults, but never touched `RoutingSlot0-6`. `RoutingSlot5` (Filter 1's own
output routing) was left at the donor's value, `kRoutingDestFilter`
(cascade into Filter 2) — meaning **every** `serum-mcp`-generated preset
with both filters enabled has been silently running them in series instead
of parallel since the project's first commit, not just Dreams. Fixed by
resetting all 7 `RoutingSlot`s to genuine absent/default in the fixture
itself (2026-07-29) — this is a code fix, not a documentation gap, and
needs no `PresetSpec` changes to take effect for future generations.

**Still open** (not pursued further this session): for Galaxy specifically,
11 of 27 routes remain unreproduced — `Arp` params (3 routes),
`NoiseOsc.kParamColor`, a few more non-wet FX params (`FXEQ.kParamFreq2`,
`FXUtils.kParamWidth`/`kParamLPF`), `VoicePanel.kParamGlobalScalingEnvTime`,
`VoiceFilter.kParamWet`, plus 3 unresolved source IDs (`24`, `40`, `57`)
blocking a couple of routes whose destination *is* already modeled. The
same direct-UI-probe method used to resolve Velocity/Mod Wheel/etc. (§6)
would work for the source IDs; likely candidates from Serum's real source
picker not yet probed: `Release Velo`, `Active Voices`, `Voice Index`,
`Voice Mod 1`/`2`.

**Update — every destination gap in this specific paragraph is now closed**
(this paragraph is kept as-written for its historical count, not updated
in place): `Arp` params, `NoiseOsc.kParamColor`, `FXEQ.kParamFreq2`,
`FXUtils.kParamWidth`/`kParamLPF`, `VoicePanel.kParamGlobalScalingEnvTime`,
and `VoiceFilter.kParamWet` are all in `MOD_DEST_TARGETS`/
`FX_EXTRA_MOD_DEST_PARAMS` now (see item 1b below for the closure
timeline). Source id `57` (`voice_mod2`) was also resolved 2026-07-30 (see
item 12) — only `24` and `40` remain genuinely unresolved source IDs, and
only a live-UI probe (not this doc's static/corpus techniques) can close
those.

None of the first two gaps caused incorrect/crashing output (both silently
under-report, they don't corrupt anything) — but together, plus the filter
and warp-lane fixes, they meant a "faithful" recreation built from
`extract_spec`'s output was missing an entire
parallel signal path and roughly 40% of the real preset's modulation,
which is a large enough gap to plausibly explain most of why the
recreation sounded meaningfully different from the original.

Result: 0 real bugs left across all 844 presets. The only remaining
failures (68, all in the Unmute bank) are genuinely missing external
files — that pack's custom wavetables were never installed alongside its
presets on this machine, not a bug in this project.

These are the honest uncertainties, ranked roughly by how much they'd
improve generation quality if resolved:

1. **Mod matrix `source` encoding is fully decoded for its original scope**
   (updated — see §6 for the full writeup). The *destination* side is
   confirmed for every destination this project models (see
   `MOD_DEST_TARGETS`) — but "confirmed" only means "correct where we
   claim coverage", not "covers everything real content uses": the Galaxy
   investigation above found real routes into `Arp`/`NoiseOsc`/non-wet FX
   params/`Global`/`VoicePanel`, none of which have a `MOD_DEST_TARGETS`
   entry at all yet (see item 1b below). The *source* side
   (`[sourceId, subIndex]`) is now resolved for every source this project
   originally set out to
   decode: LFO1-10 (ids 6-15) and Macro1-8 (ids 25-32) via statistical
   clustering (`observed`), plus Mod Wheel (`1`), Env1-4-as-source
   (`2-5`), Velocity (`16`), Key Track/`Note#` (`17`), Aftertouch (`18`),
   Poly Aftertouch (`19`), Random1 (`21`), Random2 (`22`), Pitch Bend
   (`33`), and Random-Discrete (`59`) — all `confirmed` via a 2026-07-29
   direct UI probe of a real Serum 2 instance, in two rounds (see §6,
   including the reusable method). Random turned out to be three
   independent sources, not one, which is why the original "Envelope/
   Velocity/Mod Wheel/Aftertouch/Pitch Bend/Key Track/Random" list maps to
   more than seven resolved names. **`Release Velo` (37), `Active Voices`
   (55), `Voice Mod 1`/`2` (56/57), and `Voice Index` (58) — resolved 2026-
   07-30** (see item 12 above; `MOD_SOURCE_IDS` in `schema.py` has all
   five). This paragraph previously listed them as still-unresolved; that
   was stale — fixed 2026-07-31. **Still genuinely unresolved, out of
   original scope**: `Oscillators`/`Filters`/`Note Expression` as self-mod
   sources (never probed).
   `subIndex` (`source[1]`) is unresolved for every source family outside
   the aux-source mechanism (item 14) — always 0 in every other sample so
   far. `serum-mcp` now generates and reads back mod
   routes for every confirmed source (`generation/spec.py::ModRouteSpec`);
   everything else still round-trips opaquely.
1b. **Mod matrix destination coverage is narrower than `MOD_DEST_TARGETS`
   makes it look** (found live 2026-07-29, see the Galaxy writeup above) —
   a real preset's raw file had 27 active `ModSlot`s; only 11 round-tripped
   through `extract_spec` before this was found (14 after the multi-rack FX
   fix below), the rest silently dropped for an unmodeled *destination*
   even though their source was resolved. Silent under-reporting, not
   corruption — but it means `describe_preset`/`extract_spec` can present a
   real preset as far simpler than it actually is, which misled an earlier
   recreation attempt into thinking its modulation was complete when ~40% of
   it was invisible. Originally-unmodeled categories, now mostly closed:
   `Global.kParamVoiceAmp` (closed 2026-07-29), a `WTOsc` secondary warp
   param `kParamWarpVar2` and FX params other than `kParamWet` (closed
   2026-07-29/30, see `FX_EXTRA_MOD_DEST_PARAMS`). **Closed 2026-07-30** via
   a 626-preset corpus survey of every real `ModSlot`'s destination:
   `VoiceFilter.kParamWet`/`kParamVar`/`kParamStereo`/`kParamLevelOut`
   (`filter{i}.wet`/`var`/`stereo`/`level_out`), `NoiseOsc.kParamColor`
   (`oscillator3.noise_color`, confirmed a fixed singleton at `destModuleID
   3`, matching the Noise slot's own index), `Arp.kParamGate`/`kParamRate`
   (`arp.gate`/`arp.rate`), and `VoicePanel.kParamGlobalScalingEnvTime`/
   `kParamGlobalScalingLfoTime` (`global.voice_scaling_env_time`/
   `voice_scaling_lfo_time`) — all confirmed singletons at `destModuleID 0`
   except VoiceFilter/NoiseOsc (per-slot/fixed-slot respectively). Verified
   round-trip against several real ARP-category Factory presets (e.g.
   `ARP - Acid101.SerumPreset`: `macro3 -> arp.gate`, `macro4 ->
   filter1.var`). `VoiceFilter.kParamX`/`kParamY` also appeared as real mod
   destinations but with only 4/1 samples respectively, and aren't even
   modeled as static `FilterSpec` fields yet — left out, not enough
   evidence.

   **Closed further 2026-08-01** via a bigger, 876-preset corpus survey
   (Factory + every third-party bank installed on this machine, not just
   the original 626 — this project has since accumulated several more
   banks). `VoiceFilter.kParamX`/`kParamY` stayed at essentially the same
   4/1 samples even with ~40% more presets scanned — genuinely rare in
   real content, not previously under-sampled, still left unwired.
   Everything else with real, undiminished evidence got wired up:
   `NoiseOsc.kParamInitialPhase`/`kParamFine` (7/6 samples,
   `oscillator3.noise_initial_phase`/`noise_fine` — `kParamRandomPhase`
   stayed at 1 sample, still not enough), `Arp.kParamChance`/`kParamOffset`/
   `kParamTransposeRange` (7/7/6 samples, `arp.chance`/`arp.offset`/
   `arp.transpose_range` — `kParamWrapPhantomNote`/`kParamRetrigRate`/
   `kParamVeloTarget` stayed at 1-2 samples each, not added),
   `FXUtils.kParamWidth`/`kParamHPF`/`kParamLPF`/`kParamLFXover` (~50/~30/
   ~40/3 samples, `fx{i}.width`/`hpf`/`lpf`/`lf_xover` via
   `FX_EXTRA_MOD_DEST_PARAMS`), and `FXEQ.kParamFreq2` (~60 samples,
   `fx{i}.freq2`, same mechanism). All destModuleParamID values directly
   observed from real files, not guessed. Verified round-trip with a
   dedicated regression test
   (`test_new_mod_destinations_2026_08_01_survey_round_trip`).
2. **Filter cutoff Hz curve** (§4, Filters) — **calibrated 2026-07-31** via the
   [[reference-serum-verify-audio-pipeline]] (a full sweep, not one point):
   a `lowpass_24` filter fed White noise (full-spectrum, no self-bias) at
   11 `cutoff` values, measuring 85%-energy spectral rolloff on the
   sustained portion of each render.

   | `cutoff` | rolloff85 (Hz) | | `cutoff` | rolloff85 (Hz) |
   |---|---|---|---|---|
   | 0.05 | 21.5 | | 0.65 | 1571.9 |
   | 0.15 | 43.1 | | 0.75 | 3466.8 |
   | 0.25 | 64.6 | | 0.85 | 7558.2 |
   | 0.35 | 129.2 | | 0.95 | 12919.9 |
   | 0.45 | 323.0 | | 1.00 | 14427.2 |
   | 0.55 | 710.6 | | | |

   Roughly exponential (log-linear) through the middle of the range, with
   some flattening at both extremes — plausibly a genuine warped curve (a
   common "musical" cutoff mapping), or measurement bias from spectral
   rolloff being a proxy rather than the filter's literal -3dB point at
   the very dark/bright ends. Treat this table as the current best
   reference rather than a single closed-form formula.

   **Methodological finding surfaced by this sweep, important for any
   future filter-related audio-pipeline work**: the first sweep attempt
   showed ZERO difference between the filter fully disabled, fully closed,
   and at 95% resonance — all bit-identical. Root cause: the oscillator's
   `filter_routing` was left unset (the normal/default way to write a
   preset, matching real content's own overwhelming convention, see item
   16 in this list). Real Serum resolves that absence to "route through
   the filter" when loading a genuine `.SerumPreset` file in its own GUI
   (already ear-confirmed live this project, e.g. the Dreams/Beyond
   recreations) — but `serum2-preset-loader`'s VST3 state-injection path
   apparently does NOT resolve it the same way, and the noise bypassed the
   filter entirely. Explicitly setting `filter_routing='filter'` fixed it.
   **This is a limitation of the state-injection test method, not a new
   finding about real Serum's preset-loading behavior** — don't let it
   contradict the already-confirmed absence convention documented
   elsewhere in this file. Any future audio-pipeline experiment involving
   a filter MUST set `filter_routing`/`output_routing` explicitly on the
   oscillators/filters under test, or risk silently testing a bypassed
   signal path.
3. **Unmodeled oscillator engines** — RESOLVED as of 2026-07-31: all three
   remaining alternate oscillator engines (Granular, Spectral, MultiSample)
   are now modeled, alongside the already-existing SampleOsc. See the
   timeline below for how each was decoded and confirmed.
   **Granular is now modeled, as of 2026-07-30.** `GranularOsc` turned out
   to be structurally identical to `SampleOsc`'s own file-reference shape
   (`{numChannels, numFrames, plainParams, samplePathRelative, sampleRate}`)
   — no new container type needed, just a new engine selector
   (`kParamType='kOsc_Granular'`) and its own `plainParams` schema. Full
   automatable/private param enum (22 + 7 params) mined from the VST3
   binary's own debug strings; a 66-sample corpus survey picked the 5
   highest-presence controls (`kParamDensity` 89%, `kParamGrainLength` 83%,
   `kParamRandomGrainLength` 61%, `kParamRandomPan` 62%, `kParamRandomPitch`
   33%) to wire into `OscillatorSpec` as `granular_source` (the file
   reference, same copy-into-Samples-library mechanism as
   `sample_playback_source`) plus `granular_density`/`grain_length`/
   `random_pitch`/`random_pan`/`random_grain_length`; `warp_amount`/
   `warp_mode` are shared with WTOsc/SampleOsc's existing fields (confirmed
   GranularOsc uses the SAME `kParamWarp`/`kParamWarpMenu` keys).

   **Update 2026-08-01, 8 more rarer params wired.** `granular_random_offset`
   (confidence='observed', clearer real-corpus meaning than the rest),
   `granular_loop`, `granular_jump_start`, `granular_reverse`,
   `granular_length_key_track`, `granular_max_grains`,
   `granular_random_window_amount`/`window_skew` (all confidence='uncertain'
   -- decoded from corpus survey + VST3 binary mining, meanings inferred
   from naming, never independently confirmed live). Low-risk addition:
   always written explicitly (same pattern as the original 3 `random_*`
   fields above), no omit-at-default logic involved at all, so none of
   these carry the beat_sync-class presence-bug risk found 3 times
   elsewhere this session. `granular_reverse` is a plausible (but still
   unconfirmed) explanation for the real `808 - Texture` reference
   preset's Osc B playing in reverse, noted as an open question below.
   Remaining unwired: window shape (a small named-shape enum, not a
   float), BPM-synced density/length toggles (`kParamDensityDotted`/
   `Triplet`/`kParamLengthDotted`/`Triplet` -- meaningless without their
   own base beat-sync flag, which isn't wired), a second randomizable warp
   lane (depends on `kParamWarp2`, itself not wired for this engine), and
   `kParamYAxisAssignment` (1/66 real samples, too rare to bother with) --
   still documented in `schema.GRANULAROSC_PARAMS` for round-trip/edit
   safety only. **Not yet confirmed live** — only
   confirmed reading real files and a full write→extract round-trip test
   (including an actual file copy into a temp Samples folder), same
   "experimental until tested" caveat as `LfoSpec.shape`.

   **Update 2026-07-30, first live test found (and fixed) two real
   bugs.** Loaded a generated `GranularOsc` preset in real Serum 2: engine
   selector correctly showed "Granular" (confirming `kParamType` round-
   trips correctly), but the sound was described as "plays like a sample"
   and "extremely filtered" with the filter fully open — genuinely broken,
   not just unfamiliar-sounding. Root-caused via a live-calibration method
   (typing exact knob values into Serum, reading back the saved file's raw
   CBOR): **`kParamDensity` and `kParamGrainLength` are NOT the raw
   storage value** — this project had been writing `OscillatorSpec`'s
   `granular_density`/`granular_grain_length` directly as the raw CBOR
   value, matching how every other already-modeled param works, but these
   two specifically need a conversion:
   - `kParamDensity`: `raw = displayed**4 / 810` (a clean QUARTIC curve,
     confirmed EXACT across 3 real data points: displayed 5/15/25 → raw
     0.7716/62.5/482.25). The DENS knob's own real display range is 0-30
     (confirmed by turning it to both extremes); `30**4/810 == 1000`
     exactly, a suspiciously round number strongly suggesting 1000 is the
     true raw ceiling — the project's EARLIER guess of a linear ~0-850
     range (from corpus min/max alone, no calibration) was simply wrong.
   - `kParamGrainLength`: `raw = displayed / 1000` (LINEAR, confirmed
     exact across displayed 0.05/0.3/1.0 → raw 0.00005/0.0003/0.001).
     **This was the dominant bug**: the original code wrote
     `granular_grain_length=0.15` (intended as "0.15" on Serum's own
     scale) directly as raw — but 0.15 raw actually displays as **150**
     in Serum's UI, an absurdly long, almost certainly clamped grain
     length that made the engine effectively play large continuous
     chunks of the source instead of short grains — matching "plays like
     a sample" exactly, and plausibly explaining the filtered character
     too (heavy overlap/smearing at that extreme length).

   Fixed: `mapping.py`/`introspect.py` now apply these conversions at the
   read/write boundary (`schema.GRANULAR_DENSITY_CURVE_DIVISOR`/
   `GRANULAR_GRAIN_LENGTH_DIVISOR`), so `OscillatorSpec.granular_density`/
   `granular_grain_length` are the numbers you'd actually type into
   Serum's UI, restoring the same convention every other field in this
   project already follows. Locked in with a dedicated regression test
   asserting the exact real (displayed, raw) pairs collected live, not
   just the formula's own self-consistency. **Still unconfirmed**: whether
   `kParamGrainLength`'s linear formula holds all the way to its real
   corpus-observed raw max (10.0, implying displayed=10000 if linear
   everywhere — untested, possibly a different regime or
   `kParamLengthMode` interaction at high values); whether this same
   live test's report is now actually fixed (a corrected test preset was
   generated and passed the automated CBOR scan, but a fresh real-Serum
   listen wasn't re-confirmed as of this write-up); and the newly-
   discovered `kParamScanRate`/`kParamPosition` system (present in 77%/
   57% of real Granular/Spectral oscillators, an outer `Oscillator{i}`-
   level "SCAN" position/speed control this project completely missed
   until seeing a real screenshot) remains entirely unwired — ruled out
   as the primary cause of THIS bug (manually sweeping the SCAN knob from
   -200% to +200% made no audible difference, and its own
   `kParamManualPositionMode` gate is absent in 92%+ of real content,
   contradicting an initial "stuck in manual mode" hypothesis) but still a
   real, undocumented gap worth closing later. `SpectralOsc`'s equivalent
   controls (`spectral_warp_freq_lo`/`freq_hi`) were NOT part of this live
   test and their calibration is unverified — treat with the same
   suspicion until separately confirmed.

   **Update 2026-07-30, independently cross-validated against a real
   Factory preset, and the grain-length UNIT corrected too.** After the
   fix above, the corrected test preset genuinely sounded granular in
   Serum (user-confirmed), closing the main bug. Comparing side-by-side
   against a real Xfer-designed Granular preset (`808 - Texture`, Osc B)
   surfaced one more correction: **`kParamGrainLength`'s displayed unit is
   MILLISECONDS, not seconds** as this project had assumed — the real
   preset's raw value (`0.1243`) predicted a displayed value of `124.3ms`
   via the confirmed linear formula, and the user independently read
   Serum's own UI as showing exactly `124ms`; `kParamDensity`'s predicted
   `0.90` similarly matched the UI's `0.90` exactly. Both formulas now
   have TWO independent confirmations (the original synthetic calibration
   AND this real-preset cross-check), not just internal self-consistency.
   `OscillatorSpec.granular_grain_length`'s default was raised from `0.3`
   to `100.0` (ms) to land in a musically sensible range instead of the
   sub-millisecond range the old "seconds" assumption implied. Also
   surfaced in the same comparison: `808 - Texture`'s DENS/LENGTH are
   themselves real mod-matrix destinations (`Assigned Modulators: LFO1,
   Macro 8` for density; `LFO1, LFO2, Macro 8` for length) — neither is in
   `MOD_DEST_TARGETS` yet, a real but lower-priority gap (the same
   category of fix as item 1b's mod-destination additions, just not yet
   done for `GranularOsc`/`SpectralOsc`'s own params). Also noted: the
   reference preset plays its Osc B in REVERSE (a deliberate Xfer sound-
   design choice, likely `kParamReverse` or a negative `kParamScanRate`)
   and Osc C (a `SampleOsc`, unrelated to this investigation) audibly
   slows its scan position over the note's duration, presumably via the
   same `kParamScanRate`/`kParamPosition` system flagged above as still
   unwired and now confirmed to matter for real, intentional sound design
   -- not just an edge case.

   **Update 2026-07-30, `SpectralOsc` separately live-tested and
   confirmed too.** Same session: loaded a generated `SpectralOsc` preset
   (`warp_mode='kGate'` on a noise source) in real Serum 2. Initial report
   was also "very filtered and robotic" — but unlike Granular, this turned
   out to be the CORRECT, intended character of a spectral gate effect,
   not a bug: with `warp_amount=0` the engine correctly fell back to a
   clean resynthesis of the source ("j'entends du noise" — the raw
   air-can hiss, as expected); with `warp_amount=0.6` on a high note, the
   user described "un son fluide et robotique... comme R2D2" — an apt,
   positive description of exactly what spectral gating is supposed to
   sound like. Both `GranularOsc` and `SpectralOsc` are now considered
   **confirmed live**, closing out the "experimental, not yet tested"
   caveat both carried since being modeled — `freq_lo`/`freq_hi`/
   `filter_shift`/`filter_wet`'s own calibration is the one piece NOT
   independently verified by this test (only `warp_mode`/`warp_amount`
   were exercised) and should still be treated with the same suspicion
   `granular_density`/`granular_grain_length` warranted before their fix.

   **Update 2026-07-31, automated audio-rendering verification closes two
   more open questions, no human listening required.** Found
   [wiillownet/serum-render](https://github.com/wiillownet/serum-render)
   (built on [serum2-preset-loader](https://github.com/wiillownet/serum2-preset-loader)
   + [DawDreamer](https://github.com/DBraun/DawDreamer)) — converts a real
   `.SerumPreset` into the VST3 processor-state blob Serum 2 actually
   understands (confirming, independently, this project's own CBOR schema
   understanding: their documented preset-vs-processor-state diff — the
   `"default"` string sentinel, dropped UI-only keys, added
   `component`/`version` keys — matches exactly), then renders it to audio
   completely headless. Set up as a standalone tool at `C:\serum-verify`
   (kept OUT of this repo: DawDreamer is GPL-3.0, this project is MIT) with
   a reusable `analyze_preset.py` extracting RMS/spectral centroid/onset
   timing/pitch from a render.
   - **Confirmed `spectral_warp_freq_lo`/`freq_hi` are correct as literal
     Hz** (no conversion needed, unlike `granular_density`/
     `granular_grain_length`): three renders of the same source with
     `warp_mode='kGate'` and different `freq_lo`/`freq_hi` windows
     produced spectral centroids of 102 Hz (20-500 Hz window), 6946 Hz
     (5000-20000 Hz window), and 6485 Hz (full 20-20000 Hz range,
     matching the source's own natural broadband character) — a clean,
     monotonic, correctly-directioned result with no live-typing
     calibration needed at all.
   - **`kParamScanRate`/`kParamPosition` (the outer-`Oscillator{i}`
     "SCAN" system flagged as unwired above) confirmed to have a real,
     measurable effect**, resolving the earlier "sweeping it live made no
     audible difference" finding as likely just too subtle over a short
     manual listen: rendering the same `GranularOsc` preset for 3 seconds
     at `kParamScanRate` raw values 0/50/100/200/-100 and measuring
     spectral centroid across 6 time-segments found `0.0` nearly frozen
     (10455→10445 Hz, ~70 Hz drift end-to-end) while nonzero values
     showed real drift (up to ~700 Hz), and `200.0` (the highest tested)
     produced a hard drop to silence in the last 2 of 6 segments —
     consistent with scanning past the end of the ~5-second source file
     within the render window. Confirms the mechanism is real and which
     direction increases movement speed, but NOT yet an exact raw↔real-
     world-rate calibration (no real Factory cross-reference gathered for
     this one, unlike `granular_density`/`grain_length`'s `808 - Texture`
     check) — still not wired into `OscillatorSpec`, now a well-evidenced
     rather than purely theoretical next step.

   **Update 2026-07-31, `kParamScanRate` precisely calibrated** using a
   purpose-built synthetic source: a linear chirp WAV (200Hz→4000Hz over
   5 seconds), where the INSTANTANEOUS detected pitch of the render
   directly encodes which timestamp in the source is currently being
   read. Running frame-by-frame pitch tracking (`librosa.pyin`) across a
   3-second render and fitting a line to (render-time, decoded-source-
   time) gives the scan speed as a real playback-rate multiplier
   directly, not just a qualitative "moves more" signal:

   | raw `kParamScanRate` | measured scan speed |
   |---|---|
   | 0 | 0.000× (frozen — exact) |
   | 25 | 0.143× (reproduced identically on retest) |
   | 50 | 0.527× |
   | 75 | 0.875× |
   | 100 | 1.000× (exactly real-time — exact) |
   | -50 | -0.505× (mirrors +50) |

   `0` and `100` land on clean, exact reference values (frozen / real-time
   forward playback), and negative values mirror positive ones
   (reverse-direction scanning), but the curve between them is NOT a
   simple `raw / 100` line — `25` measured well below what linear would
   predict (0.143 vs 0.25) while `50`/`75` are close to linear. Genuinely
   warped curve vs. a measurement confound (grain overlap at the fixed
   `grain_length=30ms`/`density=15` used for this sweep could bias pitch-
   tracking differently at different scan speeds) is not yet
   disambiguated — treat this table as the current best reference, same
   caveat as the filter cutoff table above, rather than a closed-form
   formula. Not yet wired into `OscillatorSpec`.

   This audio-analysis pipeline is now the go-to way to close open
   calibration questions going forward — it turns "does this sound right"
   from something only a human's ears could answer into something a
   script can check directly (RMS for silence bugs, spectral centroid for
   frequency-range/filtering claims, segmented centroid for time-varying
   effects like scan), the same class of objective, mechanical gate
   `auto-re-agent`'s build/test loop uses for compiled-code reversal (see
   the "loop engineering" discussion this session) — adapted here for a
   data-format-plus-audio-behavior reversal problem instead.
   **Update 2026-07-31, modeled via the recommended tractable first
   slice.** `MultiSampleOsc`'s own structure (`embedded_sfz` text + a
   `files` dict of per-sample metadata + `sfzPathRelative`) is a full
   SFZ-format multisample mapping across many sample files — too complex
   to synthesize from an arbitrary user file this round, so, mirroring how
   `wavetable`/`sample_source` reference curated Factory content, this
   references an EXISTING real Factory instrument's structure verbatim
   instead of building a custom keyzone map from scratch. Key finding
   enabling this: `embedded_sfz`/`files` are BYTE-IDENTICAL across every
   real preset observed referencing the same instrument (confirmed for 4
   different presets all using `Factory/Choir/Ah High.sfz` — only each
   preset's own `plainParams`, envelope/warp, differ), so it's safe to
   hard-code these two fields once per instrument. A 246-preset corpus
   survey found the full `plainParams` schema (`kParamEnvAttack`/`Decay`/
   `Release` at 97-100% presence, `kParamWarp`/`WarpMenu` shared with every
   other warp-capable engine, ~10 rarer params documented for round-trip
   safety only). 4 instruments curated to start (`choir_ah`, `synth_sid`,
   `guitar_ac`, `violins`) via `OscillatorSpec.multisample_source` +
   `multisample_env_attack`/`decay`/`release`. **Confirmed live via the
   audio-rendering pipeline**: a generated `choir_ah` preset rendered at
   MIDI note 60 detected pitch 261.6Hz (C4); at note 72 (one octave up),
   523.3Hz (C5) — exactly one octave apart, confirming correct per-note
   sample/keyzone selection and pitch tracking, not just a fixed drone.
   Still experimental (only this one pitch-tracking check performed, not a
   full listening pass) and only 4 of many real Factory instruments are
   curated — adding more is now a simple, low-risk mechanical extraction
   (same technique), no further reverse-engineering needed.

   **Update 2026-08-01, 6 more instruments curated (10 total), same
   mechanical extraction, no new reverse-engineering.** Surveyed all 626
   Factory presets for every real `kOsc_MultiSample` instrument reference
   (not just the 4 already known) to pick a diverse, popular set spanning
   categories the original 4 didn't cover: `piano_grand` (Baby Grand
   Piano, 10 real-preset uses), `strings_full` (Full Strings LE, 11),
   `brass_french_horn` (French Horns, 5), `synth_pad_superjx` (SuperJX 4
   Chorus Pad, 13 — the single most-used MultiSampleOsc instrument in the
   whole corpus), `mallet_balafon` (Balafon, 6), `epiano_suitcase`
   (Elec.Piano Suitcase, 5). Extraction was fully mechanical (same
   technique as the original 4: pull `embedded_sfz`/`files`/
   `sfzPathRelative` verbatim from one real preset per instrument,
   programmatically inserted into `schema.py` to avoid hand-transcription
   errors) — no live testing performed on these 6 specifically, same
   "experimental" caveat as before.

   **Corrected a wrong universal claim found while curating these**:
   `MultiSampleInstrumentDef`'s docstring used to assert `files`' path
   separator is ALWAYS a literal double backslash, "confirmed not a
   transcription artifact." That was only ever true for 2 of the original
   4 (`choir_ah`/`guitar_ac`) — `violins` (already in the codebase) and
   all 6 new instruments use a single backslash instead. Real,
   per-instrument inconsistency on Xfer's own sample-prep side, not a bug
   here — the code already treats `files` as opaque and preserves
   whatever a fresh extraction produces verbatim, so this was a
   documentation-only correction, not a functional fix. Confirmed live 2026-07-29 recreating a second
   real Unmute preset (`UN_PLACES_PL_Dreams`, chosen specifically for being
   otherwise fully within scope — no arp, no sample oscillators, single FX
   rack): its Osc C is a real `SpectralOsc` (`kOsc_Spectral`) referencing a
   genuine Factory `.flac` (`Spatial/Ambience Grains of Sand.flac` — a
   macro named "SPECTRAL SAND" controls its volume, confirming it's not
   incidental). `SpectralOsc2`'s raw structure: `{flex: {curve data,
   trivial single-point in this sample}, numChannels, numFrames,
   plainParams: {kParamFreqLo, kParamWarp, kParamWarpMenu}, samplePathRelative,
   sampleRate}` — a real `.flac` reference works fine written directly
   (same "reference an already-installed Factory file, don't decode it"
   approach used for wavetables), no FLAC decoder needed for THIS. A
   one-off patch (`packer.unpack_file`/`pack_file`, bypassing
   `PresetSpec` entirely) reproduced this single oscillator exactly for
   that one recreation, but this was not remotely enough evidence to design
   a general `OscillatorSpec` `SpectralOsc` feature at the time.

   **Update 2026-07-30, now modeled** (the same session as Granular). A
   53-preset corpus survey plus VST3 binary string mining found the full
   automatable/private param enum (`kParamWarp`/`WarpVar`/`WarpMenu`/
   `Warp2`/`WarpVar2`/`WarpMenu2`/`SpecFltShift`/`SpecFltWetDry`/`FreqLo`/
   `FreqHi` automatable; `PhaseLock`/`Transients`/`LoHiIsPost`/
   `LoHiIsSmooth`/`YAxisAssignment` private) and confirmed `SpectralOsc` is
   ALSO structurally identical to `SampleOsc`'s file-reference shape, plus
   the `flex` curve sibling (now decoded, see item 4). Its OWN warp-mode
   vocabulary is a separate, much larger (~80-value) enum from
   `SIMPLE_WARP_MODES` — genuinely different names (`kGate`/`kSmear`/
   `kRobotize`/`kSpectralShift`/`kVocode_OSC`/`kMask_OSC`/`kShepardFilter`/
   etc, spectral/FFT-domain effects), passed straight through via
   `OscillatorSpec.warp_mode` when not a `SIMPLE_WARP_MODES` key, same
   mechanism every warp-capable engine already used. Wired up as
   `OscillatorSpec.spectral_source` + `spectral_warp_freq_lo`/`freq_hi`
   (the frequency range the spectral effect applies to) +
   `spectral_filter_shift`/`filter_wet`. **Important limitation, unlike
   Granular**: 53% of real `SpectralOsc` instances carry a genuinely
   non-trivial hand-drawn spectral filter curve (`flex.numPoints > 1`) —
   curve GENERATION isn't implemented (see item 4), so a generated
   `SpectralOsc` always gets the exact flat/neutral sentinel 24/25 real
   no-curve instances use (`xVals=[0,1]`, `yVals=[0.5,0.5]`,
   `curveVals=[0.5,0.5]`, confirmed via corpus survey to be the canonical
   "untouched" value, not just "close enough") — written explicitly rather
   than left absent, since genuine absence was never tested and every real
   file has SOME `flex` present. An `edit_preset` call against an existing
   SpectralOsc with a real curve correctly preserves it (only writes the
   sentinel when nothing's there yet). Verified round-trip against real
   Factory content (`BA - Classic Wubber.SerumPreset`, `warp_mode='kGate'`
   extracted correctly via the passthrough). NOT yet confirmed live for
   generation — same experimental caveat as Granular.
4. **LFO curve shapes** (`curveData`) and **free-drawn envelope curves** are
   unmodeled — Serum 2's point-based custom curve editor data. Confirmed
   live 2026-07-29 that this isn't just a theoretical gap: attempting to
   recreate a real, complex Unmute preset (`UN_PLACES_ARP_120_Galaxy`) via
   `generate_preset` matched essentially every other parameter (oscillator
   wavetables/warp, filter types incl. uncurated `DistComb1BP`/`RMT`, an
   8-unit FX chain, 11 mod routes incl. the newly-decoded `key_track`
   source, arp settings) but was judged "n'a rien à voir" (nothing like the
   original) once loaded — the real preset's screenshot showed its busiest
   LFO (rate 100, driving both a table_position sweep and filter cutoff)
   set to **S&H** (Sample & Hold, a stepped-random shape), not the smooth
   default curve this project silently substitutes since shape isn't
   modeled at all. For a preset whose character depends heavily on one
   fast, heavily-routed LFO, an unmodeled shape can be the dominant
   perceptual difference, not a minor detail. Also spotted in the same
   screenshot: the `DistComb1BP` filter type exposes a `COMBFRQ` knob with
   no equivalent in this project's generic 4-param (`cutoff`/`resonance`/
   `drive`/`stereo`) filter model — unconfirmed whether that's a real
   5th parameter or a relabeling of an existing one, but a plausible
   secondary contributor, not yet investigated.

   **RESOLVED 2026-08-01, via VST3 binary string mining** (the same
   technique that decoded `RoutingSlot`/`ModSlot`'s private params): it's a
   relabeling, not a new parameter. `VoiceFilter`'s full automatable-param
   enum, found in the binary's own debug strings, is exactly `kParamEnable,
   kParamWet, kParamType, kParamFreq, kParamReso, kParamDrive, kParamVar,
   kParamStereo, kParamLevelOut, kParamX, kParamY` — no separate
   `kParamCombFrq`/similar ID exists. `"CombFrq"` sits directly adjacent to
   `"LP Frq"`/`"HP Frq"` in the binary's string table (`...kParamWarpVar\0
   ...BitOr\0CombFrq\0LP Frq\0HP Frq\0seq\0...kParamFreq\0...`) — a set of
   per-filter-type UI label variants for the SAME `kParamFreq` knob
   (already modeled as `FilterSpec.cutoff`), the same pattern already
   documented for `kParamVar` ("Var" knob relabeled per type, e.g. comb
   spacing/formant blend). No `PresetSpec`/`schema.py` change needed —
   `cutoff` already covers this; `DistComb1BP`'s "COMBFRQ" IS `cutoff`,
   just displayed under a filter-type-specific name.

   **Update 2026-07-30, the storage FORMAT is now decoded** (the *reading*
   half of this gap; *generating* a new curve from a description is still
   open, see below). Investigating `SpectralOsc`'s own `flex` curve data
   (see item 3) led to a full structural survey of every `{numPoints,
   xVals, yVals, curveVals}`-shaped dict across the entire 626-preset
   corpus — 3051 real occurrences, in `LFO{i}.curveData` (795, the exact
   data the Galaxy S&H shape above lives in), `ModSlot{n}` (main/aux curve
   data, ~200 total), `SpectralOsc{i}`/`WTOsc{i}`/`FXRack0/1` (a couple
   hundred more). 99.7% (3043/3051) confirm one consistent invariant with
   zero real exceptions (the 8 "violations" were float-precision near-misses
   or a couple of genuinely partial/incomplete curves): `len(xVals) ==
   len(yVals) == len(curveVals) == numPoints + 1`; `xVals[0] == 0.0`,
   `xVals[-1] == 1.0` always; `xVals` always monotonically increasing. This
   is a point-based curve spanning a fixed, normalized x-domain `[0, 1]`
   (time for an LFO/envelope curve, frequency for `SpectralOsc`'s spectral
   filter shape) — `yVals[i]` is that point's height (also roughly
   `[0, 1]`, `0.5` a very common "neutral/center" value at untouched
   points), `curveVals[i]` is presumed to be the curve TENSION/shape of the
   segment leading into that point (`0.5` = the overwhelmingly common
   default, seen at every point in some real curves — presumed linear;
   deviation direction/amount not independently confirmed). A visually
   distinct SEPARATE sub-format, `pathData` (49 occurrences, all on LFOs --
   presumably `LfoSpec.shape='path'`, "unconfirmed in character" per that
   field's own docstring), does NOT follow this invariant (x not always
   monotonic, doesn't always span `[0,1]`) — a genuine 2D freehand drawing,
   not a single-valued function of x, and NOT covered by this decode.
   Confirmed this data already round-trips safely through `apply_spec`
   today without any code change (a sibling key of `plainParams`, never
   touched by code that only writes specific `plainParams` fields) — see
   the regression test locking this in. **Still open**: `curveVals`'
   exact interpolation semantics (what tension value produces what audible
   curve shape) aren't independently confirmed, and no `PresetSpec` field
   exists yet to GENERATE a new custom curve from a text description (e.g.
   "make this LFO sound like S&H") — would need either live Serum
   measurement of a few known curveVals values' audible effect, or finding
   Serum's own preset-generation code for a named shape like "S&H" (which
   presumably synthesizes one of these point sequences internally) to
   reverse-engineer the mapping. This is now a well-scoped, tractable next
   step rather than a totally opaque one.

   **Update 2026-07-31, attempted via the audio-rendering pipeline, hit a
   real tool limitation (not a dead end on the underlying question).**
   Tried to calibrate `curveVals`' interpolation semantics the same way
   `kParamScanRate` was calibrated: patched a 2-point `curveData`
   (`xVals=[0,1]`, `yVals=[0,1]`, `curveVals=[0.5,0.5]`) directly onto
   `LFO0`, routed `lfo0 -> filter0.cutoff` at `amount=90`, and measured
   spectral centroid over time to reconstruct the modulation shape.
   Result: **completely flat** (no cycling at all) regardless of
   `kParamRate` (tried 0.1 and 10.66, the one empirically-known reference
   point) or whether `kParamBeatSync` was explicit-`False` vs. genuinely
   absent. Confirmed via `serum2_preset_loader.converter.
   preset_cbor_to_processor_cbor` that the `curveData` survives the CBOR
   translation byte-for-byte correctly — the state going INTO the render
   is right. Isolated the cause with a clean control: the EXACT same
   preset/rate/routing with `curveData` simply absent (Serum's own
   built-in default LFO shape instead) showed clear, strong, cyclical
   modulation (spectral centroid swinging 110↔9208 Hz repeatedly). **This
   pins the failure specifically on custom `curveData` not being
   correctly applied by Serum when loaded via `serum2-preset-loader`'s
   VST3 state-injection path** — a different, harder-to-work-around
   limitation than the `filter_routing` gotcha (item 2), since there's no
   known field to set explicitly that fixes it; the data is already
   present and structurally correct. **Practical consequence**: the
   audio-rendering pipeline cannot currently be used to reverse-engineer
   `curveVals` — this specific question needs either a real Serum GUI
   test (load a hand-crafted `curveData` preset, listen/screenshot) or
   finding a different, non-state-injection way to get a custom curve
   into a live Serum instance for rendering. Recorded in
   [[reference-serum-verify-audio-pipeline]] so a future session doesn't
   repeat this exact dead end.

   **Update 2026-08-01, internet research produced a concrete, testable
   hypothesis for `curveVals` (not a confirmation — still needs a live
   Serum GUI test to verify).** Searched for prior public reverse-
   engineering of Serum's preset format (`KennethWussmann/serum-preset-
   packager`, `0xdevalias`'s gists) — both confirm this project is ahead
   of any publicly documented work; neither has decoded the mod-matrix
   `source[1]`/aux mechanism or the curve-point format at all, so no
   direct answer was available there. Pivoted to **Vital** (`mtytel/vital`
   on GitHub, GPLv3) — a different but closely comparable open-source
   wavetable synth with its own point-based LFO/envelope curve editor.
   Its curve-interpolation code (`LineGenerator::getValueBetweenPoints`,
   `vital::futils::powerScale`) uses an exact, inspectable formula for a
   single scalar "power" value per point:

   ```cpp
   powerScale(t, power) = (exp(power * t) - 1) / (exp(power) - 1)   // power != 0
   powerScale(t, power) = t                                          // power == 0 (linear)
   ```

   i.e. a one-parameter exponential warp of the linear blend position
   `t` between two points — `power` near 0 is linear, positive/negative
   values bow the segment concave/convex. This is a common, generic DSP
   idiom (not Vital-specific), and a real-corpus check of this project's
   OWN 150-preset sample (2471 real `curveVals` entries) is consistent
   with it being the same convention: values cluster tightly around
   **0.5 as the overwhelming majority/default** (2078/2471, ~84%), with a
   **near-symmetric spread either side** (mean 0.495, observed range
   ~0.000–0.954) — exactly the shape you'd expect if `curveVals` is a
   `[0,1]`-normalized UI knob remapped to something like Vital's `power`
   via `power = (curveVals - 0.5) * 2 * max_power`, with `curveVals=0.5`
   landing on `power=0` (linear), matching this project's own independent
   finding that `0.5` is the confirmed "untouched/neutral" value. **Still
   entirely unconfirmed** — this is a plausible, testable STARTING POINT
   for the next live-Serum-GUI session, not a decoded formula: hand-craft
   2-3 presets with known `curveVals` values away from 0.5 (e.g. 0.2,
   0.5, 0.8), load each in real Serum's GUI (not via the audio pipeline,
   which can't apply custom curveData at all per the dead-end above), and
   compare the on-screen curve shape against this formula's prediction.
5. **RESOLVED 2026-07-30, all 16 FX types now have param schemas.**
   `FXSplit`/`FXSplit3`/`FXSplitMS` were assumed to need "nested
   band-splitter containers, not a flat `plainParams` dict" — a 626-preset
   corpus survey (77 real occurrences: 43/19/15) found that assumption was
   wrong. They have an ORDINARY flat `plainParams` dict like every other FX
   type; what actually differs is purely INTERPRETIVE, no new data structure
   needed: `kParamModuleCount1`/`2`/(`3`) say how many of the FOLLOWING flat
   `fx_chain` entries (same rack) belong to each frequency/channel band, in
   order — confirmed against every one of the 77 real examples with zero
   exceptions (e.g. `BA - Dual MG Bass.SerumPreset`: `kParamModuleCount1=1,
   kParamModuleCount2=1`, followed by exactly `[FXDistortion, FXDelay]`).
   Any entries left over after all bands' counts are consumed continue as
   ordinary serial processing on the recombined signal. `FXSplit` crosses
   over at `kParamFreq` (2 bands); `FXSplit3` adds `kParamFreq2` (3 bands);
   `FXSplitMS` has no frequency at all (Mid/Side channel split, not
   frequency-based). None have a wet/mix knob (absent from every real
   sample, same as `FXEQ`). Needed zero code changes beyond the schema
   entries themselves — `_build_fx_entry`/`extract_spec` already treat every
   FX type generically via the same flat, ordered `fx_chain` list; the
   calling model is responsible for setting the counts to match how many
   units it actually places in each band (see server.py's fx_chain
   guidance), same trust level as any other free-form field. (Separate from
   this: `FXRack0`/`1`/`2` — the 3 *parallel racks* each of these 16 types
   can sit in — are supported since 2026-07-29; don't confuse "unmodeled FX
   type" with "unmodeled rack".)
6. Several numeric ranges are marked `uncertain` in `schema.py` (e.g. unison
   voice count ceiling, LFO/Chorus/Delay times where only normalized values
   were observed without a confirmed Hz/ms curve) — these are *observed*
   ranges from the sample, which may not be the true engine-enforced bounds.
   6a. **`LFO_PARAMS['kParamRate']`'s FREE (non-beat-synced) Hz curve —
   RETRACTED then correctly recalibrated 2026-08-01.** Original 2026-07-31
   attempt: a single `LfoSpec(rate=X, mode='Free', beat_sync=False)` routed
   `lfo0 -> filter0.cutoff`, rendered, and measured via a new reusable
   helper, `analyze_preset.detect_modulation_rate_hz` (FFT of the
   frame-wise spectral centroid time series) — the general-purpose sibling
   of the chirp technique for "how fast does this cycle" questions where
   the source isn't a synthetic chirp. That attempt reported a clean
   `Hz = 2^(raw/10 + 1)` curve for raw 2-30 plus a "genuinely unresolved"
   anomaly above raw~35 — **both wrong, or at least half-wrong, and traced
   to a real product bug, not a Serum quirk.**

   **The bug**: `LfoSpec.beat_sync` was a plain `bool` defaulting to
   `False` — mapping.py's omit-at-default logic (see the "presence forces
   the DSP stage" pattern elsewhere in this doc) then treated any
   `beat_sync=False` spec as "untouched" and omitted `kParamBeatSync`
   entirely, silently falling back to Serum's real absent-state default
   (BPM-SYNCED, not free-Hz). Every preset in the original calibration
   sweep was therefore measured in the wrong mode — the whole "curve" was
   an artifact of note-value-quantized BPM-sync behavior misread as a Hz
   curve, not the real free-Hz mapping at all.

   **Found by the user, not by automated testing** — a live-testing request
   asked them to manually turn a calibration preset's RATE knob in Serum
   while watching the filter's cutoff, and they immediately noticed the
   knob's own display read `"BPM"` mode with a note fraction (`"1/16"`)
   instead of Hz. The automated audio-only pipeline could never have caught
   this on its own (it only ever inspects the rendered waveform, never the
   preset's own loaded UI state) — this is exactly the class of bug
   `[[feedback-serum-mcp-validate-in-real-serum]]` exists to catch, and a
   second confirmation that audio-pipeline automation and live-Serum
   testing are complementary, not substitutes for each other.

   **Real fix** (not just a doc correction): `LfoSpec.beat_sync` is now a
   3-state `bool | None` — `None` (default) omits the key, matching
   Serum's real absent-default (BPM-synced); `True`/`False` now WRITE
   explicitly, making free-Hz mode reachable through `PresetSpec` for the
   first time. This was a real, generally-impactful bug: ANY previously
   generated preset that intended `beat_sync=False` (free-running Hz LFO)
   silently got a tempo-synced LFO instead, not just this calibration
   experiment.

   **Recalibrated with the fix in place, genuine free-Hz mode confirmed
   this time**: raw 2/5/10/20/30 measured 2.0/5.0/10.0/20.0/30.0 Hz — an
   EXACT 1:1 match. **`raw kParamRate IS literal Hz` in free mode, no curve
   at all** — trust this for raw <= ~30, a much simpler and more useful
   result than the retracted "curve." `rate=0.0` (which still separately
   omits `kParamRate` itself — a correct, unrelated omission) measured
   6.25Hz, presumably Serum's own genuine free-mode rate default; not
   independently confirmed.

   **The high-range anomaly measured OK on the fixed code** (raw 40/60/80
   all measured the identical 21.6Hz, 50/70/90/100 gave inconsistent,
   non-monotonic values 11.6/18.4/8.4/23.2Hz) **but a live-Serum
   cross-check 2026-08-01 resolved it as a measurement-pipeline
   limitation, not a real Serum DSP anomaly.** Two rounds of live testing:
   1. First round (RATE swept on a LOOPING piano-roll note) found real
      visible/audible "jumps" — but traced entirely to the well-known
      per-voice LFO phase-reset-on-note-on behavior (see `LfoSpec.mono`'s
      docstring), an artifact of the note retriggering every loop
      iteration, unrelated to the rate curve. Confirmed directly:
      re-testing at raw=2 (slow enough to see clearly) with `mono=True`
      (a continuous LFO independent of note-on) showed NO jump at all on
      the same looping note.
   2. Second round, retrigger confound removed (`mono=True`, same looping
      note, RATE swept 20-100%): STILL saw visible "jumps" at the high
      end, but the user explicitly confirmed them INAUDIBLE — consistent
      with a stroboscopic/aliasing illusion (the cyclic knob's own visual
      motion beating against the screen's refresh rate, the same
      perceptual effect as a film's "wagon wheel" spinning backwards), not
      a real audio glitch.

   **Conclusion**: no evidence of a genuine Serum DSP anomaly anywhere in
   the tested range — real audio confirmed smooth throughout, by ear, with
   the retrigger confound controlled for. The automated pipeline's
   non-monotonic Hz *readings* above raw~35 are now understood to be a
   limitation of `detect_modulation_rate_hz` itself at fast target rates
   (see its own docstring's 2 documented caveats — 2nd-harmonic locking and
   the unexplained low-rate plateau, both are about the ANALYSIS struggling,
   not about Serum's output being wrong), not a real curve kink. Safe to
   treat `LfoSpec.rate` as literal-ish Hz across the WHOLE 0-100 range now
   — just don't expect the automated pipeline to report the exact Hz number
   precisely above ~35, only that the underlying audio is well-behaved.
   This whole sub-investigation is a good demonstration of why
   `[[feedback-serum-mcp-validate-in-real-serum]]`'s two check types are
   complementary: the audio pipeline flagged something worth checking, and
   live testing was what actually resolved whether it was real.

   6b. **`FX_PARAMS['FXChorus']['kParamRate']` — same technique, same
   ~16.5/32Hz anomaly, now cross-validating item 6a's finding rather than
   fixing it.** Method: `FxUnitSpec(type='FXChorus', params={'kParamRate':
   X, 'kParamDepth': 26.0, 'kParamFeedback': 0.0})`, rendered a sustained
   tone through it, measured via `detect_modulation_rate_hz`.
   - **Confirmed, trustworthy**: raw 15/20 measured EXACTLY 15.0/20.0 Hz —
     `"Hz (approx.)"` is genuine literal Hz at the top of the documented
     0-20 range.
   - **A second, DIFFERENT ambiguity found here (not seen calibrating the
     LFO)**: raw 2-10 measured inconsistently 1x or 2x the raw value (e.g.
     raw=3→6Hz, raw=4→4Hz, raw=5→10Hz, raw=7→14Hz — no clean split point).
     Most likely `detect_modulation_rate_hz` locking onto the modulation's
     2nd harmonic instead of its fundamental (spectral centroid can
     respond similarly to a sweep's "up" and "down" halves for a symmetric
     brightness effect like chorus/filter-cutoff, unlike an asymmetric
     signal such as pitch) — added as a documented limitation on the
     helper function itself (see
     [[reference-serum-verify-audio-pipeline]]), not fixed.
   - **A ~16.5/32Hz plateau at raw 0.5/1.0** — originally written up as
     matching item 6a's LFO-rate anomaly and cited as cross-validation that
     it's a shared pipeline artifact. **That framing no longer holds**:
     item 6a's original finding was RETRACTED 2026-08-01 (it had been
     measuring the wrong LFO mode entirely due to an unrelated `beat_sync`
     bug, not a real anomaly) — so this FXChorus finding is back to being a
     single, uncorroborated data point, not confirmed by a second source.
     Still real and reproducible on its own terms (`FXChorus` has no
     `beat_sync`-equivalent field, so it's unaffected by that bug), just
     don't cite it as cross-validated with the LFO investigation anymore.

   6c. **`FX_PARAMS['FXFlanger']`/`['FXPhaser']['kParamRate']` — calibrated
   2026-08-01, same technique, and the 2nd-harmonic-locking hypothesis from
   item 6b gets its strongest evidence yet.** Method identical to 6b
   (sustained tone through the FX, `kParamDepth=100`, `kParamFeedback=0`,
   measured via `detect_modulation_rate_hz`).
   - **FXFlanger**: measured Hz was EXACTLY 2x the raw value across ALL 7
     points tested (raw 1/2/3/5/7/9/10 → 2/4/6/10/14/18/20 Hz) — far more
     uniform than FXChorus's erratic 1x/2x flip-flopping, which on its own
     might suggest a genuine "2x" Serum curve rather than a measurement
     artifact. Leaning toward artifact anyway (2nd-harmonic-locking, same
     as item 6b) because a flanger's sharp comb-filter notches produce an
     especially strong, symmetric brightness swing — exactly the condition
     `detect_modulation_rate_hz`'s own docstring already flags as prone to
     this — but this is NOT independently disambiguated from "Serum really
     does use a 2x-scaled Hz curve for flangers specifically."
   - **FXPhaser**: mostly the same ~2x pattern (raw 1/2/10/15/18/20 →
     2/4/20/30/36/40 Hz) but with ONE clean break — raw=5 measured 20Hz
     (4x, not the ~10Hz/2x the pattern predicts). This inconsistency is
     itself evidence AGAINST "genuine fixed 2x curve" and FOR "harmonic-
     locking instability" — a real fixed-ratio Serum curve has no reason to
     misbehave at exactly one tested point. Re-verified the raw=18/20
     high-end readings aren't a search-band artifact (identical result
     with `fmax_hz` raised from 40 to 100).
   - **Working assumption, not a confirmed fact**: both params are
     presumed to actually be `raw = Hz` like every other similarly-labeled
     rate param calibrated this project (LFO free rate, FXChorus's own
     confirmed raw>=15 range) — `detect_modulation_rate_hz` reporting
     ~2x is treated as the tool's own bias, not Serum's real curve.
     Resolving this for certain needs either a live Serum check or
     re-measuring via an asymmetric destination signal (e.g. pitch)
     immune to the harmonic-doubling effect.

   6d. **`FX_PARAMS['FXDelay']['kParamTimeL']`/`['kParamTimeR']` —
   CONFIRMED literal seconds, but only after finding and fixing a THIRD
   instance of the exact `beat_sync` bug class first found on the LFO
   (item 6a).** Method: a sharp transient (fast-attack/near-zero-sustain
   envelope) through `FXDelay` with `kParamFeedback>0` for repeats,
   measuring the echo spacing via onset detection — a new, simpler
   sibling to `detect_modulation_rate_hz` for effects whose "rate" shows
   up as discrete repeats rather than a continuous cyclic sweep.

   First attempt (kParamTimeL/R set, nothing else) measured a suspicious,
   unmistakably QUANTIZED pattern rather than a smooth curve: raw
   0.05/0.1/0.15/0.2/0.25/0.3 measured gaps of ~0.255/~0.5/~1.0/~2.0/~2.0
   (identical to 0.2!)/~4.0 seconds — doubling at irregular raw intervals,
   with a flat plateau between 0.2 and 0.25. This pattern (not a smooth
   curve, doubling instead of scaling proportionally, a plateau where nothing
   changed at all) was immediately recognizable as the same signature as
   the LFO's BPM-synced/note-quantized fallback behavior.

   Mining the VST3 binary's own debug strings (same technique that
   decoded RoutingSlot/ModSlot/COMBFRQ) confirmed it: `FXDelay`'s real
   automatable-param enum is `kParamEnable, kParamWet, kParamFreq,
   kParamBW, kParamBeatSync, kParamLink, kParamTimeL, kParamTimeR,
   kParamMode, kParamFeedback, kParamOffsetL, kParamOffsetR,
   kParamLevelOut, kParamHQ` — `kParamBeatSync` had never been catalogued
   in this project's schema at all, so no serum-mcp-generated `FXDelay`
   has ever set it, meaning every one has silently fallen back to Serum's
   real (BPM-synced) default instead of the literal seconds
   `kParamTimeL`/`TimeR`'s `unit="seconds"` label implied — a real,
   generally-impactful bug, not just a calibration-script mistake, same
   as item 6a's LFO finding.

   Re-tested with `kParamBeatSync: False` passed explicitly via
   `FxUnitSpec.params` (validated fine — `_build_fx_entry` already allows
   unrecognized keys through via `allow_unknown=True`, so this required NO
   mapping.py code change, only a schema addition): the SAME raw values
   measured near-exact literal seconds (0.05→0.046, 0.1→0.105, 0.2→0.197,
   0.3→0.302 — all within onset-detection timing noise of the raw value
   itself). `kParamBeatSync` is now in `FX_PARAMS['FXDelay']`, confirmed;
   `FxUnitSpec.params`'s own docstring documents the gotcha directly so a
   calling model doesn't need to have read this. 6 more real, previously
   uncatalogued `FXDelay` private params (`kParamMode`, `kParamLink`,
   `kParamBW`, `kParamOffsetL`/`kParamOffsetR`, `kParamHQ`) turned up in
   the same binary string mining — added to the schema for round-trip
   safety, meanings inferred from position/naming only, not independently
   investigated.

None of these block V1's stated goal (text description → valid, loadable
`.SerumPreset` covering oscillators/filters/envelopes/macros/core FX) — they
bound what V1 can *express*, not whether what it writes is valid.

## 6. Mod matrix structure

**Editing an existing route must overwrite its slot, not add a new one**
(found live, not by inspection): `apply_spec` used to always allocate a
*free* `ModSlot` index for every entry in `spec.mod_routes`, with no check
for whether a route with the same `(source, destination)` pair already
existed elsewhere. Calling `edit_preset` a second time to change an
existing route's `amount` therefore left the *old* route active in its
original slot and added the *new* one in a different free slot — both
firing simultaneously, silently doubling up the modulation (caught when a
Reese bass's filter-cutoff LFO route, edited down from +15% to +4% to fix
audible over-wobbling, kept wobbling just as hard — the file had two
`ModSlot`s routing `lfo0 -> filter0.cutoff` at once). Fixed in
`mapping.py`: `_resolve_modslot_indices` now looks for an existing slot
matching the resolved `(source_id, dest)` first and reuses it, only
falling back to a free slot for genuinely new routes.

Each `ModSlot{n}` (`n` in `0..63`, only slots actually in use are serialized
— an unused slot is simply absent from the CBOR dict, there is no "off"
value):

```jsonc
{
  "destModuleID": 0,               // which instance -- see ID ranges below
  "destModuleParamID": 3,          // internal numeric param index
  "destModuleParamName": "kParamFreq",
  "destModuleTypeString": "VoiceFilter",
  "source": [6, 0],                // [sourceId, subIndex] -- see below
  "plainParams": {
    "kParamAmount": 53.2,          // -100..100
    "kParamBipolar": 1.0,          // optional, bool-ish
    "kParamCurveIn": 7.06,         // optional, per-route curve shaping -- see below
    "kParamMainCurveData": 1.0     // optional, alongside a hand-drawn "flex" curve -- see below
  },
  "flex": [ /* optional point-based curve, same shape as LFO curveData */ ]
}
```

**Per-route curve shaping (`kParamCurveIn`/`kParamMainCurveData`/`flex`),
found live 2026-07-29** while comparing a recreated preset's MATRIX tab
against the real one row-by-row after the user reported they "didn't have
100% the same things" — a discovery this project had never looked for
across two prior deep investigations of the same real preset's mod
routes. Two independent mechanisms, both unmodeled and NOT generated by
`serum-mcp`:

- `kParamCurveIn`: a scalar, range `-100..100` observed (521/17,361 real
  active `ModSlot`s surveyed, ~3%). Presumed to skew/bend the source-to-
  amount response curve (by analogy with "curve" controls elsewhere), not
  independently confirmed.
- `kParamMainCurveData` + a `flex` array: a genuine hand-drawn point-based
  curve (same `{curveVals, numPoints, xVals, yVals}` shape as LFO
  `curveData`, §"LFOs" above) reshaping the response nonlinearly — e.g. a
  real route observed with `xVals=[0, 0.625, 1.0]`, `yVals=[1.0, 0.37,
  0.0]`, a deliberate S-curve/taper, not a straight line. 570/17,361 (3.3%)
  and 647/17,361 (3.7%) respectively.

Both are rare (~3-4% of real routes) but clearly deliberate when present,
not incidental defaults. This is the SAME class of problem as LFO curve
shapes (arbitrary hand-drawn point data, out of scope to generate
generally) plus a smaller, more tractable scalar (`kParamCurveIn`) whose
exact semantics aren't understood yet. `serum-mcp`'s `ModRouteSpec` has no
fields for either — not modeled, not generated, and (like LFO curveData)
`extract_spec` doesn't surface them either, so a route using a custom
curve currently round-trips as if it were linear. Not pursued as a general
feature this session (too little evidence for `kParamCurveIn`'s exact
effect, and `flex` has the same arbitrary-curve-decoding difficulty as
LFO shapes) — for a specific known preset with confirmed real values, a
one-off `packer.unpack_file`/`pack_file` patch (same technique used for
`SpectralOsc`, see §5 items 3/7) is the practical path today.

**This "flex" curve system is not exclusive to mod routes**, found live
2026-07-29 tracking down a persistent audible difference ("fuzzy/buzzy/
high-pitched") a flat `plainParams`-only diff hadn't caught: individual
**FX units** (`FXRack{n}.FX[i].flex`) and **`WTOsc` containers**
(`Oscillator{i}.WTOsc{i}.flex`) carry their own, independent `flex` curves
too, using the same `{curveVals, numPoints, xVals, yVals}` shape. On one
real preset, a `FXDistortion` unit had a genuine deliberately-shaped
2-segment saturation curve here — plausibly the actual source of the
reported character, since a distortion unit's response curve directly
shapes its harmonic/saturation output, more so than any single scalar
param. This makes at least **four** independent contexts for this curve
format found so far (LFO shape, per-mod-route response, per-FX-unit
response, per-`WTOsc` — likely a general-purpose curve widget Serum reuses
internally), none generated by `serum-mcp`, all requiring the same
one-off-patch approach for now. A full recursive diff of the raw data tree
(not just top-level `plainParams`) is what surfaced this — a flat
per-module `plainParams` comparison, even an exhaustive one, doesn't see
into nested containers like `WTOsc{i}`/`FX[i]`/`ModSlot{n}`'s own
sub-keys.

### Destination side (confirmed)

`destModuleID` ranges observed per `destModuleTypeString` (confirms module
instance counts independently of §3): `Oscillator` 0-4, `VoiceFilter` 0-1,
`Env` 0-3, `Macro` 0-7, `LFO` 0-7 (0-9 expected, only 0-7 appeared in our
200-preset mod-matrix sample), `Global`/`Arp`/`VoicePanel`/`RetriggerState` 0
only, `RoutingSlot` 0-6, `LFOPointModBus` 0-14. FX destinations use the
rack-encoded IDs described in §4.

`destModuleParamID` is confirmed per `(destModuleTypeString,
destModuleParamName)` pair: sampling every `ModSlot` across all 626 factory
presets, every pair we checked mapped to exactly one ID with zero
conflicting observations (e.g. `("Oscillator", "kParamVolume") -> 1` in
1,842 samples, `("VoiceFilter", "kParamFreq") -> 3` in 1,516 samples). This
was independently cross-validated against C++ enum declarations recovered
from the Serum 2 plugin binary's own debug strings (`Contents/x86_64-win/
Serum2.vst3`, extracted as printable ASCII/UTF-16 runs) — e.g. Oscillator's
enum reads `kParamEnable=0, kParamVolume, kParamPan, kParamOctave,
kParamPitch, kParamFine, kParamCoarsePit, ...`, which assigns `kParamVolume
= 1`, matching the empirical result exactly. `schema.MOD_DEST_TARGETS`
exposes the curated, generation-ready subset of this table (oscillator
volume/pan/octave/pitch/fine/table_position/warp_amount/warp_var2; filter
cutoff/resonance/drive; envelope attack/decay/sustain/release; LFO rate;
macro value; `Global.kParamVoiceAmp` as `global.voice_amp`, confirmed
2026-07-29 against two independent real presets both using
`key_track -> Global.kParamVoiceAmp`).

Type-specific FX-internal params (anything other than `kParamWet`) live in
a separate, deliberately narrower table, `schema.FX_EXTRA_MOD_DEST_PARAMS`
— each `destModuleParamID` there is confirmed per-FX-type individually
(e.g. `FXUtils.kParamBalance` = 4), not assumed to generalize to other FX
types just because they share a param name. Addressed as `fx{i}.<suffix>`
(e.g. `fx0.balance`), same naming convention as `fx{i}.wet`.

FX destinations are a special case, handled outside `MOD_DEST_TARGETS`:
an FX rack slot's `destModuleTypeString` is whichever FX type actually sits
there (e.g. `"FXReverb"`), which depends on what a given `PresetSpec` puts
in its own `fx_chain` — it can't be a fixed table entry the way every other
destination is. `preset/mapping.py::_resolve_mod_destination` resolves the
generation-facing name `fx{i}.wet` (0-based index into that same call's
`fx_chain`) dynamically against `fx_chain[i].type`, using the confirmed
`kParamWet -> destModuleParamID 1` mapping that holds for every FX type
that has a wet knob at all (`FXEQ` doesn't, and generating a mod route
targeting `fx{i}.wet` for an `FXEQ` slot is a validation error, not a
silent no-op). `preset/introspect.py::extract_spec` mirrors this on the
read side, matching each `ModSlot` destination against the preset's own
extracted `fx_chain` before falling back to the static table.

### Source side (decoded for every originally-scoped source)

`source[0]` (the source ID) was originally approached by clustering all mod
routes across a 626-preset sample by ID, which cleanly resolved two
contiguous blocks (LFO, Macro) but left everything else circumstantial —
see "Superseded: statistical clustering" below. On 2026-07-29, two rounds
of a **direct UI probe** closed out the rest: a real Serum 2 instance's own
mod-matrix UI was used to wire up one route per known source by hand
(`Source` column dropdown → pick a named source → any destination →
nonzero amount → save), then the raw saved file was read to recover the
exact `source[0]` integer. This is strictly stronger evidence than
clustering (ground truth from the plugin itself, not inference from usage
patterns) and resolved an ambiguity clustering had left genuinely unsettled
(id 1 vs id 16 for Velocity, see below).

| Source family | Source IDs | Evidence |
|---|---|---|
| LFO 1-10 | `6-15` | Contiguous 10-ID block, statistical clustering (`observed`). Consistent bipolar rate across the block (25-39% of routes bipolar — matches LFOs being a bipolar-capable source), and total usage strictly decreases from id 6 (895 routes, 447/626 presets) down to id 15 (18 routes, 15/626 presets) — matching the "reach for LFO1 first" convention visible everywhere else in the factory content (e.g. Macro 1 used far more than Macro 8). |
| Macro 1-8 | `25-32` | Contiguous 8-ID block, statistical clustering (`observed`). Near-universal usage (544-586 of 626 presets per ID, i.e. 87-94%) — consistent with Serum's factory-content convention of wiring up all 8 macro knobs to something in almost every preset. Near-always unipolar (4-7% bipolar), consistent with macros being 0-100 knobs by convention. |
| Mod Wheel | `1` | Direct UI probe, `confirmed`. (Clustering had suspected id 1 might be Velocity instead — it's Mod Wheel.) |
| Env 1-4 as a **source** (Serum UI: `Envelopes > Env 1`..`4`) | `2-5` | Direct UI probe, `confirmed` for all four (round 1 confirmed Env 1=2; round 2 confirmed Env 2/3/4=3/4/5, validating the contiguity guess round 1 had left unconfirmed). Distinct from routing something *into* an envelope (a destination, see above) — this is an envelope's own output used to modulate something else. |
| Velocity (Serum UI: `Note > Velo`) | `16` | Direct UI probe, `confirmed`. Resolves the id-1-vs-16 ambiguity above in favor of 16. |
| Key Track (Serum UI: `Note > Note#`) | `17` | Direct UI probe, `confirmed`. Immediately after Velocity, inside the `16-24` candidate range clustering had already flagged. |
| Aftertouch | `18` | Direct UI probe, `confirmed`. Immediately after Key Track — this whole `16-19` run is one contiguous "Note" cluster. |
| Poly Aftertouch | `19` | Direct UI probe, `confirmed`. |
| Random 1 (Serum UI: `Note > NoteOn Rand1`) | `21` | Direct UI probe, `confirmed`. |
| Random 2 (Serum UI: `Note > NoteOn Rand2`) | `22` | Direct UI probe, `confirmed`. Serum 2 has **three independent** per-note random sources, not one "Random/S&H" as this project had assumed pre-probe — see Random (Discrete) below. |
| Pitch Bend | `33` | Direct UI probe, `confirmed`. Immediately after the Macro block (`25-32`) — a source-ID region clustering hadn't considered at all. |
| Random (Discrete) (Serum UI: `Note > NoteOn Rand (Discrete)`) | `59` | Direct UI probe, `confirmed`. Inside the `34+` candidate range clustering had flagged, but far higher than the other two random sources — not contiguous with them. |
| Release Velo (Serum UI: `Note > Release Velo`) | `37` | Direct UI probe, `confirmed`, 2026-07-29 round 3. Prompted by `UN_PLACES_BA_Beyond` (see below) using an unresolved source id (`38`) on 3 of its real routes — probing everything nearby in the picker to close the gap resolved these 5 instead (`38` itself resolved separately, see next row). |
| Fixed (Serum UI: `MATRIX` tab source name for a constant offset) | `38` | User-provided screenshot + corpus survey, `confirmed`, 2026-07-30 (item 14). A manual/constant `kParamAmount`, optionally paired with an independent "Aux Source" macro (`subIndex = 25 + macro_index`) that scales/gates it via a still-undecoded formula. `source='fixed'` in `ModRouteSpec` covers the common bare-constant case (`subIndex=0`, 78% of real usage); the aux-paired case (22%) is not generatable. |
| Active Voices (Serum UI: `Note > Active Voices`) | `55` | Direct UI probe, `confirmed`, round 3. |
| Voice Mod 1 (Serum UI: `Note > Voice Mod 1`) | `56` | Direct UI probe, `confirmed`, round 3. |
| Voice Mod 2 (Serum UI: `Note > Voice Mod 2`) | `57` | Direct UI probe, `confirmed`, round 3. Resolves one of the two remaining Galaxy-recreation unknowns (`24`, `40`, `57` — see item 6 in the Galaxy investigation below); `24` and `40` remain open. |
| Voice Index (Serum UI: `Note > Voice Index`) | `58` | Direct UI probe, `confirmed`, round 3. |
| Noise OSC (self-mod, Serum UI: `Oscillators > Noise OSC`) | `20` | Direct UI probe, `confirmed`, round 4 (2026-08-01). Resolves one of the original `20`/`23` cluster gaps. NOT contiguous with the other self-mod oscillator sources (`49-52` below) despite being the same category in the UI. |
| NoteOn Alt. (Serum UI: `Note > NoteOn Alt.`) | `23` | Direct UI probe, `confirmed`, round 4. Resolves the other `20`/`23` cluster gap. |
| NoteOn Alt.2 (Serum UI: `Note > NoteOn Alt.2`) | `24` | Direct UI probe, `confirmed`, round 4. Resolves one of the two remaining Galaxy-recreation unknowns (`24`, `40`, `57`); only `40` remains open now. |
| Expr X / Pan (Serum UI: `Note Expression > Expr X (Pan)`) | `34` | Direct UI probe, `confirmed`, round 4. MPE-style per-note expression; contiguous right after Pitch Bend (`33`). |
| Expr Y / Timbre (Serum UI: `Note Expression > Expr Y (Timbre)`) | `35` | Direct UI probe, `confirmed`, round 4. |
| Expr Z / Press. (Serum UI: `Note Expression > Expr Z (Press.)`) | `36` | Direct UI probe, `confirmed`, round 4. |
| OSC A (self-mod, Serum UI: `Oscillators > OSC A`) | `49` | Direct UI probe, `confirmed`, round 4. First of a clean contiguous 6-block spanning the 3 melodic oscillators, Sub, and both filters — see the next 5 rows. |
| OSC B (self-mod) | `50` | Direct UI probe, `confirmed`, round 4. |
| OSC C (self-mod) | `51` | Direct UI probe, `confirmed`, round 4. |
| SUB OSC (self-mod) | `52` | Direct UI probe, `confirmed`, round 4. |
| Filter 1 (self-mod, Serum UI: `Filters > Filter 1`) | `53` | Direct UI probe, `confirmed`, round 4. Serum's own UI numbers filters 1-indexed here, unlike this project's 0-indexed `filter0`/`filter1` destination convention — `schema.MOD_SOURCE_IDS` keeps the 0-indexed convention for API consistency (`"filter0": 53`), see the table's source code comment. |
| Filter 2 (self-mod) | `54` | Direct UI probe, `confirmed`, round 4 (`"filter1": 54`). |
| LFO 2 Y (self-mod, chaotic-attractor Y-axis output) | `40` | Read directly from a real Factory preset's own MATRIX tab, `confirmed`, round 5 (2026-08-01). Closes the LAST of this project's originally-flagged unknown source ids (`24`/`40`/`57` from the Galaxy investigation — all three now resolved). |

Round 4 (2026-08-01) resolved 12 new source names in one probe file, found
by having the user screenshot every submenu of Serum 2's own MATRIX-tab
source picker rather than guessing which names might still be unprobed —
turned up 3 entire categories (`Oscillators`, `Filters`, `Note Expression`)
this project had never even seen the contents of before, previously only
referenced abstractly as "out of original scope" in this doc. After that
round, every single named entry in the picker (49 across every submenu) had
a resolved id — none of them was `40`, making it look unreachable via the
standard UI.

**Round 5 (2026-08-01), `40` resolved anyway — the suggested alternate
approach worked.** A corpus survey (876 presets, the same technique used
for mod-destination gaps) found `40` is actually COMMON in real content —
34 real routes across Bass/Chord/Drum/Lead/Organ/Pad categories, not a rare
edge case. Rather than more picker sweeping, pointed the user at one
specific real file (`BA - Sewer Bros.SerumPreset`, `ModSlot0`, a bare
no-aux route into `WTOsc.kParamTablePos`) and asked what Serum's own MATRIX
tab displays for that exact row: **"LFO 2 Y."** Presumed to be the Y-axis/
secondary coordinate output of a chaotic-attractor LFO shape (Rossler/
Lorenz are classic multi-axis dynamical systems, see `SIMPLE_LFO_TYPES`) —
a context-sensitive menu entry that only appears for specific LFO shapes,
explaining why it was invisible to round 4's picker screenshots (which
weren't necessarily looking at an LFO using that shape at the time).
**Confirmed for this ONE LFO slot only** (`"lfo1_y": 40`, 0-indexed to
match this project's own `lfo0`..`lfo9` convention) — whether other LFO
slots have an analogous `_y` source, and what id it would use, is unknown;
don't assume a contiguous `lfo{i}_y` family exists without probing each
one.

All of the above are wired into `serum-mcp`, which generates and reads back
routes for them (see `schema.MOD_SOURCE_IDS`, `generation/spec.py::ModRouteSpec`).
**This closes out every source in this project's original gap list**
(Envelope, Velocity, Mod Wheel, Aftertouch, Pitch Bend, Key Track,
Random/S&H — all resolved, the last three via a discovery that Random is
actually three independent sources), plus all 5 of the "Note"-category
sources this project had only ever seen in the picker without a name-to-ID
mapping.

**Still genuinely unresolved, as of round 5 (2026-08-01)**: only `subIndex`
itself (`source[1]`, see below — its meaning OUTSIDE the aux-source
mechanism, which is already fully decoded, item 14) remains open. Every
source id this project ever flagged as unknown is now resolved, including
all 3 of Galaxy's original unknowns (`24`, `40`, `57`) and `38`
(resolved separately as "Fixed", item 14 — not adjacent to `Release Velo`
(`37`) in the picker, the very next item down turned out to be plain
`Velo` (id `16`, Velocity appearing a second time in the Note category),
needing its own targeted probe rather than positional guessing). `40`
specifically survived a full picker sweep (round 4) and only fell to a
DIFFERENT technique — a corpus survey to find real usage, then reading
the answer directly off a real preset's own MATRIX tab (round 5) rather
than more picker probing. The direct-probe method itself is proven fast
and reusable across 5 rounds now (round 4 alone resolved 12 IDs in one
sitting from a single probe file, after the user provided a screenshot of
every submenu; round 5 resolved the one holdout via corpus survey +
one targeted real-preset read instead).

**Reassessed 2026-08-01 — `subIndex` is arguably not a genuine open
question at all, just leftover cautious phrasing.** Revisited while
researching whether public prior art existed for it (it doesn't — see the
`curveVals` research note above; no one else has published anything on
Serum 2's `source[1]`/aux mechanism either). Every non-zero `subIndex`
value this project has ever observed across every corpus survey resolved
cleanly as a valid aux-source id from the exact same `MOD_SOURCE_IDS`
space (item 14) — there is no residual category of non-zero values left
unexplained. The only theoretical gap is whether `subIndex=0` could ever
mean something OTHER than "no aux source" in some untested context — but
`0` never collides with any real source id, so this is a clean,
unambiguous sentinel already, not a live mystery. Downgrading this from
"open question" to "settled in practice, no further action planned"
unless a future investigation surfaces a genuinely unexplained non-zero
`subIndex` value that doesn't map to a known source id.

**Method, for resolving what's left**: open Serum 2 on any preset, go to
the MATRIX tab, pick an unresolved source from the `Source` column dropdown
on an empty row, set any destination and a nonzero amount, save under a new
name, then read the raw file (`serum_mcp.preset.packer.unpack_file(path).data["ModSlot0"]["source"]`,
or whichever slot index the new row landed in — matrix rows correspond 1:1
to `ModSlot0`, `ModSlot1`, ... in ascending index order, confirmed across
multiple probes this session). Multiple sources can be probed in one file
in one sitting (this project probed 8 at once) as long as each gets its own
row — the row's position in the file, read in order, tells you which
source produced which `source[0]`; the destination doesn't need to be
distinct between rows, only the row order matters. This is faster and more
conclusive than statistical clustering and doesn't require a large corpus
of real-world presets — see `CONTRIBUTING.md`.

**Superseded: statistical clustering** (kept for method-reuse value, e.g. if
a future source can't be probed directly for some reason): before the
direct probe, `destModuleParamName` distribution per source ID gave
suggestive but not conclusive signal — id `1` most often targeted
`VoiceFilter.kParamFreq` and `Macro.kParamValue`; id `16` most often
targeted `Env.kParamDecay`/`Env.kParamAttack` (envelope *time* modulation is
a classic velocity-sensitivity technique) — correctly predicting id 16 =
Velocity, though it couldn't distinguish this from id 1 without the direct
probe. Binary string mining (searching the plugin binary's debug strings for
an enum tying source names to `ModSlot.source` integers, the technique that
worked for the destination side) did not find one for sources despite
targeted searches.

`subIndex` (`source[1]`) — **resolved 2026-07-30**, see item 14 in §5: a
second, independent source id from the exact same `MOD_SOURCE_IDS` space as
`source[0]`, Serum's "Aux"/"Via" system (`ModRouteSpec.aux_source`). 0 (no
valid source has this id) is the "no aux" sentinel, matching the "0 in the
overwhelming majority of samples" observation above.

## 7. Wavetable file format

Separate from the CBOR preset format (§1), Serum's wavetable `.wav` files
are their own undocumented format — decoded this session because
`serum-mcp` needed to write new ones (`OscillatorSpec.custom_harmonics`,
`preset/wavetable.py`), not just reference existing factory tables. Nobody
had already cracked this one publicly the way the CBOR container had been.

Found by inspecting several real factory `.wav` tables byte-for-byte:

- Standard RIFF/WAVE container: `"RIFF" <size> "WAVE"`.
- A `JUNK` chunk (28 zero bytes) before `fmt ` — present in every factory
  file inspected; reproduced for structural fidelity, though RIFF readers
  are supposed to skip unknown/`JUNK` chunks regardless.
- `fmt ` chunk: **IEEE float** (format tag `3`, not integer PCM — Python's
  stdlib `wave` module can't even open these), mono, 44100 Hz, 32-bit.
- A non-standard **`clm ` chunk** containing the literal ASCII text
  `<!>2048 01000000 wavetable (www.xferrecords.com)`. Confirmed byte-for-
  byte identical across every factory table checked regardless of that
  table's actual frame count (7, 9, 24, and 112 frames observed) — it's a
  fixed format marker, not per-file metadata. `2048` is the frame size in
  samples: every table's total sample count divided evenly by 2048 with
  zero remainder in every file checked.
- `data` chunk: raw little-endian float32 samples, `2048 * num_frames`
  samples total. Each consecutive 2048-sample block is one single-cycle
  waveform frame; Serum's wavetable position control (`kParamTablePos`,
  §4 Oscillators) scans through these frames as a value from `0.0` to
  roughly `num_frames`-ish (empirically the control tops out around `256`
  regardless of a table's actual frame count, see §4 — consistent with
  Serum normalizing the position control to a fixed range independent of
  the loaded table's real frame count).

This is `observed`-confidence, not `confirmed` — inferred from consistent
structure across multiple real files (the same evidence bar used everywhere
else undocumented-format claims are made in this project), not validated
against Xfer's own source. `preset/wavetable.py::write_wavetable_wav`
reproduces this exact byte layout; `synthesize_frame` builds one frame from
a harmonic amplitude series via inverse real FFT (`numpy.fft.irfft`),
peak-normalized to avoid clipping. Generated tables are written to
`Tables/User/serum-mcp/` under Serum's Tables folder (a sibling of
`Presets/`, resolved by `config.get_tables_dir()` — override with
`SERUM_TABLES_PATH` the same way `SERUM_PRESETS_PATH` overrides the presets
folder). Filenames are a hash of `(synthesis algorithm version, harmonic
data)`, not just the harmonic data alone -- identical definitions reuse one
file, but a `synthesize_frame` algorithm change always produces a fresh
file rather than silently continuing to serve stale cached audio for
existing presets (found the hard way: fixing the normalization bug below
had zero effect on an already-generated preset on the first attempt,
because its wavetable file already existed under the old cache key and
`preset/mapping.py` only (re)synthesizes when the target path doesn't
already exist).

**Amplitude across octaves (partially addressed, `observed`-confidence)**:
the first live real-Serum test of a synthesized wavetable played back much
quieter in upper octaves than a factory table, with the shared filter/
envelope ruled out by A/B-comparing against another oscillator in the same
preset. Root cause, as best understood: `synthesize_frame` originally
peak-normalized the *combined* multi-harmonic waveform, which scales the
whole signal down to fit whatever the harmonics' constructive-interference
peak happens to be -- under-representing how loud the fundamental ends up
once Serum's wavetable oscillator band-limits away upper harmonics at
higher played pitches (a normal thing for any wavetable synth to do, not a
bug in Serum). Changed to anchor the *fundamental's own* contribution at a
target level, with a soft-knee limiter (only compressing the portion of
each sample *above* that level, leaving the fundamental-dominated bulk of
the waveform untouched) for harmonic content that would otherwise clip.
This is a measured improvement (the fundamental's spectral energy survives
better relative to a plain peak-normalize-then-clip approach — see
`tests/test_wavetable.py`), not a proven complete fix -- it hasn't been
re-verified live yet, and there may be a Serum-side factor (e.g. how
aggressively its anti-aliasing filters upper harmonics at a given pitch)
that no normalization scheme on our end can fully compensate for. Treat
"still quiet in extreme upper octaves" as a possible remaining gap, not
disproof that the fix helped at all.

**Known gap**: phase is not exposed — `synthesize_frame` treats every
harmonic amplitude as a real-valued (cosine-phase) FFT bin, so all
generated tables currently use one fixed phase relationship between
harmonics. Real-world waveform character (e.g. the audible difference
between a cosine-phase and sine-phase harmonic stack) that depends on
relative phase isn't reachable yet.

### Sample-to-wavetable slicing

`OscillatorSpec.sample_source` builds a wavetable the same way
`custom_harmonics` does — writing a `.wav` to `Tables/User/serum-mcp/` via
`write_wavetable_wav` and referencing it exactly like a curated factory
table — but the frames come from **slicing a user-provided audio file**
instead of additive synthesis. This predates `SampleOsc` being modeled (see
§8) and remains useful in its own right: a synthesized, morphable texture
derived from a sample is a different (not strictly worse) result than
`SampleOsc` playback -- use this when the user wants that character,
`sample_playback_source` (§8) when they want the sample to stay recognizable.

`preset/wavetable.py::read_wav_mono` parses an arbitrary source file
(16/24/32-bit PCM or 32-bit IEEE float, including `WAVE_FORMAT_EXTENSIBLE`
headers common from modern DAW exports; downmixes multi-channel files by
averaging) rather than requiring pre-converted Serum-table-shaped input.
`slice_sample_to_frames` then:

1. Resamples to 44100 Hz via linear interpolation if the source rate
   differs (deliberately not audiophile-grade — every frame becomes a
   short, intentionally loop-buzzy wavetable cycle regardless, so exact
   resampling fidelity doesn't carry through to the audible result; avoids
   adding a dependency like `scipy` for a difference that wouldn't be
   perceptible here).
2. Takes `num_frames` evenly-spaced 2048-sample windows across the
   (resampled) waveform's duration — frame 0 at the very start (a drum
   hit's transient, for example), the last frame at the tail.
3. Applies a short (~64-sample) edge fade to each frame and independently
   peak-normalizes it, so looping a non-periodic slice at pitch clicks less
   and quiet tail frames aren't inaudible relative to a loud transient
   frame.

Not yet validated live in Serum as of this writing (`observed`-confidence
at best, and only against the file-format layer — see
`tests/test_wavetable.py`'s WAV-reading/slicing tests); the general
approach (looping short raw-audio windows as wavetable frames) is a known
technique used by other "sample to wavetable" tools, but this project's own
specific slicing choices (frame spacing, fade length, per-frame
normalization) haven't been ear-tested against a real preset yet.

## 8. SampleOsc (true one-shot/sample playback)

Reverse-engineered by scanning all 626 factory presets shipped with a real
Serum 2 install for oscillator slots (0-2, 1,878 total) using each of the 5
sound-source engines, using the same evidence standard as everywhere else in
this document (real preset survey, not Xfer documentation, since `SampleOsc`
isn't covered by the VST3 parameter dump this project otherwise
cross-checks against):

| Engine | Slots using it | % of 1,878 |
|---|---|---|
| `WTOsc` | 1,006 | 53.6% |
| `MultiSampleOsc` | 297 | 15.8% |
| `GranularOsc` | 76 | 4.0% |
| `SpectralOsc` | 67 | 3.6% |
| `SampleOsc` | 41 | 2.2% |

(A slot counts as "using" an engine if that engine's nested `plainParams` is
a real dict rather than the `"default"` sentinel string. This undercounts
`SampleOsc` specifically -- see the `kParamType` paragraph below for why --
the true count is somewhat higher than 41.)

### Engine selection: `kParamType`

Every `Oscillator{i}` (slots 0-2) carries `plainParams.kParamType`, one of
`kOsc_WT` / `kOsc_Sample` / `kOsc_Granular` / `kOsc_MultiSample` /
`kOsc_Spectral` -- this, not which nested engine sub-object happens to have
non-default `plainParams`, is the authoritative switch (confirmed: an
oscillator can have `kParamType = kOsc_Sample` with a fully populated
`samplePathRelative`/`sampleRate`/`numChannels`/`numFrames` while its
`SampleOsc{i}.plainParams` stays the `"default"` sentinel, because
`kParamWarp`/`kParamWarpMenu` were never touched from their defaults -- this
is why the slot-usage table above undercounts `SampleOsc`, since the initial
survey used non-default `plainParams` as the detection signal before this
was understood). Every WTOsc-engine preset `serum-mcp` has ever generated
before this was discovered omitted `kParamType` entirely and loaded fine, so
absence == `kOsc_WT` (the implicit default). `preset/mapping.py::apply_spec`
now writes `kParamType` explicitly on every call regardless of which engine
is active, rather than only when switching to `kOsc_Sample` -- otherwise a
later partial edit that switches a slot's engine back to WT could leave a
stale `kOsc_Sample` selector behind (the same partial-edit staleness class
documented elsewhere in this project's commit history, e.g. the "apply_spec
silently resetting global params on partial edits" fix).

### `SampleOsc{i}` structure

Example, from `Bass/Electric/BA - Fretless Bass.SerumPreset`, Osc B:

```
SampleOsc1:
  samplePathRelative: "Factory/Bass/Round Comforting.flac"
  sampleRate: 48000
  numChannels: 1
  numFrames: 159974
  plainParams:
    kParamWarp: 0.19736839830875397
    kParamWarpMenu: kDistAsym
```

- `samplePathRelative`/`sampleRate`/`numChannels`/`numFrames` are file
  metadata siblings of `plainParams`, exactly the same shape as `WTOsc{i}`'s
  `relativePathToWT`/etc (§4) -- same risk of a metadata/file mismatch
  causing Serum to misread the file if they're wrong.
- `samplePathRelative` is relative to Serum's **`Samples`** folder, a
  sibling of `Presets`/`Tables` under the same root (confirmed: resolved
  `Factory/Bass/Round Comforting.flac` against a real install and the file
  exists exactly there; also observed a `../Multisamples/...`-relative path
  in another preset, which only resolves correctly if the base is
  `Samples/`, confirming the sibling-folder relationship). `serum-mcp`
  copies a user's file into `Samples/User/serum-mcp/`
  (`config.get_samples_dir()`, overridable via `SERUM_SAMPLES_PATH` exactly
  like `SERUM_TABLES_PATH`/`SERUM_PRESETS_PATH`) -- see
  `preset/sample_library.py`.
- `kParamWarp`/`kParamWarpMenu` (`SAMPLEOSC_PARAMS` in `schema.py`) use the
  **same raw enum** as `WTOsc`'s `kParamWarpMenu` (confirmed: values
  observed here -- `kDistSoftClip`, `kAM_OSC`, `kPD_FILT1`, `kFM_NOISE`,
  `kFM_OSC2`, `kRM_OSC`, ... -- are all members of `WTOSC_PARAMS`'s
  already-established enum). A second warp lane (`kParamWarp2`/
  `kParamWarpMenu2`, plus a rarer, separate `kParamWarpVar2` of uncertain
  meaning) exists on both engines. **For `WTOsc` this is now generatable**
  (`OscillatorSpec.warp_mode2`/`warp_amount2`) — found live 2026-07-29 to
  matter far more than "a rarely-used extra knob": a real preset's primary
  oscillator used it to tame an otherwise-raw/digital `kFM_NOISE` warp with
  a `kFilterLPF` second stage, and a recreation missing it sounded harshly
  "8-bit" despite the primary warp matching exactly. Surveyed across all
  886 real presets: 193 `WTOsc` slots use it (not the ~10/41 this note
  originally estimated from a much smaller sample). `SampleOsc`'s own
  second lane remains unwired — same v1 scope decision, lower observed
  prevalence there, revisit if a `SampleOsc` case needs it.
- **File format**: every `samplePathRelative` observed across the factory
  survey (32 distinct references checked) was `.flac`. `serum-mcp` only
  supports `.wav` (`preset/sample_library.py`'s `_SUPPORTED_EXTENSIONS`) --
  **confirmed working live**: a `serum-mcp`-generated preset referencing a
  `.wav` under `Samples/User/serum-mcp/` loaded and played correctly in a
  real Serum 2 install (FL Studio 21), despite every factory reference
  being `.flac`. `.flac` support remains a possible future addition (would
  need a FLAC metadata parser this project doesn't have) but is no longer
  blocking.
- **Root-note/pitch reference: confirmed `C5`**. No explicit root-note
  parameter was found in `SampleOsc{i}` or `Oscillator{i}`'s own
  `plainParams` (beyond the already-shared `kParamOctave`/`kParamDetune`/
  `kParamFine`), so this had to be confirmed by ear against a live preset:
  a referenced sample plays back at its originally-recorded speed when
  `C5` is played in the piano roll -- a fixed convention, not something
  read from the file or configurable via a param. `OscillatorSpec.octave`/
  `detune`/`fine` are the only ways to shift this if the user wants a
  different reference note.
- **Pitch and playback duration are coupled, with no way to decouple them**
  (`observed`-confidence, inferred rather than exhaustively tested across
  many notes -- but a direct consequence of the confirmed finding above,
  and consistent with `SampleOsc` sharing `WTOsc`'s architecture). Like
  `WTOsc` and like a classic "resampling"-mode sampler (as opposed to a
  time-stretching one), `SampleOsc` controls pitch purely by changing
  playback rate -- a higher note reads through the buffer faster (shorter
  perceived duration), a lower note reads slower (longer). No
  formant-preserving/time-stretch parameter exists anywhere in
  `SampleOsc{i}`/`Oscillator{i}`'s `plainParams` (only the loop controls
  below and the shared warp system) -- this is a genuine engine limitation,
  not a `serum-mcp` gap, and can't be fixed from the preset-generation
  side. Consequence for melodic use: a one-shot played across multiple
  notes (e.g. a bell used for a melody) will have a different perceived
  length at each pitch. Looping (`sample_loop`, below) mitigates this for
  the *sustained* portion once the loop point is reached, but not for the
  initial attack/transient, which still speeds up or slows down with
  pitch.
- **Real one-shot recordings often have a measurable left/right level
  imbalance that has nothing to do with Serum or this project** -- found
  live, then confirmed by direct measurement: a user reported presets
  built from real samples sounding panned left despite `kParamPan` being
  verified `0.0` (center) in every generated preset this session. Decoding
  the actual source files' stereo channels and measuring RMS per channel
  found the bias in the *recordings themselves* -- e.g. one guitar pluck
  one-shot measured +4.3dB louder on the left channel, a bell one-shot
  +2.3dB -- almost certainly an off-center mic placement when the sample
  pack was originally recorded, not anything introduced downstream.
  `preset/sample_library.py::copy_sample_to_library` now corrects this by
  default (`OscillatorSpec.sample_center_pan`, default `True`): it decodes
  a stereo file, and if the channels differ by more than 1dB RMS, applies
  a linear per-channel gain that brings both to their geometric-mean
  target level, then writes that as a new 16-bit PCM WAV (re-encoding, not
  a byte-for-byte copy, only when correction is actually needed -- mono
  files and already-balanced stereo files still copy verbatim). This is a
  pure level rebalance, not a mono-sum or any other content-altering
  operation -- each channel's actual waveform is scaled, not replaced, so
  the recording's stereo width/character survives.

### Loop parameters (on `Oscillator{i}`, not `SampleOsc{i}`)

```
Oscillator1.plainParams:
  kParamLoopMode: kPingPong
  kParamLoopStart: 77.98513174057007
  kParamLoopEnd: 87.6865565776825
  kParamLoopCrossfade: 34.99999940395355
```

- Observed `kParamLoopMode` values: `kPingPong` (9), `kForward` (8),
  `kTailed` (5), out of 30 `SampleOsc`-engine slots with loop params
  present at all -- the remaining ~8 slots had no `kParamLoopMode` key,
  which is what `serum-mcp` treats as "off"/true one-shot (there's no
  observed explicit "off" enum value; omitting the key is what turns
  looping off, confirmed by cross-referencing against slots that are
  clearly one-shot drum hits, e.g. `Kick Designer`).
- `kParamLoopStart`/`kParamLoopEnd`: `0.16-100.0`/`17.6-99.4` observed, `%`
  into the sample -- modeled as `0-100` in `schema.py`.
- `kParamLoopCrossfade`: `0.5-63.2` observed; modeled with a `0-100` ceiling
  like other `%`-unit params in this schema, but the true engine-enforced
  bound isn't confirmed (`confidence="uncertain"`).
- `OscillatorSpec.sample_loop` (`'off'`/`'forward'`/`'ping_pong'`/`'tailed'`)
  plus `sample_loop_start`/`sample_loop_end`/`sample_loop_crossfade` expose
  this. `off` is the default -- a true one-shot, the main use case this
  engine was built for (drum hits, foley, vocal chops kept recognizable and
  layered/processed like any other Serum oscillator).

### What's still open

The two things that could only be resolved by a live Serum test -- whether
`.wav` works in `samplePathRelative` (yes), and the pitch-reference note
(`C5`) -- are now both confirmed (see above; tested against a real Serum 2
install in FL Studio 21, 2026-07-28). Remaining gaps:

- `preset/introspect.py::extract_spec` and `describe_preset` **now recognize
  `SampleOsc`/`kParamType`** (fixed after the cosmetic gap above was caught
  live): a `sample_playback_source` oscillator round-trips its
  `sample_playback_source` (reconstructed as an absolute path via
  `config.get_samples_dir()`, gracefully omitted if that folder isn't
  resolvable in the current environment), `warp_amount`/`warp_mode`, and
  `sample_loop`/`sample_loop_start`/`sample_loop_end`/`sample_loop_crossfade`
  -- `describe_preset` shows `sample=<path>` instead of a misleading
  `wavetable=default` for these oscillators.
- `.flac` support (would let `serum-mcp` reference Serum's own factory
  sample library directly, or accept a wider range of user files without
  requiring a WAV conversion first) remains unimplemented.
