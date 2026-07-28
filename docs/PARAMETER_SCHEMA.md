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
those.

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
| `WTOsc`, `GranularOsc`, `MultiSampleOsc`, `SpectralOsc` | *type* placeholders (empty) — actual per-slot data lives nested inside `Oscillator{i}` as `WTOsc{i}` etc. | Partially (WTOsc only) |
| `VoiceFilter0`, `VoiceFilter1` | Filter 1, Filter 2 | Yes |
| `Filter` | shared filter section UI mix knob | No |
| `Env0`..`Env3` | the 4 envelopes | Yes |
| `LFO0`..`LFO9` | the 10 LFOs | Partially (rate/mode only, not curve-drawn shapes) |
| `LFOPointModBus0`..`LFOPointModBus15` | point-editor LFO mod busses | No |
| `Macro0`..`Macro7` | the 8 macro knobs | Yes |
| `Global0` | master volume, mono, portamento, poly count, ... | Partially |
| `ModSlot0`..`ModSlot63` | the 64-slot mod matrix | Partially — all destinations + LFO/Macro sources, see §6 |
| `FXRack0`..`FXRack2` | 3 independent effects racks, each an ordered `FX` list | FXRack0 only, in V1 |
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
shared params (`kParamEnable`, `kParamOctave`, `kParamVolume`, `kParamPan`,
`kParamUnison`, `kParamDetune`) apply to all 5 slots identically and are
fully generatable via `OscillatorSpec`.

**Slots 0-2 (Osc A/B/C)** each have a sound source that's one of 5 engines,
keyed as `WTOsc{i}`, `GranularOsc{i}`, `MultiSampleOsc{i}`, `SampleOsc{i}`,
`SpectralOsc{i}` inside `Oscillator{i}`. **Only `WTOsc` (the classic
wavetable engine) is modeled** — it's the default engine and the one every
factory bass/lead/pad preset we sampled that wasn't a multisample
instrument used (`OscillatorSpec.table_position`/`warp_amount`/`warp_mode`
— the last picks the wavetable warping character via a curated subset of
the raw `kParamWarpMenu` enum, `schema.SIMPLE_WARP_MODES`: FM/AM, sync,
PWM, wavefolding/clipping distortion, quantize, and two built-in filter
warps). `oscillator{i}.table_position` and `oscillator{i}.warp_amount`
(slots 0-2) are also valid mod-matrix destinations — a classic use is an
LFO scanning through the wavetable, or a macro morphing the warp amount.
Granular, multisample, spectral and raw sample playback exist in the format
and round-trip fine, but `serum-mcp` cannot currently generate or target them.

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

Beyond selecting a curated factory table, `OscillatorSpec.custom_harmonics`
can *synthesize a brand-new wavetable* from a harmonic amplitude series —
see §7 for the wavetable `.wav` file format itself (also reverse-engineered
this session, separately from the CBOR preset format).

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
also generates `stereo` (`kParamStereo`, width/spread %) alongside
cutoff/resonance/drive.

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
`attack`/`hold`/`decay`/`sustain`/`release`; `hold` (a plateau at full level
before decay starts) defaults to 0 and is rarely needed.

### LFOs

10 slots (`LFO0..9`). `LfoSpec` generates `rate`, `mode` (`Free`/`Retrig`/
`Envelope` — `Retrig` recovered from the plugin binary's debug strings,
never observed in the factory sample), `beat_sync`, `delay` (fade-in before
the LFO starts after note-on), `rise` (ramp-up time), and `smooth` (lag
smoothing, for less steppy random/S&H shapes). Free-hand curve-drawn LFO
shapes (`curveData`: `xVals`/`yVals`/`curveVals`) exist and round-trip, but
generating them is out of scope for V1 (no natural-language mapping for
"draw this LFO shape" yet).

### Macros & Global

8 macros (`Macro0..7`, each `{name, plainParams.kParamValue}`). `Global0`
covers master volume (confirmed default `0.5` = -9dB), mono toggle, and
portamento time (`kParamPortamentoTime`, seconds — glide between notes),
all generatable via `GlobalSpec`; a handful of rarer global params (voice
count, tuning, MPE bend range, FX bus routing) are documented in
`schema.py` but not yet wired into generation.

### Effects

3 independent racks (`FXRack0..2`); V1 generation only writes to
`FXRack0`. Each rack holds an ordered `FX` list; each entry has an integer
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

We also confirmed empirically that an FX entry's `destModuleID` in the mod
matrix encodes *which rack* an FX unit lives in: `0-11` for rack 0 slots,
`100-111` for rack 1, `200-211` for rack 2 (e.g. `FXComp` destinations
`0, 1, ..., 9, 14` alongside `101, 102` and `205 `in our sample).

## 5. Known gaps and open questions

These are the honest uncertainties, ranked roughly by how much they'd
improve generation quality if resolved:

1. **Mod matrix `source` encoding is partially decoded** (updated — see §6
   for the full writeup). The *destination* side was already fully
   confirmed. The *source* side (`[sourceId, subIndex]`) is now resolved for
   two families — LFO1-10 (ids 6-15) and Macro1-8 (ids 25-32) — via
   statistical clustering across all 626 factory presets, cross-checked
   against `destModuleParamID` values recovered independently from the
   Serum 2 plugin binary's own debug/RTTI strings. **Still unresolved**:
   Envelope, Velocity, Mod Wheel, Aftertouch, Pitch Bend, Key Track and
   Random/S&H sources — several candidate IDs exist (`1-5`, `16-24`, `34+`)
   but none clustered into an evidence-backed block the way LFO/Macro did.
   `subIndex` (`source[1]`) is unresolved for every source family (always 0
   in every sample). `serum-mcp` now generates and reads back LFO/Macro mod
   routes (`generation/spec.py::ModRouteSpec`); everything else still
   round-trips opaquely.
2. **Filter cutoff Hz curve** (§4, Filters) — only one calibration point.
3. **Unmodeled oscillator engines** — Granular/MultiSample/Spectral/Sample.
   These are common enough (GranularOsc/MultiSampleOsc/SpectralOsc appeared
   in 5-15% of sampled presets each) that a V1.1 covering at least
   MultiSampleOsc (used for realistic instrument patches) would be valuable.
4. **LFO curve shapes** (`curveData`) and **free-drawn envelope curves** are
   unmodeled — Serum 2's point-based custom curve editor data.
5. **3 of 16 FX types lack param schemas**: `FXSplit`/`FXSplit3`/`FXSplitMS`
   — structurally different (nested band-splitter containers, not a flat
   `plainParams` dict), see §4. The other 13 are fully modeled.
6. Several numeric ranges are marked `uncertain` in `schema.py` (e.g. unison
   voice count ceiling, LFO/Chorus/Delay times where only normalized values
   were observed without a confirmed Hz/ms curve) — these are *observed*
   ranges from the sample, which may not be the true engine-enforced bounds.

None of these block V1's stated goal (text description → valid, loadable
`.SerumPreset` covering oscillators/filters/envelopes/macros/core FX) — they
bound what V1 can *express*, not whether what it writes is valid.

## 6. Mod matrix structure

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
    "kParamBipolar": 1.0           // optional, bool-ish
  }
}
```

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
volume/pan/octave/pitch/fine/table_position/warp_amount; filter cutoff/
resonance/drive; envelope attack/decay/sustain/release; LFO rate; macro
value).

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

### Source side (partially decoded)

`source[0]` (the source ID) was decoded by clustering all mod routes across
the same 626-preset sample by ID and looking for internally-consistent,
correctly-sized blocks:

| Source family | Source IDs | Evidence |
|---|---|---|
| LFO 1-10 | `6-15` | Contiguous 10-ID block. Consistent bipolar rate across the block (25-39% of routes bipolar — matches LFOs being a bipolar-capable source), and total usage strictly decreases from id 6 (895 routes, 447/626 presets) down to id 15 (18 routes, 15/626 presets) — matching the "reach for LFO1 first" convention visible everywhere else in the factory content (e.g. Macro 1 used far more than Macro 8). |
| Macro 1-8 | `25-32` | Contiguous 8-ID block. Near-universal usage (544-586 of 626 presets per ID, i.e. 87-94%) — consistent with Serum's factory-content convention of wiring up all 8 macro knobs to something in almost every preset. Near-always unipolar (4-7% bipolar), consistent with macros being 0-100 knobs by convention. |

Both are `observed`-confidence (statistical clustering, not cross-checked
against Xfer's own source/docs the way the destination side was) but strong
enough that `serum-mcp` generates and reads back routes for them (see
`schema.MOD_SOURCE_IDS`, `generation/spec.py::ModRouteSpec`).

**Unresolved, but with a candidate hypothesis** (do NOT wire this into
generation — it's below our confidence bar, documented so a future
contributor doesn't start from zero): ids `1-5`, `16-24`, and `34+` remain
undecoded. Two more rounds of investigation were tried and didn't clear the
bar:

- *Binary string mining*: unlike `destModuleParamID`, no enum declaration or
  control-tag JSON entry tying a specific source name (`Velocity`, `Mod
  Wheel`, `Aftertouch`, `Pitch Bend`, `KeyTrack`, `Random` all appear as
  literal UI strings in the binary) to a specific `ModSlot.source` integer
  was found, despite targeted searches.
- *destModuleParamName distribution per source ID*: looking at exactly
  which parameter (not just which module type) each source ID most often
  targets gives suggestive, but not conclusive, signal. For example: id `1`
  most often targets `VoiceFilter.kParamFreq` and `Macro.kParamValue`; id
  `16` most often targets `Env.kParamDecay`/`Env.kParamAttack` (envelope
  *time* modulation is a classic velocity-sensitivity technique, which
  would suggest id 16 = Velocity rather than id 1); id `23` targets
  `Oscillator.kParamPan` disproportionately with a high bipolar rate (75%),
  consistent with a per-voice Random source used for pan humanization. None
  of this rises to the "contiguous block, internally consistent, matches a
  known count" standard that closed the LFO/Macro case — it's circumstantial
  at best, and in at least one place (id 16 vs id 1 for Velocity) two
  plausible readings of the same data actively disagree with each other.

If you can resolve any of this further — a MIDI Learn export, a Serum
factory-default XML/plist, an enum declaration in a newer plugin build, or
just more presets that isolate a single source ID unambiguously (e.g. a
preset where you, with the real Serum UI open, wire up exactly one known
source and inspect the resulting file) — see `CONTRIBUTING.md`. The
`(destModuleTypeString, destModuleParamID)` binary-string cross-validation
technique from §2 is reusable if a similar debug enum for mod sources turns
up in a future Serum build.

`subIndex` (`source[1]`) is unresolved for every source family — it's 0 in
the overwhelming majority of samples; a handful of source IDs (notably 6-9,
inside the LFO block) show varied non-zero subIndex values correlated with
other valid source IDs (16-32ish), suggestive of some kind of chained/
secondary modulation, but this wasn't pinned down further either.

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
folder), named by a content hash of the harmonic data so identical
definitions reuse one file instead of duplicating it.

**Known gap**: phase is not exposed — `synthesize_frame` treats every
harmonic amplitude as a real-valued (cosine-phase) FFT bin, so all
generated tables currently use one fixed phase relationship between
harmonics. Real-world waveform character (e.g. the audible difference
between a cosine-phase and sine-phase harmonic stack) that depends on
relative phase isn't reachable yet.
