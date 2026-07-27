from __future__ import annotations

import pytest

from serum_mcp.preset.schema import ENV_PARAMS, VOICE_FILTER_PARAMS
from serum_mcp.preset.validator import ParamValidationError, validate_params


def test_valid_params_pass():
    validate_params("Env0", {"kParamAttack": 0.5, "kParamSustain": 1.0}, ENV_PARAMS)


def test_out_of_range_rejected():
    with pytest.raises(ParamValidationError):
        validate_params("Env0", {"kParamAttack": 999.0}, ENV_PARAMS)


def test_negative_below_min_rejected():
    with pytest.raises(ParamValidationError):
        validate_params("Env0", {"kParamSustain": -0.1}, ENV_PARAMS)


def test_unknown_param_rejected_by_default():
    with pytest.raises(ParamValidationError):
        validate_params("Env0", {"kParamNotReal": 1.0}, ENV_PARAMS)


def test_unknown_param_allowed_when_opted_in():
    validate_params("ModSlot0", {"kParamMystery": 1.0}, {}, allow_unknown=True)


def test_enum_param_validated():
    validate_params("VoiceFilter0", {"kParamType": "L24"}, VOICE_FILTER_PARAMS)
    with pytest.raises(ParamValidationError):
        validate_params("VoiceFilter0", {"kParamType": "NotAFilter"}, VOICE_FILTER_PARAMS)


def test_bool_param_type_checked():
    with pytest.raises(ParamValidationError):
        validate_params("VoiceFilter0", {"kParamEnable": "yes"}, VOICE_FILTER_PARAMS)
