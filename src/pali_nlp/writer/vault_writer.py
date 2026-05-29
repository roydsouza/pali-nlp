"""
Vault writer: append vocabulary concordance tables to mūla sutta files.

Each sutta gets a collapsible Obsidian callout appended at the end of its
mūla file listing the unique Pali headwords found in that sutta, with their
part of speech and English gloss, sorted by corpus frequency rank (common
words first, rare words last).

The block is idempotent: if the sutta already has a vocab block it is
replaced in-place so repeated runs do not accumulate duplicates.
"""

from __future__ import annotations

import re
from pathlib import Path

from pali_nlp.analysis.frequency import CorpusFrequency
from pali_nlp.dpd.lemmatizer import DPDLemmatizer, LemmaResult
from pali_nlp.ingestion.vault_reader import SuttaDoc

# The sentinel that marks the start of an injected vocab block
_VOCAB_SENTINEL = "<!-- pali-nlp:vocab-start -->"
_VOCAB_END = "<!-- pali-nlp:vocab-end -->"
_BLOCK_RE = re.compile(
    r"\n?" + re.escape(_VOCAB_SENTINEL) + r".*?" + re.escape(_VOCAB_END) + r"\n?",
    re.DOTALL,
)

# Omit extremely common grammatical particles from the concordance table
# (they appear in every sutta and add no study value)
_STOPWORDS = {
    "ca", "vā", "na", "pi", "hi", "eva", "ti", "iti", "so", "no", "nu",
    "kho", "pana", "tu", "ce", "yeva", "neva", "api", "atha",
}


def _build_vocab_block(
    doc: SuttaDoc,
    lemmatizer: DPDLemmatizer,
    corpus_freq: CorpusFrequency,
    max_entries: int = 60,
) -> str:
    """Build the collapsible vocab callout block for one sutta."""
    unique = lemmatizer.lookup_unique(doc.pali_tokens)
    entries: list[tuple[int, LemmaResult]] = []
    for r in unique.values():
        if r.headword in _STOPWORDS:
            continue
        rank = corpus_freq.rank(r.headword)
        entries.append((rank if rank > 0 else 999999, r))

    # Sort: rarer words first (higher rank number = rarer), cap at max_entries
    entries.sort(key=lambda x: -x[0])
    entries = entries[:max_entries]

    rows = []
    for rank, r in entries:
        gloss = r.meaning[:60] + "…" if len(r.meaning) > 60 else r.meaning
        found_marker = "" if r.found else " (?)"
        rows.append(f"| {r.headword}{found_marker} | {r.pos} | {gloss} |")

    if not rows:
        return ""

    table = "\n".join([
        "| Headword | POS | Meaning |",
        "|---|---|---|",
        *rows,
    ])

    return (
        f"\n{_VOCAB_SENTINEL}\n"
        f"> [!NOTE]- Vocabulary ({len(rows)} entries, rarest first)\n"
        f"> \n"
        + "\n".join(f"> {line}" for line in table.splitlines())
        + f"\n{_VOCAB_END}\n"
    )


def write_vocab_block(
    doc: SuttaDoc,
    lemmatizer: DPDLemmatizer,
    corpus_freq: CorpusFrequency,
    dry_run: bool = False,
) -> bool:
    """
    Append or replace the vocabulary block in a sutta's mūla file.

    Returns True if the file was (or would be) modified.
    """
    original = doc.path.read_text(encoding="utf-8")
    # Strip any existing block
    stripped = _BLOCK_RE.sub("", original).rstrip()
    block = _build_vocab_block(doc, lemmatizer, corpus_freq)
    if not block:
        return False

    new_content = stripped + "\n" + block
    if new_content == original:
        return False
    if not dry_run:
        doc.path.write_text(new_content, encoding="utf-8")
    return True
