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


def _soft_limit(waveform: np.ndarray, threshold: float, ceiling: float) -> np.ndarray:
    """Soft-knee limiter: samples at or below ``threshold`` pass through
    completely unchanged; only the portion of each sample's magnitude above
    ``threshold`` is compressed (via tanh) toward ``ceiling``.

    A plain ``tanh(x / ceiling) * ceiling`` compresses the *entire* signal
    once any sample exceeds the ceiling, including the many samples that
    were already well within range -- which is what undid the
    fundamental-anchoring in :func:`synthesize_frame` the first time this
    was tried (a waveform peaking at 2.5x ceiling got squashed hard enough
    that even its fundamental-dominated regions lost most of their level).
    Leaving everything below ``threshold`` untouched preserves that.
    """
    sign = np.sign(waveform)
    magnitude = np.abs(waveform)
    span = ceiling - threshold
    over = magnitude > threshold
    limited = magnitude.copy()
    if span > 0:
        limited[over] = threshold + span * np.tanh((magnitude[over] - threshold) / span)
    else:
        limited[over] = ceiling
    return sign * limited


def synthesize_frame(
    harmonics: list[float], *, frame_size: int = FRAME_SIZE, fundamental_level: float = 0.85
) -> np.ndarray:
    """Additive-synthesize one single-cycle waveform frame from a harmonic
    amplitude series (index 0 = fundamental, index 1 = 2nd harmonic, ...).

    Amplitudes are used as real-valued (cosine-phase) FFT bins and inverse
    Fourier transformed. Normalized so the *fundamental's own* contribution
    reaches ``fundamental_level`` -- not simply peak- or RMS-normalizing the
    combined waveform, which scales the whole signal down to fit whatever
    the harmonics' combined peak happens to be. That under-represents how
    loud the fundamental ends up once Serum's wavetable oscillator
    band-limits away upper harmonics at higher played pitches: observed
    live, a custom multi-harmonic table played back much quieter in upper
    octaves than a factory table with comparable harmonic content, with
    octave-independent factors (the shared filter/envelope) ruled out by
    A/B comparison. If anchoring the fundamental drives the combined peak
    over 1.0 (common for harmonic-rich content), a soft-knee limiter (see
    :func:`_soft_limit`) compresses only the excursions above
    ``fundamental_level`` -- the fundamental-dominated bulk of the waveform
    passes through unchanged, unlike a plain rescale/tanh over the whole
    signal, which would undo the anchoring this function exists to provide.
    Returns ``frame_size`` float32 samples.
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

    # A single unit-amplitude harmonic bin produces a sinusoid of peak
    # 2/frame_size (numpy's irfft scaling convention) -- so this is the
    # scale factor that puts the fundamental's own peak at fundamental_level.
    fundamental_amplitude = abs(harmonics[0])
    if fundamental_amplitude > 1e-9:
        natural_fundamental_peak = fundamental_amplitude * 2.0 / frame_size
        waveform = waveform * (fundamental_level / natural_fundamental_peak)

    peak = float(np.max(np.abs(waveform)))
    if peak > fundamental_level:
        waveform = _soft_limit(waveform, threshold=fundamental_level, ceiling=0.98)

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


# Bump whenever synthesize_frame's algorithm changes in a way that alters
# output for the same harmonics input (normalization scheme, limiter, ...).
# wavetable_filename folds this into the cache key specifically so that an
# existing file on disk (preset/mapping.py only (re)synthesizes if the
# target path doesn't already exist) can't silently keep serving stale
# audio content after a synthesis fix -- found the hard way: fixing a
# fundamental-level normalization bug had zero effect on an already-cached
# preset, because the file already existed under the same content hash and
# was never regenerated.
_SYNTHESIS_VERSION = 2


def wavetable_filename(frames_harmonics: list[list[float]]) -> str:
    """Deterministic filename for a given harmonic-series definition (and
    the current synthesis algorithm version), so identical content across
    presets reuses one file instead of duplicating it, different content
    never collides, and a synthesize_frame algorithm change always produces
    a fresh file instead of serving stale cached audio."""
    payload = repr((_SYNTHESIS_VERSION, frames_harmonics)).encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"wt_{digest}.wav"
