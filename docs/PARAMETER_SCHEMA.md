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
   more than seven resolved names. **Still unresolved, but out of original
   scope** (only discovered by seeing Serum 2's real source picker):
   `Release Velo`, `Active Voices`, `Voice Index`, `Voice Mod 1`/`2`, and
   `Oscillators`/`Filters`/`Note Expression` as self-mod sources.
   `subIndex` (`source[1]`) is unresolved for every source family (always 0
   in every sample so far). `serum-mcp` now generates and reads back mod
   routes for every confirmed source (`generation/spec.py::ModRouteSpec`);
   everything else still round-trips opaquely.
1b. **Mod matrix destination coverage is narrower than `MOD_DEST_TARGETS`
   makes it look** (found live 2026-07-29, see the Galaxy writeup above) —
   a real preset's raw file had 27 active `ModSlot`s; only 11 round-tripped
   through `extract_spec` before this was found (14 after the multi-rack FX
   fix below), the rest silently dropped for an unmodeled *destination*
   even though their source was resolved. Unmodeled destination categories:
   `Arp` params (e.g. modulating the arpeggiator's gate/chance live), a
   `WTOsc` secondary warp param (`kParamWarpVar2`), `NoiseOsc.kParamColor`,
   FX params other than `kParamWet` (currently the ONLY FX param
   generatable as a mod destination), `VoiceFilter.kParamWet`, `Global.
   kParamVoiceAmp`, `VoicePanel.kParamGlobalScalingEnvTime`. Silent
   under-reporting, not corruption — but it means `describe_preset`/
   `extract_spec` can present a real preset as far simpler than it actually
   is, which misled an earlier recreation attempt into thinking its
   modulation was complete when ~40% of it was invisible.
2. **Filter cutoff Hz curve** (§4, Filters) — only one calibration point.
3. **Unmodeled oscillator engines** — Granular/MultiSample/Spectral remain
   unmodeled (GranularOsc/MultiSampleOsc/SpectralOsc appeared in 3.6-15.8%
   of the 1,878 slot-0-2 sample, see §8's table). `SampleOsc` (2.2% of
   slots, true one-shot/sample playback) **is now modeled** — see §8 —
   which was the highest-value item in this list as of this project's
   earlier sessions; MultiSampleOsc (used for realistic multisampled
   instrument patches, e.g. real pianos/guitars) is arguably the next most
   valuable remaining gap. Confirmed live 2026-07-29 recreating a second
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
   that one recreation, but this is not remotely enough evidence to design
   a general `OscillatorSpec` `SpectralOsc` feature (one sample, `flex`'s
   real meaning/range totally unexplored, `kParamFreqLo` suggests other
   related params likely exist unseen) — would need the same kind of
   corpus survey done for LFO shapes/second-warp-lane before generalizing.
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
5. **3 of 16 FX types lack param schemas**: `FXSplit`/`FXSplit3`/`FXSplitMS`
   — structurally different (nested band-splitter containers, not a flat
   `plainParams` dict), see §4. The other 13 are fully modeled. (Separate
   from this: `FXRack0`/`1`/`2` — the 3 *parallel racks* each of these 16
   types can sit in — are now all supported, as of 2026-07-29; don't
   confuse "unmodeled FX type" with the now-fixed "unmodeled rack".)
6. Several numeric ranges are marked `uncertain` in `schema.py` (e.g. unison
   voice count ceiling, LFO/Chorus/Delay times where only normalized values
   were observed without a confirmed Hz/ms curve) — these are *observed*
   ranges from the sample, which may not be the true engine-enforced bounds.

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

Note: `20` and `23+` (within the probed `16-24` cluster) weren't assigned to
anything in this project's original scope and remain unidentified — likely
`Release Velo` or one of the voice-management sources mentioned below, but
not probed.

All of the above are wired into `serum-mcp`, which generates and reads back
routes for them (see `schema.MOD_SOURCE_IDS`, `generation/spec.py::ModRouteSpec`).
**This closes out every source in this project's original gap list**
(Envelope, Velocity, Mod Wheel, Aftertouch, Pitch Bend, Key Track,
Random/S&H — all resolved, the last three via a discovery that Random is
actually three independent sources).

**Genuinely out of original scope, still unresolved**: `subIndex`
(`source[1]`, see below), and a handful of sources this project only
learned existed by seeing Serum 2's real source picker rather than being
part of the original gap list: `Release Velo`, `Active Voices`,
`Voice Index`, `Voice Mod 1`/`Voice Mod 2` (all nested
under `Note`, likely voice-management/polyphony-related, not in the
original "Envelope/Velocity/Mod Wheel/Aftertouch/Pitch Bend/Key
Track/Random" gap list this project started from) — none of these are
decoded or wired in, but the direct-probe method below is proven to reach
them quickly if/when they're needed.

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

`subIndex` (`source[1]`) is unresolved for every source family — it's 0 in
the overwhelming majority of samples (including every route in the
2026-07-29 probe session); a handful of source IDs (notably 6-9, inside the
LFO block) show varied non-zero subIndex values correlated with other valid
source IDs (16-32ish), suggestive of some kind of chained/secondary
modulation, but this wasn't pinned down further either.

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
