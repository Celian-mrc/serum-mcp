# Sound design reference: patterns from a real professional bank

Derived by statistically analyzing all 180 presets in **Unmute — "Places For
Serum 2"** (a real commercial pack, ambient/emotional style), broken down by
role category (parsed from each preset's `UN_PLACES_<CATEGORY>_<Name>`
filename). Not a style to copy verbatim — a data point on what a
professionally-built preset of a given role actually looks like
structurally, to use as a starting point instead of guessing from scratch.

Method: `extract_spec` on every preset, aggregated per category. Ranges are
`min..max (median)` across that category's presets. Categories with very few
presets (DR n=6, FX n=4, STR n=3, GTR n=2) are noted but too small to trust
statistically — treat as anecdotal, not a pattern.

## Universal findings (true across every category)

- **`FXComp` and `FXEQ` are the two most-used FX types everywhere**, usually
  by a wide margin over reverb/delay/distortion — often multiple compressor/
  EQ stages per preset. The backbone of these FX chains is utility/glue
  processing (compression, EQ correction), not stacked "obvious" character
  effects. A preset with only a reverb+delay and no comp/EQ is missing what
  actually anchors these chains.
- **Moog-style lowpass dominates** (`moog_lowpass_12`/`MgL12`, and the
  uncurated `MgL18`) as the single most common filter type in every
  category.
- **Modulation is often macro-driven, not LFO-driven**, except in
  pad/chord/arp roles (see below) — many of these presets are built for
  live performance control via mapped macros, not just a fixed static
  sound. `macro -> env`/`macro -> fx`/`macro -> oscillator` routes are
  extremely common; don't treat mod_routes as purely a "subtle movement"
  feature — a macro wired to sweep the filter cutoff or fade an FX wet is
  a first-class, common design choice, not an edge case.
- Real FX chains commonly run 7-16 units total (see
  `server.py`'s generation guidance) — don't self-limit to 2-4.

## Per-role starting points

### BA (bass, n=26)
- **Mono, almost always** (25/26).
- Envelope: attack ~4ms (fast), release ~45ms (short) — a **held, punchy**
  tone, not a pluck. Sustain high (median 0.84).
- Filter: `moog_lowpass_12` most common, resonance **low** (median 7.2,
  the lowest of any category), drive **moderate-high** (median 13.8 — some
  grit is normal for bass).
- 2 oscillators typical. `fm` warp dominant.
- Mod routes lean `macro -> oscillator`/`macro -> env` over LFO.

### PL (pluck, n=24)
- Envelope: attack ~6ms, decay ~232ms, **sustain is 0 in the median** — a
  true decaying pluck, not a held note. This is the single clearest
  role-defining signal in the whole dataset.
- `bend` warp mode most common (not `fm` — a real difference from bass/
  chords/synth roles).
- Filter: `moog_lowpass_12` dominant, resonance moderate (median 10).
- Mod routes lean `macro -> env` (macro controlling decay/release feel)
  then `macro -> fx`.

### LD (lead, n=22)
- Mostly mono (20/22).
- Envelope: attack ~26ms, decay/release longer than PL (median 1.08s/0.38s)
  and moderate sustain (0.74) — sustained melodic voice, not a pluck.
- `bend` warp most common.
- Top mod route: `macro -> fx` (macro-controlled effect intensity), then
  `lfo -> oscillator` (vibrato/movement).

### PD (pad, n=12, smaller sample)
- Envelope: attack **long** (median 664ms), decay/release long (median
  1.75s/1.1s) — matches expectation exactly.
- 3 oscillators typical (8/12). `fm` warp most common.
- Top mod route: `lfo -> oscillator` (continuous evolving movement, not
  macro-driven like bass/lead).

### CH (chords/keys, n=23)
- **100% polyphonic** (0/23 mono).
- 2 filters active in 19/23 presets (richer layering than most other
  roles). 3 oscillators most common (14/23).
- `fm` warp dominant.
- Top mod route: `lfo -> oscillator`, close behind `macro -> oscillator`.

### SY (synth, n=28, largest category)
- Mix of 2-3 oscillators. Decay longer than average (median 0.81s).
- `fm` warp dominant. Heaviest and most evenly-spread macro usage across
  fx/env/oscillator/filter of any category — the most "built for live
  tweaking" role.

### ARP (arp, n=16)
- Mostly polyphonic (12/16) despite the role name.
- Short attack/release. `fm` warp dominant.
- Top mod route: `lfo -> oscillator`.

### SEQ (sequence, n=14)
- Very short attack (median 1ms), long decay/sustain held near max — built
  to be gated/retriggered rhythmically rather than shaped by its own
  envelope.
- By far the heaviest `lfo -> oscillator` usage of any category (median
  route count for that pair alone is high) — strong rhythmic pitch/timbre
  modulation is a defining trait here.

## Known ceiling on replicating this bank exactly

50% of Unmute's presets (90/180) use `FXSplit`/`FXSplit3`/`FXSplitMS`
(parallel/multiband FX routing) — not yet modeled in `FxUnitSpec`, so this
project can read these presets without crashing but can't generate that
specific technique itself. Treat the FX-chain patterns above as what's
achievable with a flat, serial chain; the real bank likely leans on
multiband processing for some of its polish beyond what's captured here.
