"""Lightweight, numpy-only acoustic descriptors for a single one-shot audio
file.

Complements ``tools/list_sample_files.py``'s filename/folder-based browsing:
category folders in a real sample bank ("Pluck"/"Bell"/"Key"/"String") are
usually reliably named, but individual filenames *within* a category often
aren't ("Sample_004.wav") -- this gives the calling model an objective
secondary signal to pick between candidates in that case.

Deliberately does **not** guess instrument identity ("this is a kick") --
that needs a trained classifier and labeled data this project doesn't have,
and a wrong confident guess is worse than no guess (this project's usual
evidence standard, see ``CONTRIBUTING.md``). Instead this exposes
well-understood, individually-interpretable signal-processing quantities --
peak/RMS level, spectral brightness, tonal-vs-noisy texture, a gated pitch
estimate, attack/sustain shape -- for the calling model (which already has
the file's name and folder context) to combine into its own judgment.

``peak_dbfs``/``rms_dbfs`` exist specifically for gain-matching multiple
``sample_playback_source`` layers in one preset: raw one-shot libraries are
not recorded/normalized to a common level, so two files can need very
different ``OscillatorSpec.volume`` values to sound equally present --
guessing a volume without checking these first risks a layer that's
audible in isolation but effectively silent once mixed against louder
layers (found live: an 18dB RMS gap between two one-shots in the same
preset, with volume set almost the same for both).

Validated informally (a sanity check, not a rigorous evaluation) against 5
real one-shots from two different factory sample packs:

- a bell: spectral centroid 1894Hz, flatness 0.082 (correctly tonal), pitch
  correctly found at **C5** -- independently confirming this project's live
  pitch-reference finding for the ``SampleOsc`` engine (see
  ``docs/PARAMETER_SCHEMA.md`` §8).
- a kick: 168Hz, flatness 0.001 (correctly dark and tonal). The *first*
  version of the pitch estimator here locked onto a spurious ~1520Hz
  "pitch" for this file (a kick's real content is ~60-170Hz) -- purely an
  autocorrelation artifact of the transient, not a real fundamental. The
  centroid-consistency gate below exists specifically because of this
  finding.
- a hi-hat: 10280Hz, flatness 0.360 (correctly bright, noisy, unpitched).
- a snare and a clap, both correctly read as bright/noisy/unpitched (the
  snare's estimated pitch, ~F#4 at moderate confidence, plausibly reflects
  its drum-shell body resonance rather than being wrong).
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from .wavetable import read_wav_mono

_SUPPORTED_EXTENSIONS = (".wav",)

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Spectral centroid bucket boundaries (Hz) -- picked from where the 5
# real one-shots in the validation set landed (kick 168Hz dark, bell 1894Hz
# warm, snare 3134Hz / clap 4617Hz bright, hihat 10280Hz airy), not a
# published standard. Treat as a rough perceptual bucketing, not a precise
# boundary -- `spectral_centroid_hz` is included in the result for anyone
# who wants the raw number instead.
_BRIGHTNESS_BUCKETS: tuple[tuple[float, str], ...] = (
    (500.0, "dark"),
    (2000.0, "warm"),
    (6000.0, "bright"),
    (float("inf"), "airy"),
)

# Spectral flatness bucket boundaries -- same caveat, picked from where the
# validation set landed (kick 0.001 / bell 0.082 clearly tonal, snare 0.294 /
# clap 0.277 / hihat 0.360 clearly noisier).
_TEXTURE_BUCKETS: tuple[tuple[float, str], ...] = (
    (0.15, "tonal"),
    (0.30, "mixed"),
    (float("inf"), "noisy"),
)

_PITCH_MIN_HZ = 50.0
_PITCH_MAX_HZ = 1500.0
_PITCH_MIN_CONFIDENCE = 0.5
# A genuine fundamental for real one-shot content doesn't usually sit far
# ABOVE the spectral centroid (energy-weighted, so for harmonic content it
# normally sits at or above the fundamental) -- see the kick false-positive
# in the module docstring. This gate rejects that failure mode.
_PITCH_CENTROID_GATE_RATIO = 1.5


def _bucket(value: float, boundaries: tuple[tuple[float, str], ...]) -> str:
    for threshold, label in boundaries:
        if value < threshold:
            return label
    return boundaries[-1][1]


def _attack_and_sustain(samples: np.ndarray, sample_rate: int) -> tuple[float, float]:
    """Returns ``(attack_seconds, sustain_ratio)``: time from the start of
    the file to its peak RMS level, and the fraction of 10ms windows that
    stay within -12dB of that peak (a rough percussive-vs-sustained signal --
    exposed as a raw ratio rather than a forced percussive/sustained label,
    since a slow-decaying long tail, e.g. a bell, doesn't cleanly fit either
    bucket)."""
    win = max(1, int(0.01 * sample_rate))
    n_windows = len(samples) // win
    if n_windows < 2:
        return 0.0, 0.0
    rms = np.array(
        [
            np.sqrt(np.mean(samples[i * win : (i + 1) * win].astype(np.float64) ** 2))
            for i in range(n_windows)
        ]
    )
    peak_idx = int(np.argmax(rms))
    peak = rms[peak_idx] + 1e-12
    above_threshold = rms > (peak * 10 ** (-12 / 20))
    sustain_ratio = float(np.sum(above_threshold)) / n_windows
    return peak_idx * win / sample_rate, sustain_ratio


def _spectral_features(samples: np.ndarray, sample_rate: int) -> tuple[float, float]:
    """Returns ``(centroid_hz, flatness)`` from the whole file's FFT
    magnitude spectrum. ``flatness`` is the ratio of the geometric to
    arithmetic mean of the spectrum (0 = pure tone, 1 = white noise)."""
    n = len(samples)
    if n < 2:
        return 0.0, 0.0
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(samples * window))
    freqs = np.fft.rfftfreq(n, d=1 / sample_rate)
    mag_sum = spectrum.sum() + 1e-12
    centroid = float((spectrum * freqs).sum() / mag_sum)

    eps = 1e-12
    geo_mean = np.exp(np.mean(np.log(spectrum + eps)))
    arith_mean = np.mean(spectrum) + eps
    flatness = float(geo_mean / arith_mean)
    return centroid, flatness


_SILENCE_FLOOR_DBFS = -120.0


def _loudness(samples: np.ndarray) -> tuple[float, float]:
    """Returns ``(peak_dbfs, rms_dbfs)`` -- absolute level relative to full
    scale (0dBFS = a sample at +/-1.0). Found live: two one-shots from the
    same combined preset measured 18dB apart in RMS despite both having
    OscillatorSpec.volume in the same ballpark (0.55 vs 0.75) -- raw sample
    libraries are not gain-matched to each other, so ``volume`` alone can't
    correct for it without first knowing how loud the *source file* already
    is. Floored at ``_SILENCE_FLOOR_DBFS`` instead of returning -inf for a
    silent/near-silent file."""
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) if len(samples) else 0.0
    peak_dbfs = 20.0 * np.log10(peak) if peak > 1e-9 else _SILENCE_FLOOR_DBFS
    rms_dbfs = 20.0 * np.log10(rms) if rms > 1e-9 else _SILENCE_FLOOR_DBFS
    return max(peak_dbfs, _SILENCE_FLOOR_DBFS), max(rms_dbfs, _SILENCE_FLOOR_DBFS)


def _zero_crossing_rate(samples: np.ndarray) -> float:
    if len(samples) < 2:
        return 0.0
    signs = np.sign(samples)
    signs[signs == 0] = 1
    crossings = np.sum(signs[:-1] != signs[1:])
    return float(crossings) / len(samples)


def _freq_to_note(freq: float) -> str:
    midi = 69 + 12 * np.log2(freq / 440.0)
    midi_round = int(round(midi))
    note = _NOTE_NAMES[midi_round % 12]
    octave = midi_round // 12 - 1
    cents = (midi - midi_round) * 100
    return f"{note}{octave}{cents:+.0f}c"


def _estimate_pitch(
    samples: np.ndarray, sample_rate: int, centroid_hz: float
) -> tuple[str | None, float | None, float]:
    """Autocorrelation pitch estimate on the loudest ~50ms window, gated
    against implausible results (see ``_PITCH_CENTROID_GATE_RATIO``).
    Returns ``(note_name_or_None, frequency_hz_or_None, confidence)`` --
    ``confidence`` is returned even when the estimate is rejected, so a
    caller can tell "no pitch found" apart from "found one but distrusted
    it"."""
    win = min(int(0.05 * sample_rate), len(samples)) or 1
    hop = win // 2 or 1
    best_start, best_rms = 0, -1.0
    for start in range(0, max(1, len(samples) - win), hop):
        seg = samples[start : start + win]
        r = np.sqrt(np.mean(seg.astype(np.float64) ** 2))
        if r > best_rms:
            best_rms, best_start = r, start
    seg = samples[best_start : best_start + win].astype(np.float64)
    seg = seg - seg.mean()
    corr = np.correlate(seg, seg, mode="full")[len(seg) - 1 :]
    if corr[0] <= 1e-12:
        return None, None, 0.0

    corr = corr / corr[0]
    min_lag = max(1, int(sample_rate / _PITCH_MAX_HZ))
    max_lag = min(int(sample_rate / _PITCH_MIN_HZ), len(corr) - 1)
    if max_lag <= min_lag:
        return None, None, 0.0

    segment = corr[min_lag:max_lag]
    peak_lag = int(np.argmax(segment)) + min_lag
    confidence = float(corr[peak_lag])
    if confidence < _PITCH_MIN_CONFIDENCE:
        return None, None, confidence

    freq = sample_rate / peak_lag
    if freq > centroid_hz * _PITCH_CENTROID_GATE_RATIO:
        return None, None, confidence

    return _freq_to_note(freq), freq, confidence


def _midi_note_to_name(midi_note: int) -> str:
    octave = midi_note // 12 - 1
    return f"{_NOTE_NAMES[midi_note % 12]}{octave}"


def _parse_inst_chunk(body: bytes) -> dict[str, int] | None:
    """RIFF `inst` chunk: 7 bytes, root note + tuning/gain + key/velocity
    range, authored by whoever built the sample pack -- not something this
    project infers."""
    if len(body) < 7:
        return None
    unshifted_note, fine_tune, gain, *_ = struct.unpack_from("<BbbBBBB", body, 0)
    return {"root_note_midi": unshifted_note, "fine_tune_cents": fine_tune, "gain_db": gain}


def _parse_smpl_chunk(body: bytes) -> dict[str, object] | None:
    """RIFF `smpl` chunk: root note (`dwMIDIUnityNote`) plus, if present,
    sample-accurate loop points from its first loop record -- both authored
    by the sample's creator, not inferred."""
    if len(body) < 36:
        return None
    _, _, _, midi_unity_note, _, _, _, num_loops, _ = struct.unpack_from("<9I", body, 0)
    result: dict[str, object] = {"root_note_midi": midi_unity_note}
    if num_loops > 0 and len(body) >= 36 + 24:
        _, loop_type, start, end, _, play_count = struct.unpack_from("<6I", body, 36)
        result["loop_type"] = {0: "forward", 1: "ping_pong", 2: "backward"}.get(
            loop_type, "unknown"
        )
        result["loop_start_frame"] = start
        result["loop_end_frame"] = end
        result["loop_play_count"] = play_count  # 0 == infinite
    return result


def read_embedded_metadata(path: Path) -> dict[str, object]:
    """Parse RIFF `inst`/`smpl` chunks, if present, for sampler metadata
    authored by whoever created the sample -- root note, tuning, and
    sample-accurate loop points. This is real, human-authored ground truth
    when available -- a stronger signal than this module's own DSP
    estimates (`pitch`/`pitch_confidence`) or a guessed octave. **Not
    universal**: confirmed absent from an entire KSHMR vocal/choir pack
    checked during development, present in others (e.g. an Ellis Lost bell
    one-shot declared `root_note_midi: 60`, i.e. C4) -- always returns a
    dict (empty if neither chunk is present), never guesses or raises.
    """
    raw = path.read_bytes()
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return {}

    chunks: dict[bytes, bytes] = {}
    pos = 12
    while pos + 8 <= len(raw):
        chunk_id = raw[pos : pos + 4]
        (chunk_size,) = struct.unpack_from("<I", raw, pos + 4)
        chunks[chunk_id] = raw[pos + 8 : pos + 8 + chunk_size]
        pos += 8 + chunk_size + (chunk_size & 1)

    smpl_info = _parse_smpl_chunk(chunks[b"smpl"]) if b"smpl" in chunks else None
    inst_info = _parse_inst_chunk(chunks[b"inst"]) if b"inst" in chunks else None

    result: dict[str, object] = {}
    # smpl's root note is paired with the sample-accurate loop points in
    # the same chunk, so prefer it as the more complete/consistent source
    # when both chunks are present.
    root_source = smpl_info or inst_info
    if root_source is not None:
        midi_note = root_source["root_note_midi"]
        result["root_note_midi"] = midi_note
        result["root_note"] = _midi_note_to_name(midi_note)
    if inst_info is not None:
        result["root_note_fine_tune_cents"] = inst_info["fine_tune_cents"]
    if smpl_info is not None and "loop_start_frame" in smpl_info:
        result["loop_type"] = smpl_info["loop_type"]
        result["loop_start_frame"] = smpl_info["loop_start_frame"]
        result["loop_end_frame"] = smpl_info["loop_end_frame"]
        result["loop_play_count"] = smpl_info["loop_play_count"]

    return result


def analyze_sample(path: Path) -> dict[str, object]:
    """Compute lightweight acoustic descriptors for one ``.wav`` file. See
    the module docstring for scope and validation notes.

    Raises :class:`ValueError` for any extension other than ``.wav`` (this
    project can only decode WAV audio content, see
    ``preset/wavetable.py::read_wav_mono``) or for a malformed file.
    """
    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ValueError(f"analyze_sample only supports .wav files; got {path.suffix!r} for {path}")

    samples, sample_rate = read_wav_mono(path)
    duration_seconds = len(samples) / sample_rate
    total_frames = len(samples)

    peak_dbfs, rms_dbfs = _loudness(samples)
    attack_seconds, sustain_ratio = _attack_and_sustain(samples, sample_rate)
    centroid_hz, flatness = _spectral_features(samples, sample_rate)
    zcr = _zero_crossing_rate(samples)
    note, pitch_hz, pitch_confidence = _estimate_pitch(samples, sample_rate, centroid_hz)
    embedded = read_embedded_metadata(path)
    if "loop_start_frame" in embedded and total_frames > 0:
        embedded["loop_start_percent"] = round(
            100.0 * embedded["loop_start_frame"] / total_frames, 2
        )
        embedded["loop_end_percent"] = round(100.0 * embedded["loop_end_frame"] / total_frames, 2)

    return {
        "duration_seconds": round(duration_seconds, 3),
        "peak_dbfs": round(peak_dbfs, 1),
        "rms_dbfs": round(rms_dbfs, 1),
        "brightness": _bucket(centroid_hz, _BRIGHTNESS_BUCKETS),
        "spectral_centroid_hz": round(centroid_hz, 1),
        "texture": _bucket(flatness, _TEXTURE_BUCKETS),
        "spectral_flatness": round(flatness, 4),
        "zero_crossing_rate": round(zcr, 4),
        "pitch": note,
        "pitch_hz": round(pitch_hz, 1) if pitch_hz is not None else None,
        "pitch_confidence": round(pitch_confidence, 2),
        "attack_ms": round(attack_seconds * 1000, 1),
        "sustain_ratio": round(sustain_ratio, 3),
        "embedded_metadata": embedded,
    }
