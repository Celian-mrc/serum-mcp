"""The semantic, MCP-client-facing preset schema.

This is deliberately a *simplified* view of the full raw parameter set in
:mod:`serum_mcp.preset.schema` -- friendly field names, a curated filter-type
vocabulary, seconds instead of opaque curve values where we're confident of
the unit. The calling model (see ``server.py``'s tool instructions) builds
JSON matching :class:`PresetSpec` itself; :mod:`serum_mcp.preset.mapping`
then translates a validated ``PresetSpec`` onto the raw CBOR structure.

Every field range mirrors the bounds recorded in ``preset/schema.py`` --
if you change one, change the other.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from serum_mcp.preset.schema import SIMPLE_FILTER_TYPES, SIMPLE_SUB_SHAPES

FilterTypeName = str  # validated against SIMPLE_FILTER_TYPES keys in mapping.py


class OscillatorSpec(BaseModel):
    """Shared fields apply to all 5 oscillator slots (A/B/C/Noise/Sub).
    ``table_position``/``warp_amount`` only affect slots 0-2 (the wavetable
    engine); ``noise_type`` only affects slot 3; ``sub_shape`` only affects
    slot 4 -- mapping.py ignores the fields that don't apply to a given slot
    rather than writing them somewhere Serum doesn't expect.
    """

    enabled: bool = True
    octave: float = Field(0.0, ge=-4.0, le=4.0)
    volume: float = Field(0.75, ge=0.0, le=1.0, description="0=silent, 1=unity gain")
    pan: float = Field(0.0, ge=-50.0, le=50.0)
    unison: float = Field(
        1.0,
        ge=1.0,
        le=16.0,
        description="voice count, slots 0-2 only. Stored as a float in Serum's own "
        "format even though it's conceptually an integer -- keep it typed float here "
        "so pydantic doesn't hand back a Python int, which would encode as the wrong "
        "CBOR wire type (see docs/PARAMETER_SCHEMA.md's CBOR bool/float note).",
    )
    detune: float = Field(0.0, ge=0.0, le=1.0, description="unison detune amount, slots 0-2 only")
    table_position: float = Field(
        0.0, ge=0.0, le=256.0, description="wavetable frame position, slots 0-2 only"
    )
    warp_amount: float = Field(0.0, ge=0.0, le=1.0, description="slots 0-2 only")
    noise_type: str = Field(
        "White", description="slot 3 (Noise) only, one of: White, Pink, Brown, Geiger"
    )
    sub_shape: str = Field(
        "saw",
        description=f"slot 4 (Sub) only, one of: {', '.join(sorted(SIMPLE_SUB_SHAPES))}",
    )


class FilterSpec(BaseModel):
    enabled: bool = True
    type: FilterTypeName = Field(
        "lowpass_24", description=f"one of: {', '.join(sorted(SIMPLE_FILTER_TYPES))}"
    )
    cutoff: float = Field(0.5, ge=0.0, le=1.0, description="0=closed, 1=fully open")
    resonance: float = Field(10.0, ge=0.0, le=100.0)
    drive: float = Field(0.0, ge=0.0, le=100.0)


class EnvelopeSpec(BaseModel):
    attack: float = Field(0.0005, ge=0.0, le=7.0, description="seconds")
    decay: float = Field(1.0, ge=0.0, le=32.0, description="seconds")
    sustain: float = Field(1.0, ge=0.0, le=1.0)
    release: float = Field(0.015, ge=0.0, le=13.0, description="seconds")


class LfoSpec(BaseModel):
    rate: float = Field(0.0, ge=0.0, le=100.0, description="normalized rate, not literal Hz")
    mode: str = Field("Free", description="'Free' or 'Envelope'")


class MacroSpec(BaseModel):
    name: str = ""
    value: float = Field(0.0, ge=0.0, le=100.0)


class FxUnitSpec(BaseModel):
    type: str = Field(description="one of the FX_TYPE_IDS names, e.g. 'FXReverb'")
    wet: float = Field(50.0, ge=0.0, le=100.0)
    params: dict[str, float | str] = Field(default_factory=dict)


class GlobalSpec(BaseModel):
    master_volume: float = Field(0.5, ge=0.0, le=1.0)
    mono: bool = False


class ModRouteSpec(BaseModel):
    """One mod-matrix route: ``source`` modulates ``destination`` by ``amount``.

    Only two source families are currently supported -- ``lfo0``..``lfo9``
    and ``macro0``..``macro7`` -- and only the destinations enumerated in
    ``preset.schema.MOD_DEST_TARGETS`` (oscillator volume/pan/octave/pitch/
    fine, filter cutoff/resonance/drive, envelope attack/decay/sustain/
    release). Other mod sources (envelopes, velocity, mod wheel, aftertouch,
    ...) exist in Serum but their internal source IDs are not decoded yet --
    see docs/PARAMETER_SCHEMA.md.
    """

    source: str = Field(description="'lfo0'..'lfo9' or 'macro0'..'macro7'")
    destination: str = Field(description="e.g. 'filter0.cutoff', 'oscillator0.pitch', 'env0.decay'")
    amount: float = Field(0.0, ge=-100.0, le=100.0)
    bipolar: bool = False


class PresetSpec(BaseModel):
    """The full target state for a generated or edited preset."""

    name: str = Field(description="short preset name, Serum-style, e.g. 'BA - Acid Growl'")
    description: str = Field(description="one-sentence description of the sound design intent")
    oscillators: list[OscillatorSpec] = Field(
        default_factory=list,
        max_length=5,
        description="index 0..4 = Osc A, B, C, Noise, Sub. Omit trailing slots to leave untouched.",
    )
    filters: list[FilterSpec] = Field(
        default_factory=list,
        max_length=2,
        description="index 0..1 = Filter 1, Filter 2",
    )
    envelopes: list[EnvelopeSpec] = Field(
        default_factory=list,
        max_length=4,
        description="index 0..3; Env 1 (index 0) is conventionally the amp envelope",
    )
    lfos: list[LfoSpec] = Field(default_factory=list, max_length=10)
    macros: list[MacroSpec] = Field(default_factory=list, max_length=8)
    fx_chain: list[FxUnitSpec] = Field(
        default_factory=list,
        max_length=12,
        description="effects, in order, on FX rack 1",
    )
    mod_routes: list[ModRouteSpec] = Field(
        default_factory=list,
        max_length=16,
        description="modulation matrix routes; see ModRouteSpec for supported sources/destinations",
    )
    global_: GlobalSpec = Field(default_factory=GlobalSpec, alias="global")

    model_config = {"populate_by_name": True}
