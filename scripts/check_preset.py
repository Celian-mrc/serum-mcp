#!/usr/bin/env python
"""Run the pre-real-Serum-test checklist against one or more .SerumPreset
files: scan for CBOR wire-type issues (the class of bug that crashed FL
Studio earlier this project -- see docs/PARAMETER_SCHEMA.md), then print a
human-readable summary of what's in the file.

Usage:
    uv run python scripts/check_preset.py <path-to-preset> [<path>...]

This does NOT prove a preset works -- only loading it in real Serum does
(see the project's own established lesson on this). It catches the
specific, previously-seen failure mode automatically instead of relying on
remembering to check for it by hand every time.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from serum_mcp.preset.packer import unpack_file  # noqa: E402
from serum_mcp.preset.safety import scan_wire_types  # noqa: E402
from serum_mcp.tools.describe_preset import describe_preset  # noqa: E402


def check_one(path: Path) -> bool:
    print(f"=== {path.name} ===")
    preset = unpack_file(path)
    issues = scan_wire_types(preset.data)
    if issues:
        print(f"FAIL -- {len(issues)} CBOR wire-type issue(s) found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("OK -- no CBOR wire-type issues found (bool/int leaks into plainParams).")
    print()
    print(describe_preset(str(path)))
    print()
    return not issues


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    all_ok = True
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"=== {arg} ===\nFAIL -- file does not exist\n")
            all_ok = False
            continue
        all_ok = check_one(path) and all_ok
    if not all_ok:
        print("One or more files failed the wire-type scan -- do not ask the user to load these.")
        return 1
    print(
        "All files passed the automated scan. This does NOT confirm they work -- "
        "load them in real Serum to actually verify."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
