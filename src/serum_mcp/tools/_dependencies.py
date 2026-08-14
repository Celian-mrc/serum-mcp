"""Shared helper for surfacing a generated/edited preset's external file
dependencies (custom-synthesized wavetables, user-supplied samples) back to
the calling model.

Serum's own wavetable/sample engines always store this content as a
SEPARATE file on the local machine (Tables/User/serum-mcp or Samples/User/
serum-mcp), referenced from the .SerumPreset by relative path only -- this
is true of Serum itself, not a serum-mcp limitation (a wavetable hand-drawn
in Serum's own editor and saved works the exact same way). A preset built
with ``custom_harmonics``/``sample_source``/``sample_playback_source``/
``granular_source``/``spectral_source`` is therefore NOT self-contained:
sharing just the .SerumPreset file with someone else (a different machine,
a bank being distributed for testing) leaves those referenced files
missing, and Serum will show a blank/broken table or sample on their end.

Both ``generate_preset`` and ``edit_preset`` collect these paths via
``mapping.apply_spec``'s ``external_files`` parameter and append the note
this module builds -- so the dependency is visible in the tool's own
return value instead of being a silent trap only discovered later, when
someone else's copy of the preset already doesn't work.
"""

from __future__ import annotations

from pathlib import Path


def append_dependency_note(result_path: str, external_files: list[Path]) -> str:
    """Return ``result_path`` unchanged if ``external_files`` is empty
    (the common case); otherwise append a clearly-delimited note on
    following lines listing each dependency's absolute path.

    The FIRST LINE of the return value is always exactly ``result_path``
    -- callers that only need the file path (e.g. ``Path(result.splitlines()[0])``)
    can still recover it even when a note is appended; only callers that
    blindly do ``Path(result)`` on a preset using one of these techniques
    need to account for the extra lines, the same way a human sharing a
    hand-drawn-wavetable preset from Serum's own UI would need to notice
    and attach the extra file themselves.
    """
    if not external_files:
        return result_path
    lines = [
        result_path,
        f"NOTE: this preset depends on {len(external_files)} local file"
        f"{'s' if len(external_files) != 1 else ''} not embedded in the "
        ".SerumPreset itself (same real Serum limitation as a hand-drawn "
        "wavetable saved from Serum's own editor) -- bundle these alongside "
        "the preset if sharing it with anyone else or on another machine:",
    ]
    lines.extend(f"  - {path}" for path in external_files)
    return "\n".join(lines)
