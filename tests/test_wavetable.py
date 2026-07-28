from __future__ import annotations

import struct

import numpy as np
import pytest

from serum_mcp.preset.wavetable import (
    FRAME_SIZE,
    SAMPLE_RATE,
    read_wav_mono,
    sample_wavetable_filename,
    slice_sample_to_frames,
    synthesize_frame,
    wavetable_filename,
    write_wavetable_wav,
)


def _write_test_wav(
    path,
    samples: np.ndarray,
    *,
    sample_rate: int = 44100,
    channels: int = 1,
    bits_per_sample: int = 16,
    float_format: bool = False,
) -> None:
    """Minimal standalone WAV writer for test fixtures -- deliberately
    independent of write_wavetable_wav (which only ever produces float32
    mono 44100 Hz Serum tables) so it can exercise the other formats
    read_wav_mono needs to handle (16/24-bit PCM, stereo, other rates)."""
    fmt_tag = 3 if float_format else 1
    if float_format:
        data = samples.astype("<f4").tobytes()
    elif bits_per_sample == 16:
        data = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    elif bits_per_sample == 24:
        ints = (np.clip(samples, -1.0, 1.0) * (2**23 - 1)).astype(np.int32)
        # Pack each int32 sample down to its low 3 bytes, little-endian.
        as_bytes = ints.astype("<i4").tobytes()
        data = b"".join(as_bytes[i : i + 3] for i in range(0, len(as_bytes), 4))
    else:
        raise ValueError(f"unsupported test bits_per_sample {bits_per_sample}")

    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    fmt_chunk = struct.pack(
        "<HHIIHH", fmt_tag, channels, sample_rate, byte_rate, block_align, bits_per_sample
    )
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def test_synthesize_frame_pure_sine_has_expected_shape():
    frame = synthesize_frame([1.0])
    assert len(frame) == FRAME_SIZE
    assert frame.dtype == np.float32
    # Fundamental-anchored normalization: a pure sine's peak IS the
    # fundamental's contribution, so it lands exactly at fundamental_level.
    assert np.max(np.abs(frame)) == pytest.approx(0.85, abs=1e-4)


def test_synthesize_frame_fundamental_level_survives_extra_harmonics():
    """Regression test found via real-world use: a preset with a 10-harmonic
    custom wavetable played back much quieter in upper octaves than a
    factory table, while the shared filter/envelope were ruled out by A/B
    testing another oscillator. Root cause: the original peak-normalization
    scaled the *whole* multi-harmonic waveform down to fit its combined
    peak, diluting the fundamental's own level -- exactly what survives once
    Serum's wavetable oscillator band-limits away upper harmonics at high
    pitch. Fundamental-anchoring plus a soft-knee limiter (only compressing
    the portion of the waveform *above* the fundamental's own level, leaving
    the fundamental-dominated bulk of each cycle untouched) meaningfully
    improves this over plain peak-normalization or a whole-signal tanh
    clip, though physically it can't be made perfectly independent of
    harmonic content -- a genuinely louder set of upper harmonics always
    costs *some* headroom. This asserts the improvement, not perfection."""
    sine = synthesize_frame([1.0])
    rich = synthesize_frame([1.0, 0.5, 0.35, 0.5, 0.25, 0.2, 0.3, 0.15, 0.2, 0.1])

    sine_fund_bin = np.abs(np.fft.rfft(sine))[1]
    rich_fund_bin = np.abs(np.fft.rfft(rich))[1]
    # A plain whole-signal tanh clip measured ~0.71x here; soft-knee limiting
    # measured ~0.72x. Assert it doesn't regress below that -- not a tight
    # bound, since some reduction is physically unavoidable for this content.
    assert rich_fund_bin > 0.65 * sine_fund_bin


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


def test_read_wav_mono_16bit(tmp_path):
    t = np.linspace(0, 1, 4410, endpoint=False)
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float64)
    path = tmp_path / "tone16.wav"
    _write_test_wav(path, tone, sample_rate=44100, bits_per_sample=16)

    samples, sr = read_wav_mono(path)
    assert sr == 44100
    assert len(samples) == len(tone)
    assert samples.dtype == np.float32
    np.testing.assert_allclose(samples, tone, atol=1e-3)


def test_read_wav_mono_24bit(tmp_path):
    t = np.linspace(0, 1, 2205, endpoint=False)
    tone = (0.7 * np.sin(2 * np.pi * 220 * t)).astype(np.float64)
    path = tmp_path / "tone24.wav"
    _write_test_wav(path, tone, sample_rate=22050, bits_per_sample=24)

    samples, sr = read_wav_mono(path)
    assert sr == 22050
    assert len(samples) == len(tone)
    np.testing.assert_allclose(samples, tone, atol=1e-4)


def test_read_wav_mono_float32(tmp_path):
    tone = np.array([0.1, -0.2, 0.3, -0.4], dtype=np.float64)
    path = tmp_path / "tonef32.wav"
    _write_test_wav(path, tone, sample_rate=48000, bits_per_sample=32, float_format=True)

    samples, sr = read_wav_mono(path)
    assert sr == 48000
    np.testing.assert_allclose(samples, tone, atol=1e-6)


def test_read_wav_mono_downmixes_stereo(tmp_path):
    # Interleaved L/R: constant +1.0 / -1.0 -> mono average is 0.0.
    interleaved = np.array([1.0, -1.0] * 100, dtype=np.float64)
    path = tmp_path / "stereo.wav"
    _write_test_wav(path, interleaved, sample_rate=44100, channels=2, bits_per_sample=16)

    samples, sr = read_wav_mono(path)
    assert len(samples) == 100
    np.testing.assert_allclose(samples, np.zeros(100), atol=1e-3)


def test_read_wav_mono_rejects_non_riff(tmp_path):
    path = tmp_path / "not_a_wav.wav"
    path.write_bytes(b"not a riff file at all")
    with pytest.raises(ValueError, match="not a RIFF/WAVE file"):
        read_wav_mono(path)


def test_slice_sample_to_frames_shape():
    samples = np.linspace(-1.0, 1.0, FRAME_SIZE * 10).astype(np.float32)
    frames = slice_sample_to_frames(samples, SAMPLE_RATE, num_frames=5)
    assert len(frames) == 5
    for frame in frames:
        assert len(frame) == FRAME_SIZE
        assert frame.dtype == np.float32


def test_slice_sample_to_frames_pads_short_sample():
    samples = np.array([0.5, -0.5, 0.5, -0.5], dtype=np.float32)
    frames = slice_sample_to_frames(samples, SAMPLE_RATE, num_frames=1)
    assert len(frames) == 1
    assert len(frames[0]) == FRAME_SIZE


def test_slice_sample_to_frames_normalizes_each_frame_independently():
    # A quiet first half, loud second half -- each sliced frame should
    # still reach close to the same peak after independent normalization,
    # rather than the quiet frame staying quiet.
    quiet = 0.01 * np.sin(np.linspace(0, 40 * np.pi, FRAME_SIZE))
    loud = 0.9 * np.sin(np.linspace(0, 40 * np.pi, FRAME_SIZE))
    samples = np.concatenate([quiet, loud]).astype(np.float32)
    frames = slice_sample_to_frames(samples, SAMPLE_RATE, num_frames=2, frame_size=FRAME_SIZE)
    peaks = [float(np.max(np.abs(f))) for f in frames]
    assert peaks[0] == pytest.approx(0.9, abs=0.05)
    assert peaks[1] == pytest.approx(0.9, abs=0.05)


def test_slice_sample_to_frames_resamples_lower_rate_stretches_content():
    # A source at half SAMPLE_RATE should be upsampled (stretched) so the
    # same number of source cycles still fits, rather than truncated.
    t = np.linspace(0, 1, 22050, endpoint=False)
    tone = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    frames = slice_sample_to_frames(tone, 22050, num_frames=1)
    assert len(frames[0]) == FRAME_SIZE


def test_slice_sample_to_frames_rejects_zero_frames():
    samples = np.zeros(FRAME_SIZE, dtype=np.float32)
    with pytest.raises(ValueError, match="num_frames"):
        slice_sample_to_frames(samples, SAMPLE_RATE, num_frames=0)


def test_sample_wavetable_filename_deterministic_and_content_keyed(tmp_path):
    path_a = tmp_path / "a.wav"
    path_b = tmp_path / "b.wav"
    _write_test_wav(path_a, np.array([0.1, 0.2], dtype=np.float64))
    _write_test_wav(path_b, np.array([0.3, 0.4], dtype=np.float64))

    name_a1 = sample_wavetable_filename(path_a, 16)
    name_a2 = sample_wavetable_filename(path_a, 16)
    name_a_diff_frames = sample_wavetable_filename(path_a, 32)
    name_b = sample_wavetable_filename(path_b, 16)

    assert name_a1 == name_a2
    assert name_a1 != name_a_diff_frames
    assert name_a1 != name_b
    assert name_a1.startswith("wts_") and name_a1.endswith(".wav")
