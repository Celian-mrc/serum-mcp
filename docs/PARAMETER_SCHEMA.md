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
| `ModSlot0`..`ModSlot63` | the 64-slot mod matrix | Structure only, see §6 |
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
`plainParams` dict specific to that type. 9 of the 16 are modeled with full
param schemas in V1 (`FXDistortion`, `FXChorus`, `FXFlanger`, `FXPhaser`,
`FXDelay`, `FXReverb`, `FXComp`, `FXEQ`, `FXFilter`); `FXBode` (frequency
shifter), `FXHyperD` ("hyper dimension" widener), `FXConv` (convolution/IR),
`FXUtils`, and the `FXSplit*` band-splitter variants are cataloged (types
enumerated) but their parameters are not yet schema'd.

We also confirmed empirically that an FX entry's `destModuleID` in the mod
matrix encodes *which rack* an FX unit lives in: `0-11` for rack 0 slots,
`100-111` for rack 1, `200-211` for rack 2 (e.g. `FXComp` destinations
`0, 1, ..., 9, 14` alongside `101, 102` and `205 `in our sample).

## 5. Known gaps and open questions

These are the honest uncertainties, ranked roughly by how much they'd
improve generation quality if resolved:

1. **Mod matrix `source` encoding is not decoded.** `ModSlot{n}.source` is a
   `[sourceId, subIndex]` pair. We confirmed the matrix's *destination* side
   completely (`destModuleTypeString` + `destModuleParamName` + `kParamAmount`
   / `kParamBipolar`), but the *source* side — which integer ID means "LFO 3"
   vs "Envelope 2" vs "Velocity" vs "Mod Wheel" — was not conclusively
   matched to a name list. ~40 distinct source IDs were observed (source `1`
   appears in nearly every sampled preset, suggesting it's a common default
   like velocity or a template-inherited route, but this is a guess). Until
   this is solved, `serum-mcp` treats `ModSlot` entries as structurally
   understood but semantically opaque — it can round-trip existing mod
   routes but the LLM mapper does not generate new ones in V1.
2. **Filter cutoff Hz curve** (§4, Filters) — only one calibration point.
3. **Unmodeled oscillator engines** — Granular/MultiSample/Spectral/Sample.
   These are common enough (GranularOsc/MultiSampleOsc/SpectralOsc appeared
   in 5-15% of sampled presets each) that a V1.1 covering at least
   MultiSampleOsc (used for realistic instrument patches) would be valuable.
4. **LFO curve shapes** (`curveData`) and **free-drawn envelope curves** are
   unmodeled — Serum 2's point-based custom curve editor data.
5. **5 of 16 FX types lack full param schemas** (`FXBode`, `FXHyperD`,
   `FXConv`, `FXUtils`, `FXSplit`/`FXSplit3`/`FXSplitMS`) — see §4.
6. Several numeric ranges are marked `uncertain` in `schema.py` (e.g. unison
   voice count ceiling, LFO/Chorus/Delay times where only normalized values
   were observed without a confirmed Hz/ms curve) — these are *observed*
   ranges from the sample, which may not be the true engine-enforced bounds.

None of these block V1's stated goal (text description → valid, loadable
`.SerumPreset` covering oscillators/filters/envelopes/macros/core FX) — they
bound what V1 can *express*, not whether what it writes is valid.

## 6. Mod matrix structure (confirmed parts)

Each `ModSlot{n}` (`n` in `0..63`):

```jsonc
{
  "destModuleID": 0,               // which instance (see per-type ID ranges below)
  "destModuleParamID": 3,          // internal numeric param index
  "destModuleParamName": "kParamFreq",
  "destModuleTypeString": "VoiceFilter",
  "source": [4, 0],                // NOT decoded -- see gap #1 above
  "plainParams": {
    "kParamAmount": 53.2,          // -100..100
    "kParamBipolar": 1.0           // optional, bool-ish
  }
}
```

`destModuleID` ranges observed per `destModuleTypeString` (confirms module
instance counts independently of §3): `Oscillator` 0-4, `VoiceFilter` 0-1,
`Env` 0-3, `Macro` 0-7, `LFO` 0-7 (0-9 expected, only 0-7 appeared in our
200-preset mod-matrix sample), `Global`/`Arp`/`VoicePanel`/`RetriggerState` 0
only, `RoutingSlot` 0-6, `LFOPointModBus` 0-14. FX destinations use the
rack-encoded IDs described in §4.
