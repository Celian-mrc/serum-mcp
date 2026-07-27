"""The semantic, LLM-facing preset schema.

This is deliberately a *simplified* view of the full raw parameter set in
:mod:`serum_mcp.preset.schema` -- friendly field names, a curated filter-type
vocabulary, seconds instead of opaque curve values where we're confident of
the unit. The LLM is constrained to emit JSON matching :class:`PresetSpec`
(via Anthropic tool-use / structured output); :mod:`serum_mcp.preset.mapping`
then translates a validated ``PresetSpec`` onto the raw CBOR structure.

Every field range mirrors the bounds recorded in ``preset/schema.py`` --
if you change one, change the other.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from serum_mcp.preset.schema import SIMPLE_FILTER_TYPES

FilterTypeName = str  # validated against SIMPLE_FILTER_TYPES keys in mapping.py


class OscillatorSpec(BaseModel):
    enabled: bool = True
    octave: float = Field(0.0, ge=-4.0, le=4.0)
    volume: float = Field(0.75, ge=0.0, le=1.0, description="0=silent, 1=unity gain")
    pan: float = Field(0.0, ge=-50.0, le=50.0)
    unison: int = Field(1, ge=1, le=16)
    detune: float = Field(0.0, ge=0.0, le=1.0, description="unison detune amount")
    table_position: float = Field(0.0, ge=0.0, le=256.0, description="wavetable frame position")
    warp_amount: float = Field(0.0, ge=0.0, le=1.0)


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
    global_: GlobalSpec = Field(default_factory=GlobalSpec, alias="global")

    model_config = {"populate_by_name": True}
