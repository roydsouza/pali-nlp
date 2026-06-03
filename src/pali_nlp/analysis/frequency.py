"""
Corpus-wide token and lemma frequency analysis.

Builds frequency tables from all mūla documents in the vault so that
graded-reader ranking and vocabulary-concordance generation can use
consistent corpus frequencies rather than per-sutta counts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import SuttaDoc, iter_mula_docs


@dataclass
class CorpusFrequency:
    """Frequency tables built from the full vault corpus."""

    token_freq: Counter[str]
    headword_freq: Counter[str]
    total_tokens: int
    total_unique_headwords: int
    # Pre-built rank index: headword → 1-based rank (1 = most common)
    _rank_index: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._rank_index = {
            hw: i for i, (hw, _) in enumerate(self.headword_freq.most_common(), start=1)
        }

    def rank(self, headword: str) -> int:
        """1-based frequency rank. Returns 0 if not found."""
        return self._rank_index.get(headword, 0)

    def is_common(self, headword: str, top_n: int = 200) -> bool:
        return self.rank(headword) <= top_n


def build_corpus_frequency(
    vault_root: Path,
    lemmatizer: DPDLemmatizer,
) -> CorpusFrequency:
    """
    Walk all mūla docs and build token + headword frequency tables.

    Collects all unique tokens first, bulk-fetches from DPD in one pass,
    then maps token counts to headword counts — avoids N SQLite round-trips.
    """
    token_freq: Counter[str] = Counter()

    # First pass: count tokens across all docs
    for doc in iter_mula_docs(vault_root):
        token_freq.update(doc.pali_tokens)

    # Bulk lookup of all unique tokens (lemmatizer caches per token internally)
    unique_tokens = list(token_freq.keys())
    results = lemmatizer.lookup_many(unique_tokens)
    token_to_headword = {r.token: r.headword for r in results}

    # Map token counts → headword counts
    headword_freq: Counter[str] = Counter()
    for token, count in token_freq.items():
        hw = token_to_headword.get(token, token)
        headword_freq[hw] += count

    return CorpusFrequency(
        token_freq=token_freq,
        headword_freq=headword_freq,
        total_tokens=sum(token_freq.values()),
        total_unique_headwords=len(headword_freq),
    )


def sutta_difficulty_score(
    doc: SuttaDoc,
    corpus_freq: CorpusFrequency,
    lemmatizer: DPDLemmatizer,
) -> float:
    """
    Difficulty score for one sutta: mean rank of unique non-common headwords.
    Lower = easier (more common vocabulary). Skips top-50 corpus words.
    """
    if not doc.pali_tokens:
        return 0.0

    results = lemmatizer.lookup_unique(doc.pali_tokens)
    scores = [
        corpus_freq.rank(r.headword)
        for r in results.values()
        if corpus_freq.rank(r.headword) > 50
    ]
    return sum(scores) / len(scores) if scores else 0.0
