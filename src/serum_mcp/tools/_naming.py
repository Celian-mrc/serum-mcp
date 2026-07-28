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


def sanitize_subfolder(subfolder: str) -> str:
    """Turn a possibly-nested subfolder string (e.g. ``"RAGE Bank/Leads"``)
    into a safe relative path, one path segment at a time. Each segment has
    the same characters stripped as :func:`slugify_preset_name` (notably
    ``.``, so a ``".."`` segment becomes empty) but -- unlike that function --
    an empty segment here is *dropped* rather than replaced with a fallback
    name, so path-traversal attempts (``"../../etc"``) collapse away
    entirely instead of turning into an unexpected literal folder. Returns
    segments rejoined with ``/`` (a valid separator on both Windows and
    POSIX); an all-traversal input returns ``""``, meaning "no subfolder"."""
    segments = re.split(r"[\\/]+", subfolder)
    safe_segments = [re.sub(r"[^A-Za-z0-9 _\-]", "", seg).strip() for seg in segments]
    return "/".join(seg for seg in safe_segments if seg)
