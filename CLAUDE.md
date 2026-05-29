# CLAUDE.md — pali-nlp Agent Guardrails

*Read this FIRST before making changes to this repository.*

## Purpose

`pali-nlp` is the NLP companion to the [`pali-canon`](https://github.com/roydsouza/pali-canon) Obsidian vault. It reads vault mūla files, processes Pali text using the Digital Pāḷi Dictionary (DPD) database, and writes reading aids (vocabulary concordance tables, graded-reader rankings, SRS cards) back into the vault as plain Markdown.

**The vault is the product. This repo is the tooling.** Do not put Markdown study content here.

## Repository Layout

```
pali-nlp/
├── src/pali_nlp/
│   ├── ingestion/    # vault_reader.py — walk mūla files, extract Pali tokens
│   ├── dpd/          # lemmatizer.py — DPD SQLite lookup
│   ├── analysis/     # frequency.py, graded_reader.py
│   ├── writer/       # vault_writer.py — write artefacts back to vault
│   └── scripts/      # CLI entry points (grade_suttas, build_vocab, write_vocab_tables)
├── tests/
└── data/             # git-ignored: dpd.db goes here
```

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `PALI_VAULT` | Absolute path to pali-canon vault root | Required |
| `PALI_DPD` | Absolute path to `dpd.db` | `data/dpd.db` |

## Setup

```bash
# 1. Install (editable, with dev deps)
pip install -e ".[dev]"

# 2. Set environment variables
export PALI_VAULT=/Users/rds/pali_canon
export PALI_DPD=/Users/rds/pali-nlp/data/dpd.db

# 3. Download the DPD database (one-time, ~500MB)
#    https://github.com/digitalpalidictionary/dpd-db/releases
#    Drop dpd.db into data/dpd.db (git-ignored)

# 4. Run tests
pytest
```

## DPD Database

The DPD database is already installed on this machine via Simsapa Dhamma Reader:

    ~/Library/Application Support/simsapa/assets/dpd.sqlite3

The lemmatizer defaults to this path automatically — no configuration needed. Set `PALI_DPD` to override.

The DB is git-ignored and must never be committed. It uses two tables:
- `lookup` (1.1M rows) — maps inflected forms to headwords via `lookup_key` → `grammar` JSON
- `dpd_headwords` — canonical headwords with `lemma_clean`, `pos`, `meaning_1`, `ebt_count`

The pipeline runs in **stub mode** if the DB is absent (useful for CI/tests without the DB).

## CLI Tools

```bash
# Corpus frequency statistics
pali-vocab --vault $PALI_VAULT --top 50

# Graded reading list (easiest → hardest)
pali-grade --vault $PALI_VAULT --out $PALI_VAULT/paths/graded_reader.md

# Inject vocabulary tables into vault mūla files
pali-write --vault $PALI_VAULT --dry-run      # preview
pali-write --vault $PALI_VAULT                # write
pali-write --vault $PALI_VAULT --sutta MN10   # single sutta
```

## Guardrails

1. **Tests must pass before every commit**: `pytest`
2. **Ruff must pass**: `ruff check src/ tests/`
3. **Never write to the vault without `--dry-run` preview first**
4. **Never commit `dpd.db`**, derived corpora, or vault files into this repo
5. **The vault's pre-commit hook** (link validator) will catch broken wikilinks injected by `pali-write` — always run it in the vault after a write pass
6. **Push after every commit**: `git push origin main` (no post-commit hook here; push manually)

## Phase 17 Roadmap

| Stage | Status | Description |
|---|---|---|
| 1A — Ingestion & Lemmatization | ✅ Architecture complete (stub mode) | vault_reader + DPD lemmatizer |
| 1B — Frequency & Graded Reader | ✅ Architecture complete | corpus frequency + difficulty ranking |
| 1C — Vocabulary Writer | ✅ Architecture complete | inject vocab callouts into vault |
| 1D — SRS Cards | ⬜ Not started | Obsidian spaced-repetition card generation |
| 2A — Concordance Index | ⬜ Not started | offline concordance + collocation search |
| 2B — NER / Prosopography | ⬜ Not started | Named entity tagger → vault people/ pages |
| 3A — Vector Search | ⬜ Not started | local embeddings + semantic search |
| 4A — Rust Porting | ⬜ Not started | tokenizer + sandhi-splitting in Rust |

## Relationship to pali-canon

- **pali-nlp reads**: `$PALI_VAULT/mula/sutta/**/*.md`
- **pali-nlp writes back**: vocabulary callout blocks appended to mūla files, graded reader Markdown under `paths/`, future SRS cards under `practice/`
- **Never modify**: atthakathā, ṭīkā, mātikā, or meta/ files from this repo
- **After any write pass**: run `python3 scratch/validate_links.py` in the vault
