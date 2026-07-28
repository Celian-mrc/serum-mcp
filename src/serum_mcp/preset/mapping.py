"""Merge a semantic :class:`~serum_mcp.generation.spec.PresetSpec` onto the
raw CBOR payload of a base preset (typically ``fixtures/init_preset.SerumPreset``).

Only the fields present on the spec are touched -- everything else in the
base preset's ``data`` dict (mod matrix, arpeggiator, GUI state, unmodeled
oscillator engines, ...) passes through unchanged, so editing an existing
preset only perturbs what the instruction actually asked for.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from serum_mcp import config
from serum_mcp.generation.spec import FxUnitSpec, ModRouteSpec, OscillatorSpec, PresetSpec

from . import sample_library, schema, wavetable
from .validator import validate_params

_CUSTOM_WAVETABLE_SUBDIR = ("User", "serum-mcp")
_MAX_CUSTOM_WAVETABLE_FRAMES = 256
_CUSTOM_SAMPLE_SUBDIR = ("User", "serum-mcp")

_OSC_KEYS = {
    "octave": "kParamOctave",
    "semitone": "kParamPitch",
    "volume": "kParamVolume",
    "pan": "kParamPan",
    "unison": "kParamUnison",
    "detune": "kParamDetune",
}
_WTOSC_KEYS = {
    "table_position": "kParamTablePos",
    "warp_amount": "kParamWarp",
}
_SAMPLEOSC_KEYS = {
    "warp_amount": "kParamWarp",
}
# Which slot indices use which sound-source engine. Slots 0-2 (Osc A/B/C)
# default to the wavetable engine (or the sample-playback engine, if
# sample_playback_source is set); slot 3 is always Noise, slot 4 always
# Sub -- real Serum presets never have a WTOsc3/WTOsc4/SampleOsc3/SampleOsc4
# key, only NoiseOsc3/SubOsc4, so none of this must be written there (see
# docs/PARAMETER_SCHEMA.md).
_WTOSC_SLOTS = (0, 1, 2)
_NOISE_SLOT = 3
_SUB_SLOT = 4
_ENGINE_TYPE_WT = "kOsc_WT"
_ENGINE_TYPE_SAMPLE = "kOsc_Sample"
_FILTER_KEYS = {
    "cutoff": "kParamFreq",
    "resonance": "kParamReso",
    "drive": "kParamDrive",
    "stereo": "kParamStereo",
}
_ENV_KEYS = {
    "attack": "kParamAttack",
    "hold": "kParamHold",
    "decay": "kParamDecay",
    "sustain": "kParamSustain",
    "release": "kParamRelease",
}
_LFO_KEYS = {
    "rate": "kParamRate",
    "beat_sync": "kParamBeatSync",
    "delay": "kParamDelay",
    "rise": "kParamRise",
    "smooth": "kParamSmooth",
}


def _plain_params(container: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``container[key]["plainParams"]`` as a real dict, replacing the
    sentinel string ``"default"`` Serum uses for untouched modules with {}."""
    sub = container.setdefault(key, {})
    if not isinstance(sub.get("plainParams"), dict):
        sub["plainParams"] = {}
    return sub["plainParams"]


def _resolve_sample_playback(osc: OscillatorSpec) -> schema.SampleAudioDef:
    """Resolve an oscillator's ``sample_playback_source`` into a
    :class:`schema.SampleAudioDef`: copy the referenced WAV into Serum's
    Samples/User/serum-mcp folder (if not already there) -- pan-balanced
    per ``osc.sample_center_pan`` -- and read its header metadata, so
    ``SampleOsc{i}`` plays the file back as recorded (just re-centered, if
    requested) -- see ``preset/sample_library.py``."""
    source_path = Path(osc.sample_playback_source)
    if not source_path.is_file():
        raise ValueError(f"sample_playback_source {osc.sample_playback_source!r} does not exist")
    # Extension check first: copy_sample_to_library rejects unsupported
    # formats (e.g. .flac) with a clear message, whereas read_wav_metadata
    # would instead fail deep inside a RIFF parse with a confusing error.
    dest = sample_library.copy_sample_to_library(
        source_path,
        config.get_samples_dir(),
        _CUSTOM_SAMPLE_SUBDIR,
        center_pan=osc.sample_center_pan,
    )
    channels, sample_rate, num_frames = sample_library.read_wav_metadata(source_path)
    relative_path = "/".join((*_CUSTOM_SAMPLE_SUBDIR, dest.name))
    return schema.SampleAudioDef(relative_path, num_frames, sample_rate, channels)


def _resolve_wavetable(osc: OscillatorSpec) -> schema.WavetableDef:
    """Resolve an oscillator's wavetable: a curated factory table
    (schema.SIMPLE_WAVETABLES), a table synthesized from ``custom_harmonics``,
    or one sliced from a user audio file via ``sample_source`` -- in that
    priority order -- written to Serum's Tables/User folder as needed."""
    if osc.sample_source:
        source_path = Path(osc.sample_source)
        if not source_path.is_file():
            raise ValueError(f"sample_source {osc.sample_source!r} does not exist")
        if osc.sample_frames > _MAX_CUSTOM_WAVETABLE_FRAMES:
            raise ValueError(
                f"sample_frames is {osc.sample_frames}; max is {_MAX_CUSTOM_WAVETABLE_FRAMES}"
            )
        filename = wavetable.sample_wavetable_filename(source_path, osc.sample_frames)
        dest = config.get_tables_dir().joinpath(*_CUSTOM_WAVETABLE_SUBDIR, filename)
        if not dest.exists():
            samples, sample_rate = wavetable.read_wav_mono(source_path)
            frames = wavetable.slice_sample_to_frames(samples, sample_rate, osc.sample_frames)
            wavetable.write_wavetable_wav(dest, frames)
        relative_path = "/".join((*_CUSTOM_WAVETABLE_SUBDIR, filename))
        num_frames = osc.sample_frames * wavetable.FRAME_SIZE
        return schema.WavetableDef(relative_path, num_frames, wavetable.SAMPLE_RATE, 1)

    if osc.custom_harmonics:
        frames_harmonics = osc.custom_harmonics
        if len(frames_harmonics) > _MAX_CUSTOM_WAVETABLE_FRAMES:
            raise ValueError(
                f"custom_harmonics has {len(frames_harmonics)} frames; "
                f"max is {_MAX_CUSTOM_WAVETABLE_FRAMES}"
            )
        filename = wavetable.wavetable_filename(frames_harmonics)
        dest = config.get_tables_dir().joinpath(*_CUSTOM_WAVETABLE_SUBDIR, filename)
        if not dest.exists():
            frames = [wavetable.synthesize_frame(h) for h in frames_harmonics]
            wavetable.write_wavetable_wav(dest, frames)
        relative_path = "/".join((*_CUSTOM_WAVETABLE_SUBDIR, filename))
        num_frames = len(frames_harmonics) * wavetable.FRAME_SIZE
        return schema.WavetableDef(relative_path, num_frames, wavetable.SAMPLE_RATE, 1)

    wt_def = schema.SIMPLE_WAVETABLES.get(osc.wavetable)
    if wt_def is None:
        raise ValueError(
            f"unknown wavetable {osc.wavetable!r}; "
            f"expected one of {sorted(schema.SIMPLE_WAVETABLES)}"
        )
    return wt_def


def _build_fx_entry(fx: FxUnitSpec) -> dict[str, Any]:
    fx_module_key = fx.type
    if fx_module_key not in schema.FX_PARAMS:
        raise ValueError(f"unknown FX type {fx.type!r}; expected one of {sorted(schema.FX_PARAMS)}")
    fx_schema = schema.FX_PARAMS[fx_module_key]
    # Not every FX type has a wet/mix knob (FXEQ doesn't) -- forcing one in
    # unconditionally made FXEQ impossible to generate at all.
    plain_params: dict[str, Any] = {}
    if "kParamWet" in fx_schema:
        plain_params["kParamWet"] = fx.wet
    plain_params.update(fx.params)
    validate_params(fx_module_key, plain_params, fx_schema)

    type_id = next(i for i, name in schema.FX_TYPE_IDS.items() if name == fx_module_key)
    return {
        "type": type_id,
        "kUIParamMixOrGain": 0.0,
        fx_module_key: {"plainParams": plain_params},
    }


def _resolve_mod_destination(destination: str, fx_chain: list[FxUnitSpec]) -> schema.ModDestDef:
    """Resolve a mod-matrix destination name.

    Most destinations are static (fixed module type + slot index), looked
    up directly in ``schema.MOD_DEST_TARGETS``. FX destinations are the
    exception: an FX rack slot's ``destModuleTypeString`` is whichever FX
    type actually sits there (e.g. "FXReverb"), which is only known once
    ``fx_chain`` has been built -- so ``fx{i}.wet`` is resolved dynamically
    against ``fx_chain[i]`` instead of being a fixed table entry.
    """
    if destination in schema.MOD_DEST_TARGETS:
        return schema.MOD_DEST_TARGETS[destination]

    if destination.startswith("fx") and destination.endswith(".wet"):
        index_part = destination[len("fx") : -len(".wet")]
        if index_part.isdigit():
            index = int(index_part)
            if index >= len(fx_chain):
                raise ValueError(
                    f"mod destination {destination!r} references fx_chain[{index}], "
                    f"but fx_chain only has {len(fx_chain)} entries"
                )
            fx_type = fx_chain[index].type
            if fx_type not in schema.FX_PARAMS or "kParamWet" not in schema.FX_PARAMS[fx_type]:
                raise ValueError(f"{fx_type!r} (fx_chain[{index}]) has no kParamWet to modulate")
            # kParamWet -> destModuleParamID 1 is confirmed for every FX
            # type that has a wet knob at all (see docs/PARAMETER_SCHEMA.md).
            return schema.ModDestDef(fx_type, index, "kParamWet", 1)

    raise ValueError(
        f"unknown mod destination {destination!r}; expected one of "
        f"{sorted(schema.MOD_DEST_TARGETS)}, or 'fx{{i}}.wet' for an index into fx_chain"
    )


def _resolve_route_source(route: ModRouteSpec) -> int:
    if route.source not in schema.MOD_SOURCE_IDS:
        raise ValueError(
            f"unknown mod source {route.source!r}; expected one of {sorted(schema.MOD_SOURCE_IDS)}"
        )
    return schema.MOD_SOURCE_IDS[route.source]


def _build_modslot_entry(route: ModRouteSpec, fx_chain: list[FxUnitSpec]) -> dict[str, Any]:
    source_id = _resolve_route_source(route)
    dest = _resolve_mod_destination(route.destination, fx_chain)
    plain_params: dict[str, Any] = {"kParamAmount": route.amount}
    if route.bipolar:
        plain_params["kParamBipolar"] = True
    validate_params("ModSlot", plain_params, schema.MODSLOT_PARAMS)

    return {
        "source": [source_id, 0],
        "destModuleID": dest.dest_id,
        "destModuleParamID": dest.param_id,
        "destModuleParamName": dest.param_name,
        "destModuleTypeString": dest.dest_type,
        "plainParams": plain_params,
    }


def _find_existing_modslot_index(
    data: dict[str, Any], source_id: int, dest: schema.ModDestDef
) -> int | None:
    """Find a ModSlot already routing from ``source_id`` to ``dest``, so an
    edit_preset call that updates that route's amount/bipolar overwrites it
    in place instead of accumulating a second, additive route in a
    different slot -- found live: editing a route's amount on an
    already-generated preset left both the old and new route active,
    silently doubling up the modulation."""
    for key, entry in data.items():
        if not (
            isinstance(key, str) and key.startswith("ModSlot") and key[len("ModSlot") :].isdigit()
        ):
            continue
        if not isinstance(entry, dict):
            continue
        src = entry.get("source")
        if not (isinstance(src, list) and len(src) == 2 and src[0] == source_id):
            continue
        if (
            entry.get("destModuleTypeString") == dest.dest_type
            and entry.get("destModuleID") == dest.dest_id
            and entry.get("destModuleParamName") == dest.param_name
        ):
            return int(key[len("ModSlot") :])
    return None


def _resolve_modslot_indices(
    data: dict[str, Any], routes: list[ModRouteSpec], fx_chain: list[FxUnitSpec]
) -> list[int]:
    """Assign a ModSlot index to each route in ``routes``: reuse an
    existing slot already routing the same (source, destination) pair if
    one exists, otherwise allocate a free slot (see
    ``_find_existing_modslot_index``)."""
    assignments: list[int | None] = []
    for route in routes:
        source_id = _resolve_route_source(route)
        dest = _resolve_mod_destination(route.destination, fx_chain)
        assignments.append(_find_existing_modslot_index(data, source_id, dest))

    free = iter(_free_modslot_indices(data, assignments.count(None)))
    return [idx if idx is not None else next(free) for idx in assignments]


def _free_modslot_indices(data: dict[str, Any], count: int) -> list[int]:
    used = {
        int(k[len("ModSlot") :])
        for k in data
        if isinstance(k, str) and k.startswith("ModSlot") and k[len("ModSlot") :].isdigit()
    }
    free = [i for i in range(64) if i not in used]
    if len(free) < count:
        raise ValueError(
            f"not enough free mod matrix slots: need {count}, only {len(free)} of 64 free"
        )
    return free[:count]


def apply_spec(base_data: dict[str, Any], spec: PresetSpec) -> dict[str, Any]:
    """Return a new raw ``data`` dict with ``spec`` merged onto ``base_data``."""
    data = copy.deepcopy(base_data)

    # Oscillator's own plainParams live directly on the Oscillator{i} dict,
    # not nested -- handled separately from the generic _plain_params helper
    # (which is for the sub-modules keyed *inside* Oscillator{i}, e.g. WTOsc{i}).
    for i, osc in enumerate(spec.oscillators):
        osc_container = data.setdefault(f"Oscillator{i}", {})
        if not isinstance(osc_container.get("plainParams"), dict):
            osc_container["plainParams"] = {}
        osc_params = osc_container["plainParams"]
        osc_params["kParamEnable"] = osc.enabled
        for spec_key, param_key in _OSC_KEYS.items():
            osc_params[param_key] = getattr(osc, spec_key)

        if i in _WTOSC_SLOTS:
            if osc.sample_playback_source:
                # kParamType is written explicitly on every call (not just
                # when switching TO sample playback) so a later partial edit
                # that switches this slot back to WT can't leave a stale
                # kOsc_Sample selector behind -- the same staleness risk
                # class documented on schema.OSCILLATOR_PARAMS["kParamType"].
                osc_params["kParamType"] = _ENGINE_TYPE_SAMPLE

                sample_key = f"SampleOsc{i}"
                sample_def = _resolve_sample_playback(osc)
                sample_container = osc_container.setdefault(sample_key, {})
                # File metadata, not a plainParams knob -- must match the
                # referenced audio file exactly or Serum may misread it (same
                # risk class as the CBOR bool/int wire-type bugs, see
                # docs/PARAMETER_SCHEMA.md).
                sample_container["samplePathRelative"] = sample_def.relative_path
                sample_container["numFrames"] = sample_def.num_frames
                sample_container["sampleRate"] = sample_def.sample_rate
                sample_container["numChannels"] = sample_def.num_channels

                sample_params = _plain_params(osc_container, sample_key)
                for spec_key, param_key in _SAMPLEOSC_KEYS.items():
                    sample_params[param_key] = getattr(osc, spec_key)
                sample_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                validate_params(sample_key, sample_params, schema.SAMPLEOSC_PARAMS)

                if osc.sample_loop != "off":
                    loop_mode = schema.SIMPLE_SAMPLE_LOOP_MODES.get(osc.sample_loop)
                    if loop_mode is None:
                        raise ValueError(
                            f"unknown sample_loop {osc.sample_loop!r}; expected 'off' or "
                            f"one of {sorted(schema.SIMPLE_SAMPLE_LOOP_MODES)}"
                        )
                    osc_params["kParamLoopMode"] = loop_mode
                    osc_params["kParamLoopStart"] = osc.sample_loop_start
                    osc_params["kParamLoopEnd"] = osc.sample_loop_end
                    osc_params["kParamLoopCrossfade"] = osc.sample_loop_crossfade
            else:
                osc_params["kParamType"] = _ENGINE_TYPE_WT

                wt_key = f"WTOsc{i}"
                wt_def = _resolve_wavetable(osc)
                wtosc_container = osc_container.setdefault(wt_key, {})
                # File metadata, not a plainParams knob -- must match the
                # referenced .wav exactly or Serum may misread the table (same
                # risk class as the CBOR bool/int wire-type bugs, see
                # docs/PARAMETER_SCHEMA.md). Real ints, not floats -- confirmed
                # against real Serum-saved presets.
                wtosc_container["relativePathToWT"] = wt_def.relative_path
                wtosc_container["numFrames"] = wt_def.num_frames
                wtosc_container["sampleRate"] = wt_def.sample_rate
                wtosc_container["numChannels"] = wt_def.num_channels

                wtosc_params = _plain_params(osc_container, wt_key)
                for spec_key, param_key in _WTOSC_KEYS.items():
                    wtosc_params[param_key] = getattr(osc, spec_key)
                wtosc_params["kParamWarpMenu"] = schema.SIMPLE_WARP_MODES.get(
                    osc.warp_mode, osc.warp_mode
                )
                validate_params(f"WTOsc{i}", wtosc_params, schema.WTOSC_PARAMS)
        elif i == _NOISE_SLOT:
            noise_params = _plain_params(osc_container, f"NoiseOsc{i}")
            noise_params["kParamNoiseType"] = osc.noise_type
            validate_params(f"NoiseOsc{i}", noise_params, schema.NOISEOSC_PARAMS)
        elif i == _SUB_SLOT:
            sub_params = _plain_params(osc_container, f"SubOsc{i}")
            sub_params["kParamShape"] = schema.SIMPLE_SUB_SHAPES.get(osc.sub_shape, osc.sub_shape)
            validate_params(f"SubOsc{i}", sub_params, schema.SUBOSC_PARAMS)
        validate_params(f"Oscillator{i}", osc_params, schema.OSCILLATOR_PARAMS)

    for i, flt in enumerate(spec.filters):
        filter_params = _plain_params(data, f"VoiceFilter{i}")
        filter_params["kParamEnable"] = flt.enabled
        filter_params["kParamType"] = schema.SIMPLE_FILTER_TYPES.get(flt.type, flt.type)
        for spec_key, param_key in _FILTER_KEYS.items():
            filter_params[param_key] = getattr(flt, spec_key)
        validate_params(f"VoiceFilter{i}", filter_params, schema.VOICE_FILTER_PARAMS)

    for i, env in enumerate(spec.envelopes):
        env_params = _plain_params(data, f"Env{i}")
        for spec_key, param_key in _ENV_KEYS.items():
            env_params[param_key] = getattr(env, spec_key)
        validate_params(f"Env{i}", env_params, schema.ENV_PARAMS)

    for i, lfo in enumerate(spec.lfos):
        lfo_params = _plain_params(data, f"LFO{i}")
        for spec_key, param_key in _LFO_KEYS.items():
            lfo_params[param_key] = getattr(lfo, spec_key)
        lfo_params["kParamMode"] = lfo.mode
        validate_params(f"LFO{i}", lfo_params, schema.LFO_PARAMS)

    for i, macro in enumerate(spec.macros):
        macro_container = data.setdefault(f"Macro{i}", {})
        if macro.name:
            macro_container["name"] = macro.name
        macro_params = _plain_params(data, f"Macro{i}")
        macro_params["kParamValue"] = macro.value
        validate_params(f"Macro{i}", macro_params, schema.MACRO_PARAMS)

    if spec.fx_chain:
        fx_rack = data.setdefault("FXRack0", {})
        fx_rack["FX"] = [_build_fx_entry(fx) for fx in spec.fx_chain]

    if spec.mod_routes:
        indices = _resolve_modslot_indices(data, spec.mod_routes, spec.fx_chain)
        for idx, route in zip(indices, spec.mod_routes, strict=True):
            data[f"ModSlot{idx}"] = _build_modslot_entry(route, spec.fx_chain)

    # Unlike oscillators/filters/envelopes/etc. (lists, only touched per
    # index when present), `global` is a single nested object that always
    # has a value -- PresetSpec() with no "global" key still gets a
    # default-valued GlobalSpec(). Without this check, every edit_preset
    # call that didn't explicitly repeat the current global settings would
    # silently reset them to defaults, breaking the "only change what you
    # specify" contract every other section honors.
    if "global_" in spec.model_fields_set:
        global_params = _plain_params(data, "Global0")
        global_params["kParamMasterVolume"] = spec.global_.master_volume
        global_params["kParamMonoToggle"] = spec.global_.mono
        global_params["kParamPortamentoTime"] = spec.global_.portamento_time
        global_params["kParamPolyCount"] = spec.global_.poly_count
        validate_params("Global0", global_params, schema.GLOBAL_PARAMS)

    return data
