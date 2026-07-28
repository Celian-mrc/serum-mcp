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
SAMPLES_ENV_VAR = "SERUM_SAMPLES_PATH"
SAMPLE_BANK_ENV_VAR = "SAMPLE_BANK_PATH"

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


class SamplesFolderNotFoundError(RuntimeError):
    """Raised when no usable Serum samples folder could be determined."""

    def __init__(self) -> None:
        super().__init__(
            "Could not locate your Serum samples folder (needed to copy a one-shot "
            f"in for SampleOsc playback). Set the {SAMPLES_ENV_VAR} environment "
            'variable to Serum\'s "Samples" folder (a sibling of "Presets" under '
            'the same root Serum shows via "Show Serum Presets folder"), or make '
            "sure it exists at the standard location next to your configured "
            f"{ENV_VAR}."
        )


class SampleBankPathInvalidError(RuntimeError):
    """Raised when ``SAMPLE_BANK_PATH`` is set but doesn't point at a real
    directory -- distinct from simply being unset (which is not an error,
    see :func:`get_sample_bank_dir`)."""

    def __init__(self, configured: str) -> None:
        super().__init__(
            f"{SAMPLE_BANK_ENV_VAR} is set to {configured!r}, but that's not a "
            "directory that exists. Fix or unset the environment variable."
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


def get_samples_dir() -> Path:
    """Return Serum's "Samples" folder (where one-shot/multisample audio
    files referenced by ``SampleOsc``/``MultiSampleOsc`` live).

    Resolution order mirrors :func:`get_tables_dir`:
    1. The ``SERUM_SAMPLES_PATH`` environment variable, if set.
    2. Derived from the presets folder: every known Serum install layout has
       "Samples" as a sibling of "Presets" under the same root.

    Raises :class:`SamplesFolderNotFoundError` if neither resolves.
    """
    configured = os.environ.get(SAMPLES_ENV_VAR)
    if configured:
        path = Path(configured).expanduser()
        if not path.is_dir():
            raise SamplesFolderNotFoundError()
        return path

    try:
        presets_dir = get_presets_dir()
    except PresetsFolderNotFoundError:
        raise SamplesFolderNotFoundError() from None

    candidate = presets_dir.parent.parent / "Samples"
    if candidate.is_dir():
        return candidate

    raise SamplesFolderNotFoundError()


def get_sample_bank_dir() -> Path | None:
    """Return the user's own one-shot/sample library folder (e.g. a
    drumkit pack root), if configured -- unlike the Serum-owned folders
    above, this has no default install location to guess (it's the user's
    own library, not part of a Serum install), so it's simply absent
    (``None``) rather than an error when unset. Callers that want to
    proactively browse a sample bank (``tools/list_sample_files.py``) use
    this as a fallback when no explicit directory is given; callers that
    require an explicit directory just don't call this at all.

    Raises :class:`SampleBankPathInvalidError` if ``SAMPLE_BANK_PATH`` is
    set but doesn't point at a real directory -- a misconfigured value
    should fail loudly, not silently disable the feature.
    """
    configured = os.environ.get(SAMPLE_BANK_ENV_VAR)
    if not configured:
        return None
    path = Path(configured).expanduser()
    if not path.is_dir():
        raise SampleBankPathInvalidError(configured)
    return path
