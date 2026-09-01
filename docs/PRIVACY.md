# Privacy Policy

**Last updated: 2026-09-01**

`serum-mcp` is a local MCP server. It runs entirely on your own machine and
makes no network requests of any kind.

## Data collection

`serum-mcp` does not collect any data. It has no analytics, no telemetry, no
crash reporting, and no update-check mechanism. There is no external service
this project talks to -- the codebase contains no HTTP client, no socket
usage, and no API key of any kind (see the [source on
GitHub](https://github.com/Celian-mrc/serum-mcp)).

## Data usage and storage

All work happens through local file I/O:

- It reads `.SerumPreset`, `.wav`, and wavetable files that already exist on
  your machine (your Serum presets/tables folders, and any sample
  folder you point it at).
- It writes new or edited `.SerumPreset` files, and occasionally a
  synthesized wavetable `.wav`, to your configured Serum presets/tables
  folders (see `SERUM_PRESETS_PATH` / `SERUM_TABLES_PATH` in the README).

Everything it reads or writes stays on your filesystem, under your own
account, for as long as you keep those files. `serum-mcp` itself keeps no
separate copy, cache, log, or history of anything you generate.

## Third-party sharing

None. There is nothing to share -- no server-side component, no cloud
backend, and no third party this project sends data to.

## Data retention

Not applicable: `serum-mcp` does not retain anything itself. The only
persistent output is the preset/wavetable files it writes, which you own and
control exactly like any other file on your disk.

## Contact

Questions about this policy or the project: open an issue at
https://github.com/Celian-mrc/serum-mcp/issues.
