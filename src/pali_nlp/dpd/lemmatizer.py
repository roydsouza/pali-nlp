"""
DPD (Digital Pāḷi Dictionary) lemmatizer.

Uses the Simsapa DPD SQLite database already installed on this machine at:
    ~/Library/Application Support/simsapa/assets/dpd.sqlite3

Two-table lookup strategy:
  1. lookup(lookup_key) → grammar JSON → headword + POS + inflection form
     Covers 1.1M inflected forms; this is the primary path.
  2. dpd_headwords(lemma_clean) → meaning_1, ebt_count
     Fallback for tokens that are already headwords or not in the lookup table.

Runs in stub mode (returns token as its own headword, no gloss) if the DB
is not found, so tests and dry-runs work without the database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LemmaResult:
    token: str            # original token as found in text
    headword: str         # DPD lemma_clean (or token if not found)
    pos: str              # part of speech ("?" if not found)
    meaning: str          # primary English gloss ("" if not found)
    ebt_count: int        # occurrences in early Buddhist texts (0 if not found)
    found: bool           # False = token not in DPD


_SIMSAPA_DEFAULT = (
    Path.home() / "Library" / "Application Support" / "simsapa" / "assets" / "dpd.sqlite3"
)


def _default_db_path() -> Path:
    env = os.environ.get("PALI_DPD")
    if env:
        return Path(env)
    return _SIMSAPA_DEFAULT


class DPDLemmatizer:
    """
    Stateful lemmatizer backed by the DPD SQLite connection.

    Usage:
        with DPDLemmatizer() as lem:
            results = lem.lookup_many(["bhikkhuno", "dhammā", "nibbānaṁ"])
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._stub_mode = not self._db_path.is_file()
        if self._stub_mode:
            warnings.warn(
                f"DPD database not found at {self._db_path}. "
                "Running in stub mode — tokens returned as-is without glosses.",
                RuntimeWarning,
                stacklevel=2,
            )

    def __enter__(self) -> "DPDLemmatizer":
        if not self._stub_mode:
            self._conn = sqlite3.connect(
                f"file:{self._db_path}?mode=ro", uri=True, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, *_) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, token: str) -> LemmaResult:
        """Look up a single token. Always returns a LemmaResult."""
        if self._stub_mode or self._conn is None:
            return _stub(token)
        result = self._lookup_via_lookup_table(token)
        if result is None:
            result = self._lookup_via_headwords(token)
        return result or _stub(token)

    def lookup_many(self, tokens: list[str]) -> list[LemmaResult]:
        """Batch lookup preserving order; reuses cached results for duplicates."""
        cache: dict[str, LemmaResult] = {}
        out = []
        for tok in tokens:
            if tok not in cache:
                cache[tok] = self.lookup(tok)
            out.append(cache[tok])
        return out

    def lookup_unique(self, tokens: list[str]) -> dict[str, LemmaResult]:
        """One result per unique headword (first token to map to it wins)."""
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _lookup_via_lookup_table(self, token: str) -> LemmaResult | None:
        """
        Primary path: lookup table covers ~1.1M inflected forms.
        grammar column is a JSON list of [headword, pos, inflection_form] triples.
        """
        assert self._conn
        row = self._conn.execute(
            "SELECT grammar, headwords FROM lookup WHERE lookup_key = ? LIMIT 1",
            (token,),
        ).fetchone()
        if row is None:
            return None

        grammar_raw = row["grammar"]
        if not grammar_raw:
            return None
        try:
            grammar = json.loads(grammar_raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not grammar or not isinstance(grammar[0], list):
            return None

        headword = grammar[0][0]
        pos = grammar[0][1] if len(grammar[0]) > 1 else "?"
        meaning, ebt = self._fetch_headword_meaning(headword)
        return LemmaResult(
            token=token, headword=headword, pos=pos,
            meaning=meaning, ebt_count=ebt, found=True,
        )

    def _lookup_via_headwords(self, token: str) -> LemmaResult | None:
        """Fallback: direct match on lemma_clean (token is already a headword)."""
        assert self._conn
        row = self._conn.execute(
            "SELECT lemma_clean, pos, meaning_1, ebt_count "
            "FROM dpd_headwords WHERE lemma_clean = ? LIMIT 1",
            (token,),
        ).fetchone()
        if row is None:
            return None
        return LemmaResult(
            token=token,
            headword=row["lemma_clean"] or token,
            pos=row["pos"] or "?",
            meaning=row["meaning_1"] or "",
            ebt_count=row["ebt_count"] or 0,
            found=True,
        )

    def _fetch_headword_meaning(self, headword: str) -> tuple[str, int]:
        """Return (meaning_1, ebt_count) for a headword string."""
        assert self._conn
        row = self._conn.execute(
            "SELECT meaning_1, ebt_count FROM dpd_headwords "
            "WHERE lemma_clean = ? LIMIT 1",
            (headword,),
        ).fetchone()
        if row is None:
            return "", 0
        return row["meaning_1"] or "", row["ebt_count"] or 0


def _stub(token: str) -> LemmaResult:
    return LemmaResult(token=token, headword=token, pos="?", meaning="", ebt_count=0, found=False)
