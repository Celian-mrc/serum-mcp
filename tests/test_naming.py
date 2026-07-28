from __future__ import annotations

from serum_mcp.tools._naming import sanitize_subfolder, slugify_preset_name


def test_slugify_preset_name_strips_unsafe_characters():
    assert slugify_preset_name("BA - Acid Growl!!") == "BA - Acid Growl"


def test_slugify_preset_name_falls_back_to_untitled_when_empty():
    assert slugify_preset_name("...") == "Untitled"
    assert slugify_preset_name("") == "Untitled"


def test_sanitize_subfolder_simple_name():
    assert sanitize_subfolder("RAGE Bank") == "RAGE Bank"


def test_sanitize_subfolder_nested_path():
    assert sanitize_subfolder("RAGE Bank/Leads") == "RAGE Bank/Leads"


def test_sanitize_subfolder_normalizes_backslashes():
    assert sanitize_subfolder("RAGE Bank\\Leads") == "RAGE Bank/Leads"


def test_sanitize_subfolder_drops_traversal_segments():
    assert sanitize_subfolder("../../etc/RAGE Bank") == "etc/RAGE Bank"


def test_sanitize_subfolder_pure_traversal_returns_empty():
    assert sanitize_subfolder("../..") == ""


def test_sanitize_subfolder_empty_input_returns_empty():
    assert sanitize_subfolder("") == ""
