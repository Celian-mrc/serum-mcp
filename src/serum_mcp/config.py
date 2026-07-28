"""Locating the user's Serum presets and wavetables folders.

Serum's user preset folder is configurable from within the plugin itself
("Show Serum Presets folder" in the hamburger menu) and its location varies by
install. We never hardcode it: callers must set ``SERUM_PRESETS_PATH``, or we
fall back to the handful of locations Serum 2 is known to use by default.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "SERUM_PRESETS_PATH"
TABLES_ENV_VAR = "SERUM_TABLES_PATH"

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


class TablesFolderNotFoundError(RuntimeError):
    """Raised when no usable Serum wavetables folder could be determined."""

    def __init__(self) -> None:
        super().__init__(
            "Could not locate your Serum wavetables folder (needed to write "
            f"custom-synthesized wavetables). Set the {TABLES_ENV_VAR} environment "
            'variable to Serum\'s "Tables" folder (a sibling of "Presets" under '
            'the same root Serum shows via "Show Serum Presets folder"), or make '
            "sure it exists at the standard location next to your configured "
            f"{ENV_VAR}."
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


def get_tables_dir() -> Path:
    """Return Serum's "Tables" folder (where wavetable ``.wav`` files live).

    Resolution order:
    1. The ``SERUM_TABLES_PATH`` environment variable, if set.
    2. Derived from the presets folder: every known Serum install layout
       has "Tables" as a sibling of "Presets" under the same root (e.g.
       ".../Serum 2 Presets/{Presets,Tables}"), so ``Tables`` is
       ``get_presets_dir().parent.parent / "Tables"``.

    Raises :class:`TablesFolderNotFoundError` if neither resolves.
    """
    configured = os.environ.get(TABLES_ENV_VAR)
    if configured:
        path = Path(configured).expanduser()
        if not path.is_dir():
            raise TablesFolderNotFoundError()
        return path

    try:
        presets_dir = get_presets_dir()
    except PresetsFolderNotFoundError:
        raise TablesFolderNotFoundError() from None

    candidate = presets_dir.parent.parent / "Tables"
    if candidate.is_dir():
        return candidate

    raise TablesFolderNotFoundError()
