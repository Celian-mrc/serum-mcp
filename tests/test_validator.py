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


def test_bool_params_normalized_to_cbor_safe_floats():
    """Regression test: real Serum presets store plainParams booleans as
    CBOR floats (1.0/0.0), never a native CBOR bool. Writing a real Python
    bool into the CBOR payload crashes Serum's loader (confirmed against a
    live FL Studio + Serum 2 install -- the host closed ~2s after selecting
    a preset built with a raw bool in kParamEnable, no error dialog)."""
    params = {"kParamEnable": True, "kParamFreq": 0.5}
    validate_params("VoiceFilter0", params, VOICE_FILTER_PARAMS)
    assert params["kParamEnable"] == 1.0
    assert type(params["kParamEnable"]) is float

    params = {"kParamEnable": False}
    validate_params("VoiceFilter0", params, VOICE_FILTER_PARAMS)
    assert params["kParamEnable"] == 0.0
    assert type(params["kParamEnable"]) is float


def test_bool_param_accepts_already_cbor_safe_float_pass_through():
    """Found live editing real Factory content: a "bool"-kind key this
    project doesn't actively write itself (e.g. VoiceFilter's
    kParamKeyTrack) can arrive here as a pass-through value from a real
    preset's plainParams -- already the CBOR-safe float Serum itself wrote,
    just not a Python bool. Must be accepted as-is, not rejected."""
    params = {"kParamKeyTrack": 1.0}
    validate_params("VoiceFilter0", params, VOICE_FILTER_PARAMS)
    assert params["kParamKeyTrack"] == 1.0

    params = {"kParamKeyTrack": 0.0}
    validate_params("VoiceFilter0", params, VOICE_FILTER_PARAMS)
    assert params["kParamKeyTrack"] == 0.0


def test_bool_param_rejects_a_float_that_isnt_zero_or_one():
    with pytest.raises(ParamValidationError):
        validate_params("VoiceFilter0", {"kParamKeyTrack": 0.5}, VOICE_FILTER_PARAMS)
