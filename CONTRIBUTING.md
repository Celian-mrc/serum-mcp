# Contributing to serum-mcp

Thanks for considering contributing! This project reverse-engineers and
targets an undocumented, third-party file format, so contributions that
expand or correct our understanding of it are just as valuable as code.

## Ways to help

- **Fill in a documented gap.** `docs/PARAMETER_SCHEMA.md` §5 lists known
  unknowns — the remaining mod matrix `source` IDs (Envelope/Velocity/Mod
  Wheel/Aftertouch/Pitch Bend/Key Track/Random are still unresolved, though
  LFO and Macro sources were decoded — see §6 for the method, which is
  reusable), the filter cutoff Hz curve, unmodeled oscillator engines
  (granular/multisample/spectral/sample), LFO/envelope curve shapes, and the
  3 band-splitter FX types (`FXSplit`/`FXSplit3`/`FXSplitMS`), which need a
  recursive FX schema rather than a flat one. Any of these, backed by
  evidence (see "Evidence standard" below), is welcome.
- **Add parameter coverage.** More of Serum 2's ~2,600 VST3 parameters could
  be mapped into `src/serum_mcp/preset/schema.py` and exposed through
  `generation/spec.py`.
- **Support another Xfer synth.** The container format
  (`serum_mcp.preset.packer`) is Serum-2-shaped but not Serum-2-specific;
  a differently-schemad sibling package for another Xfer product is a
  reasonable extension.
- **Improve generation quality.** This lives in `server.py`'s tool
  instructions (the guidance the calling model reads before building a
  `PresetSpec`) and in `generation/spec.py`'s semantic vocabulary — there's
  no prompt-engineering-against-our-own-LLM-call to do, since this server
  doesn't make one (see the README's "How it works").
- **Bug reports.** Especially "this loads in Serum but sounds wrong" or
  "Serum rejected this file" — both are regressions in our understanding of
  the format, not just code bugs.

## Evidence standard

Because Xfer doesn't document this format, every parameter claim in this
codebase carries a `confidence` level (`confirmed` / `observed` /
`uncertain` — see `ParamDef` in `schema.py`). When contributing a new or
corrected parameter:

1. Prefer **confirming** over guessing: cross-reference against a real
   Serum 2 install if you have one (e.g. the VST3 parameter dump technique
   described in `docs/PARAMETER_SCHEMA.md` §2).
2. If you can only observe it empirically (e.g. sampling factory presets),
   say so and mark it `observed`, not `confirmed`.
3. Update `docs/PARAMETER_SCHEMA.md` alongside `schema.py` — they should
   never drift apart.

Please don't submit parameter values you're not confident about without
flagging the uncertainty; a wrong `confirmed` claim is worse than an honest
`uncertain` one.

## Development setup

```bash
git clone https://github.com/Celian-mrc/serum-mcp
cd serum-mcp
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

No Serum installation, DAW, or API key of any kind is required to run the
test suite — there is no LLM call anywhere in this package (see the
README's "How it works" for why: sound-design reasoning happens in the
calling MCP client, not in this server). Tests work against the committed
`fixtures/init_preset.SerumPreset` and synthetic payloads. If you do have
Serum 2 installed and want to validate real presets,
`serum_mcp.preset.packer.unpack_file` / `pack_file` work on any
`.SerumPreset` on disk.

## Pull requests

- Keep PRs focused — one gap filled or one feature at a time.
- Add or update tests for anything you change in `preset/` or `generation/`.
- Run `ruff check .`, `ruff format .` and `pytest` before opening a PR (CI
  runs the same checks).
- If you're touching the parameter schema, update
  `docs/PARAMETER_SCHEMA.md` in the same PR.

## Out of scope (see project README for the full list)

MIDI generation/writing, real-time DAW control or plugin automation, and
loading the Serum plugin itself to render/preview audio are explicitly out
of scope for this project (see the README's Disclaimer / Scope section).
PRs adding these will likely be declined — please open an issue to discuss
first if you think an exception is warranted.
