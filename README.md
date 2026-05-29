# pali-nlp

NLP companion to the [pali-canon](https://github.com/roydsouza/pali-canon) Obsidian vault.

Reads vault mūla files, lemmatizes Pali tokens against the [Digital Pāḷi Dictionary](https://digitalpalidictionary.github.io) (DPD) database, and writes reading aids back into the vault as plain Markdown — vocabulary concordance tables, a graded-reader ranking, and (coming) spaced-repetition cards.

**The vault is the product. This repo is the tooling.**

---

## Setup

```bash
git clone https://github.com/roydsouza/pali-nlp.git
cd pali-nlp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export PALI_VAULT=/path/to/pali_canon   # pali-canon vault root
export PALI_DPD=/path/to/data/dpd.db   # DPD SQLite (see below)
```

### DPD Database

Already installed via Simsapa Dhamma Reader at:

    ~/Library/Application Support/simsapa/assets/dpd.sqlite3

No configuration needed — the lemmatizer finds it automatically. Set `PALI_DPD` to override the path.

---

## CLI Tools

```bash
# Corpus-wide headword frequency statistics
pali-vocab --top 100

# Graded reading list (easiest Pali → hardest)
pali-grade --out $PALI_VAULT/paths/graded_reader.md

# Inject vocabulary concordance tables into vault mūla files
pali-write --dry-run     # preview changes
pali-write               # write to vault
pali-write --sutta MN10  # single sutta
```

After any write pass, run the vault's link validator:

```bash
cd $PALI_VAULT && python3 scratch/validate_links.py
```

---

## Architecture

```
src/pali_nlp/
├── ingestion/     vault_reader.py      — walk mūla files, extract Pali tokens
├── dpd/           lemmatizer.py        — DPD SQLite lemmatizer (stub if no DB)
├── analysis/      frequency.py         — corpus-wide token/headword frequency
│                  graded_reader.py     — difficulty ranking by lexical frequency
├── writer/        vault_writer.py      — inject vocabulary callouts into vault files
└── scripts/       grade_suttas.py      — pali-grade CLI
                   build_vocab.py       — pali-vocab CLI
                   write_vocab_tables.py — pali-write CLI
```

---

## Roadmap (Phase 17)

| Stage | Status | Description |
|---|---|---|
| 1A — Ingestion & Lemmatization | ✅ | vault_reader + DPD lemmatizer |
| 1B — Frequency & Graded Reader | ✅ | corpus frequency + difficulty ranking |
| 1C — Vocabulary Writer | ✅ | inject vocab callouts into vault files |
| 1D — SRS Cards | planned | Obsidian spaced-repetition card generation |
| 2A — Concordance Index | planned | offline concordance + collocation search |
| 2B — NER / Prosopography | planned | Named entity tagger → vault people/ pages |
| 3A — Vector Search | planned | local embeddings + semantic search |
| 4A — Rust Porting | planned | tokenizer + sandhi-splitting in Rust |

---

## Tests

```bash
pytest          # 14 tests, no DB required
ruff check src/ tests/
```
