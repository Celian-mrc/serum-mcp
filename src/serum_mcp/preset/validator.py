"""Validate raw ``plainParams``-style dicts against a :mod:`.schema` table
before they get written into a preset. Catches out-of-range values and typos
in ``kParam*`` names early, instead of silently writing a file Serum may
refuse to load or may clip/misinterpret.
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
    """Validate ``params`` (a ``{kParamX: value}`` dict) against ``schema``.

    Raises :class:`ParamValidationError` on the first problem found. Set
    ``allow_unknown=True`` to permit keys absent from ``schema`` (useful for
    modules we only partially model, like ModSlot).
    """
    for key, value in params.items():
        param_def = schema.get(key)
        if param_def is None:
            if allow_unknown:
                continue
            raise ParamValidationError(f"{module_name}.{key} is not a known parameter")

        if param_def.kind == "bool":
            if not isinstance(value, bool):
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
