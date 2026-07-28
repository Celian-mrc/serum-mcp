from __future__ import annotations

import json
import struct

import pytest

from serum_mcp import config
from serum_mcp.tools.list_sample_files import list_sample_files


def _write_wav(path, *, num_samples: int = 4410, sample_rate: int = 44100) -> None:
    data = b"\x00\x01" * num_samples
    fmt_chunk = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.write_bytes(bytes(riff))


def test_lists_wav_with_metadata(tmp_path):
    _write_wav(tmp_path / "kick.wav", num_samples=4410, sample_rate=44100)

    result = json.loads(list_sample_files(str(tmp_path)))
    assert result["count"] == 1
    assert result["truncated"] is False
    entry = result["files"][0]
    assert entry["name"] == "kick.wav"
    assert entry["extension"] == ".wav"
    assert entry["channels"] == 1
    assert entry["sample_rate"] == 44100
    assert entry["duration_seconds"] == pytest.approx(0.1, abs=1e-3)


def test_lists_non_wav_without_audio_metadata(tmp_path):
    (tmp_path / "snare.flac").write_bytes(b"fLaC-ish bytes, not a real flac")

    result = json.loads(list_sample_files(str(tmp_path)))
    assert result["count"] == 1
    entry = result["files"][0]
    assert entry["extension"] == ".flac"
    assert "duration_seconds" not in entry
    assert "sample_rate" not in entry


def test_ignores_non_audio_files(tmp_path):
    (tmp_path / "readme.txt").write_text("not audio")
    _write_wav(tmp_path / "kick.wav")

    result = json.loads(list_sample_files(str(tmp_path)))
    assert result["count"] == 1
    assert result["files"][0]["name"] == "kick.wav"


def test_recursive_scans_subfolders(tmp_path):
    sub = tmp_path / "BELLS"
    sub.mkdir()
    _write_wav(sub / "bell.wav")

    result = json.loads(list_sample_files(str(tmp_path)))
    assert result["count"] == 1
    assert result["files"][0]["path"].endswith("bell.wav")


def test_non_recursive_skips_subfolders(tmp_path):
    sub = tmp_path / "BELLS"
    sub.mkdir()
    _write_wav(sub / "bell.wav")
    _write_wav(tmp_path / "kick.wav")

    result = json.loads(list_sample_files(str(tmp_path), recursive=False))
    assert result["count"] == 1
    assert result["files"][0]["name"] == "kick.wav"


def test_truncates_and_flags_when_over_max_results(tmp_path):
    for i in range(5):
        _write_wav(tmp_path / f"one_shot_{i}.wav")

    result = json.loads(list_sample_files(str(tmp_path), max_results=3))
    assert result["truncated"] is True
    assert result["count"] == 3


def test_rejects_non_directory(tmp_path):
    fake = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="not a directory"):
        list_sample_files(str(fake))


def test_omitted_directory_falls_back_to_configured_sample_bank(tmp_path, monkeypatch):
    _write_wav(tmp_path / "kick.wav")
    monkeypatch.setenv(config.SAMPLE_BANK_ENV_VAR, str(tmp_path))

    result = json.loads(list_sample_files())
    assert result["count"] == 1
    assert result["files"][0]["name"] == "kick.wav"


def test_omitted_directory_without_configured_bank_raises(monkeypatch):
    monkeypatch.delenv(config.SAMPLE_BANK_ENV_VAR, raising=False)
    with pytest.raises(ValueError, match="no default sample bank"):
        list_sample_files()


def test_explicit_directory_overrides_configured_bank(tmp_path, monkeypatch):
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    _write_wav(bank_dir / "bank_kick.wav")
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    _write_wav(explicit_dir / "explicit_kick.wav")
    monkeypatch.setenv(config.SAMPLE_BANK_ENV_VAR, str(bank_dir))

    result = json.loads(list_sample_files(str(explicit_dir)))
    assert result["files"][0]["name"] == "explicit_kick.wav"
