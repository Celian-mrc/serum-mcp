---
name: serum-sound-design
description: Design Xfer Serum 2 presets and themed preset banks from plain-language requests using the open-source serum-mcp MCP server. Use when the user asks for a Serum preset, a sound ("dark pad", "drill 808", "Rhodes keys"), a preset bank for a genre or artist, or wants to tweak an existing .SerumPreset ("make it warmer", "more movement"). Requires the serum-mcp server (free, MIT, https://github.com/Celian-mrc/serum-mcp) and a Serum 2 install.
---

# Serum sound design with serum-mcp

serum-mcp writes real `.SerumPreset` files straight into the user's Serum
presets folder. It has no model of its own: **you** turn the request into a
`PresetSpec`, the server validates and writes it. It never renders audio, so
you can't hear the result. Good presets come from following the rules below
and from studying real reference presets, not from guessing.

## 0. Check the server is available

Look for the tools `generate_preset`, `edit_preset`, `describe_preset`,
`list_parameters`, `find_reference_presets`, `list_sample_files`,
`analyze_sample_file`.

If they are missing, stop and tell the user that this skill needs the
serum-mcp server. Point them to the install section of
https://github.com/Celian-mrc/serum-mcp. They need:
- Python 3.11+ and `uv`;
- `uv sync` in the cloned repo;
- an MCP entry with `SERUM_PRESETS_PATH` set to their `Serum 2 Presets/Presets/User` folder.

Don't invent preset files by hand. The format is binary and undocumented.

## 1. Understand the request

Pin down three things:
- **role**: pad, lead, pluck, keys, bass, 808, arp, bell, texture, FX;
- **character**: dark/bright, static/evolving, clean/dirty, wide/mono;
- **context**: genre, artist, tempo feel.

If the user names a genre, artist or style, research it on the web before
designing. Find the signature sounds, the typical processing, and what that
genre avoids. A drill bank and a future-bass bank should not share an FX
template.

For a *bank* (several presets), only include the roles the user asked for.
Don't add basses or FX "to complete the set" unless they asked.

## 2. Study real references before writing a spec

- Call `find_reference_presets("<role> <character>")`. Then call
  `describe_preset` on the 2–3 closest hits (factory or user presets).
- Use them to set a **complexity floor**: how many oscillators, LFOs and
  mod routes, which macros, how long the FX chain is. Generated presets tend
  to be thinner than hand-made ones. Match or exceed the references.
- Call `list_parameters()` whenever you're unsure of a range or enum value.
  Invalid enum names (a distortion mode that doesn't exist, a reverb width
  above its max) are rejected.

## 3. Design rules that make the difference

**Sources**
- Give every active oscillator a **different wavetable**. Same-table
  layers sound thin.
- `wavetable` accepts real Tables-relative paths, not just the curated
  names. Examples: `S2 Tables/Digital/RMrk1.wav` (Rhodes),
  `S2 Tables/Digital/Wuuurli.wav`, `S2 Tables/Digital/Braids Bell Pluck.wav`,
  `Vowel/DudaChoir.wav` (choir), `S2 Tables/Digital/Brass Stab.wav`.
  When the request names an instrument, try a matching real table first.
- For bells and mallets, consider a real multisample (`multisample_source`),
  e.g. `mallet_balafon`, layered with a wavetable. Some multisamples sound
  an octave off. Check the octave and correct it with `octave`.
- A preset built on one special technique (multisample, custom harmonics,
  sample playback) still usually wants a second layer.
- Wind and flute sounds need a filtered noise layer for breath. A single
  wavetable can't produce it.

**Movement**
- A multi-frame wavetable without a mod route to `table_position` is
  static. If you chose an evolving table, modulate its position.
- Pads want several LFOs at different slow rates (filter, table position,
  pan). Don't avoid LFOs. Never set an LFO `rate` to 0 to mean "frozen":
  that value is dropped, so don't rely on it.
- Only route modulation to oscillators that are **enabled**. A route to a
  disabled oscillator does nothing, with no warning.
- With a bipolar source and a decaying envelope, the sweep can go the
  opposite way from what you expect. Check the sign of the amount.
- Arpeggiators are a real tool when the genre uses them. Name those
  presets `ARP - …`.

**Macros**
- Assign and name **several** of the 8 macros (e.g. TONE, SPACE, MOTION,
  DIRT). Each one should drive 2+ meaningful destinations.
- The preset must sound **complete with every macro at its default**.
  Never leave a layer at volume 0 for a macro to "unlock".

**Processing**
- Match FX to the genre. Dark styles want EQ cuts, reverb and delay, with
  little distortion on non-bass roles.
- Mono + legato + portamento gives 808 glides: overlapping notes slide.

**Naming**
- Prefix by role, e.g. `PD - `, `KY - `, `PL - `, `LD - `, `BA - `, `BL - `,
  `ARP - `.
- Save a bank in its own `subfolder`.

## 4. Loudness: the most common complaint

Presets built on one-shot samples often come out **much quieter** than a
plain Serum saw (about -18 dBFS RMS). Oscillator and master volume both
max out at 1.0.
- For sample-based presets, end the FX chain with a clean gain stage:
  `FXComp` with threshold 1.0, ratio 1.0 and makeup above 1. Makeup 2 is
  about +6 dB, makeup 4 about +12 dB. Put it **last** so earlier FX indices
  used by mod routes don't shift.
- Makeup can't go below 1. To turn a preset *down*, lower the oscillator
  volumes instead.
- Keep levels consistent across a bank, so no preset is noticeably quieter
  than the others.

## 5. Generate, report, iterate

1. Call `generate_preset(spec, subfolder=...)`.
2. Show the returned summary to the user. If the result says the preset
   depends on extra files (a generated wavetable or a copied sample), say
   so: they must share those files along with the preset.
3. For tweaks, use `edit_preset(path, partial_spec)` rather than starting
   over. It changes only what you pass. To remove a mod route, send it again
   with `amount=0`. Then call `describe_preset` to confirm the change landed.
4. Before calling it done, review the bank as a whole. Look for presets that
   repeat each other, or that repeat banks you made earlier (same macro
   names, same recipe).
5. Ask the user to load the preset in Serum and listen. You haven't heard
   it, so don't claim it "sounds" a certain way. Describe what you built.

## Using the user's own samples

If the user mentions their drum kits or sample library, use
`list_sample_files` and `analyze_sample_file`.
- `sample_playback_source` plays the file back recognisably. It plays at
  its original pitch on C5.
- `sample_source` slices the file into a wavetable instead.
