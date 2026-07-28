"""``list_sample_files`` MCP tool implementation."""

from __future__ import annotations

import json
from pathlib import Path

from serum_mcp import config
from serum_mcp.preset.sample_library import read_wav_metadata

_AUDIO_EXTENSIONS = (".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg")
_DEFAULT_MAX_RESULTS = 500


def list_sample_files(
    directory: str | None = None,
    *,
    recursive: bool = True,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> str:
    """List audio files under ``directory`` (e.g. a drumkit/sample bank
    folder) as JSON, so the calling model can pick a one-shot for
    ``OscillatorSpec.sample_playback_source``/``sample_source`` by filename,
    folder context, and (for ``.wav`` files) duration -- without needing raw
    filesystem access.

    If ``directory`` is omitted, falls back to the user's configured
    default sample bank (``config.get_sample_bank_dir()``, i.e. the
    ``SAMPLE_BANK_PATH`` environment variable) -- this is what lets the
    calling model proactively check "does the user have a one-shot that
    fits this?" without being told a path first, for any user of this MCP
    server who has set that variable. Raises :class:`ValueError` if
    ``directory`` is omitted and no default bank is configured either.

    Metadata beyond path/name/extension/size is currently WAV-only (this
    project can only read WAV headers without a FLAC/MP3 parser -- see
    docs/PARAMETER_SCHEMA.md). Non-WAV files still show up (drumkits commonly
    mix formats) with no ``duration_seconds``/``sample_rate``/``channels``,
    so filename/folder context is the only signal available for those.

    Raises :class:`ValueError` if ``directory`` doesn't exist or isn't a
    directory. Results are sorted alphabetically by path and truncated to
    ``max_results`` if there are more -- the returned ``truncated`` field
    signals whether that happened.
    """
    if directory is None:
        bank_dir = config.get_sample_bank_dir()
        if bank_dir is None:
            raise ValueError(
                "no directory given and no default sample bank is configured -- "
                f"pass a directory explicitly, or set {config.SAMPLE_BANK_ENV_VAR}"
            )
        root = bank_dir
    else:
        root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"{directory!r} is not a directory")

    pattern = "**/*" if recursive else "*"
    matches = sorted(
        p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS
    )

    truncated = len(matches) > max_results
    files: list[dict[str, object]] = []
    for path in matches[:max_results]:
        entry: dict[str, object] = {
            "path": str(path),
            "name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
        }
        if path.suffix.lower() == ".wav":
            try:
                channels, sample_rate, num_frames = read_wav_metadata(path)
            except ValueError:
                pass  # malformed/unreadable WAV -- still list it, just without audio metadata
            else:
                entry["channels"] = channels
                entry["sample_rate"] = sample_rate
                entry["duration_seconds"] = round(num_frames / sample_rate, 3)
        files.append(entry)

    return json.dumps(
        {
            "directory": str(root),
            "count": len(files),
            "truncated": truncated,
            "files": files,
        },
        indent=2,
    )
