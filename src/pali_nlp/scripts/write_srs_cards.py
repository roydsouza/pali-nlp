"""pali-srs: generate Obsidian-native spaced repetition cards for Pali vocabulary."""

from __future__ import annotations

from pathlib import Path

import click

from pali_nlp.analysis.frequency import build_corpus_frequency
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import iter_mula_docs, vault_root_from_env
from pali_nlp.writer.vault_writer import _STOPWORDS, update_srs_file


@click.command()
@click.option("--vault", envvar="PALI_VAULT", type=click.Path(exists=True, file_okay=False),
              help="Path to pali-canon vault root (or set PALI_VAULT).")
@click.option("--dpd", envvar="PALI_DPD", type=click.Path(),
              help="Path to dpd.db (or set PALI_DPD).")
@click.option("--dry-run", is_flag=True, help="Report what would change without writing.")
@click.option("--sutta", default=None, help="Process only this sutta ID (e.g. MN10).")
@click.option("--all-suttas", is_flag=True, help="Process all suttas in the vault.")
@click.option("--top", default=None, type=int,
              help="Generate core vocabulary cards for the top N most frequent headwords.")
@click.option("--min-rank", default=50, show_default=True,
              help="Exclude top-N common words to filter out basic vocabulary (ignored for --top).")
@click.option("--max-cards", default=50, show_default=True,
              help="Maximum number of cards to generate per block (sutta or top-N deck).")
@click.option("--out", type=click.Path(), default=None,
              help="Custom output file path. Defaults to $PALI_VAULT/practice/vocabulary_cards.md.")
def main(
    vault: str | None,
    dpd: str | None,
    dry_run: bool,
    sutta: str | None,
    all_suttas: bool,
    top: int | None,
    min_rank: int,
    max_cards: int,
    out: str | None,
) -> None:
    """
    Generate Obsidian-native spaced-repetition vocabulary cards.
    
    Creates double-colon card entries and organizes them into sub-decks
    under a main deck 'Vocabulary' (e.g. Vocabulary/MN10, Vocabulary/Core200).
    Updates practice/vocabulary_cards.md in-place.
    """
    if not sutta and not all_suttas and not top:
        raise click.UsageError("Please specify either --sutta, --all-suttas, or --top.")

    vault_path = Path(vault) if vault else vault_root_from_env()
    out_path = Path(out) if out else vault_path / "practice" / "vocabulary_cards.md"

    blocks = {}

    with DPDLemmatizer(dpd) as lem:
        if lem.is_stub:
            click.echo(
                "WARNING: Running in stub mode (no DPD database). "
                "Vocabulary cards will have no glosses.",
                err=True,
            )

        click.echo("Building corpus frequency table…", err=True)
        freq = build_corpus_frequency(vault_path, lem)

        # 1. Process specific sutta or all suttas
        if sutta or all_suttas:
            for doc in iter_mula_docs(vault_path):
                if sutta and doc.sutta_id.upper() != sutta.upper():
                    continue

                # Query unique headwords
                unique = lem.lookup_unique(doc.pali_tokens)
                entries = []
                for r in unique.values():
                    if r.headword in _STOPWORDS:
                        continue
                    rank = freq.rank(r.headword)
                    if rank <= min_rank and rank > 0:
                        continue
                    entries.append((rank if rank > 0 else 999999, r))

                # Sort by frequency rank (ascending: common first, but after min_rank threshold)
                entries.sort(key=lambda x: x[0])
                entries = entries[:max_cards]

                cards = []
                for _, r in entries:
                    meaning = r.meaning[:100] + "..." if len(r.meaning) > 100 else r.meaning
                    pos_label = f"[{r.pos}] " if r.pos else ""
                    back = f"{pos_label}{meaning}" if r.found else f"{pos_label}(meaning unknown)"
                    cards.append((r.headword, back))

                if cards:
                    target_id = f"sutta:{doc.sutta_id.upper()}"
                    deck_name = f"Vocabulary/{doc.sutta_id.upper()}"
                    title = f"{doc.sutta_id.upper()}: {doc.title}"
                    blocks[target_id] = (deck_name, title, cards)

        # 2. Process top N core vocabulary
        if top is not None:
            # We don't apply min_rank for core vocabulary
            entries = []
            for hw, count in freq.headword_freq.most_common(top):
                if hw in _STOPWORDS:
                    continue
                res = lem.lookup(hw)
                rank = freq.rank(hw)
                entries.append((rank if rank > 0 else 999999, res))

            entries.sort(key=lambda x: x[0])
            entries = entries[:max_cards]

            cards = []
            for _, r in entries:
                meaning = r.meaning[:100] + "..." if len(r.meaning) > 100 else r.meaning
                pos_label = f"[{r.pos}] " if r.pos else ""
                back = f"{pos_label}{meaning}" if r.found else f"{pos_label}(meaning unknown)"
                cards.append((r.headword, back))

            if cards:
                target_id = f"top:{top}"
                deck_name = f"Vocabulary/Core{top}"
                title = f"Top {top} Core Vocabulary"
                blocks[target_id] = (deck_name, title, cards)

    # 3. Perform batch write
    if blocks:
        changed = update_srs_file(out_path, blocks, dry_run=dry_run)
        action = "Would update" if dry_run else "Updated"
        if changed:
            click.echo(f"{action} {len(blocks)} block(s) in {out_path.name}")
        else:
            click.echo(f"No changes needed for {out_path.name}")
    else:
        click.echo("No cards generated.")
