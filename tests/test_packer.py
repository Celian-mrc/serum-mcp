"""Round-trip tests for the binary container codec.

We don't ship real Xfer factory presets in this repo (unclear redistribution
rights), so these tests exercise the codec against our own committed
``fixtures/init_preset.SerumPreset`` plus synthetic payloads shaped like real
Serum 2 CBOR data (nested dicts/lists/strings/floats/bools, the "default"
sentinel, etc.).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from serum_mcp.preset.packer import (
    MAGIC,
    PresetFormatError,
    SerumPreset,
    pack_bytes,
    pack_file,
    unpack_bytes,
    unpack_file,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_roundtrip_init_fixture():
    preset = unpack_file(FIXTURES_DIR / "init_preset.SerumPreset")
    again = unpack_bytes(pack_bytes(preset))
    assert again.data == preset.data
    assert again.metadata == preset.metadata


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"Oscillator0": {"plainParams": "default"}},
        {
            "Env0": {"plainParams": {"kParamAttack": 0.001, "kParamSustain": 1.0}},
            "nested": {"list": [1, 2.5, "three", True, None, {"deep": [1, 2]}]},
            "unicode": "chorus warm évolutif 🎹",
        },
    ],
)
def test_roundtrip_synthetic_payloads(data):
    preset = SerumPreset(metadata={"presetName": "Test", "fileType": "SerumPreset"}, data=data)
    again = unpack_bytes(pack_bytes(preset))
    assert again.data == data


def test_pack_file_writes_valid_container(tmp_path):
    preset = SerumPreset(metadata={"presetName": "X"}, data={"a": 1})
    dest = tmp_path / "sub" / "out.SerumPreset"
    written = pack_file(preset, dest)
    assert written == dest
    assert dest.read_bytes().startswith(MAGIC)
    assert unpack_file(dest).data == {"a": 1}


def test_unpack_rejects_bad_magic():
    with pytest.raises(PresetFormatError):
        unpack_bytes(b"NotASerumFile\x00" + b"\x00" * 32)
