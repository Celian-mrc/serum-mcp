"""Validate raw ``plainParams``-style dicts against a :mod:`.schema` table
before they get written into a preset. Catches out-of-range values and typos
in ``kParam*`` names early, instead of silently writing a file Serum may
refuse to load or may clip/misinterpret.

Also normalizes "bool"-kind values in place: real Serum presets store
`plainParams` booleans as CBOR floats (``1.0``/``0.0``), never a native CBOR
boolean -- writing a real ``bool`` there produces a structurally different
CBOR type that Serum's loader does not expect and reliably crashes on
(confirmed: a hand-built preset with a raw CBOR bool in ``kParamEnable``
crashed FL Studio ~2 seconds after selecting the preset in the browser, no
error dialog). :func:`validate_params` is called at every site that writes
into a preset's raw data, so folding the fix in here means it cannot be
forgotten at a new call site.
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
            if not isinstance(value, bool):
                raise ParamValidationError(f"{module_name}.{key} expects a bool, got {value!r}")
            params[key] = 1.0 if value else 0.0
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
