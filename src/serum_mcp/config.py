"""Locating the user's Serum presets folder.

Serum's user preset folder is configurable from within the plugin itself
("Show Serum Presets folder" in the hamburger menu) and its location varies by
install. We never hardcode it: callers must set ``SERUM_PRESETS_PATH``, or we
fall back to the handful of locations Serum 2 is known to use by default.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "SERUM_PRESETS_PATH"

# Default install locations Serum 2 is known to use, relative to $HOME, in
# priority order. Not exhaustive -- e.g. custom Documents redirection or a
# non-default "Serum Presets folder" location won't be picked up.
_CANDIDATE_SUBPATHS = (
    ("Documents", "Xfer", "Serum 2 Presets", "Presets", "User"),
    ("Documents", "Xfer", "Serum Presets", "Presets", "User"),
    ("Music", "Xfer", "Serum 2 Presets", "Presets", "User"),
)


class PresetsFolderNotFoundError(RuntimeError):
    """Raised when no usable Serum user presets folder could be determined."""

    def __init__(self) -> None:
        checked = "\n".join(f"  - {Path.home().joinpath(*parts)}" for parts in _CANDIDATE_SUBPATHS)
        super().__init__(
            "Could not locate your Serum user presets folder.\n\n"
            f"Set the {ENV_VAR} environment variable to the folder Serum shows "
            'under its menu ("Show Serum Presets folder" -> Presets/User), or '
            "create one of these default locations:\n"
            f"{checked}"
        )


def get_presets_dir() -> Path:
    """Return the directory generated/edited presets should be written to.

    Resolution order:
    1. The ``SERUM_PRESETS_PATH`` environment variable, if set.
    2. The first known default install location that exists on disk.

    Raises :class:`PresetsFolderNotFoundError` if neither resolves.
    """
    configured = os.environ.get(ENV_VAR)
    if configured:
        path = Path(configured).expanduser()
        if not path.is_dir():
            raise PresetsFolderNotFoundError()
        return path

    for parts in _CANDIDATE_SUBPATHS:
        candidate = Path.home().joinpath(*parts)
        if candidate.is_dir():
            return candidate

    raise PresetsFolderNotFoundError()
