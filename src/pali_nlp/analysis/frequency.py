"""
Corpus-wide token and lemma frequency analysis.

Builds frequency tables from all mūla documents in the vault so that
graded-reader ranking and vocabulary-concordance generation can use
consistent corpus frequencies rather than per-sutta counts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from pali_nlp.dpd.lemmatizer import DPDLemmatizer, LemmaResult
from pali_nlp.ingestion.vault_reader import SuttaDoc, iter_mula_docs


@dataclass
class CorpusFrequency:
    """Frequency tables built from the full vault corpus."""

    token_freq: Counter[str]          # raw token counts
    headword_freq: Counter[str]       # lemma headword counts
    total_tokens: int
    total_unique_headwords: int

    def rank(self, headword: str) -> int:
        """1-based frequency rank (1 = most common). Returns 0 if not found."""
        ranked = self.headword_freq.most_common()
        for i, (hw, _) in enumerate(ranked, start=1):
            if hw == headword:
                return i
        return 0

    def is_common(self, headword: str, top_n: int = 200) -> bool:
        """True if headword is in the top-N most frequent across the corpus."""
        return self.rank(headword) <= top_n


def build_corpus_frequency(
    vault_root: Path,
    lemmatizer: DPDLemmatizer,
) -> CorpusFrequency:
    """
    Walk all mūla docs and build token + headword frequency tables.
    Expensive first call; cache the result externally if needed.
    """
    token_freq: Counter[str] = Counter()
    headword_freq: Counter[str] = Counter()

    for doc in iter_mula_docs(vault_root):
        token_freq.update(doc.pali_tokens)
        results = lemmatizer.lookup_many(doc.pali_tokens)
        headword_freq.update(r.headword for r in results)

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
    Compute a difficulty score for one sutta.

    Lower score = more common vocabulary = easier to read.
    Score = mean inverse frequency rank of the sutta's unique headwords,
    ignoring the top-50 corpus-wide words (they appear everywhere and
    don't differentiate difficulty).
    """
    if not doc.pali_tokens:
        return 0.0

    results = lemmatizer.lookup_unique(doc.pali_tokens)
    scores = []
    for r in results.values():
        rank = corpus_freq.rank(r.headword)
        if rank == 0 or rank <= 50:
            continue
        scores.append(rank)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)
