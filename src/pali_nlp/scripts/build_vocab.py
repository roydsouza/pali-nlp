"""pali-vocab: show corpus-wide headword frequency statistics."""

from __future__ import annotations

from pathlib import Path

import click

from pali_nlp.analysis.frequency import build_corpus_frequency
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import vault_root_from_env


@click.command()
@click.option("--vault", envvar="PALI_VAULT", type=click.Path(exists=True, file_okay=False))
@click.option("--dpd", envvar="PALI_DPD", type=click.Path())
@click.option("--top", default=100, show_default=True, help="Show top-N headwords.")
@click.option("--nikaya", default=None, help="Filter to a specific nikāya directory name.")
def main(vault: str | None, dpd: str | None, top: int, nikaya: str | None) -> None:
    """Print the most frequent Pali headwords across the vault corpus."""
    vault_path = Path(vault) if vault else vault_root_from_env()
    with DPDLemmatizer(dpd) as lem:
        freq = build_corpus_frequency(vault_path, lem)

    click.echo(f"Total tokens : {freq.total_tokens:,}")
    click.echo(f"Unique heads : {freq.total_unique_headwords:,}")
    click.echo("")
    click.echo(f"{'Rank':>5}  {'Count':>7}  Headword")
    click.echo("-" * 40)
    for rank, (hw, count) in enumerate(freq.headword_freq.most_common(top), start=1):
        click.echo(f"{rank:5}  {count:7,}  {hw}")
