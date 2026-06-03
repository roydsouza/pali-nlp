"""Tests for vault_reader ingestion module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pali_nlp.ingestion.vault_reader import (
    _extract_pali_tokens,
    _parse_frontmatter,
    iter_mula_docs,
)

SAMPLE_MULA = textwrap.dedent("""\
    ---
    id: MN10
    title: "Satipaṭṭhānasutta"
    type: mula
    ---

    # MN 10: Satipaṭṭhānasutta

    **Evaṁ me sutaṁ—**
    *So I have heard.*

    **Ekaṁ samayaṁ bhagavā**
    *At one time the Buddha*

    **kurūsu viharati kammāsadhammaṁ nāma kurūnaṁ nigamo.**
    *was staying in the land of the Kurus, at a town of the Kurus named Kammāsadamma.*
""")


def test_parse_frontmatter_extracts_id():
    fm = _parse_frontmatter(SAMPLE_MULA)
    assert fm["id"] == "MN10"
    assert fm["title"] == "Satipaṭṭhānasutta"


def test_parse_frontmatter_missing_returns_empty():
    fm = _parse_frontmatter("# No frontmatter here\n\nJust text.")
    assert fm == {}


def test_extract_pali_tokens_returns_bold_content():
    raw, tokens = _extract_pali_tokens(SAMPLE_MULA)
    assert "evaṁ" in tokens
    assert "me" in tokens
    assert "sutaṁ" in tokens
    # italic English should NOT appear
    assert "so" not in tokens
    assert "i" not in tokens


def test_extract_pali_tokens_strips_punctuation():
    text = "**bhikkhu, ca vā.**\n*monk and or.*\n"
    _, tokens = _extract_pali_tokens(text)
    assert "bhikkhu" in tokens
    assert "," not in " ".join(tokens)
    assert "." not in " ".join(tokens)


def test_extract_pali_tokens_lowercases():
    text = "**Evaṁ Me Sutaṁ**\n*So I have heard.*\n"
    _, tokens = _extract_pali_tokens(text)
    assert "evaṁ" in tokens
    assert "Evaṁ" not in tokens


def test_iter_mula_docs_uses_vault(tmp_path: Path):
    """iter_mula_docs yields one doc per sutta file, skipping INDEX.md."""
    mula_dir = tmp_path / "mula" / "sutta" / "majjhima_nikaya"
    mula_dir.mkdir(parents=True)
    (mula_dir / "mn10.md").write_text(SAMPLE_MULA, encoding="utf-8")
    (mula_dir / "INDEX.md").write_text("# Index\n", encoding="utf-8")

    docs = list(iter_mula_docs(tmp_path))
    assert len(docs) == 1
    assert docs[0].sutta_id == "MN10"
    assert docs[0].nikaya == "majjhima_nikaya"
    assert len(docs[0].pali_tokens) > 0


def test_iter_mula_docs_raises_on_missing_vault(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        list(iter_mula_docs(tmp_path / "nonexistent"))
