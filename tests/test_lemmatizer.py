"""Tests for DPD lemmatizer — stub mode (no DB required)."""

from __future__ import annotations

import pytest

from pali_nlp.dpd.lemmatizer import DPDLemmatizer


def test_stub_mode_when_no_db(tmp_path):
    """Without a DB, lemmatizer should run in stub mode without raising."""
    with pytest.warns(RuntimeWarning, match="stub mode"):
        lem = DPDLemmatizer(db_path=tmp_path / "nonexistent.db")
    assert lem.is_stub


def test_stub_lookup_returns_token_as_headword(tmp_path):
    with pytest.warns(RuntimeWarning):
        lem = DPDLemmatizer(db_path=tmp_path / "nonexistent.db")
    with lem:
        result = lem.lookup("bhikkhu")
    assert result.token == "bhikkhu"
    assert result.headword == "bhikkhu"
    assert result.found is False
    assert result.pos == "?"


def test_stub_lookup_many_deduplicates(tmp_path):
    with pytest.warns(RuntimeWarning):
        lem = DPDLemmatizer(db_path=tmp_path / "nonexistent.db")
    with lem:
        results = lem.lookup_many(["dhamma", "dhamma", "bhikkhu"])
    assert len(results) == 3
    assert results[0].headword == results[1].headword == "dhamma"


def test_stub_lookup_unique_deduplicates_headwords(tmp_path):
    with pytest.warns(RuntimeWarning):
        lem = DPDLemmatizer(db_path=tmp_path / "nonexistent.db")
    with lem:
        unique = lem.lookup_unique(["dhamma", "dhamma", "bhikkhu"])
    # stub headword == token, so two "dhamma" → one entry
    assert len(unique) == 2
