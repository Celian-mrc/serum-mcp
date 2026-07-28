from __future__ import annotations

import json
import struct

import numpy as np
import pytest

from serum_mcp.tools.analyze_sample_file import analyze_sample_file


def _write_wav(
    path, *, freq: float = 440.0, duration_s: float = 0.5, sample_rate: int = 44100
) -> None:
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    samples = 0.8 * np.sin(2 * np.pi * freq * t)
    data = (samples * 32767.0).astype("<i2").tobytes()
    fmt_chunk = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def test_returns_valid_json_with_expected_keys(tmp_path):
    path = tmp_path / "tone.wav"
    _write_wav(path)

    result = json.loads(analyze_sample_file(str(path)))
    for key in (
        "duration_seconds",
        "brightness",
        "spectral_centroid_hz",
        "texture",
        "spectral_flatness",
        "zero_crossing_rate",
        "pitch",
        "pitch_hz",
        "pitch_confidence",
        "attack_ms",
        "sustain_ratio",
    ):
        assert key in result


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        analyze_sample_file(str(tmp_path / "nope.wav"))
