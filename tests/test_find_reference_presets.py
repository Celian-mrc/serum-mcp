from __future__ import annotations

import json

import pytest

from serum_mcp import config
from serum_mcp.tools.find_reference_presets import find_reference_presets


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


@pytest.fixture
def fake_corpus(tmp_path, monkeypatch):
    """A fake .../Presets/{User,Factory} layout, mirroring the real Serum
    install structure find_reference_presets expects (User is what
    config.get_presets_dir() returns; Factory is its sibling)."""
    presets_root = tmp_path / "Presets"
    user_dir = presets_root / "User"
    factory_dir = presets_root / "Factory"
    monkeypatch.setenv(config.ENV_VAR, str(user_dir))
    user_dir.mkdir(parents=True)
    factory_dir.mkdir(parents=True)
    return user_dir, factory_dir


def test_matches_by_folder_name(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(factory_dir / "Pluck" / "PL - Adam.SerumPreset")
    _touch(factory_dir / "Pad" / "PD - Warm.SerumPreset")

    result = json.loads(find_reference_presets("pluck"))
    assert result["count"] == 1
    assert result["results"][0]["path"].endswith("PL - Adam.SerumPreset")
    assert result["results"][0]["source"] == "Factory"


def test_genre_keyword_expansion_finds_factory_folder(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(factory_dir / "Bass" / "Reese" / "BA - Oscars.SerumPreset")
    _touch(factory_dir / "Lead" / "LD - Bright.SerumPreset")

    result = json.loads(find_reference_presets("dubstep bass"))
    assert "reese" in result["expanded_terms"]
    assert any(r["path"].endswith("BA - Oscars.SerumPreset") for r in result["results"])


def test_user_root_file_gets_user_source(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(user_dir / "BA - Wobble Growl.SerumPreset")

    result = json.loads(find_reference_presets("wobble"))
    assert result["results"][0]["source"] == "User"


def test_third_party_bank_subfolder_gets_bank_name_as_source(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(user_dir / "RAGE Bank" / "RAGE - Reese Bass.SerumPreset")

    result = json.loads(find_reference_presets("reese"))
    assert result["results"][0]["source"] == "RAGE Bank"


def test_test_and_calib_subfolders_excluded(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(user_dir / "serum-mcp Tests" / "ArpRateCalib" / "CALIB ArpRate 01.SerumPreset")
    _touch(user_dir / "RAGE Bank" / "RAGE - Arp Thing.SerumPreset")

    result = json.loads(find_reference_presets("arp"))
    paths = [r["path"] for r in result["results"]]
    assert not any("Tests" in p or "Calib" in p for p in paths)
    assert any("RAGE - Arp Thing" in p for p in paths)


def test_limit_and_truncated(fake_corpus):
    user_dir, factory_dir = fake_corpus
    for i in range(5):
        _touch(factory_dir / "Pad" / f"PD - Pad{i}.SerumPreset")

    result = json.loads(find_reference_presets("pad", limit=3))
    assert result["count"] == 3
    assert result["truncated"] is True


def test_no_match_returns_empty_results(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(factory_dir / "Lead" / "LD - Bright.SerumPreset")

    result = json.loads(find_reference_presets("zzz_no_such_term"))
    assert result["count"] == 0
    assert result["results"] == []


def test_empty_query_raises(fake_corpus):
    with pytest.raises(ValueError, match="at least one searchable word"):
        find_reference_presets("   ")


def test_matched_terms_reported(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(factory_dir / "Bass" / "Hard" / "BA - Growler.SerumPreset")

    result = json.loads(find_reference_presets("dubstep bass"))
    entry = next(r for r in result["results"] if r["path"].endswith("BA - Growler.SerumPreset"))
    assert "growl" in entry["matched_terms"]
    assert "bass" in entry["matched_terms"]


def test_more_matched_terms_ranks_first(fake_corpus):
    user_dir, factory_dir = fake_corpus
    _touch(factory_dir / "Bass" / "Reese" / "BA - Reese Bass.SerumPreset")  # matches reese + bass
    _touch(factory_dir / "Lead" / "LD - Bass Lead.SerumPreset")  # matches bass only

    result = json.loads(find_reference_presets("reese bass"))
    assert result["results"][0]["path"].endswith("BA - Reese Bass.SerumPreset")
