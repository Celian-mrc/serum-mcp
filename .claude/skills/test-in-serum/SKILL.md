---
name: test-in-serum
description: Run the pre-real-Serum-test checklist on one or more .SerumPreset files -- automated CBOR wire-type scan plus a human-readable summary -- then hand off to the user for the real load-it-in-Serum test. Use this after any generate_preset/edit_preset call on serum-mcp, or whenever a preset file needs to be verified before asking the user to check it in FL Studio/Serum. Also relevant when serum-mcp source code was just changed and needs live testing.
---

# Test a serum-mcp preset before asking the user to load it

This project's own hard-won lesson (see `docs/PARAMETER_SCHEMA.md` and
`CONTRIBUTING.md`): unit tests and round-trip checks are **not sufficient**
to prove a generated preset works. The first fully-tested preset this
project shipped still crashed FL Studio ~2 seconds after being selected,
from a CBOR wire-type mismatch no amount of self-consistent round-tripping
could catch. That specific failure class is now automatable; whether the
preset actually *sounds* right, or loads without some other real-Serum-only
issue, is not -- that part still needs the user.

## Steps

1. **Run the automated scan** on every preset file involved:
   ```bash
   uv run python scripts/check_preset.py "<path-to-preset>" ["<path-to-preset-2>" ...]
   ```
   If mid-session code changes to `src/serum_mcp/` haven't been picked up
   by a normal `uv run` yet (e.g. the entry-point `.exe` is locked by a
   connected MCP server process, a known Windows gotcha this session hit
   repeatedly), use `uv run --no-sync python scripts/check_preset.py ...`
   instead.

2. **If it reports FAIL** (a CBOR wire-type issue): stop -- do not tell the
   user to load the file. This means a real bug slipped past
   `preset/validator.py`'s normalization. Go fix `preset/mapping.py` (or
   wherever the offending value was written), rerun the scan, and only
   proceed once it's clean. This is a hard gate, not a warning to note and
   move past.

3. **If it reports OK**: summarize the preset's key sections (oscillators,
   filters, envelope shape, FX chain, mod routes -- whatever's relevant to
   what was just generated/edited) for the user in a few lines, pointing
   out anything worth specifically checking in Serum's UI (e.g. "a new FX
   type that's never been tested live before", "a custom-synthesized
   wavetable", "an edited param that should have changed vs. what should
   have stayed the same").

4. **Ask the user to load it and report back** -- don't declare the
   feature/fix done based on the scan alone. If this was verifying a fix
   for something the user already reported, be specific about what
   changed and what you want them to check (the original symptom, not just
   "does it work").

5. **Reminder for code changes**: if `src/serum_mcp/` was edited this
   session and the user has a `serum-mcp` MCP server connected (i.e. you've
   been calling `mcp__serum-mcp__*` tools), that server process was spawned
   before the edit and does **not** hot-reload -- it's still running the
   old code. Either generate/edit the test preset via a direct
   `uv run --no-sync python -c "..."` call (bypassing the stale server, see
   `src/serum_mcp/tools/generate_preset.py` /`edit_preset.py` for the
   pattern used throughout this project's own commits) to get something
   testable *now*, or tell the user a restart (`claude -c` is fine) is
   needed before the fix is live through natural-language `generate_preset`
   calls.
