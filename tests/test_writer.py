"""Tests for vault_writer — idempotency and block format."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest

from pali_nlp.analysis.frequency import CorpusFrequency
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import SuttaDoc
from pali_nlp.writer.vault_writer import (
    _VOCAB_SENTINEL,
    _VOCAB_END,
    _BLOCK_RE,
    write_vocab_block,
)

from collections import Counter


SAMPLE_MULA = textwrap.dedent("""\
    ---
    id: MN10
    title: "Test Sutta"
    ---

    **bhikkhu ca dhamma**
    *monk and dhamma*
""")


def _make_doc(path: Path, content: str) -> SuttaDoc:
    path.write_text(content, encoding="utf-8")
    return SuttaDoc(
        path=path,
        sutta_id="MN10",
        title="Test Sutta",
        nikaya="majjhima_nikaya",
        frontmatter={"id": "MN10"},
        pali_tokens=["bhikkhu", "ca", "dhamma"],
        raw_pali_text="bhikkhu ca dhamma",
    )


def _stub_lem(tmp_path: Path) -> DPDLemmatizer:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return DPDLemmatizer(db_path=tmp_path / "nodb.db")


def _fake_freq() -> CorpusFrequency:
    hf: Counter[str] = Counter({"dhamma": 1000, "bhikkhu": 500, "ca": 2000})
    return CorpusFrequency(
        token_freq=hf, headword_freq=hf,
        total_tokens=3500, total_unique_headwords=3,
    )


def test_write_vocab_block_appends_sentinel(tmp_path):
    doc = _make_doc(tmp_path / "mn10.md", SAMPLE_MULA)
    lem = _stub_lem(tmp_path)
    freq = _fake_freq()
    with lem:
        changed = write_vocab_block(doc, lem, freq)
    assert changed
    content = (tmp_path / "mn10.md").read_text()
    assert _VOCAB_SENTINEL in content
    assert _VOCAB_END in content


def test_write_vocab_block_idempotent(tmp_path):
    doc = _make_doc(tmp_path / "mn10.md", SAMPLE_MULA)
    lem = _stub_lem(tmp_path)
    freq = _fake_freq()
    with lem:
        write_vocab_block(doc, lem, freq)
        first = (tmp_path / "mn10.md").read_text()
        # Re-read so doc.path content is fresh
        doc2 = _make_doc(tmp_path / "mn10.md", first)
        doc2.pali_tokens[:] = doc.pali_tokens
        changed = write_vocab_block(doc2, lem, freq)
    assert not changed
    assert (tmp_path / "mn10.md").read_text().count(_VOCAB_SENTINEL) == 1


def test_write_vocab_block_dry_run_does_not_write(tmp_path):
    doc = _make_doc(tmp_path / "mn10.md", SAMPLE_MULA)
    lem = _stub_lem(tmp_path)
    freq = _fake_freq()
    with lem:
        changed = write_vocab_block(doc, lem, freq, dry_run=True)
    assert changed  # reports would-change
    content = (tmp_path / "mn10.md").read_text()
    assert _VOCAB_SENTINEL not in content  # file not touched
