"""Binary (un)packing of ``.SerumPreset`` / ``.XferArpBank`` files.

Serum 2's own container format (undocumented by Xfer, reverse-engineered by the
community -- see ``docs/PARAMETER_SCHEMA.md``) is:

1. An 9-byte magic header: ``b"XferJson\\x00"``.
2. A little-endian ``(uint32 length, uint32 flags)`` pair, followed by that many
   bytes of UTF-8 JSON: the preset *metadata* (name, author, tags, product version...).
3. A second little-endian ``(uint32 length, uint32 flags)`` pair -- ``length`` is the
   size of the *uncompressed* payload, ``flags`` is a format marker (``2`` in every
   preset we've observed) -- followed by a Zstandard frame. Decompressing it yields
   CBOR-encoded bytes; decoding those CBOR bytes gives the actual synth engine state
   (oscillators, filters, envelopes, mod matrix, effects...).

This module only handles the container. It knows nothing about what the CBOR
*payload* means -- see :mod:`serum_mcp.preset.schema` for that.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cbor2
import zstandard

MAGIC = b"XferJson\x00"
_HEADER_STRUCT = struct.Struct("<II")  # (length, flags)
_ZSTD_COMPRESSION_LEVEL = 19


class PresetFormatError(ValueError):
    """Raised when a file does not look like a valid Serum 2 container."""


@dataclass
class SerumPreset:
    """A fully decoded Serum 2 preset: human-readable metadata + engine state."""

    metadata: dict[str, Any]
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return self.metadata.get("presetName", "")


def unpack_bytes(raw: bytes) -> SerumPreset:
    """Decode the raw bytes of a ``.SerumPreset``/``.XferArpBank`` file."""
    if raw[: len(MAGIC)] != MAGIC:
        raise PresetFormatError(
            f"not a Serum 2 preset file: expected magic {MAGIC!r}, got {raw[: len(MAGIC)]!r}"
        )
    offset = len(MAGIC)

    meta_len, _meta_flags = _HEADER_STRUCT.unpack_from(raw, offset)
    offset += _HEADER_STRUCT.size
    metadata = json.loads(raw[offset : offset + meta_len])
    offset += meta_len

    payload_len, _payload_flags = _HEADER_STRUCT.unpack_from(raw, offset)
    offset += _HEADER_STRUCT.size
    cbor_bytes = zstandard.ZstdDecompressor().decompress(raw[offset:])
    if len(cbor_bytes) != payload_len:
        raise PresetFormatError(
            f"decompressed payload size mismatch: header says {payload_len}, got {len(cbor_bytes)}"
        )
    data = cbor2.loads(cbor_bytes)

    return SerumPreset(metadata=metadata, data=data)


def unpack_file(path: str | Path) -> SerumPreset:
    """Decode a ``.SerumPreset``/``.XferArpBank`` file from disk."""
    return unpack_bytes(Path(path).read_bytes())


def pack_bytes(preset: SerumPreset) -> bytes:
    """Encode a :class:`SerumPreset` back into the on-disk container format."""
    meta_bytes = json.dumps(preset.metadata, separators=(",", ":")).encode("utf-8")
    cbor_bytes = cbor2.dumps(preset.data)
    compressed = zstandard.ZstdCompressor(level=_ZSTD_COMPRESSION_LEVEL).compress(cbor_bytes)

    out = bytearray()
    out += MAGIC
    out += _HEADER_STRUCT.pack(len(meta_bytes), 0)
    out += meta_bytes
    out += _HEADER_STRUCT.pack(len(cbor_bytes), 2)
    out += compressed
    return bytes(out)


def pack_file(preset: SerumPreset, path: str | Path) -> Path:
    """Encode a :class:`SerumPreset` and write it to disk. Returns the written path."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(pack_bytes(preset))
    return dest
