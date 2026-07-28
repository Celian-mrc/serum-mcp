"""Synthesize and write custom Serum-compatible wavetable ``.wav`` files.

Serum's wavetable file format is undocumented, like everything else this
project reverse-engineers -- but unlike the CBOR preset format, nobody had
already cracked it publicly. Decoded this session by inspecting real
factory `.wav` files byte-for-byte:

- Standard RIFF/WAVE container, IEEE float (format tag 3), mono, 32-bit,
  44100 Hz.
- A non-standard ``clm `` chunk containing the literal ASCII text
  ``<!>2048 01000000 wavetable (www.xferrecords.com)`` -- confirmed
  identical across every factory table inspected (a fixed marker, not
  metadata that varies per file). ``2048`` is the frame size in samples:
  every file's total sample count divides evenly by 2048 with zero
  remainder across every table checked (7, 9, 24 and 112 frames observed).
- A ``data`` chunk of raw little-endian float32 samples, ``frame_size *
  num_frames`` samples long, each consecutive 2048-sample block being one
  single-cycle waveform frame that Serum's wavetable position control (0.0
  to ~256.0, see ``preset/schema.py``'s ``WTOSC_PARAMS``) scans through.

This has NOT been confirmed against Xfer's own source -- it's inferred from
consistent structure across multiple real files, the same evidence standard
used for the rest of this project's undocumented-format findings. Real
Serum-authored wavetables also carry a ``JUNK`` padding chunk before
``fmt ``; we reproduce it for structural fidelity even though RIFF readers
should ignore it.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np

FRAME_SIZE = 2048
SAMPLE_RATE = 44100
_CLM_MARKER = b"<!>2048 01000000 wavetable (www.xferrecords.com)"
_JUNK_PADDING = b"\x00" * 28


def synthesize_frame(harmonics: list[float], *, frame_size: int = FRAME_SIZE) -> np.ndarray:
    """Additive-synthesize one single-cycle waveform frame from a harmonic
    amplitude series (index 0 = fundamental, index 1 = 2nd harmonic, ...).

    Amplitudes are used as real-valued (cosine-phase) FFT bins and inverse
    Fourier transformed; the result is peak-normalized to 0.98 to avoid
    clipping while leaving headroom. Returns ``frame_size`` float32 samples.
    """
    max_harmonic = frame_size // 2
    if not harmonics:
        raise ValueError("harmonics must be a non-empty list")
    if len(harmonics) > max_harmonic:
        raise ValueError(
            f"too many harmonics ({len(harmonics)}); max is {max_harmonic} for a "
            f"{frame_size}-sample frame"
        )
    spectrum = np.zeros(frame_size // 2 + 1, dtype=np.complex128)
    spectrum[1 : len(harmonics) + 1] = harmonics
    waveform = np.fft.irfft(spectrum, n=frame_size)
    peak = float(np.max(np.abs(waveform)))
    if peak > 1e-9:
        waveform = waveform / peak * 0.98
    return waveform.astype(np.float32)


def write_wavetable_wav(
    path: Path, frames: list[np.ndarray], *, sample_rate: int = SAMPLE_RATE
) -> tuple[int, int, int]:
    """Write a Serum-compatible multi-frame wavetable ``.wav`` file.

    Returns ``(num_samples, sample_rate, num_channels)`` -- exactly what
    needs to go into a preset's ``WTOsc{i}`` block alongside the file path
    (see ``preset/mapping.py``).
    """
    data = np.concatenate(frames).astype("<f4")
    data_bytes = data.tobytes()
    channels = 1
    bits_per_sample = 32
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    fmt_chunk = struct.pack(
        "<HHIIHH", 3, channels, sample_rate, byte_rate, block_align, bits_per_sample
    )

    body = bytearray()
    body += b"JUNK" + struct.pack("<I", len(_JUNK_PADDING)) + _JUNK_PADDING
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"clm " + struct.pack("<I", len(_CLM_MARKER)) + _CLM_MARKER
    body += b"data" + struct.pack("<I", len(data_bytes)) + data_bytes

    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(riff))
    return len(data), sample_rate, channels


def wavetable_filename(frames_harmonics: list[list[float]]) -> str:
    """Deterministic filename for a given harmonic-series definition, so
    identical content across presets reuses one file instead of duplicating
    it, and different content never collides."""
    digest = hashlib.sha256(repr(frames_harmonics).encode()).hexdigest()[:16]
    return f"wt_{digest}.wav"
