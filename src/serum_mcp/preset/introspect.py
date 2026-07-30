"""Read a raw CBOR payload back into a semantic
:class:`~serum_mcp.generation.spec.PresetSpec`.

The inverse of :func:`serum_mcp.preset.mapping.apply_spec`. Used to give the
LLM a compact, semantic view of an existing preset when editing it, and to
power ``describe_preset``. Missing/`"default"`-sentinel values fall back to
the confirmed defaults recorded in :mod:`.schema`.
"""

from __future__ import annotations

from typing import Any

from serum_mcp import config
from serum_mcp.generation.spec import (
    ArpPatternNoteSpec,
    ArpSpec,
    EnvelopeSpec,
    FilterSpec,
    FxUnitSpec,
    GlobalSpec,
    LfoSpec,
    MacroSpec,
    ModRouteSpec,
    OscillatorSpec,
    PresetSpec,
)

from . import schema

_REVERSE_FILTER_TYPES = {v: k for k, v in schema.SIMPLE_FILTER_TYPES.items()}
_REVERSE_WARP_MODES = {v: k for k, v in schema.SIMPLE_WARP_MODES.items()}
_REVERSE_ARP_SHAPES = {v: k for k, v in schema.SIMPLE_ARP_SHAPES.items()}
_REVERSE_WAVETABLES = {wt.relative_path: name for name, wt in schema.SIMPLE_WAVETABLES.items()}
_REVERSE_SAMPLE_LOOP_MODES = {v: k for k, v in schema.SIMPLE_SAMPLE_LOOP_MODES.items()}
_REVERSE_LFO_TYPES = {v: k for k, v in schema.SIMPLE_LFO_TYPES.items()}
_REVERSE_MOD_SOURCE_IDS = {v: k for k, v in schema.MOD_SOURCE_IDS.items()}
_REVERSE_MOD_DEST_TARGETS = {
    (d.dest_type, d.dest_id, d.param_name): name for name, d in schema.MOD_DEST_TARGETS.items()
}


def _resolve(plain_params: Any, key: str, param_defs: dict[str, schema.ParamDef]) -> Any:
    default = param_defs[key].default
    if not isinstance(plain_params, dict):
        return default
    return plain_params.get(key, default)


def _sub_plain_params(container: dict[str, Any], key: str) -> Any:
    sub = container.get(key)
    return sub.get("plainParams") if isinstance(sub, dict) else None


def count_unmodeled_fx_units(data: dict[str, Any]) -> int:
    """How many entries across FXRack0/1/2 are a structural FX routing type
    (FXSplit/FXSplit3/FXSplitMS -- parallel/multiband chains, found live in
    a real third-party bank) that :func:`extract_spec` silently skips rather
    than crashing on. Lets a caller like ``describe_preset`` surface that
    its reported ``fx_chain`` is incomplete instead of quietly under-
    reporting it -- these presets' FX racks aren't actually simpler than
    what's shown, this project just can't decode the branch structure yet
    (see docs/PARAMETER_SCHEMA.md)."""
    count = 0
    for rack_key in ("FXRack0", "FXRack1", "FXRack2"):
        for entry in (data.get(rack_key, {}) or {}).get("FX", []) or []:
            fx_name = schema.FX_TYPE_IDS.get(entry.get("type"))
            if fx_name is not None and fx_name in entry and fx_name not in schema.FX_PARAMS:
                count += 1
    return count


# Coarsest-first: straight subdivisions down to 64th notes, plus their
# triplet counterparts. Used to find the coarsest grid that explains a real
# preset's note timing/lengths within _ARP_GRID_TOLERANCE, rather than an
# exact GCD -- found live, a real preset's raw values include both genuine
# floating-point serialization noise around a clean value (e.g. 0.5,
# 0.49999999999999734, 0.5000000000000027 all meaning "half a beat") AND
# at least one genuinely non-gridded/"humanized" timestamp
# (0.4411764705882355, no clean musical fraction) in the same clip -- an
# exact-GCD approach is far too sensitive to either and can infer an
# absurdly fine step size (one real preset blew up to 62500 step-units for
# a single note this way).
_ARP_STEP_CANDIDATES: tuple[float, ...] = (
    1.0,
    0.5,
    1 / 3,
    0.25,
    1 / 6,
    0.125,
    1 / 12,
    0.0625,
    1 / 24,
    0.03125,
)
_ARP_GRID_TOLERANCE_BEATS = 0.01


def _infer_step_beats(values: list[float]) -> float:
    """Coarsest candidate step size (see ``_ARP_STEP_CANDIDATES``) that
    explains every value within ``_ARP_GRID_TOLERANCE_BEATS`` -- falls back
    to the finest candidate (accepting some rounding) if a value is
    genuinely free-timed and fits no candidate grid well."""
    for candidate in _ARP_STEP_CANDIDATES:
        if all(abs(v - round(v / candidate) * candidate) < _ARP_GRID_TOLERANCE_BEATS for v in values):
            return candidate
    return _ARP_STEP_CANDIDATES[-1]


def _infer_arp_pattern(clip: Any) -> tuple[list[ArpPatternNoteSpec], float] | None:
    """Reconstruct ``(notes, step_beats)`` from a real ``ArpClip0.clip``
    dict's ``notes`` list (``shape='Pattern'`` only). Returns None if there
    are no real notes to reconstruct. See ``_infer_step_beats`` for how the
    grid is chosen; a note whose own timing doesn't fit that grid exactly
    still gets rounded to the nearest step rather than raising, since this
    project only ever generates grid-quantized patterns to begin with (see
    ``ArpPatternNoteSpec``) -- round-tripping such a preset accepts a small,
    documented precision loss on that specific note rather than failing.
    """
    notes_raw = clip.get("notes") if isinstance(clip, dict) else None
    if not notes_raw:
        return None

    values = [v for n in notes_raw for v in (n.get("timeStamp", 0.0), n.get("length", 0.0)) if v > 0]
    if not values:
        return None
    step_beats = _infer_step_beats(values)

    notes = [
        ArpPatternNoteSpec(
            step=round(n.get("timeStamp", 0.0) / step_beats),
            note_offset=int(n.get("noteNum", 0)),
            length_steps=max(round(n.get("length", 0.0) / step_beats), 1),
        )
        for n in notes_raw
    ]
    return notes, step_beats


def extract_spec(data: dict[str, Any]) -> PresetSpec:
    """Best-effort reconstruction of a :class:`PresetSpec` from raw preset data."""
    _reverse_sub_shapes = {v: k for k, v in schema.SIMPLE_SUB_SHAPES.items()}

    oscillators = []
    for i in range(5):
        container = data.get(f"Oscillator{i}", {}) or {}
        pp = container.get("plainParams")
        # kParamEnable's default is slot-dependent: only Osc A (index 0)
        # defaults to on. schema.OSCILLATOR_PARAMS records the common case
        # (off); override for slot 0 explicitly rather than baking a
        # per-index default into the shared schema table.
        enabled = pp.get("kParamEnable") if isinstance(pp, dict) else None
        if enabled is None:
            enabled = i == 0

        kwargs: dict[str, Any] = dict(
            enabled=bool(enabled),
            octave=_resolve(pp, "kParamOctave", schema.OSCILLATOR_PARAMS),
            semitone=_resolve(pp, "kParamPitch", schema.OSCILLATOR_PARAMS),
            fine=_resolve(pp, "kParamFine", schema.OSCILLATOR_PARAMS),
            volume=_resolve(pp, "kParamVolume", schema.OSCILLATOR_PARAMS),
            pan=_resolve(pp, "kParamPan", schema.OSCILLATOR_PARAMS),
            unison=_resolve(pp, "kParamUnison", schema.OSCILLATOR_PARAMS),
            detune=_resolve(pp, "kParamDetune", schema.OSCILLATOR_PARAMS),
        )
        if i in (0, 1, 2):
            engine = _resolve(pp, "kParamType", schema.OSCILLATOR_PARAMS)
            if engine == "kOsc_Sample":
                sample_container = container.get(f"SampleOsc{i}") or {}
                sample_pp = sample_container.get("plainParams")
                kwargs["warp_amount"] = _resolve(sample_pp, "kParamWarp", schema.SAMPLEOSC_PARAMS)
                raw_warp_mode = _resolve(sample_pp, "kParamWarpMenu", schema.SAMPLEOSC_PARAMS)
                kwargs["warp_mode"] = _REVERSE_WARP_MODES.get(raw_warp_mode, raw_warp_mode)

                raw_sample_path = sample_container.get("samplePathRelative")
                if raw_sample_path:
                    try:
                        kwargs["sample_playback_source"] = str(
                            config.get_samples_dir() / raw_sample_path
                        )
                    except config.SamplesFolderNotFoundError:
                        # Introspection must still succeed even if the
                        # Samples folder isn't configured/resolvable in the
                        # current environment (e.g. describe_preset run
                        # somewhere without SERUM_SAMPLES_PATH set) -- the
                        # relative reference still round-trips in the raw
                        # data either way, this just can't show it as a
                        # ready-to-reuse absolute path.
                        pass

                raw_loop_mode = pp.get("kParamLoopMode") if isinstance(pp, dict) else None
                if raw_loop_mode:
                    kwargs["sample_loop"] = _REVERSE_SAMPLE_LOOP_MODES.get(
                        raw_loop_mode, raw_loop_mode
                    )
                    kwargs["sample_loop_start"] = _resolve(
                        pp, "kParamLoopStart", schema.OSCILLATOR_PARAMS
                    )
                    kwargs["sample_loop_end"] = _resolve(
                        pp, "kParamLoopEnd", schema.OSCILLATOR_PARAMS
                    )
                    kwargs["sample_loop_crossfade"] = _resolve(
                        pp, "kParamLoopCrossfade", schema.OSCILLATOR_PARAMS
                    )
            else:
                wt_container = container.get(f"WTOsc{i}") or {}
                wt_pp = wt_container.get("plainParams")
                kwargs["table_position"] = _resolve(wt_pp, "kParamTablePos", schema.WTOSC_PARAMS)
                kwargs["warp_amount"] = _resolve(wt_pp, "kParamWarp", schema.WTOSC_PARAMS)
                raw_warp_mode = _resolve(wt_pp, "kParamWarpMenu", schema.WTOSC_PARAMS)
                kwargs["warp_mode"] = _REVERSE_WARP_MODES.get(raw_warp_mode, raw_warp_mode)
                raw_path = wt_container.get("relativePathToWT")
                kwargs["wavetable"] = _REVERSE_WAVETABLES.get(raw_path, raw_path or "default")
                # kParamWarpMenu2's own ParamDef default ("kFM_OSC") isn't a
                # safe "absent" sentinel here (unlike LFO kParamType's None
                # default) -- check the raw dict directly so an oscillator
                # with no second warp lane at all doesn't get one invented.
                raw_warp_mode2 = wt_pp.get("kParamWarpMenu2") if isinstance(wt_pp, dict) else None
                if raw_warp_mode2 is not None:
                    kwargs["warp_mode2"] = _REVERSE_WARP_MODES.get(raw_warp_mode2, raw_warp_mode2)
                    kwargs["warp_amount2"] = _resolve(wt_pp, "kParamWarp2", schema.WTOSC_PARAMS)
                # kParamWarpVar2 is a DIFFERENT, sparser field than
                # kParamWarp2 -- same "check presence directly" reasoning.
                if isinstance(wt_pp, dict) and "kParamWarpVar2" in wt_pp:
                    kwargs["warp_var2"] = wt_pp["kParamWarpVar2"]
        elif i == 3:
            noise_pp = _sub_plain_params(container, f"NoiseOsc{i}")
            kwargs["noise_type"] = _resolve(noise_pp, "kParamNoiseType", schema.NOISEOSC_PARAMS)
        elif i == 4:
            sub_pp = _sub_plain_params(container, f"SubOsc{i}")
            raw_shape = _resolve(sub_pp, "kParamShape", schema.SUBOSC_PARAMS)
            kwargs["sub_shape"] = _reverse_sub_shapes.get(raw_shape, raw_shape)

        oscillators.append(OscillatorSpec(**kwargs))

    filters = []
    for i in range(2):
        pp = (data.get(f"VoiceFilter{i}", {}) or {}).get("plainParams")
        raw_type = _resolve(pp, "kParamType", schema.VOICE_FILTER_PARAMS)
        # RoutingSlot5/RoutingSlot6 -- each filter's OWN output routing (see
        # FilterSpec.output_routing / mapping.apply_spec). Only extracted as
        # 'parallel'/'series' when EXPLICITLY set to that value -- absence
        # (Serum's real default, meaning parallel) round-trips as None so
        # re-applying an extracted spec doesn't start writing a key the
        # original file never had.
        routing_pp = (data.get(f"RoutingSlot{5 + i}", {}) or {}).get("plainParams")
        raw_routing_dest = routing_pp.get("kParamRoutingDest") if isinstance(routing_pp, dict) else None
        output_routing = {
            "kRoutingDestMaster": "parallel",
            "kRoutingDestFilter": "series",
        }.get(raw_routing_dest)
        filters.append(
            FilterSpec(
                enabled=bool(_resolve(pp, "kParamEnable", schema.VOICE_FILTER_PARAMS)),
                type=_REVERSE_FILTER_TYPES.get(raw_type, raw_type),
                cutoff=_resolve(pp, "kParamFreq", schema.VOICE_FILTER_PARAMS),
                resonance=_resolve(pp, "kParamReso", schema.VOICE_FILTER_PARAMS),
                drive=_resolve(pp, "kParamDrive", schema.VOICE_FILTER_PARAMS),
                stereo=_resolve(pp, "kParamStereo", schema.VOICE_FILTER_PARAMS),
                var=_resolve(pp, "kParamVar", schema.VOICE_FILTER_PARAMS),
                key_track=bool(_resolve(pp, "kParamKeyTrack", schema.VOICE_FILTER_PARAMS)),
                wet=_resolve(pp, "kParamWet", schema.VOICE_FILTER_PARAMS),
                level_out=_resolve(pp, "kParamLevelOut", schema.VOICE_FILTER_PARAMS),
                output_routing=output_routing,
            )
        )

    envelopes = []
    for i in range(4):
        pp = (data.get(f"Env{i}", {}) or {}).get("plainParams")
        envelopes.append(
            EnvelopeSpec(
                attack=_resolve(pp, "kParamAttack", schema.ENV_PARAMS),
                hold=_resolve(pp, "kParamHold", schema.ENV_PARAMS),
                decay=_resolve(pp, "kParamDecay", schema.ENV_PARAMS),
                sustain=_resolve(pp, "kParamSustain", schema.ENV_PARAMS),
                release=_resolve(pp, "kParamRelease", schema.ENV_PARAMS),
                attack_curve=_resolve(pp, "kParamCurve1", schema.ENV_PARAMS),
                decay_curve=_resolve(pp, "kParamCurve2", schema.ENV_PARAMS),
                release_curve=_resolve(pp, "kParamCurve3", schema.ENV_PARAMS),
            )
        )

    lfos = []
    for i in range(10):
        pp = (data.get(f"LFO{i}", {}) or {}).get("plainParams")
        raw_lfo_type = _resolve(pp, "kParamType", schema.LFO_PARAMS)
        lfos.append(
            LfoSpec(
                rate=_resolve(pp, "kParamRate", schema.LFO_PARAMS),
                mode=_resolve(pp, "kParamMode", schema.LFO_PARAMS),
                beat_sync=bool(_resolve(pp, "kParamBeatSync", schema.LFO_PARAMS)),
                delay=_resolve(pp, "kParamDelay", schema.LFO_PARAMS),
                rise=_resolve(pp, "kParamRise", schema.LFO_PARAMS),
                smooth=_resolve(pp, "kParamSmooth", schema.LFO_PARAMS),
                shape=_REVERSE_LFO_TYPES.get(raw_lfo_type, raw_lfo_type)
                if raw_lfo_type is not None
                else None,
                mono=bool(_resolve(pp, "kParamMono", schema.LFO_PARAMS)),
                swing=_resolve(pp, "kParamSwing", schema.LFO_PARAMS),
                dotted=bool(_resolve(pp, "kParamDotted", schema.LFO_PARAMS)),
                triplets=bool(_resolve(pp, "kParamTriplets", schema.LFO_PARAMS)),
                rate10x=bool(_resolve(pp, "kParamRate10x", schema.LFO_PARAMS)),
            )
        )

    macros = []
    for i in range(8):
        container = data.get(f"Macro{i}", {}) or {}
        pp = container.get("plainParams")
        macros.append(
            MacroSpec(
                name=container.get("name", ""),
                value=_resolve(pp, "kParamValue", schema.MACRO_PARAMS),
            )
        )

    fx_chain = []
    # module_id_by_flat_index[i] = fx_chain[i]'s real destModuleID
    # (rack*100 + position-within-that-rack, see mapping._fx_dest_module_id)
    # -- needed below to match ModSlot destinations, which is NOT the same
    # as i once more than one rack is in use.
    module_id_by_flat_index: list[int] = []
    for rack in range(3):
        position_in_rack = 0
        for entry in (data.get(f"FXRack{rack}", {}) or {}).get("FX", []) or []:
            type_id = entry.get("type")
            fx_name = schema.FX_TYPE_IDS.get(type_id)
            if fx_name is None or fx_name not in entry or fx_name not in schema.FX_PARAMS:
                # fx_name not in schema.FX_PARAMS: a structural/routing type
                # (e.g. FXSplit/FXSplit3/FXSplitMS -- parallel/multiband FX
                # routing, found live in a real third-party bank) rather
                # than an audio effect with a param table. These don't
                # carry a kParamWet or any other modeled param, and the
                # units nested inside their branch aren't distinguishable
                # from top-level ones without also decoding branch
                # boundaries (observed kParamModuleCount1/2/3 fields,
                # semantics not yet reverse-engineered -- see
                # docs/PARAMETER_SCHEMA.md) -- skip rather than crash or
                # misrepresent a parallel chain as sequential.
                # count_unmodeled_fx exists so callers can at least surface
                # that something was skipped instead of silently
                # under-reporting the FX chain. Still counts towards this
                # rack's position (Serum itself counts it), so later real
                # units' destModuleID stays correctly aligned.
                position_in_rack += 1
                continue
            pp = entry[fx_name].get("plainParams")
            if not isinstance(pp, dict):
                # Real-world finding: an FX unit's plainParams can be the raw
                # string sentinel "default" (same pattern as VoiceFilter0/1
                # when never touched, see _sub_plain_params) instead of a
                # dict -- `.get("plainParams", {}) or {}` doesn't catch this
                # since a non-empty string is truthy, and used to crash with
                # AttributeError on the next line.
                pp = {}
            # kParamWet absent means fully wet (100.0) for every FX type,
            # confirmed live 2026-07-29 -- see mapping.build_fx_unit. Each
            # FX_PARAMS type's own schema default (e.g. FXDelay's 30.0) is
            # only what's typically OBSERVED when the key is present, not
            # the true absent-state value, so it must not be used here.
            wet = pp.get("kParamWet", 100.0)
            params = {k: v for k, v in pp.items() if k != "kParamWet"}
            fx_chain.append(FxUnitSpec(type=fx_name, wet=wet, params=params, rack=rack))
            module_id_by_flat_index.append(rack * 100 + position_in_rack)
            position_in_rack += 1

    # fx{i}.wet destinations aren't in the static _REVERSE_MOD_DEST_TARGETS
    # table -- an FX rack slot's destModuleTypeString is whichever FX type
    # is actually there, only known from this preset's own fx_chain (see
    # mapping._resolve_mod_destination). Keyed by the real destModuleID
    # (module_id_by_flat_index[idx]), not the flat index idx itself, since
    # those diverge once rack 1/2 are in use -- but still NAMED "fx{idx}.wet"
    # using the flat index, matching how generation addresses fx_chain.
    fx_wet_dest_by_key = {
        (fx.type, module_id_by_flat_index[idx], "kParamWet"): f"fx{idx}.wet"
        for idx, fx in enumerate(fx_chain)
    }
    # Mirrors mapping._resolve_mod_destination's FX_EXTRA_MOD_DEST_PARAMS
    # handling on the write side -- confirmed non-wet FX params, per type.
    for idx, fx in enumerate(fx_chain):
        for suffix, (param_name, _param_id) in schema.FX_EXTRA_MOD_DEST_PARAMS.get(
            fx.type, {}
        ).items():
            fx_wet_dest_by_key[(fx.type, module_id_by_flat_index[idx], param_name)] = (
                f"fx{idx}.{suffix}"
            )

    # Only routes whose source AND destination are both in our resolved
    # vocabulary (see schema.MOD_SOURCE_IDS / MOD_DEST_TARGETS) round-trip
    # here -- everything else (undecoded sources, unmodeled destinations)
    # is silently skipped, since we can't name it safely. It still survives
    # unchanged in the raw data (mapping.apply_spec never touches ModSlot
    # keys it didn't create), it just won't show up in describe_preset or
    # be visible to the LLM when editing.
    mod_routes = []
    for key, entry in data.items():
        if not (isinstance(key, str) and key.startswith("ModSlot") and isinstance(entry, dict)):
            continue
        src = entry.get("source")
        if not (isinstance(src, list) and len(src) == 2):
            continue
        source_name = _REVERSE_MOD_SOURCE_IDS.get(src[0])
        if source_name is None:
            continue
        dest_key = (
            entry.get("destModuleTypeString"),
            entry.get("destModuleID"),
            entry.get("destModuleParamName"),
        )
        dest_name = _REVERSE_MOD_DEST_TARGETS.get(dest_key) or fx_wet_dest_by_key.get(dest_key)
        if dest_name is None:
            continue
        pp = entry.get("plainParams")
        if not isinstance(pp, dict):
            # Same "default" string sentinel pattern as the FX/VoiceFilter
            # cases above -- `.get("plainParams", {}) or {}` doesn't catch
            # it since a non-empty string is truthy (found live on a real
            # Factory preset's ModSlot, not just third-party content).
            pp = {}
        mod_routes.append(
            ModRouteSpec(
                source=source_name,
                destination=dest_name,
                amount=pp.get("kParamAmount", 0.0),
                bipolar=bool(pp.get("kParamBipolar", False)),
            )
        )

    global_pp = (data.get("Global0", {}) or {}).get("plainParams")
    global_spec = GlobalSpec(
        master_volume=_resolve(global_pp, "kParamMasterVolume", schema.GLOBAL_PARAMS),
        mono=bool(_resolve(global_pp, "kParamMonoToggle", schema.GLOBAL_PARAMS)),
        portamento_time=_resolve(global_pp, "kParamPortamentoTime", schema.GLOBAL_PARAMS),
        poly_count=_resolve(global_pp, "kParamPolyCount", schema.GLOBAL_PARAMS),
        limit_same_note_polyphony=bool(
            _resolve(global_pp, "kParamLimitSameNotePolyphony", schema.GLOBAL_PARAMS)
        ),
    )

    arp_pp = (data.get("Arp0", {}) or {}).get("plainParams")
    arp_spec = None
    if isinstance(arp_pp, dict) and arp_pp.get("kParamEnabled"):
        clip_pp = (data.get("ArpClip0", {}) or {}).get("plainParams")
        raw_shape = _resolve(clip_pp, "kParamShape", schema.ARPCLIP_PARAMS)
        raw_transpose_shape = (
            clip_pp.get("kParamTransposeShape") if isinstance(clip_pp, dict) else None
        )
        pattern_notes: list[ArpPatternNoteSpec] = []
        pattern_step_beats = 0.25
        if raw_shape == "Pattern":
            clip = (data.get("ArpClip0", {}) or {}).get("clip")
            inferred = _infer_arp_pattern(clip)
            if inferred is not None:
                pattern_notes, pattern_step_beats = inferred
        arp_spec = ArpSpec(
            enabled=True,
            shape=_REVERSE_ARP_SHAPES.get(raw_shape, raw_shape),
            rate=_resolve(clip_pp, "kParamRate", schema.ARPCLIP_PARAMS),
            gate=_resolve(clip_pp, "kParamGate", schema.ARPCLIP_PARAMS),
            dotted=bool(_resolve(clip_pp, "kParamDotted", schema.ARPCLIP_PARAMS)),
            triplets=bool(_resolve(clip_pp, "kParamTriplets", schema.ARPCLIP_PARAMS)),
            transpose_shift=_resolve(clip_pp, "kParamTransposeShift", schema.ARPCLIP_PARAMS),
            transpose_shape=(
                _REVERSE_ARP_SHAPES.get(raw_transpose_shape, raw_transpose_shape)
                if raw_transpose_shape
                else None
            ),
            pattern=pattern_notes or None,
            pattern_step_beats=pattern_step_beats,
        )

    return PresetSpec(
        name="",
        description="",
        oscillators=oscillators,
        filters=filters,
        envelopes=envelopes,
        lfos=lfos,
        macros=macros,
        fx_chain=fx_chain,
        mod_routes=mod_routes,
        arp=arp_spec,
        **{"global": global_spec},
    )
