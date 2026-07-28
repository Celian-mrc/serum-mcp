"""Copy user-provided one-shot audio files into Serum's Samples library for
true playback via the SampleOsc engine (``OscillatorSpec.sample_playback_source``).

Unlike :mod:`serum_mcp.preset.wavetable`'s sample-to-wavetable slicing (which
resynthesizes new audio from the source file), this module never touches the
audio data: it copies the original file byte-for-byte into
``Samples/User/serum-mcp/`` and reads only the WAV header for the
``numChannels``/``sampleRate``/``numFrames`` metadata ``SampleOsc{i}`` needs
alongside the file reference. Preserving the original bytes exactly is the
whole point of this engine over wavetable slicing -- the one-shot's actual
recorded character survives instead of becoming loop-buzzy synthesized
material.

Reverse-engineered by inspecting real factory presets that use ``SampleOsc``
(41 oscillator slots across ~626 presets), not from any Xfer documentation --
see ``docs/PARAMETER_SCHEMA.md``. Every factory-authored reference observed
during that survey pointed at a ``.flac`` file; this module only supports
``.wav`` for now, since that's the one format this project can read metadata
for without a FLAC parser. Confirmed live (2026-07-28, real Serum 2 in FL
Studio 21) that Serum accepts a plain ``.wav`` here despite every factory
reference being ``.flac`` -- ``.flac`` support remains a possible future
addition, not a blocker.
"""

from __future__ import annotations

import hashlib
import shutil
import struct
from pathlib import Path

import numpy as np

_SUPPORTED_EXTENSIONS = (".wav",)

# Only correct stereo balance if the channels differ by more than this --
# avoids needlessly re-encoding (and losing a little precision to 16-bit
# requantization) a file that's already essentially centered.
_PAN_IMBALANCE_THRESHOLD_DB = 1.0

# Bump whenever the balancing algorithm changes in a way that alters output
# for the same input (e.g. switching from RMS- to peak-based gain, as
# happened here -- found live: a file RMS-centered to 0.00dB still showed a
# real 2.7dB PEAK imbalance, because a single loud transient on one channel
# doesn't move the RMS much but fully dominates a peak meter, which is what
# a DAW mixer actually displays). Folded into the cache filename so an
# already-written file from the old algorithm doesn't keep silently serving
# stale, still-imbalanced-on-peak audio after a fix -- the same staleness
# bug class ``wavetable.py``'s ``_SYNTHESIS_VERSION`` exists to prevent.
_PAN_CORRECTION_VERSION = 2


def read_wav_metadata(path: Path) -> tuple[int, int, int]:
    """Return ``(num_channels, sample_rate, num_frames)`` from a WAV file's
    ``fmt ``/``data`` chunk headers, without decoding the audio itself --
    the file is copied byte-for-byte elsewhere, so only the metadata Serum
    needs alongside the reference is read here."""
    raw = path.read_bytes()
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"{path} is not a RIFF/WAVE file")

    channels: int | None = None
    sample_rate: int | None = None
    bits_per_sample: int | None = None
    data_size: int | None = None

    pos = 12
    while pos + 8 <= len(raw):
        chunk_id = raw[pos : pos + 4]
        (chunk_size,) = struct.unpack_from("<I", raw, pos + 4)
        if chunk_id == b"fmt ":
            _, channels, sample_rate, _, _, bits_per_sample = struct.unpack_from(
                "<HHIIHH", raw, pos + 8
            )
        elif chunk_id == b"data":
            data_size = chunk_size
        pos += 8 + chunk_size + (chunk_size & 1)  # chunks are word-aligned

    if channels is None or sample_rate is None or data_size is None or not bits_per_sample:
        raise ValueError(f"{path} is missing a fmt or data chunk")

    bytes_per_frame = channels * (bits_per_sample // 8)
    num_frames = data_size // bytes_per_frame
    return channels, sample_rate, num_frames


def sample_library_filename(source_path: Path, *, centered: bool = False) -> str:
    """Deterministic filename for a copied one-shot, keyed on the source
    file's own content (so re-referencing the same file across presets
    reuses one copy, and editing the source in place -- same filename, new
    bytes -- produces a fresh copy instead of a stale one) plus its
    extension, since Serum picks a decoder from it. ``centered`` is folded
    into the hash payload so a pan-corrected copy and a verbatim copy of
    the same source file never collide under the same filename -- toggling
    ``sample_center_pan`` must produce a distinct cache entry, not silently
    keep serving whichever version happened to be written first (the same
    staleness bug class documented on ``wavetable.py``'s
    ``_SYNTHESIS_VERSION``)."""
    content_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()[:16]
    marker = f"_centered_v{_PAN_CORRECTION_VERSION}" if centered else ""
    return f"smp_{content_hash}{marker}{source_path.suffix.lower()}"


def _decode_wav_samples(path: Path) -> tuple[np.ndarray, int]:
    """Decode a WAV file's full audio to a ``(num_frames, num_channels)``
    float32 array in roughly [-1, 1], plus its sample rate. Supports the
    same 16/24/32-bit PCM and 32-bit float formats as
    :func:`read_wav_metadata`. Deliberately separate from
    :mod:`serum_mcp.preset.wavetable`'s ``read_wav_mono`` -- that one
    downmixes to mono for wavetable slicing, which would destroy exactly
    the per-channel information pan-centering needs to measure."""
    raw = path.read_bytes()
    fmt_tag = channels = sample_rate = bits_per_sample = None
    data_bytes: bytes | None = None

    pos = 12
    while pos + 8 <= len(raw):
        chunk_id = raw[pos : pos + 4]
        (chunk_size,) = struct.unpack_from("<I", raw, pos + 4)
        if chunk_id == b"fmt ":
            fmt_tag, channels, sample_rate, _, _, bits_per_sample = struct.unpack_from(
                "<HHIIHH",
                raw,
                pos + 8,
            )
        elif chunk_id == b"data":
            data_bytes = raw[pos + 8 : pos + 8 + chunk_size]
        pos += 8 + chunk_size + (chunk_size & 1)

    if fmt_tag is None or data_bytes is None or channels is None:
        raise ValueError(f"{path} is missing a fmt or data chunk")

    if fmt_tag == 3 and bits_per_sample == 32:
        flat = np.frombuffer(data_bytes, dtype="<f4").astype(np.float32)
    elif fmt_tag == 1 and bits_per_sample == 16:
        flat = np.frombuffer(data_bytes, dtype="<i2").astype(np.float32) / 32768.0
    elif fmt_tag == 1 and bits_per_sample == 24:
        raw24 = np.frombuffer(data_bytes, dtype=np.uint8)
        raw24 = raw24[: len(raw24) - (len(raw24) % 3)].reshape(-1, 3)
        padded = np.zeros((raw24.shape[0], 4), dtype=np.uint8)
        padded[:, 1:] = raw24
        flat = padded.view("<i4").astype(np.float32).flatten() / float(2**31)
    elif fmt_tag == 1 and bits_per_sample == 32:
        flat = np.frombuffer(data_bytes, dtype="<i4").astype(np.float32) / float(2**31)
    else:
        raise ValueError(
            f"{path}: unsupported WAV format (format tag {fmt_tag}, {bits_per_sample}-bit)"
        )

    samples = flat.reshape(-1, channels)
    return samples, sample_rate


def _channel_balance_gains(samples: np.ndarray) -> tuple[float, float] | None:
    """Given a ``(num_frames, num_channels)`` array, return
    ``(gain_left, gain_right)`` that brings both channels to the same
    target PEAK level -- their geometric mean, which redistributes level
    rather than just attenuating the louder channel, so overall loudness
    doesn't drop. Targets peak, not RMS: a DAW mixer's level meters read
    peak, and a file can have perfectly balanced RMS while still showing a
    real peak imbalance from a single louder transient on one channel (see
    ``_PAN_CORRECTION_VERSION``'s note -- found live, an RMS-centered file
    still measured +2.7dB louder on the left channel's peak). Returns
    ``None`` if the file isn't stereo, either channel is silent, or the
    channels' peaks are already within ``_PAN_IMBALANCE_THRESHOLD_DB`` of
    each other (correcting would be pointless and would only cost a
    needless re-encode)."""
    if samples.ndim != 2 or samples.shape[1] != 2:
        return None
    peak_l = float(np.max(np.abs(samples[:, 0])))
    peak_r = float(np.max(np.abs(samples[:, 1])))
    if peak_l <= 1e-9 or peak_r <= 1e-9:
        return None
    imbalance_db = 20.0 * np.log10(peak_l / peak_r)
    if abs(imbalance_db) < _PAN_IMBALANCE_THRESHOLD_DB:
        return None
    target = float(np.sqrt(peak_l * peak_r))
    return target / peak_l, target / peak_r


def _write_wav_pcm16(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """Write a standard 16-bit PCM WAV file -- no wavetable-specific ``clm``
    marker or other special-casing, since SampleOsc just needs a normal,
    valid WAV (confirmed live). ``samples`` is ``(num_frames,
    num_channels)`` in roughly [-1, 1]."""
    channels = samples.shape[1] if samples.ndim == 2 else 1
    clipped = np.clip(samples, -1.0, 1.0)
    data = (clipped * 32767.0).astype("<i2").tobytes()
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    fmt_chunk = struct.pack(
        "<HHIIHH", 1, channels, sample_rate, byte_rate, block_align, bits_per_sample
    )
    body = bytearray()
    body += b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"data" + struct.pack("<I", len(data)) + data
    riff = bytearray(b"RIFF")
    riff += struct.pack("<I", 4 + len(body))
    riff += b"WAVE"
    riff += body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(riff))


def copy_sample_to_library(
    source_path: Path, dest_root: Path, subdir: tuple[str, ...], *, center_pan: bool = True
) -> Path:
    """Copy ``source_path`` into ``dest_root/subdir/`` under a
    content-hashed filename, if not already there. Returns the destination path.

    If ``center_pan`` is true (the default) and the file is stereo with a
    measurable level imbalance between channels (see
    ``_PAN_IMBALANCE_THRESHOLD_DB`` -- real one-shots often have one, e.g.
    an off-center mic placement in the original recording), each channel is
    scaled by a linear gain to bring both to the same peak level before
    writing -- this only rebalances level, it doesn't sum to mono or alter
    either channel's actual waveform/character, so the recording's stereo
    width and content survive, just centered. Mono files, or stereo files
    that are already balanced, are copied byte-for-byte unchanged (no
    needless re-encode). Pass ``center_pan=False`` to always copy verbatim.

    Raises :class:`ValueError` for any extension other than ``.wav`` --
    see the module docstring for why FLAC isn't supported yet.
    """
    if source_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"sample_playback_source {source_path} has unsupported extension "
            f"{source_path.suffix!r}; only {_SUPPORTED_EXTENSIONS} is supported. "
            "Serum's own factory library uses .flac here, but this project can't "
            "yet read FLAC metadata -- convert the file to WAV first."
        )

    gains = None
    if center_pan:
        samples, sample_rate = _decode_wav_samples(source_path)
        gains = _channel_balance_gains(samples)

    if gains is None:
        filename = sample_library_filename(source_path, centered=False)
        dest = dest_root.joinpath(*subdir, filename)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, dest)
        return dest

    gain_l, gain_r = gains
    corrected = samples.copy()
    corrected[:, 0] *= gain_l
    corrected[:, 1] *= gain_r
    filename = sample_library_filename(source_path, centered=True)
    dest = dest_root.joinpath(*subdir, filename)
    if not dest.exists():
        _write_wav_pcm16(dest, corrected, sample_rate)
    return dest
