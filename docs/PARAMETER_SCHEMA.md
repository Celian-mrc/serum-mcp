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
dicts, conceptually-boolean fields (`kParamEnable`, `kParamBipolar`,
`kParamMonoToggle`, ...) are stored as CBOR **doubles** (`1.0`/`0.0`),
*never* as a native CBOR boolean, even though they only ever hold 0 or 1.
Writing a real CBOR boolean there (e.g. naively serializing a Python `bool`)
produces a structurally different wire type — confirmed to reliably crash
Serum's native loader (FL Studio closed ~2 seconds after selecting a preset
built this way, no error dialog). `serum_mcp.preset.validator.validate_params`
normalizes this automatically for every "bool"-kind field it validates, so
nothing above that layer needs to think about it — but if you're writing
CBOR by hand outside this codebase, don't assume Python's natural bool → CBOR
bool mapping is safe here. Note this is scoped to `plainParams` fields
specifically: a few *top-level* flags outside `plainParams` (`mpeEnabled`,
`lockOversampling`, `lockTuning`) genuinely are native CBOR booleans in real
presets — don't "fix" those.

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
special-cases slot 0 rather than encoding it in the shared param table.

Each slot's sound source is one of 5 engines, keyed as `WTOsc{i}`,
`GranularOsc{i}`, `MultiSampleOsc{i}`, `SampleOsc{i}`, `SpectralOsc{i}` inside
`Oscillator{i}`. **Only `WTOsc` (the classic wavetable engine) is modeled**
in V1 — it's the default engine and the one every factory bass/lead/pad
preset we sampled that wasn't a multisample instrument used. Granular,
multisample, spectral and raw sample playback exist in the format and
round-trip fine, but `serum-mcp` cannot currently generate or target them.

### Filters

2 slots (`VoiceFilter0`/`VoiceFilter1` = Filter 1/2). **Both off by default**
(confirmed). The raw `kParamType` enum has 66 observed values (ladder, SVF,
comb, phaser-as-filter, formant, "Scream" distortion-filter hybrids, etc.);
`SIMPLE_FILTER_TYPES` in `schema.py` curates 11 of them with unambiguous
names (`lowpass_12`, `lowpass_24`, `highpass_12`, ...) for the LLM mapper to
target in V1. The raw enum remains fully valid for `edit_preset` /
`list_parameters` consumers who want the rest.

`kParamFreq` (cutoff) is the biggest known gap: it's a normalized `0.0..1.0`
value, and we have exactly **one** calibration point (`0.5 ≈ 425 Hz` at
default resonance, from the VST3 dump) — not enough to reconstruct the true
Hz curve (believed logarithmic, roughly 9 Hz–19 kHz). Treat `cutoff` as a
perceptual position, not a literal frequency, until someone samples enough
points to fit the curve.

### Envelopes

4 slots (`Env0..3`), all identical schema. Env 1 (`Env0`) is *conventionally*
the amp envelope in factory content, but nothing in the format enforces
that — it's just how presets are usually built.

### LFOs

10 slots (`LFO0..9`). Only `kParamRate`/`kParamMode`/basic timing are
modeled. Free-hand curve-drawn LFO shapes (`curveData`: `xVals`/`yVals`/
`curveVals`) exist and round-trip, but generating them is out of scope for
V1 (no natural-language mapping for "draw this LFO shape" yet).

### Macros & Global

8 macros (`Macro0..7`, each `{name, plainParams.kParamValue}`). `Global0`
covers master volume (confirmed default `0.5` = -9dB), mono toggle,
portamento and voice count; a handful of rarer global params (tuning, MPE
bend range, FX bus routing) are documented in `schema.py` but not yet wired
into generation.

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
volume/pan/octave/pitch/fine; filter cutoff/resonance/drive; envelope
attack/decay/sustain/release).

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

**Unresolved**: ids `1-5` (low usage relative to Macro, low bipolar rate —
plausibly Envelope 1-4 plus one more, but id 3 is used almost as often as
the Macro block while ids 2/5 are used an order of magnitude less, which
doesn't cleanly fit "4 envelopes used somewhat evenly"), ids `16-24`
(scattered usage and bipolar rates, no clean block), and ids `34+` (rare,
small samples, high noise). These are plausibly Velocity, Mod Wheel,
Aftertouch, Pitch Bend, Key Track, and Random/S&H, based on their names
appearing in the plugin binary's strings (`Velocity`, `Mod Wheel`,
`Aftertouch`, `Pitch Bend`, `KeyTrack`, `Random` all appear as literal UI
strings), but no enum declaration tying a specific string to a specific
`ModSlot.source` integer was found. `subIndex` (`source[1]`) is unresolved
for every source family — it's 0 in the overwhelming majority of samples;
a handful of source IDs (notably 6-9) show varied non-zero subIndex values
correlated with other valid source IDs (16-32ish), suggestive of some kind
of chained/secondary modulation, but this wasn't pinned down further.

If you can resolve any of this further — a MIDI Learn export, a Serum
factory-default XML/plist, or just more presets that isolate a single
source ID in an unambiguous way — see `CONTRIBUTING.md`.
