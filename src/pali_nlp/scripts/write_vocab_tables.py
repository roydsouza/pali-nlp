"""pali-write: inject vocabulary concordance tables into vault mūla files."""

from __future__ import annotations

import click
from pathlib import Path

from pali_nlp.analysis.frequency import build_corpus_frequency
from pali_nlp.dpd.lemmatizer import DPDLemmatizer
from pali_nlp.ingestion.vault_reader import iter_mula_docs, vault_root_from_env
from pali_nlp.writer.vault_writer import write_vocab_block


@click.command()
@click.option("--vault", envvar="PALI_VAULT", type=click.Path(exists=True, file_okay=False))
@click.option("--dpd", envvar="PALI_DPD", type=click.Path())
@click.option("--dry-run", is_flag=True, help="Report what would change without writing.")
@click.option("--sutta", default=None, help="Process only this sutta ID (e.g. MN10).")
@click.option("--min-tokens", default=20, show_default=True)
def main(
    vault: str | None,
    dpd: str | None,
    dry_run: bool,
    sutta: str | None,
    min_tokens: int,
) -> None:
    """
    Append or refresh vocabulary concordance callouts in mūla sutta files.

    The callout is a collapsible > [!NOTE]- Vocabulary block listing unique
    Pali headwords (DPD lookup), sorted rarest-first, appended after the
    sutta body. Idempotent: safe to re-run.
    """
    vault_path = Path(vault) if vault else vault_root_from_env()

    with DPDLemmatizer(dpd) as lem:
        if lem.is_stub:
            click.echo(
                "WARNING: Running in stub mode (no DPD database). "
                "Vocabulary blocks will have no glosses.",
                err=True,
            )
        click.echo("Building corpus frequency table…", err=True)
        freq = build_corpus_frequency(vault_path, lem)

        modified = 0
        skipped = 0
        for doc in iter_mula_docs(vault_path):
            if sutta and doc.sutta_id.upper() != sutta.upper():
                continue
            if len(doc.pali_tokens) < min_tokens:
                skipped += 1
                continue
            changed = write_vocab_block(doc, lem, freq, dry_run=dry_run)
            if changed:
                modified += 1
                verb = "Would update" if dry_run else "Updated"
                click.echo(f"  {verb}: {doc.path.name} ({doc.sutta_id})")

    action = "Would modify" if dry_run else "Modified"
    click.echo(f"\n{action} {modified} file(s). Skipped {skipped} (too short).")
