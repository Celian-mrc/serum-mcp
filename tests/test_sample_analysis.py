from __future__ import annotations

import struct

import numpy as np
import pytest

from serum_mcp.preset.sample_analysis import analyze_sample, read_embedded_metadata


def _write_wav(
    path,
    samples: np.ndarray,
    *,
    sample_rate: int = 44100,
    inst_chunk: bytes | None = None,
    smpl_chunk: bytes | None = None,
) -> None:
    data = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    fmt_chunk = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    if inst_chunk is not None:
        body += b"inst" + struct.pack("<I", len(inst_chunk)) + inst_chunk
        if len(inst_chunk) % 2:
            body += b"\x00"  # RIFF chunks are word-aligned
    if smpl_chunk is not None:
        body += b"smpl" + struct.pack("<I", len(smpl_chunk)) + smpl_chunk
        if len(smpl_chunk) % 2:
            body += b"\x00"
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def _make_inst_chunk(
    *,
    root_note: int = 60,
    fine_tune: int = 0,
    gain: int = 0,
    low_note: int = 0,
    high_note: int = 127,
    low_vel: int = 0,
    high_vel: int = 127,
) -> bytes:
    return struct.pack(
        "<BbbBBBB", root_note, fine_tune, gain, low_note, high_note, low_vel, high_vel
    )


def _make_smpl_chunk(
    *,
    root_note: int = 60,
    loop_start: int | None = None,
    loop_end: int | None = None,
    loop_type: int = 0,
    play_count: int = 0,
) -> bytes:
    num_loops = 1 if loop_start is not None else 0
    header = struct.pack("<9I", 0, 0, 0, root_note, 0, 0, 0, num_loops, 0)
    if num_loops == 0:
        return header
    loop_record = struct.pack("<6I", 0, loop_type, loop_start, loop_end, 0, play_count)
    return header + loop_record


def _sine(freq: float, duration_s: float, sample_rate: int = 44100, amplitude: float = 0.8):
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_pure_sine_is_tonal_and_correctly_pitched(tmp_path):
    path = tmp_path / "tone.wav"
    _write_wav(path, _sine(440.0, 0.5))

    result = analyze_sample(path)
    assert result["texture"] == "tonal"
    assert result["pitch"] is not None
    assert result["pitch"].startswith("A4")
    assert result["pitch_hz"] == pytest.approx(440.0, abs=5.0)
    assert result["pitch_confidence"] > 0.9


def test_white_noise_is_noisy_and_unpitched(tmp_path):
    rng = np.random.default_rng(42)
    path = tmp_path / "noise.wav"
    _write_wav(path, rng.uniform(-0.8, 0.8, size=22050))

    result = analyze_sample(path)
    assert result["texture"] == "noisy"
    assert result["pitch"] is None
    assert result["pitch_hz"] is None


def test_low_frequency_tone_is_dark(tmp_path):
    path = tmp_path / "low.wav"
    _write_wav(path, _sine(90.0, 0.5))

    result = analyze_sample(path)
    assert result["brightness"] == "dark"


def test_high_frequency_tone_is_airy(tmp_path):
    path = tmp_path / "high.wav"
    _write_wav(path, _sine(8000.0, 0.5))

    result = analyze_sample(path)
    assert result["brightness"] == "airy"


def test_duration_is_reported_accurately(tmp_path):
    path = tmp_path / "tone.wav"
    _write_wav(path, _sine(440.0, 1.0))

    result = analyze_sample(path)
    assert result["duration_seconds"] == pytest.approx(1.0, abs=0.01)


def test_rejects_non_wav_extension(tmp_path):
    path = tmp_path / "tone.flac"
    path.write_bytes(b"fLaC-ish, not real")

    with pytest.raises(ValueError, match="only supports .wav"):
        analyze_sample(path)


def test_short_percussive_burst_has_low_sustain_ratio(tmp_path):
    """A brief loud transient followed by near-silence should show a fast
    attack and a low sustain_ratio -- the raw, uncategorized shape signal
    this module exposes instead of a forced percussive/sustained label."""
    sample_rate = 44100
    burst = _sine(200.0, 0.02, sample_rate=sample_rate, amplitude=0.9)
    tail = np.zeros(int(sample_rate * 0.3))
    path = tmp_path / "burst.wav"
    _write_wav(path, np.concatenate([burst, tail]), sample_rate=sample_rate)

    result = analyze_sample(path)
    assert result["attack_ms"] < 50
    assert result["sustain_ratio"] < 0.3


def test_read_embedded_metadata_empty_when_no_chunks_present(tmp_path):
    path = tmp_path / "plain.wav"
    _write_wav(path, _sine(440.0, 0.2))

    assert read_embedded_metadata(path) == {}


def test_read_embedded_metadata_inst_chunk_only(tmp_path):
    path = tmp_path / "with_inst.wav"
    _write_wav(
        path, _sine(440.0, 0.2), inst_chunk=_make_inst_chunk(root_note=60, fine_tune=-5, gain=2)
    )

    result = read_embedded_metadata(path)
    assert result["root_note_midi"] == 60
    assert result["root_note"] == "C4"
    assert result["root_note_fine_tune_cents"] == -5
    assert "loop_start_frame" not in result


def test_read_embedded_metadata_smpl_chunk_with_loop(tmp_path):
    path = tmp_path / "with_smpl.wav"
    _write_wav(
        path,
        _sine(440.0, 0.2),
        smpl_chunk=_make_smpl_chunk(root_note=69, loop_start=100, loop_end=5000, loop_type=1),
    )

    result = read_embedded_metadata(path)
    assert result["root_note_midi"] == 69
    assert result["root_note"] == "A4"
    assert result["loop_type"] == "ping_pong"
    assert result["loop_start_frame"] == 100
    assert result["loop_end_frame"] == 5000


def test_read_embedded_metadata_smpl_without_loop_records(tmp_path):
    path = tmp_path / "with_smpl_no_loop.wav"
    _write_wav(path, _sine(440.0, 0.2), smpl_chunk=_make_smpl_chunk(root_note=48))

    result = read_embedded_metadata(path)
    assert result["root_note_midi"] == 48
    assert "loop_start_frame" not in result


def test_read_embedded_metadata_prefers_smpl_root_note_when_both_present(tmp_path):
    path = tmp_path / "both.wav"
    _write_wav(
        path,
        _sine(440.0, 0.2),
        inst_chunk=_make_inst_chunk(root_note=60),
        smpl_chunk=_make_smpl_chunk(root_note=72),
    )

    result = read_embedded_metadata(path)
    assert result["root_note_midi"] == 72  # smpl wins per the documented priority
    assert result["root_note_fine_tune_cents"] == 0  # still pulled from inst


def test_analyze_sample_includes_embedded_metadata_with_loop_percentages(tmp_path):
    path = tmp_path / "with_smpl.wav"
    sample_rate = 44100
    tone = _sine(440.0, 1.0, sample_rate=sample_rate)  # 44100 frames total
    _write_wav(
        path,
        tone,
        sample_rate=sample_rate,
        smpl_chunk=_make_smpl_chunk(root_note=60, loop_start=4410, loop_end=39690),
    )

    result = analyze_sample(path)
    embedded = result["embedded_metadata"]
    assert embedded["root_note"] == "C4"
    assert embedded["loop_start_percent"] == pytest.approx(10.0, abs=0.1)
    assert embedded["loop_end_percent"] == pytest.approx(90.0, abs=0.1)


def test_analyze_sample_embedded_metadata_empty_when_absent(tmp_path):
    path = tmp_path / "plain.wav"
    _write_wav(path, _sine(440.0, 0.2))

    result = analyze_sample(path)
    assert result["embedded_metadata"] == {}
