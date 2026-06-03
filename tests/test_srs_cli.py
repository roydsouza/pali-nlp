"""Tests for pali-srs CLI tool."""

from __future__ import annotations

import textwrap
from pathlib import Path

from click.testing import CliRunner

from pali_nlp.scripts.write_srs_cards import main

SAMPLE_MULA = textwrap.dedent("""\
    ---
    id: MN10
    title: "Satipaṭṭhānasutta"
    type: mula
    ---

    # MN 10: Satipaṭṭhānasutta

    **bhikkhu ca dhamma**
    *monk and dhamma*
""")


def _setup_mock_vault(tmp_path: Path) -> Path:
    mula_dir = tmp_path / "mula" / "sutta" / "majjhima_nikaya"
    mula_dir.mkdir(parents=True)
    (mula_dir / "mn10.md").write_text(SAMPLE_MULA, encoding="utf-8")
    return tmp_path


def test_cli_requires_action(tmp_path):
    vault = _setup_mock_vault(tmp_path)
    runner = CliRunner()
    # Should fail because neither --sutta, --all-suttas, nor --top is specified
    result = runner.invoke(main, ["--vault", str(vault)])
    assert result.exit_code != 0
    assert "Error: Please specify either --sutta, --all-suttas, or --top." in result.output


def test_cli_sutta_generation(tmp_path):
    vault = _setup_mock_vault(tmp_path)
    srs_file = tmp_path / "practice" / "vocabulary_cards.md"
    runner = CliRunner()
    
    # Run with a stub DPD path (will run in stub/warning mode but still generate cards)
    result = runner.invoke(main, [
        "--vault", str(vault),
        "--dpd", str(tmp_path / "nodb.db"),
        "--sutta", "MN10",
        "--out", str(srs_file),
        "--min-rank", "0",
    ])
    
    assert result.exit_code == 0
    assert "Updated 1 block(s)" in result.output
    assert srs_file.is_file()
    
    content = srs_file.read_text()
    assert "<!-- pali-nlp:srs-start target=sutta:MN10 -->" in content
    assert "<!-- card-deck: Vocabulary/MN10 -->" in content
    # Note: 'ca' is a stopword and should be filtered out. 'bhikkhu' and 'dhamma' should be cards.
    assert "bhikkhu :: [?] (meaning unknown)" in content
    assert "dhamma :: [?] (meaning unknown)" in content
    assert "ca ::" not in content


def test_cli_top_generation(tmp_path):
    vault = _setup_mock_vault(tmp_path)
    srs_file = tmp_path / "practice" / "vocabulary_cards.md"
    runner = CliRunner()
    
    result = runner.invoke(main, [
        "--vault", str(vault),
        "--dpd", str(tmp_path / "nodb.db"),
        "--top", "5",
        "--out", str(srs_file),
    ])
    
    assert result.exit_code == 0
    assert "Updated 1 block(s)" in result.output
    assert srs_file.is_file()
    
    content = srs_file.read_text()
    assert "<!-- pali-nlp:srs-start target=top:5 -->" in content
    assert "<!-- card-deck: Vocabulary/Core5 -->" in content
