"""``find_reference_presets`` MCP tool implementation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from serum_mcp import config

_DEFAULT_LIMIT = 8
_MAX_SCAN = 8000  # safety cap on how many files to score in one call

# Genre/style keyword -> extra search terms likely to appear in real preset
# paths. This is COMMUNITY sound-design convention (genre <-> instrument
# role/character associations documented across producer guides and
# commercial preset-pack naming), NOT derived from this project's own corpus
# analysis the way schema.ROLE_STARTING_POINTS is -- treat it as a search
# aid, not a measured fact. Deliberately generous/overlapping (e.g. "dubstep"
# also pulls in "reese"/"wobble"/"growl") since a false-positive candidate
# costs nothing (the calling model still evaluates it via describe_preset
# before using it), while a missed real match costs a lot. Serum's own
# Factory library is organized by instrument/role + rough character (e.g.
# Bass/Reese, Bass/808, Bass/Modulated), not by genre name, so this table
# exists specifically to bridge a genre query to those folder/character
# names -- real third-party packs are often already genre/artist-branded and
# tend to match directly without needing this expansion at all.
_GENRE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dubstep": ("dubstep", "wobble", "growl", "reese", "riddim", "modulated"),
    "riddim": ("riddim", "growl", "reese", "wobble"),
    "trap": ("trap", "808", "sub"),
    "house": ("house", "sub", "pluck"),
    "deep house": ("house", "deep", "sub", "pad"),
    "tech house": ("house", "tech", "pluck"),
    "techno": ("techno", "acid", "hard", "hoover"),
    "trance": ("trance", "lead", "pad", "pluck", "hoover"),
    "dnb": ("reese", "dnb", "sub", "hard"),
    "drum and bass": ("reese", "sub", "hard"),
    "jungle": ("reese", "sub", "hard"),
    "future bass": ("future", "chord", "pluck", "vox"),
    "lo-fi": ("lofi", "keyboard", "e piano", "vinyl", "mallet"),
    "lofi": ("lofi", "keyboard", "e piano", "vinyl", "mallet"),
    "ambient": ("ambient", "pad", "soundscape", "drone"),
    "cinematic": ("cinematic", "orchestral", "pad", "soundscape", "hit"),
    "synthwave": ("synthwave", "retro analog", "lead", "pad"),
    "retrowave": ("synthwave", "retro analog", "lead", "pad"),
    "trip hop": ("keyboard", "e piano", "pad", "vinyl"),
    "hip hop": ("808", "trap", "sub", "keyboard"),
    "edm": ("lead", "pluck", "chord", "hoover"),
    "big room": ("lead", "hoover", "pluck", "chord"),
    "psytrance": ("acid", "lead", "hoover"),
}

_NON_WORD = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {t for t in _NON_WORD.sub(" ", text.lower()).split() if t}


def _expand_query(query: str) -> set[str]:
    tokens = _tokenize(query)
    lower_query = query.lower()
    for phrase, extra in _GENRE_KEYWORDS.items():
        if phrase in lower_query:
            tokens.update(extra)
    return tokens


def find_reference_presets(query: str, limit: int = _DEFAULT_LIMIT) -> str:
    """Search the real preset corpus (Serum's own Factory library plus
    everything in the user's Presets/User folder, including any installed
    third-party banks) by keyword match against each preset's folder path
    and filename, and return the best-matching candidates as JSON.

    Call this whenever a request references a GENRE or an ARTIST'S STYLE
    ("dubstep bass", "something in the style of Flume", "a Reese bass like
    in DnB") before generating from scratch -- grounding a preset in a
    real, already-designed reference (even just to see what filter type/
    FX chain/mod routes it actually uses) beats guessing purely from
    parametric knowledge of the genre. Also useful for a bare instrument/
    role request ("a pluck", "a warm pad") to find real examples beyond
    what ``list_parameters()['role_starting_points']`` already summarizes.

    This is filename/folder-path matching only (no audio analysis, no ML
    embeddings) -- cheap and dependency-free, but only as good as how
    descriptive the corpus's own names happen to be. Real third-party
    packs are often already genre/artist-branded (a pack literally named
    after a genre or producer) and match directly; Serum's Factory
    library is organized by instrument/role + rough character (e.g.
    Bass/Reese, Bass/808, Bass/Modulated, Lead, Pad), not by genre name,
    so a genre query is additionally expanded against a small curated
    keyword table (community sound-design convention -- e.g. "dubstep"
    also searches "reese"/"wobble"/"growl"/"modulated" -- see this
    module's own comments for the full table) to still surface relevant
    Factory candidates when no genre-named pack exists locally.

    Results are a STARTING POINT, not an answer: call describe_preset()
    on the most promising matches to see their actual parameters before
    using one as a reference or as the base for edit_preset(). Zero/weak
    matches don't mean synthesis from scratch won't work well -- this is
    one more source of grounding, not a requirement, and this project's
    own corpus is finite (mostly Xfer's Factory library plus whatever
    third-party banks this specific user happens to have installed).

    Returns JSON: ``query`` (the original), ``expanded_terms`` (what was
    actually searched for, useful to see if genre expansion kicked in),
    ``count``/``truncated``, and ``results`` (each: ``path``, ``source``
    -- "Factory" or the top-level folder name under Presets/User a
    third-party bank lives in -- and ``matched_terms``), sorted by number
    of matched terms descending then path length ascending (shorter/more
    specific paths first among equal-scoring candidates).
    """
    terms = _expand_query(query)
    if not terms:
        raise ValueError("query must contain at least one searchable word")

    presets_dir = config.get_presets_dir()  # .../Presets/User
    roots: list[tuple[Path, str | None]] = [(presets_dir, None)]
    factory_dir = presets_dir.parent / "Factory"
    if factory_dir.is_dir():
        roots.append((factory_dir, "Factory"))

    scored: list[tuple[int, int, dict[str, object]]] = []
    scanned = 0
    for root, forced_source in roots:
        for path in root.rglob("*.SerumPreset"):
            scanned += 1
            if scanned > _MAX_SCAN:
                break
            if forced_source != "Factory":
                top_folder = path.relative_to(presets_dir).parts[0].lower()
                if "test" in top_folder or "calib" in top_folder:
                    # Heuristic, not an enforced convention: skips common
                    # scratch/calibration subfolder names (e.g. this
                    # project's own dev sessions tend to use names like
                    # "serum-mcp Tests"/"ArpRateCalib") so throwaway probe
                    # presets don't surface as sound-design references. A
                    # deliberately-named real bank that happens to contain
                    # "test"/"calib" is a rare, low-cost false negative --
                    # the user can still search with more specific terms.
                    continue
            rel_str = str(path.relative_to(root))
            path_tokens = _tokenize(rel_str)
            # Substring match (not just exact token match) against the
            # RELATIVE path only -- e.g. "acid" should match "Acid101".
            # Deliberately excludes the absolute path's own parent
            # directories (username, temp folders, ...), which could
            # otherwise produce false matches unrelated to the preset
            # itself (found via a test whose own tmp_path folder name
            # happened to contain a query substring).
            haystack = rel_str.lower()
            matched = {t for t in terms if t in path_tokens or t in haystack}
            if not matched:
                continue
            if forced_source == "Factory":
                source = "Factory"
            else:
                rel_parts = path.relative_to(presets_dir).parts
                # len==1 means the preset sits directly in Presets/User with
                # no subfolder -- parts[0] would just be its own filename.
                source = rel_parts[0] if len(rel_parts) > 1 else "User"
            scored.append(
                (
                    len(matched),
                    len(str(path)),
                    {
                        "path": str(path),
                        "source": source,
                        "matched_terms": sorted(matched),
                    },
                )
            )

    scored.sort(key=lambda t: (-t[0], t[1]))
    truncated = len(scored) > limit
    results = [entry for _, _, entry in scored[:limit]]

    return json.dumps(
        {
            "query": query,
            "expanded_terms": sorted(terms),
            "count": len(results),
            "truncated": truncated,
            "results": results,
        },
        indent=2,
    )
