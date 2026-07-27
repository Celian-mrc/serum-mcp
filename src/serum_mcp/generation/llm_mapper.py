"""Turn a natural-language sound description into a validated
:class:`~serum_mcp.generation.spec.PresetSpec`, via the Claude API's
tool-use / structured output.

The LLM never writes raw ``kParam*`` values or touches the binary format --
it only fills in :class:`PresetSpec`, whose field ranges match
:mod:`serum_mcp.preset.schema` exactly. Pydantic validates the ranges;
:func:`serum_mcp.preset.mapping.apply_spec` does the final translation to
raw parameters (re-validating against the ground-truth schema again there).
"""

from __future__ import annotations

import json
import os

import anthropic

from serum_mcp.preset.schema import ALL_FX_TYPES, SIMPLE_FILTER_TYPES

from .spec import PresetSpec

_MODEL = os.environ.get("SERUM_MCP_MODEL", "claude-sonnet-4-5")

_TOOL_NAME = "emit_preset_spec"

_SYSTEM_PROMPT = f"""\
You are a sound designer configuring an Xfer Serum 2 synth patch. Given a \
natural-language description of a desired sound (and optionally the current \
state of an existing patch, for edit requests), call the `{_TOOL_NAME}` tool \
with a complete target patch specification.

Guidelines:
- Prefer Osc A (index 0) as the primary sound source unless the description \
  clearly calls for layering (e.g. "fat", "wide", "detuned stack").
- `filters[].type` must be one of: {", ".join(sorted(SIMPLE_FILTER_TYPES))}.
- `fx_chain[].type` must be one of: {", ".join(ALL_FX_TYPES)}.
- `fx_chain[].params` keys must be raw kParam* names valid for that FX type \
  (e.g. FXReverb accepts kParamType, kParamSize, kParamDelay, kParamWidth).
- For an *edit* instruction, only include the sections/indices that should \
  change; omitted oscillators/filters/envelopes are left as-is by the caller.
- Keep `cutoff` in mind as 0.0 (fully closed) to 1.0 (fully open), not Hz.
- envelope times are in seconds; macro/reso/wet/drive values are 0-100 percent \
  unless the field description says otherwise.
"""


def _preset_spec_tool() -> dict:
    schema = PresetSpec.model_json_schema(by_alias=True)
    return {
        "name": _TOOL_NAME,
        "description": "Emit a complete Serum 2 preset specification.",
        "input_schema": schema,
    }


def generate_spec(
    description: str,
    *,
    current_spec: PresetSpec | None = None,
    client: anthropic.Anthropic | None = None,
) -> PresetSpec:
    """Call Claude to translate ``description`` into a :class:`PresetSpec`.

    If ``current_spec`` is given, the prompt frames this as an edit of that
    existing patch rather than a from-scratch generation.
    """
    client = client or anthropic.Anthropic()

    if current_spec is not None:
        user_content = (
            "Current patch state (JSON):\n"
            f"{current_spec.model_dump_json(by_alias=True, indent=2)}\n\n"
            f"Edit instruction: {description}\n\n"
            "Return the FULL updated patch spec (not just the diff), keeping "
            "everything not mentioned by the instruction unchanged."
        )
    else:
        user_content = f"Generate a Serum 2 patch for: {description}"

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_preset_spec_tool()],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return PresetSpec.model_validate(block.input)

    raise RuntimeError(
        f"Claude did not call {_TOOL_NAME!r}; response: "
        f"{json.dumps([b.model_dump() for b in response.content])}"
    )
