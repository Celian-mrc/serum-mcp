# serum-mcp

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Celian-mrc/serum-mcp/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)

**Generate, edit and save [Xfer Serum 2](https://xferrecords.com/products/serum-2) presets from a plain-English description — as an [MCP](https://modelcontextprotocol.io) server, so any MCP client (Claude Code, Claude Desktop, ...) can drive it directly.**

```
You:    generate a dark, evolving pad with a slow chorus
Claude: [calls generate_preset("a dark, evolving pad with a slow chorus")]
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

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Celian-mrc/serum-mcp
cd serum-mcp
uv sync
```

You'll need an [Anthropic API key](https://console.anthropic.com/) for the
LLM-backed generation/editing tools (`list_parameters` and `describe_preset`
work without one).

### Configure your Serum presets folder

Serum's user preset folder location varies by install — find yours via
Serum's hamburger menu → "Show Serum Presets folder" → the `Presets/User`
subfolder. Then set:

```bash
export SERUM_PRESETS_PATH="/path/to/Serum 2 Presets/Presets/User"
export ANTHROPIC_API_KEY="sk-ant-..."
```

If unset, `serum-mcp` falls back to a couple of known default install
locations (see `src/serum_mcp/config.py`) before failing with a clear error
— it never silently guesses or hardcodes a path.

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
        "SERUM_PRESETS_PATH": "/path/to/Serum 2 Presets/Presets/User",
        "ANTHROPIC_API_KEY": "sk-ant-..."
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
        "SERUM_PRESETS_PATH": "/path/to/Serum 2 Presets/Presets/User",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `generate_preset(description)` | Generate a new preset from a text description; writes it to your Serum presets folder. |
| `edit_preset(preset_path, instruction)` | Apply a natural-language edit to an existing preset, in place. |
| `list_parameters()` | Full documented parameter schema (names, ranges, units, enum values, confidence) as JSON. |
| `describe_preset(preset_path)` | Human-readable summary of a preset's current sound-shaping parameters. |

## How it works

```
Prompt (natural language)
        │
        ▼
generate_preset / edit_preset  (MCP tool)
        │
        ▼
generation/llm_mapper.py  ── calls the Claude API with the parameter schema
        │                    in context, constrained via tool-use to emit a
        │                    PresetSpec (generation/spec.py) — friendly field
        │                    names, ranges that mirror preset/schema.py exactly
        ▼
preset/mapping.py  ── merges the validated PresetSpec onto a base preset
        │              (fixtures/init_preset.SerumPreset for generation, the
        │              existing file's own state for edits), re-validating
        │              every value against preset/schema.py's ground-truth
        │              bounds before it touches anything
        ▼
preset/packer.py  ── encodes the result back into the real Serum 2 container
        │              format (XferJson header + zstd-compressed CBOR)
        ▼
Written to $SERUM_PRESETS_PATH as a real .SerumPreset file
```

The LLM never emits raw binary or touches the file format directly — it
only fills in the semantic `PresetSpec`, which is schema-validated twice
(once by Pydantic on the way out of the LLM call, once against the raw
parameter bounds on the way into the file). Everything in an existing
preset that isn't part of this schema (arpeggiator, MIDI clips, GUI state,
mod matrix routing, ...) round-trips through edits completely untouched.

Full parameter documentation, including exactly how each bound was verified
(or wasn't): [`docs/PARAMETER_SCHEMA.md`](docs/PARAMETER_SCHEMA.md).

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
- Generated presets are only as good as the underlying LLM's sound-design
  judgment and this project's parameter coverage (currently: oscillators,
  filters, envelopes, macros, and 9 of 16 effect types — see
  [Known gaps](docs/PARAMETER_SCHEMA.md#5-known-gaps-and-open-questions)).

## Roadmap

- **V1** (this repo, current): generate from a description, edit an existing
  preset by instruction, write directly to your Serum presets folder,
  documented and tested parameter schema.
- **V2** (not started): "reproduce this sound" from an audio file, via audio
  rendering (e.g. [`spotify/pedalboard`](https://github.com/spotify/pedalboard))
  and spectral comparison. The current architecture deliberately avoids
  choices that would foreclose this later.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) — filling in a documented gap in
`docs/PARAMETER_SCHEMA.md` is one of the most valuable things you can do,
even without writing code.

## License

[MIT](LICENSE)
