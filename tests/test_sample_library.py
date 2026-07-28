from __future__ import annotations

import struct

import numpy as np
import pytest

from serum_mcp.preset.sample_library import (
    _channel_balance_gains,
    _decode_wav_samples,
    copy_sample_to_library,
    read_wav_metadata,
    sample_library_filename,
)


def _write_wav(
    path, *, num_samples: int = 100, sample_rate: int = 44100, channels: int = 1
) -> None:
    data = b"\x00\x01" * num_samples * channels  # 16-bit PCM, arbitrary content
    fmt_chunk = struct.pack(
        "<HHIIHH", 1, channels, sample_rate, sample_rate * channels * 2, channels * 2, 16
    )
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def _write_stereo_wav(
    path,
    *,
    left_amp: float = 0.5,
    right_amp: float = 0.5,
    num_samples: int = 4410,
    sample_rate: int = 44100,
) -> None:
    """A stereo sine tone with independently controllable per-channel
    amplitude, for pan-centering tests."""
    t = np.linspace(0, 1, num_samples, endpoint=False)
    left = (left_amp * np.sin(2 * np.pi * 440 * t) * 32767.0).astype("<i2")
    right = (right_amp * np.sin(2 * np.pi * 440 * t) * 32767.0).astype("<i2")
    interleaved = np.empty(num_samples * 2, dtype="<i2")
    interleaved[0::2] = left
    interleaved[1::2] = right
    data = interleaved.tobytes()
    fmt_chunk = struct.pack("<HHIIHH", 1, 2, sample_rate, sample_rate * 4, 4, 16)
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def test_read_wav_metadata_mono(tmp_path):
    path = tmp_path / "kick.wav"
    _write_wav(path, num_samples=500, sample_rate=44100, channels=1)
    channels, sample_rate, num_frames = read_wav_metadata(path)
    assert channels == 1
    assert sample_rate == 44100
    assert num_frames == 500


def test_read_wav_metadata_stereo(tmp_path):
    path = tmp_path / "pad.wav"
    _write_wav(path, num_samples=300, sample_rate=48000, channels=2)
    channels, sample_rate, num_frames = read_wav_metadata(path)
    assert channels == 2
    assert sample_rate == 48000
    # num_frames is per-channel frame count, not raw sample count.
    assert num_frames == 300


def test_read_wav_metadata_rejects_non_riff(tmp_path):
    path = tmp_path / "not_a_wav.wav"
    path.write_bytes(b"definitely not a riff file")
    with pytest.raises(ValueError, match="not a RIFF/WAVE file"):
        read_wav_metadata(path)


def test_sample_library_filename_deterministic_content_and_extension_keyed(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(b"content one")
    b.write_bytes(b"content two")

    name_a1 = sample_library_filename(a)
    name_a2 = sample_library_filename(a)
    name_b = sample_library_filename(b)

    assert name_a1 == name_a2
    assert name_a1 != name_b
    assert name_a1.startswith("smp_")
    assert name_a1.endswith(".wav")


def test_copy_sample_to_library_copies_bytes_and_dedupes(tmp_path):
    source = tmp_path / "kick.wav"
    _write_wav(source, num_samples=200)
    dest_root = tmp_path / "Samples"

    dest1 = copy_sample_to_library(source, dest_root, ("User", "serum-mcp"))
    assert dest1.exists()
    assert dest1.read_bytes() == source.read_bytes()

    # Second call with the same content must reuse the same file, not
    # write a duplicate.
    dest2 = copy_sample_to_library(source, dest_root, ("User", "serum-mcp"))
    assert dest1 == dest2
    assert len(list(dest1.parent.iterdir())) == 1


def test_copy_sample_to_library_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "kick.flac"
    source.write_bytes(b"fLaC-ish bytes")
    dest_root = tmp_path / "Samples"
    with pytest.raises(ValueError, match="unsupported extension"):
        copy_sample_to_library(source, dest_root, ("User", "serum-mcp"))


def test_channel_balance_gains_none_for_mono():
    samples = np.zeros((100, 1), dtype=np.float32)
    assert _channel_balance_gains(samples) is None


def test_channel_balance_gains_none_when_already_balanced():
    t = np.linspace(0, 1, 1000, endpoint=False)
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    samples = np.stack([tone, tone], axis=1)
    assert _channel_balance_gains(samples) is None


def test_channel_balance_gains_corrects_imbalance():
    t = np.linspace(0, 1, 1000, endpoint=False)
    left = (0.8 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    right = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    samples = np.stack([left, right], axis=1)

    gains = _channel_balance_gains(samples)
    assert gains is not None
    gain_l, gain_r = gains
    assert gain_l < 1.0  # louder channel attenuated
    assert gain_r > 1.0  # quieter channel boosted

    new_peak_l = np.max(np.abs(left * gain_l))
    new_peak_r = np.max(np.abs(right * gain_r))
    assert new_peak_l == pytest.approx(new_peak_r, rel=1e-6)


def test_channel_balance_gains_targets_peak_not_rms():
    """Regression test found live: a file RMS-centered to 0.00dB still
    measured a real peak imbalance on a DAW mixer's level meters, because a
    single loud transient on one channel barely moves that channel's RMS
    but fully dominates its peak. Build a case where RMS is already equal
    but peak isn't (a brief spike on the left channel only) -- the old
    RMS-based version of this function would return None (nothing to
    correct); it must now detect and correct the peak imbalance."""
    n = 200_000  # realistic one-shot length -- a single spike must stay
    # negligible to RMS at this scale, the way it would in a real recording
    rng = np.random.default_rng(7)
    left = (0.01 * rng.standard_normal(n)).astype(np.float32)
    right = left.copy()
    left[0] = 0.9  # one loud spike, left channel only

    # RMS is nearly identical (a single sample barely moves it)...
    rms_l = np.sqrt(np.mean(left.astype(np.float64) ** 2))
    rms_r = np.sqrt(np.mean(right.astype(np.float64) ** 2))
    assert rms_l == pytest.approx(rms_r, rel=0.05)
    # ...but peak is wildly different.
    assert np.max(np.abs(left)) > 5 * np.max(np.abs(right))

    samples = np.stack([left, right], axis=1)
    gains = _channel_balance_gains(samples)
    assert gains is not None
    gain_l, gain_r = gains

    new_peak_l = np.max(np.abs(left * gain_l))
    new_peak_r = np.max(np.abs(right * gain_r))
    assert new_peak_l == pytest.approx(new_peak_r, rel=1e-6)


def test_copy_sample_to_library_centers_imbalanced_stereo(tmp_path):
    source = tmp_path / "guitar.wav"
    _write_stereo_wav(source, left_amp=0.8, right_amp=0.4)
    dest_root = tmp_path / "Samples"

    dest = copy_sample_to_library(source, dest_root, ("User", "serum-mcp"))
    assert dest.read_bytes() != source.read_bytes()  # re-encoded, not a verbatim copy

    corrected, _ = _decode_wav_samples(dest)
    peak_l = np.max(np.abs(corrected[:, 0]))
    peak_r = np.max(np.abs(corrected[:, 1]))
    assert peak_l == pytest.approx(peak_r, rel=0.02)


def test_copy_sample_to_library_leaves_balanced_stereo_untouched(tmp_path):
    source = tmp_path / "guitar.wav"
    _write_stereo_wav(source, left_amp=0.5, right_amp=0.5)
    dest_root = tmp_path / "Samples"

    dest = copy_sample_to_library(source, dest_root, ("User", "serum-mcp"))
    assert dest.read_bytes() == source.read_bytes()


def test_copy_sample_to_library_leaves_mono_untouched(tmp_path):
    source = tmp_path / "kick.wav"
    _write_wav(source, num_samples=200, channels=1)
    dest_root = tmp_path / "Samples"

    dest = copy_sample_to_library(source, dest_root, ("User", "serum-mcp"))
    assert dest.read_bytes() == source.read_bytes()


def test_copy_sample_to_library_center_pan_false_copies_verbatim(tmp_path):
    source = tmp_path / "guitar.wav"
    _write_stereo_wav(source, left_amp=0.8, right_amp=0.2)
    dest_root = tmp_path / "Samples"

    dest = copy_sample_to_library(source, dest_root, ("User", "serum-mcp"), center_pan=False)
    assert dest.read_bytes() == source.read_bytes()


def test_sample_library_filename_centered_flag_changes_filename(tmp_path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"content")

    plain = sample_library_filename(source, centered=False)
    centered = sample_library_filename(source, centered=True)

    assert plain != centered
    assert "_centered" in centered
    assert plain.endswith(".wav") and centered.endswith(".wav")
