"""
Graded-reader: rank suttas by vocabulary difficulty.

Produces a sorted list of (sutta_id, nikaya, title, score, token_count)
from easiest to hardest, suitable for a practitioner who wants to read
Pali texts in order of increasing lexical difficulty.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pali_nlp.analysis.frequency import CorpusFrequency, sutta_difficulty_score
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import iter_mula_docs


@dataclass
class GradedEntry:
    sutta_id: str
    file_stem: str        # actual filename stem for reliable wikilinks
    nikaya: str
    title: str
    score: float          # mean frequency rank of unique non-common headwords
    token_count: int      # total Pali tokens in mūla
    unique_headwords: int # unique lemmas after DPD lookup


def build_graded_list(
    vault_root: Path,
    corpus_freq: CorpusFrequency,
    lemmatizer: DPDLemmatizer,
    min_tokens: int = 20,
) -> list[GradedEntry]:
    """
    Return suttas sorted easiest → hardest (ascending score).

    min_tokens: skip files with fewer tokens than this (stubs, indexes).
    """
    entries = []
    for doc in iter_mula_docs(vault_root):
        if len(doc.pali_tokens) < min_tokens:
            continue
        score = sutta_difficulty_score(doc, corpus_freq, lemmatizer)
        unique_hw = len(set(
            r.headword
            for r in lemmatizer.lookup_many(doc.pali_tokens)
        ))
        entries.append(GradedEntry(
            sutta_id=doc.sutta_id,
            file_stem=doc.path.stem,
            nikaya=doc.nikaya,
            title=doc.title,
            score=score,
            token_count=len(doc.pali_tokens),
            unique_headwords=unique_hw,
        ))
    entries.sort(key=lambda e: e.score)
    return entries


def render_graded_markdown(entries: list[GradedEntry]) -> str:
    """Render the graded list as a Markdown table for the vault."""
    lines = [
        "---",
        "id: graded_reader",
        "title: Pali Graded Reader",
        "type: path",
        "tags:",
        "  - graded-reader",
        "  - pali-nlp",
        "---",
        "",
        "# Pali Graded Reader",
        "",
        "Suttas ordered by vocabulary difficulty (easiest first).",
        "Score = mean frequency rank of unique non-common headwords.",
        "Lower score = more common vocabulary = easier Pali.",
        "",
        "| Rank | Sutta | Nikāya | Score | Tokens | Unique Words |",
        "|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(entries, start=1):
        nikaya_label = e.nikaya.replace('_nikaya', '').replace('_', ' ').title()
        lines.append(
            f"| {i} | [[{e.file_stem}\\|{e.sutta_id}]] "
            f"| {nikaya_label} "
            f"| {e.score:.0f} | {e.token_count} | {e.unique_headwords} |"
        )
    return "\n".join(lines) + "\n"
