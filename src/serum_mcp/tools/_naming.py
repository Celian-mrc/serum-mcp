"""Shared helper for turning a preset name into a filesystem-safe filename.

Serum's own preset browser displays the *filename*, not the internal
``presetName`` metadata field inside the file (confirmed against a live
Serum 2 install: editing a preset's metadata name alone, without renaming
the file, left the name shown in Serum unchanged). Both generate_preset and
edit_preset need this, so it lives here rather than being duplicated or
imported across tool modules.
"""

from __future__ import annotations

import re


def slugify_preset_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 _\-]", "", name).strip()
    return slug or "Untitled"
