"""Exact matching and ambiguity tests."""

from __future__ import annotations

import pytest

from hermes_credential_switcher.matching import MatchError, infer_provider, resolve_target
from tests.helpers import fake_entry


def _entries():
    return [
        fake_entry(entry_id="id-one", label="Alpha", priority=0),
        fake_entry(entry_id="id-two", label="Beta", priority=1),
        fake_entry(entry_id="id-three", label="beta", priority=2),  # label clash case?
    ]


def test_exact_id_match():
    m = resolve_target(_entries()[:2], "id-two")
    assert m.index == 1
    assert m.matched_by == "id"
    assert m.entry["label"] == "Beta"


def test_exact_label_case_insensitive():
    m = resolve_target(_entries()[:2], "alpha")
    assert m.index == 0
    assert m.matched_by == "label"


def test_ambiguous_label():
    entries = [
        fake_entry(entry_id="1", label="Same", priority=0),
        fake_entry(entry_id="2", label="same", priority=1),
    ]
    with pytest.raises(MatchError, match="Ambiguous"):
        resolve_target(entries, "SAME")


def test_index_1_based():
    m = resolve_target(_entries()[:2], "2")
    assert m.index == 1
    assert m.matched_by == "index"


def test_index_out_of_range():
    with pytest.raises(MatchError, match="No credential #9"):
        resolve_target(_entries()[:2], "9")


def test_no_substring_label_match():
    with pytest.raises(MatchError, match="No credential matching"):
        resolve_target(_entries()[:2], "Alp")  # partial


def test_empty_target():
    with pytest.raises(MatchError, match="No credential target"):
        resolve_target(_entries()[:2], "  ")


def test_id_preferred_over_index_when_id_is_numeric_looking():
    entries = [
        fake_entry(entry_id="2", label="x", priority=0),
        fake_entry(entry_id="other", label="y", priority=1),
    ]
    # Exact id "2" wins before index interpretation.
    m = resolve_target(entries, "2")
    assert m.matched_by == "id"
    assert m.entry["label"] == "x"


def test_infer_provider_single():
    pool = {"only": [fake_entry(entry_id="a", label="a", priority=0)]}
    assert infer_provider(pool, provider=None) == "only"


def test_infer_provider_requires_explicit_when_multi():
    pool = {
        "a": [fake_entry(entry_id="a1", label="a", priority=0)],
        "b": [fake_entry(entry_id="b1", label="b", priority=0)],
    }
    with pytest.raises(MatchError, match="Multiple providers"):
        infer_provider(pool, provider=None)


def test_infer_provider_from_unique_target():
    pool = {
        "a": [fake_entry(entry_id="a1", label="alpha", priority=0)],
        "b": [fake_entry(entry_id="b1", label="beta", priority=0)],
    }
    assert infer_provider(pool, provider=None, target="beta") == "b"
