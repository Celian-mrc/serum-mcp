from __future__ import annotations

import struct

import numpy as np
import pytest

from serum_mcp.preset.wavetable import (
    FRAME_SIZE,
    SAMPLE_RATE,
    synthesize_frame,
    wavetable_filename,
    write_wavetable_wav,
)


def test_synthesize_frame_pure_sine_has_expected_shape():
    frame = synthesize_frame([1.0])
    assert len(frame) == FRAME_SIZE
    assert frame.dtype == np.float32
    # Peak-normalized to 0.98, not clipped.
    assert 0.9 < np.max(np.abs(frame)) <= 0.98


def test_synthesize_frame_rejects_empty_or_too_many_harmonics():
    with pytest.raises(ValueError, match="non-empty"):
        synthesize_frame([])
    with pytest.raises(ValueError, match="too many harmonics"):
        synthesize_frame([1.0] * (FRAME_SIZE // 2 + 1))


def test_synthesize_frame_more_harmonics_is_more_complex_than_pure_sine():
    sine = synthesize_frame([1.0])
    rich = synthesize_frame([1.0, 0.8, 0.6, 0.4, 0.2])
    # A richer harmonic series should have more spectral energy above the
    # fundamental than a pure sine (a coarse but robust complexity check).
    sine_fft = np.abs(np.fft.rfft(sine))
    rich_fft = np.abs(np.fft.rfft(rich))
    assert rich_fft[2:10].sum() > sine_fft[2:10].sum()


def test_write_wavetable_wav_produces_valid_riff_structure(tmp_path):
    frames = [synthesize_frame([1.0]), synthesize_frame([1.0, 0.5])]
    dest = tmp_path / "sub" / "test.wav"
    num_samples, sample_rate, channels = write_wavetable_wav(dest, frames)

    assert num_samples == 2 * FRAME_SIZE
    assert sample_rate == SAMPLE_RATE
    assert channels == 1
    assert dest.exists()

    data = dest.read_bytes()
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"

    # Walk the chunk list the same way we'd need to for real Serum tables.
    chunks = {}
    off = 12
    while off < len(data):
        chunk_id = data[off : off + 4]
        chunk_size = struct.unpack_from("<I", data, off + 4)[0]
        chunks[chunk_id] = (off, chunk_size)
        off += 8 + chunk_size + (chunk_size % 2)

    assert b"fmt " in chunks
    fmt_off, _ = chunks[b"fmt "]
    fmt_tag, num_channels, sr, _, _, bits = struct.unpack_from("<HHIIHH", data, fmt_off + 8)
    assert fmt_tag == 3  # IEEE float
    assert num_channels == 1
    assert sr == SAMPLE_RATE
    assert bits == 32

    assert b"clm " in chunks
    clm_off, clm_size = chunks[b"clm "]
    assert (
        data[clm_off + 8 : clm_off + 8 + clm_size]
        == b"<!>2048 01000000 wavetable (www.xferrecords.com)"
    )

    assert b"data" in chunks
    data_off, data_size = chunks[b"data"]
    assert data_size == num_samples * 4  # float32 = 4 bytes/sample


def test_wavetable_filename_deterministic_and_distinct():
    a = wavetable_filename([[1.0, 0.5]])
    b = wavetable_filename([[1.0, 0.5]])
    c = wavetable_filename([[1.0, 0.6]])
    assert a == b
    assert a != c
    assert a.startswith("wt_") and a.endswith(".wav")
