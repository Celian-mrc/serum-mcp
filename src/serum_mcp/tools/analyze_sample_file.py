"""``analyze_sample_file`` MCP tool implementation."""

from __future__ import annotations

import json
from pathlib import Path

from serum_mcp.preset.sample_analysis import analyze_sample


def analyze_sample_file(path: str) -> str:
    """Compute lightweight acoustic descriptors for one ``.wav`` one-shot
    and return them as JSON -- see
    ``serum_mcp.preset.sample_analysis`` for scope/method/validation notes.

    Includes ``peak_dbfs``/``rms_dbfs``: call this on every candidate file
    BEFORE combining multiple ``sample_playback_source`` layers in one
    preset and picking their ``volume`` values. Raw one-shot libraries are
    not gain-matched to each other -- two files can differ by 15-20dB in
    RMS -- so a volume guessed without checking this risks a layer that's
    inaudible once mixed even though its volume field looks reasonable
    next to the others.

    Also includes an ``embedded_metadata`` field: sampler tags (root note,
    fine tune, sample-accurate loop points as both frame numbers and
    percentages) read from the file's own ``inst``/``smpl`` RIFF chunks
    when the sample pack's creator embedded them -- real, human-authored
    ground truth, stronger than any DSP estimate in this module, but not
    universal (an empty dict when neither chunk is present, never guessed).

    Raises :class:`ValueError` if the file doesn't exist or isn't a ``.wav``.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"{path!r} does not exist")
    return json.dumps(analyze_sample(file_path), indent=2)
