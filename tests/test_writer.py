"""Tests for vault_writer — idempotency and block format."""

from __future__ import annotations

import textwrap
import warnings
from collections import Counter
from pathlib import Path

from pali_nlp.analysis.frequency import CorpusFrequency
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import SuttaDoc
from pali_nlp.writer.vault_writer import (
    _VOCAB_END,
    _VOCAB_SENTINEL,
    update_srs_file,
    write_vocab_block,
)

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


def test_update_srs_file_creates_and_updates(tmp_path):
    srs_file = tmp_path / "srs.md"
    blocks = {
        "sutta:MN10": (
            "Vocabulary/MN10",
            "MN 10: Satipaṭṭhānasutta",
            [("bhikkhu", "[masc] monk"), ("dhamma", "[masc] teaching")],
        ),
    }
    
    # 1. Create file and write block
    changed = update_srs_file(srs_file, blocks)
    assert changed
    assert srs_file.is_file()
    content = srs_file.read_text()
    assert "<!-- pali-nlp:srs-start target=sutta:MN10 -->" in content
    assert "<!-- card-deck: Vocabulary/MN10 -->" in content
    assert "bhikkhu :: [masc] monk" in content
    assert "dhamma :: [masc] teaching" in content

    # 2. Re-run identical: should not report change
    changed = update_srs_file(srs_file, blocks)
    assert not changed

    # 3. Update block content
    blocks_updated = {
        "sutta:MN10": (
            "Vocabulary/MN10",
            "MN 10: Satipaṭṭhānasutta",
            [("bhikkhu", "[masc] monk"), ("dhamma", "[masc] teaching"), ("citta", "[neut] mind")],
        ),
    }
    changed = update_srs_file(srs_file, blocks_updated)
    assert changed
    content = srs_file.read_text()
    assert "citta :: [neut] mind" in content

    # 4. Remove block if cards empty
    blocks_empty = {
        "sutta:MN10": ("Vocabulary/MN10", "MN 10: Satipaṭṭhānasutta", []),
    }
    changed = update_srs_file(srs_file, blocks_empty)
    assert changed
    content = srs_file.read_text()
    assert "<!-- pali-nlp:srs-start target=sutta:MN10 -->" not in content


def test_update_srs_file_dry_run(tmp_path):
    srs_file = tmp_path / "srs.md"
    blocks = {
        "sutta:MN10": ("Vocabulary/MN10", "MN 10: Satipaṭṭhānasutta", [("bhikkhu", "[masc] monk")]),
    }
    changed = update_srs_file(srs_file, blocks, dry_run=True)
    assert changed
    assert not srs_file.is_file()  # not written

