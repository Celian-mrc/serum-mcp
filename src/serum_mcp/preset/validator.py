"""Validate raw ``plainParams``-style dicts against a :mod:`.schema` table
before they get written into a preset. Catches out-of-range values and typos
in ``kParam*`` names early, instead of silently writing a file Serum may
refuse to load or may clip/misinterpret.

Also normalizes values to CBOR-safe types in place, for the same reason in
both cases: Serum's native CBOR parser is strict about wire types even for
fields that are conceptually simpler than what they're stored as, and
writing the "obviously correct" Python type produces a structurally
different (and sometimes crashing) CBOR encoding:

- "bool"-kind values: real Serum presets store `plainParams` booleans as
  CBOR floats (``1.0``/``0.0``), never a native CBOR boolean -- writing a
  real ``bool`` there produces a structurally different CBOR type that
  Serum's loader does not expect and reliably crashes on (confirmed: a
  hand-built preset with a raw CBOR bool in ``kParamEnable`` crashed FL
  Studio ~2 seconds after selecting the preset in the browser, no error
  dialog).
- "float"-kind values: real Serum presets store even integer-valued fields
  (e.g. unison voice count) as CBOR doubles, never a CBOR integer -- a
  Python ``int`` slipping through (e.g. from a strictly-``int``-typed
  Pydantic field) would hit the same class of bug.

:func:`validate_params` is called at every site that writes into a preset's
raw data, so folding both fixes in here means neither can be forgotten at a
new call site.
"""

from __future__ import annotations

from .schema import ParamDef


class ParamValidationError(ValueError):
    pass


def validate_params(
    module_name: str,
    params: dict[str, float | str | bool],
    schema: dict[str, ParamDef],
    *,
    allow_unknown: bool = False,
) -> None:
    """Validate ``params`` (a ``{kParamX: value}`` dict) against ``schema``,
    normalizing "bool"-kind values to CBOR-safe floats in place (see module
    docstring).

    Raises :class:`ParamValidationError` on the first problem found. Set
    ``allow_unknown=True`` to permit keys absent from ``schema`` (useful for
    modules we only partially model, like ModSlot).
    """
    for key, value in list(params.items()):
        param_def = schema.get(key)
        if param_def is None:
            if allow_unknown:
                continue
            raise ParamValidationError(f"{module_name}.{key} is not a known parameter")

        if param_def.kind == "bool":
            if isinstance(value, bool):
                params[key] = 1.0 if value else 0.0
            elif isinstance(value, float) and value in (0.0, 1.0):
                # Already the CBOR-safe representation Serum itself writes
                # -- accepted as-is. Found live: a "bool"-kind key we don't
                # actively write ourselves (e.g. VoiceFilter's
                # kParamKeyTrack) can arrive here as a pass-through value
                # from a real third-party preset's plainParams (same
                # edit-round-trip path as _plain_params's docstring), and
                # it's already correct -- only a genuinely wrong type
                # (anything but a Python bool or a literal 0.0/1.0) should
                # be rejected.
                pass
            else:
                raise ParamValidationError(f"{module_name}.{key} expects a bool, got {value!r}")
        elif param_def.kind == "enum":
            if value not in param_def.enum_values:
                raise ParamValidationError(
                    f"{module_name}.{key}={value!r} is not one of {param_def.enum_values}"
                )
        elif param_def.kind == "float":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ParamValidationError(f"{module_name}.{key} expects a number, got {value!r}")
            if param_def.min is not None and value < param_def.min:
                raise ParamValidationError(
                    f"{module_name}.{key}={value} is below the minimum {param_def.min}"
                )
            if param_def.max is not None and value > param_def.max:
                raise ParamValidationError(
                    f"{module_name}.{key}={value} is above the maximum {param_def.max}"
                )
            if isinstance(value, int):
                params[key] = float(value)
