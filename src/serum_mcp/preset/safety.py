"""Recursive scan for CBOR wire-type mismatches in a packed preset's raw data.

Codifies a check that was, until now, retyped by hand as an inline Python
one-liner every time a real-Serum test was needed this session: every
``plainParams`` dict's values must be CBOR floats, never a native CBOR
``bool`` or ``int`` -- real Serum presets store even conceptually boolean
or integer fields (``kParamEnable``, ``kParamUnison``, ...) as doubles, and
:func:`serum_mcp.preset.validator.validate_params` normalizes both cases on
the way in. This scan is the independent, after-the-fact check on the
*output*: it doesn't trust that every code path went through validation
correctly, it just looks at what actually got written (see
``docs/PARAMETER_SCHEMA.md``'s CBOR wire-type note for the full story,
including the crash this was found from).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Top-level flags (outside any plainParams dict) that are genuinely native
# CBOR booleans in real Serum presets -- not a bug if found here.
KNOWN_LEGITIMATE_TOP_LEVEL_BOOLS = frozenset({"mpeEnabled", "lockOversampling", "lockTuning"})


@dataclass(frozen=True)
class WireTypeIssue:
    path: str
    value: Any
    reason: str

    def __str__(self) -> str:
        return f"{self.path} = {self.value!r} ({self.reason})"


def scan_wire_types(data: dict[str, Any]) -> list[WireTypeIssue]:
    """Walk a preset's raw ``data`` dict and return every ``plainParams``
    value that's a raw Python ``bool``/``int`` instead of a ``float`` --
    each one would encode as a CBOR wire type real Serum presets never use
    in that position, which has previously crashed FL Studio on load."""
    issues: list[WireTypeIssue] = []

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            plain_params = obj.get("plainParams")
            if isinstance(plain_params, dict):
                for key, value in plain_params.items():
                    if isinstance(value, bool):
                        issues.append(
                            WireTypeIssue(
                                f"{path}.plainParams.{key}",
                                value,
                                "raw bool -- must be a 1.0/0.0 float",
                            )
                        )
                    elif isinstance(value, int):
                        issues.append(
                            WireTypeIssue(
                                f"{path}.plainParams.{key}", value, "raw int -- must be a float"
                            )
                        )
            for key, value in obj.items():
                walk(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                walk(value, f"{path}[{index}]")

    walk(data, "")
    return issues
