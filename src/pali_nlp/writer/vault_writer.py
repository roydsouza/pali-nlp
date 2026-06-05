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
    # Words with corpus rank below this threshold are too common to be worth reviewing
    min_rank: int = 30,
) -> str:
    """Build the collapsible vocab callout block for one sutta."""
    unique = lemmatizer.lookup_unique(doc.pali_tokens)
    entries: list[tuple[int, LemmaResult]] = []
    for r in unique.values():
        # Skip stopwords and unresolved forms (empty gloss + unknown POS)
        if r.headword in _STOPWORDS:
            continue
        if not r.found:
            continue  # filter out unresolved sandhi/inflected forms marked (?)
        rank = corpus_freq.rank(r.headword)
        if rank <= 0:
            rank = 999999  # unknown rank → treat as very rare; include but sort last
        if rank < min_rank:
            continue  # skip very-high-frequency structural words
        entries.append((rank, r))

    # Sort by ascending rank (most common learnable words first).
    # This surfaces mid-frequency practice vocabulary above hyper-rare
    # anatomical or technical terms that only appear in specialized passages.
    entries.sort(key=lambda x: x[0])
    entries = entries[:max_entries]

    rows = []
    for rank, r in entries:
        gloss = r.meaning[:60] + "…" if len(r.meaning) > 60 else r.meaning
        rows.append(f"| {r.headword} | {r.pos} | {gloss} |")

    if not rows:
        return ""

    table = "\n".join([
        "| Headword | POS | Meaning |",
        "|---|---|---|",
        *rows,
    ])

    return (
        f"\n{_VOCAB_SENTINEL}\n"
        f"> [!NOTE]- Vocabulary ({len(rows)} entries, most frequent first)\n"
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


def update_srs_file(
    file_path: Path,
    blocks: dict[str, tuple[str, str, list[tuple[str, str]]]],
    dry_run: bool = False,
) -> bool:
    """
    Batch update multiple SRS blocks in a single file.
    blocks: dict mapping target_id -> (deck_name, title, list of (front, back) tuples)
    Returns True if the file content was (or would be) modified.
    """
    original = ""
    if file_path.is_file():
        original = file_path.read_text(encoding="utf-8")

    content = original if original else (
        "---\n"
        "id: vocabulary_cards\n"
        "title: Pāḷi Vocabulary Flashcards\n"
        "type: practice\n"
        "tags:\n"
        "  - practice/vocabulary\n"
        "  - flashcards\n"
        "---\n\n"
        "# Pāḷi Vocabulary Flashcards\n\n"
        "This file contains auto-generated vocabulary flashcards for early Buddhist texts.\n"
        "See [[tutorial/07_vocabulary_srs|Tutorial 7: Vocabulary Spaced Repetition (SRS)]] for CLI commands, reference documentation, and setup instructions.\n"
        "Use the Obsidian Spaced Repetition plugin to review them.\n\n"
        "---\n"
    )

    modified = False

    for target_id, (deck_name, title, cards) in blocks.items():
        start_sent = f"<!-- pali-nlp:srs-start target={target_id} -->"
        end_sent = f"<!-- pali-nlp:srs-end target={target_id} -->"

        pattern = re.compile(
            r"\n?" + re.escape(start_sent) + r".*?" + re.escape(end_sent) + r"\n?",
            re.DOTALL,
        )

        if not cards:
            if pattern.search(content):
                content = pattern.sub("", content)
                modified = True
            continue

        # Build the block string
        block_lines = [
            start_sent,
            f"### {title}",
            f"<!-- card-deck: {deck_name} -->",
            "",
        ]
        for front, back in cards:
            block_lines.append(f"{front} :: {back}")
        block_lines.append(end_sent)
        block_str = "\n".join(block_lines)

        if pattern.search(content):
            new_content = pattern.sub(f"\n{block_str}\n", content)
        else:
            new_content = content.rstrip() + f"\n\n{block_str}\n"

        if new_content != content:
            content = new_content
            modified = True

    if modified and not dry_run:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return modified

