from __future__ import annotations

from serum_mcp.preset.safety import scan_wire_types


def test_clean_preset_has_no_issues():
    data = {
        "Oscillator0": {"plainParams": {"kParamEnable": 1.0, "kParamOctave": -1.0}},
        "mpeEnabled": False,  # legitimate top-level bool, not a plainParams value
    }
    assert scan_wire_types(data) == []


def test_detects_bool_in_plain_params():
    data = {"Oscillator0": {"plainParams": {"kParamEnable": True}}}
    issues = scan_wire_types(data)
    assert len(issues) == 1
    assert issues[0].path == ".Oscillator0.plainParams.kParamEnable"
    assert issues[0].value is True
    assert "bool" in issues[0].reason


def test_detects_int_in_plain_params():
    data = {"Oscillator0": {"plainParams": {"kParamUnison": 4}}}
    issues = scan_wire_types(data)
    assert len(issues) == 1
    assert issues[0].value == 4
    assert type(issues[0].value) is int
    assert "int" in issues[0].reason


def test_walks_nested_lists_and_dicts():
    data = {
        "FXRack0": {
            "FX": [
                {"FXDistortion": {"plainParams": {"kParamWet": 50.0}}},
                {"FXComp": {"plainParams": {"kParamThresh": True}}},  # bug, buried in a list
            ]
        }
    }
    issues = scan_wire_types(data)
    assert len(issues) == 1
    assert "FXRack0.FX[1].FXComp.plainParams.kParamThresh" in issues[0].path


def test_string_manager_plain_params_ignored():
    """The 'default' sentinel string (untouched module) isn't a dict, so it
    can't contain wire-type issues -- must not crash or false-positive."""
    data = {"Env0": {"plainParams": "default"}}
    assert scan_wire_types(data) == []
