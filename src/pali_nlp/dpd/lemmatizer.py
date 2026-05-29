"""
DPD (Digital Pāḷi Dictionary) lemmatizer.

Looks up Pali tokens in the DPD SQLite database and returns the canonical
headword, part of speech, and primary English meaning for each.

DPD database: https://github.com/digitalpalidictionary/dpd-db/releases
Expected path: $PALI_DPD or data/dpd.db relative to the repo root.

The DPD `dpd_headwords` table schema (relevant columns):
    id              INTEGER PRIMARY KEY
    lemma_1         TEXT    -- headword with number suffix (e.g. "bhikkhu 1")
    lemma_clean     TEXT    -- headword without suffix (e.g. "bhikkhu")
    pos             TEXT    -- part of speech (nt, masc, fem, ind, pr, aor, ...)
    meaning_1       TEXT    -- primary English gloss
    meaning_2       TEXT    -- secondary gloss (often Pali synonym)
    construction    TEXT    -- sandhi/derivation info
    frequency       INTEGER -- corpus frequency count (from DPD's own analysis)

If the DB is not present, the lemmatizer runs in stub mode: it returns
the raw token as its own headword with no gloss. This lets the full
pipeline run without the DB so the architecture can be tested end-to-end.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LemmaResult:
    token: str            # original token as found in text
    headword: str         # DPD lemma_clean (or token if not found)
    pos: str              # part of speech ("?" if not found)
    meaning: str          # primary English gloss ("" if not found)
    dpd_frequency: int    # DPD's own corpus frequency (0 if not found)
    found: bool           # False = token not in DPD (unknown / proper noun / sandhi)


_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # pali-nlp/


def _default_db_path() -> Path:
    env = os.environ.get("PALI_DPD")
    if env:
        return Path(env)
    return _REPO_ROOT / "data" / "dpd.db"


class DPDLemmatizer:
    """
    Stateful lemmatizer backed by a DPD SQLite connection.

    Usage:
        with DPDLemmatizer() as lem:
            results = lem.lookup_many(["bhikkhu", "dhamma", "nibbāna"])
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._stub_mode = not self._db_path.is_file()
        if self._stub_mode:
            import warnings
            warnings.warn(
                f"DPD database not found at {self._db_path}. "
                "Running in stub mode — tokens returned as-is without glosses. "
                "Download dpd.db from https://github.com/digitalpalidictionary/dpd-db/releases",
                RuntimeWarning,
                stacklevel=2,
            )

    def __enter__(self) -> "DPDLemmatizer":
        if not self._stub_mode:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Read-only pragma for safety
            self._conn.execute("PRAGMA query_only = ON")
        return self

    def __exit__(self, *_) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def lookup(self, token: str) -> LemmaResult:
        """Look up a single token. Always returns a LemmaResult."""
        if self._stub_mode or self._conn is None:
            return LemmaResult(
                token=token, headword=token, pos="?", meaning="", dpd_frequency=0, found=False
            )
        # Try exact match on lemma_clean first, then strip trailing digits/spaces
        row = self._query_exact(token)
        if row is None:
            # Try lowercase normalized form
            row = self._query_exact(token.lower())
        if row is None:
            return LemmaResult(
                token=token, headword=token, pos="?", meaning="", dpd_frequency=0, found=False
            )
        return LemmaResult(
            token=token,
            headword=row["lemma_clean"] or token,
            pos=row["pos"] or "?",
            meaning=row["meaning_1"] or "",
            dpd_frequency=row["frequency"] or 0,
            found=True,
        )

    def _query_exact(self, token: str) -> sqlite3.Row | None:
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT lemma_clean, pos, meaning_1, frequency "
            "FROM dpd_headwords WHERE lemma_clean = ? LIMIT 1",
            (token,),
        )
        return cur.fetchone()

    def lookup_many(self, tokens: list[str]) -> list[LemmaResult]:
        """Deduplicated batch lookup. Preserves order of first occurrence."""
        seen: dict[str, LemmaResult] = {}
        result = []
        for tok in tokens:
            if tok not in seen:
                seen[tok] = self.lookup(tok)
            result.append(seen[tok])
        return result

    def lookup_unique(self, tokens: list[str]) -> dict[str, LemmaResult]:
        """Return one LemmaResult per unique token (headword-deduplicated)."""
        seen_headwords: set[str] = set()
        out: dict[str, LemmaResult] = {}
        for tok in tokens:
            r = self.lookup(tok)
            if r.headword not in seen_headwords:
                seen_headwords.add(r.headword)
                out[tok] = r
        return out

    @property
    def is_stub(self) -> bool:
        return self._stub_mode
