# serum-mcp

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Celian-mrc/serum-mcp/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)

**Generate, edit and save [Xfer Serum 2](https://xferrecords.com/products/serum-2) presets from a plain-English description — as an [MCP](https://modelcontextprotocol.io) server, so any MCP client (Claude Code, Claude Desktop, ...) can drive it directly.**

```
You:    generate a dark, evolving pad with a slow chorus
Claude: [builds a PresetSpec from your description, calls
         generate_preset(spec)]
        Wrote ~/Documents/Xfer/Serum 2 Presets/Presets/User/PD - Dark Evolving Chorus.SerumPreset

        Osc A: ON  octave=-1  volume=0.75  table_pos=42.0
        Filter 1: ON  type=lowpass_24  cutoff=0.32  resonance=18%
        Env 1: attack=0.8s  decay=2.5s  sustain=0.70  release=3.0s
        FX chain: FXChorus (wet=45%)
```

Open Serum in whatever DAW you use (FL Studio, Ableton, Bitwig, ...), load
the preset, done. `serum-mcp` never touches your DAW, never renders audio,
and never loads the Serum plugin itself — it reads and writes the
`.SerumPreset` file format directly.

## Why

Existing "AI Serum preset" tools are either closed-source SaaS products or
one-shot config-to-preset generators. `serum-mcp` is:

- **Open source**, MIT licensed.
- **Native to your agentic coding workflow** — it's an MCP server, not a
  separate web app. Ask for a sound the same way you'd ask for a code change.
- **Conversational and iterative** — `edit_preset` lets you refine an
  existing patch ("make it warmer", "add more resonance") instead of only
  generating from scratch.
- **Transparent about its own limits** — every parameter this tool knows
  about is documented with how confidently it was verified (see
  [`docs/PARAMETER_SCHEMA.md`](docs/PARAMETER_SCHEMA.md)), because Xfer
  doesn't publish this format and we don't pretend otherwise.

See [Prior art](#prior-art) for how this compares to
[Serum-Preset-Generator](https://github.com/Tdub206/Serum-Preset-Generator),
[SerumPresetGenerator](https://github.com/potatoTeto/SerumPresetGenerator),
and [Pounding Systems' AI preset generator](https://pounding.systems/products/ai-serum-preset-generator).

## Scope — what this is *not*

By design, and deliberately not planned for later:

- No MIDI generation or writing.
- No real-time DAW control, automation, or plugin scripting (no FL Studio
  MIDI scripting, no Ableton Remote Script, no ReaScript).
- No loading of the Serum plugin itself — this tool does not render or
  preview audio. Input is text, output is a `.SerumPreset` file.
- No DAW dependency anywhere in the pipeline. FL Studio is only where the
  author happens to open Serum afterwards; any DAW works identically.

A [V2 direction](#roadmap) — "reproduce this sound from an audio file" — is
kept in mind architecturally but not started.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). No API key of
any kind is required — see [How it works](#how-it-works) for why.

### Not comfortable with the command line? Let an LLM do it for you

Most people reaching for this tool are producers, not developers. If the
steps below look intimidating, paste this into Claude Desktop (or any LLM
assistant that has file/terminal access on your computer) instead of typing
any of it yourself:

```
Please set up the serum-mcp MCP server on this computer so I can use it
with my MCP client.

1. Install `uv` (a Python package manager) if not already installed --
   on Windows: run
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   on Mac/Linux: run `curl -LsSf https://astral.sh/uv/install.sh | sh`

2. Clone https://github.com/Celian-mrc/serum-mcp somewhere on this
   machine (or download it as a ZIP and extract it), then run `uv sync`
   inside that folder.

3. Find my Serum presets folder -- in Serum, the hamburger menu ->
   "Show Serum Presets folder" -> note the path ending in Presets/User
   (Presets\User on Windows).

4. Add serum-mcp as an MCP server in my client's config, pointing
   `--directory` at the folder from step 2 and setting
   SERUM_PRESETS_PATH to the path from step 3. If I'm on Claude Desktop
   for Windows, the config file is claude_desktop_config.json -- NOTE:
   if Claude Desktop was installed via the Microsoft Store, the real
   config file is NOT in the normal %APPDATA%\Claude location, it's
   under %LOCALAPPDATA%\Packages\Claude_<random id>\LocalCache\Roaming\Claude\
   -- search for claude_desktop_config.json across %LOCALAPPDATA% if the
   normal path doesn't have it or seems unused. If I'm on Claude Code,
   use `claude mcp add serum-mcp -- uv --directory <path> run serum-mcp`
   instead.

5. Tell me exactly what you did, then tell me to fully quit and restart
   my MCP client (not just close the window) for the change to take
   effect.

If you don't have filesystem/terminal access to do any of this, say so
clearly and walk me through the manual steps from serum-mcp's own README
instead.
```

Otherwise, do it yourself:

```bash
git clone https://github.com/Celian-mrc/serum-mcp
cd serum-mcp
uv sync
```

### Configure your Serum presets folder

Serum's user preset folder location varies by install — find yours via
Serum's hamburger menu → "Show Serum Presets folder" → the `Presets/User`
subfolder. Then set:

```bash
export SERUM_PRESETS_PATH="/path/to/Serum 2 Presets/Presets/User"
```

If unset, `serum-mcp` falls back to a couple of known default install
locations (see `src/serum_mcp/config.py`) before failing with a clear error
— it never silently guesses or hardcodes a path.

If you ask for a custom-synthesized wavetable (`custom_harmonics`) or a
wavetable sliced from one of your own audio files (`sample_source`, e.g.
"turn this drum one-shot into a wavetable" — see [How it
works](#how-it-works)), `serum-mcp` also needs Serum's **Tables** folder
(a sibling of `Presets/`) to write the generated `.wav` into. It's derived
automatically from `SERUM_PRESETS_PATH`; override with `SERUM_TABLES_PATH`
if your install doesn't follow the standard layout. Note `sample_source`
slices the file into a wavetable, it does not play the sample back
faithfully.

If you instead ask to keep a one-shot/sample recognizable (`sample_playback_source`,
e.g. "turn this drum hit into a preset" or "layer this vocal chop with a
synth pad"), `serum-mcp` uses Serum's actual sample-playback engine
(`SampleOsc`) and copies the file into Serum's **Samples** folder (also a
sibling of `Presets/`, derived automatically or overridden via
`SERUM_SAMPLES_PATH`). Only `.wav` is supported for this (confirmed working
live, despite every factory preset referencing `.flac` instead — see
`docs/PARAMETER_SCHEMA.md` §8). The sample plays back at its originally
recorded pitch/speed when **C5** is played — a fixed reference note, not
configurable. If the source file is stereo, its channels are gain-balanced
by default (`sample_center_pan`) to correct any left/right level bias in
the original recording (common — real one-shots are often mic'd slightly
off-center) without altering either channel's actual content.

Any of these (`custom_harmonics`, `sample_source`, `sample_playback_source`,
`granular_source`, `spectral_source`) write a file outside the `.SerumPreset`
itself — the same real Serum limitation as a wavetable hand-drawn in Serum's
own editor, not something this tool routes around. `generate_preset`/
`edit_preset` surface this: if the write depends on one of these files, the
returned path is followed by a note listing it, so you know to send that file
along too if you share the preset with someone else.

Optionally, set `SAMPLE_BANK_PATH` to the root of your own one-shot/drumkit
library (unrelated to Serum's own folders — this can point anywhere). With
it set, `list_sample_files()` can be called with no arguments and defaults
to browsing that folder, which lets the calling model proactively check
whether you have a fitting one-shot for a request even if you didn't
explicitly mention your sample bank. Not set by default, and nothing reads
your filesystem unless you configure this or point the model at a
directory yourself.

### Add to Claude Code

```bash
claude mcp add serum-mcp -- uv --directory /path/to/serum-mcp run serum-mcp
```

Or add manually to `.claude/settings.json` / `~/.claude.json`:

```json
{
  "mcpServers": {
    "serum-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/serum-mcp", "run", "serum-mcp"],
      "env": {
        "SERUM_PRESETS_PATH": "/path/to/Serum 2 Presets/Presets/User"
      }
    }
  }
}
```

### Add to Claude Desktop

Same shape, in Claude Desktop's `claude_desktop_config.json`
(Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "serum-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/serum-mcp", "run", "serum-mcp"],
      "env": {
        "SERUM_PRESETS_PATH": "/path/to/Serum 2 Presets/Presets/User"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `generate_preset(spec, subfolder=None)` | Build a new preset from a `PresetSpec` and write it to your Serum presets folder. `subfolder` (e.g. `"RAGE Bank"`) nests a themed set of presets together instead of writing them flat. |
| `edit_preset(preset_path, spec)` | Apply a partial `PresetSpec` update to an existing preset. Renames the file if `spec.name` changes (Serum's browser displays the filename, not internal metadata). |
| `list_parameters()` | Full documented parameter schema (names, ranges, units, enum values, confidence) as JSON. |
| `describe_preset(preset_path)` | Human-readable summary of a preset's current sound-shaping parameters. |
| `find_reference_presets(query, limit=8)` | Search Serum's Factory library plus your own installed banks by folder/filename keyword match — for grounding a genre/artist-style request ("dubstep bass", "in the style of Flume") in a real, already-designed preset instead of generating purely from parametric knowledge. Genre queries are expanded against a small curated keyword table bridging genre names to Serum's role-organized Factory folders. |
| `list_sample_files(directory=None)` | List audio files under a folder (e.g. a drumkit/sample bank) as JSON — path, name, size, and duration/sample rate/channels for `.wav` — so a specific file can be picked by name/folder context instead of guessed. Defaults to `SAMPLE_BANK_PATH` if `directory` is omitted. |
| `analyze_sample_file(path)` | Lightweight acoustic descriptors for one `.wav` one-shot as JSON — brightness, tonal/noisy texture, a gated pitch estimate, attack/sustain shape — for when filenames within a sample-bank category aren't descriptive enough on their own. Also surfaces `embedded_metadata` (root note, sample-accurate loop points) when the sample pack's creator embedded RIFF `inst`/`smpl` tags — not universal, empty when absent. |

You don't write `PresetSpec` JSON by hand — the calling model (Claude Code,
Claude Desktop, ...) builds it from your natural-language request using the
tool descriptions and `list_parameters()` as a guide, the same way it would
construct arguments for any other MCP tool.

## How it works

```
Prompt (natural language)
        │
        ▼
The calling model (Claude Code / Claude Desktop) translates the request
into a PresetSpec (generation/spec.py) itself -- no separate LLM call.
This server has no model of its own to call.
        │
        ▼
generate_preset(spec) / edit_preset(path, spec)   (MCP tool)
        │
        ▼
preset/mapping.py  ── merges the validated PresetSpec onto a base preset
        │              (fixtures/init_preset.SerumPreset for generation, the
        │              existing file's own state for edits), validating
        │              every value against preset/schema.py's ground-truth
        │              bounds before it touches anything
        ▼
preset/packer.py  ── encodes the result back into the real Serum 2 container
        │              format (XferJson header + zstd-compressed CBOR)
        ▼
Written to $SERUM_PRESETS_PATH as a real .SerumPreset file
```

Deliberately **no LLM call happens inside this server.** An earlier design
had `generate_preset` call the Claude API internally to turn free text into
a `PresetSpec` — but every MCP tool call is already made *by* an LLM-driven
client, so that second call was pure redundancy: an extra, separately-billed
API request on top of whatever you already pay for Claude Code/Desktop, to
do reasoning the calling model could do itself for free (from your
perspective) as part of the same turn. `PresetSpec` is schema-validated
twice regardless (once by Pydantic when the model calls the tool, once
against the raw parameter bounds on the way into the file), so nothing about
correctness was lost — only cost. Everything in an existing preset that
isn't part of this schema (arpeggiator, MIDI clips, GUI state, unresolved
mod matrix sources, ...) round-trips through edits completely untouched.

Full parameter documentation, including exactly how each bound was verified
(or wasn't): [`docs/PARAMETER_SCHEMA.md`](docs/PARAMETER_SCHEMA.md).

## Getting good results

`serum-mcp` has no sound-design opinion of its own — the model in your MCP
client does all of it, using this server's tools plus its own general
knowledge. A few things that noticeably change how well that goes:

- **Talk to it like you'd describe a sound to a producer**, not like you're
  filling out a form: genre, mood, role (bass/pad/lead/pluck/...), and — if
  you have one in mind — a reference artist or track.
- **Name a specific preset or pack you already like** if you want the result
  to lean toward a particular character ("give this the grain of my `<X>`
  preset"). `find_reference_presets` already searches your Factory library
  and any installed banks by keyword automatically, with no setup required —
  but naming something specific lets the model inspect its actual parameters
  via `describe_preset` instead of guessing from a folder/file name, which is
  a lot more precise.
- **You don't need to ask it to "study the MCP" first.** This server pushes
  its own detailed usage conventions to the calling model automatically as
  part of the MCP connection, and `list_parameters()` is what the model calls
  on its own whenever it needs exact ranges/enums before writing a spec.
  There's no separate analysis step for you to trigger.
- **Precise listening feedback is the real lever, not upfront analysis.** A
  documented convention doesn't guarantee it gets followed every single time
  — the most effective way to improve a result is to load it in Serum,
  listen, and describe concretely what's off ("the attack is too slow",
  "this reads as a pluck, not a flute", "there's no real breath/texture
  layer") rather than a general "I don't like it." A specific complaint is
  something the model can actually act on.
- **Always load the result in real Serum.** Nothing in this pipeline renders
  or listens to audio — the test suite and `describe_preset` confirm a file
  is *structurally* valid, never that it *sounds* right. Test-listening is
  the only way to actually judge a preset.
- Asking for a themed **bank** of presets defaults to melodic/textural roles
  (lead, pluck, pad, keys, arp, ...) — mention bass or FX/riser presets
  explicitly if you want those included too.
- Result quality tracks the capability of whichever model your MCP client is
  running — a stronger model follows this server's conventions more
  reliably.

### Recommended: reinforce this in your client's own project instructions

This server already pushes detailed usage guidance to the calling model
automatically (see above) — but a documented convention living inside a
large system prompt doesn't guarantee it gets applied on every single
generation. If your MCP client supports per-project custom instructions
(Claude Desktop's Projects, for example), pasting this block in noticeably
improves consistency, especially for anything more ambitious than a single
one-off preset:

```
When generating or editing Serum presets via serum-mcp, aim for real
depth, not a minimal valid spec:

- Call list_parameters() to confirm valid field names/ranges before
  generating. The top-level mod-matrix field is `mod_routes` (a list of
  {source, destination, amount, bipolar}) -- not `mod_matrix` or any
  other variant.
- Name and use several of the 8 available macros per preset (not just
  1-2), with real fanout -- some macros driving 2+ destinations at once,
  some starting near 0% as performer "bring-in" controls.
- Build out a real mod matrix -- 10+ routes per preset touching
  velocity/key_track/envelope/LFO/macro sources, not just 2-3 obvious
  ones.
- Whenever an oscillator uses a curated wavetable at a meaningful
  table_position, or a multi-frame custom_harmonics list, wire an actual
  mod route (envelope/LFO/macro) to table_position. A static
  table_position on a multi-frame/curated table wastes the point of it
  -- the sound should genuinely evolve/morph over the note.
- Before synthesizing an instrument-named role (guitar, piano, violin,
  choir, strings, bell/mallet...), check multisample_source's curated
  list first (brass_french_horn, choir_ah, epiano_suitcase, guitar_ac,
  mallet_balafon, piano_grand, strings_full, synth_pad_superjx,
  synth_sid, violins) -- a real sample reads far more convincing than a
  synthesized approximation for these roles.
- Before generating from scratch for any genre/artist/style-named
  request, call find_reference_presets(query) to search the real Serum
  Factory library and any installed third-party banks -- ground the
  design in an actual reference via describe_preset() rather than
  working purely from parametric knowledge. For a themed request, also
  do a quick web search on that genre/artist's real production
  character.
- For a themed bank ("make me a bank of X"), default to melodic/textural
  roles only (lead, pluck, pad, keys, arp) -- don't add bass or FX/riser
  presets unless explicitly asked for.
- If I mention a specific preset or pack I already like, use
  describe_preset() on it directly to ground the new design in its
  actual parameters, rather than guessing from its name alone.

Always remind me to load the result in real Serum to check it sounds
right -- nothing in this pipeline renders or listens to audio, so
describe_preset()/tests only confirm the file is structurally valid,
never that it sounds correct.
```

## Prior art

- [Serum-Preset-Generator](https://github.com/Tdub206/Serum-Preset-Generator) — Python API, generates from a JSON config you write by hand.
- [SerumPresetGenerator](https://github.com/potatoTeto/SerumPresetGenerator) — clean-room C# library.
- [Pounding Systems' AI Serum preset generator](https://pounding.systems/products/ai-serum-preset-generator) — closed-source, paid SaaS.

`serum-mcp`'s difference isn't better AI — it's distribution (an MCP tool,
not a separate app), editability (iterate on an existing patch, not just
one-shot generation), and honesty about format coverage (see
[Known gaps](docs/PARAMETER_SCHEMA.md#5-known-gaps-and-open-questions)).

## Disclaimer

- **Not affiliated with, endorsed by, or supported by Xfer Records.**
  "Serum" is a trademark of Xfer Records; this is an independent,
  community-driven interoperability project.
- The `.SerumPreset` file format is **not officially documented**. Everything
  this tool knows about it comes from community reverse-engineering plus
  empirical verification against a real Serum 2 install (see
  [`docs/PARAMETER_SCHEMA.md`](docs/PARAMETER_SCHEMA.md) for methodology and
  confidence levels per parameter).
- **This can and likely will break** on future Serum updates that change the
  file format or parameter set. If it breaks for you, please open an issue —
  ideally with a preset exported from the new version.
- Generated presets are only as good as the calling model's sound-design
  judgment and this project's parameter coverage (currently: oscillators,
  filters, envelopes, macros, the full mod matrix, the arpeggiator, and all 16
  effect types, including the 3 frequency/channel-band splitters — see [Known
  gaps](docs/PARAMETER_SCHEMA.md#5-known-gaps-and-open-questions) for the
  handful of narrower open questions that remain).

## Roadmap

- **V1** (this repo, current): generate from a description, edit an existing
  preset by instruction, write directly to your Serum presets folder,
  documented and tested parameter schema.
- **V2** (not started): "reproduce this sound" from an audio file, via audio
  rendering (e.g. [`spotify/pedalboard`](https://github.com/spotify/pedalboard))
  and spectral comparison. The current architecture deliberately avoids
  choices that would foreclose this later.

## Privacy Policy

See [`docs/PRIVACY.md`](docs/PRIVACY.md). Short version: `serum-mcp` makes no
network requests and collects no data -- everything it does is local file
I/O against your own Serum presets/tables folders.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) — filling in a documented gap in
`docs/PARAMETER_SCHEMA.md` is one of the most valuable things you can do,
even without writing code.

## License

[MIT](LICENSE)
