"""pali-grade: print or write a graded sutta reading list."""

from __future__ import annotations

from pathlib import Path

import click

from pali_nlp.analysis.frequency import build_corpus_frequency
from pali_nlp.analysis.graded_reader import build_graded_list, render_graded_markdown
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import vault_root_from_env


@click.command()
@click.option("--vault", envvar="PALI_VAULT", type=click.Path(exists=True, file_okay=False),
              help="Path to pali-canon vault root (or set PALI_VAULT).")
@click.option("--dpd", envvar="PALI_DPD", type=click.Path(),
              help="Path to dpd.db (or set PALI_DPD).")
@click.option("--out", type=click.Path(), default=None,
              help="Write graded list to this file (default: stdout).")
@click.option("--min-tokens", default=20, show_default=True,
              help="Skip suttas with fewer Pali tokens than this.")
def main(vault: str | None, dpd: str | None, out: str | None, min_tokens: int) -> None:
    """Build and output a vocabulary-difficulty-ordered reading list."""
    vault_path = Path(vault) if vault else vault_root_from_env()
    with DPDLemmatizer(dpd) as lem:
        click.echo("Building corpus frequency table…", err=True)
        freq = build_corpus_frequency(vault_path, lem)
        click.echo(
            f"Corpus: {freq.total_tokens:,} tokens, "
            f"{freq.total_unique_headwords:,} unique headwords",
            err=True,
        )
        click.echo("Grading suttas…", err=True)
        entries = build_graded_list(vault_path, freq, lem, min_tokens=min_tokens)
        md = render_graded_markdown(entries)

    if out:
        Path(out).write_text(md, encoding="utf-8")
        click.echo(f"Written to {out}", err=True)
    else:
        click.echo(md)
