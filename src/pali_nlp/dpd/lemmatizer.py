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
        """
        Batch lookup preserving order.

        For lists > BATCH_THRESHOLD unique tokens, pre-fetches all from the
        lookup table in a single IN(...) query, falling back to per-token
        lookup for misses. This makes corpus-wide passes ~100× faster.
        """
        BATCH_THRESHOLD = 20
        unique = list(dict.fromkeys(tokens))  # deduplicated, order-preserving
        cache: dict[str, LemmaResult] = {}

        if not self._stub_mode and self._conn is not None and len(unique) >= BATCH_THRESHOLD:
            self._bulk_prefetch(unique, cache)

        for tok in unique:
            if tok not in cache:
                cache[tok] = self.lookup(tok)

        return [cache[tok] for tok in tokens]

    _CHUNK = 500  # safely below SQLite's 999-variable limit

    def _bulk_prefetch(self, tokens: list[str], cache: dict[str, LemmaResult]) -> None:
        """
        Fetch all tokens from DPD in chunked IN queries.

        Two-pass strategy:
          1. lookup table → grammar JSON → headword list
          2. dpd_headwords bulk fetch for all headwords found in pass 1
             + direct match for tokens that are themselves headwords (misses in pass 1)
        """
        assert self._conn
        found_keys: set[str] = set()
        # token → (headword, pos) from lookup table
        token_hw: dict[str, tuple[str, str]] = {}

        for chunk in _chunks(tokens, self._CHUNK):
            ph = ",".join("?" * len(chunk))
            for row in self._conn.execute(
                f"SELECT lookup_key, grammar FROM lookup WHERE lookup_key IN ({ph})",
                chunk,
            ).fetchall():
                key = row["lookup_key"]
                found_keys.add(key)
                try:
                    grammar = json.loads(row["grammar"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    continue
                if grammar and isinstance(grammar[0], list) and grammar[0]:
                    hw = grammar[0][0]
                    pos = grammar[0][1] if len(grammar[0]) > 1 else "?"
                    token_hw[key] = (hw, pos)

        # Bulk-fetch meanings for all headwords found in pass 1
        headwords_needed = list({hw for hw, _ in token_hw.values()})
        hw_data: dict[str, tuple[str, int]] = {}
        for chunk in _chunks(headwords_needed, self._CHUNK):
            ph = ",".join("?" * len(chunk))
            for row in self._conn.execute(
                f"SELECT lemma_clean, meaning_1, ebt_count "
                f"FROM dpd_headwords WHERE lemma_clean IN ({ph})",
                chunk,
            ).fetchall():
                hw_data[row["lemma_clean"]] = (row["meaning_1"] or "", row["ebt_count"] or 0)

        for token, (hw, pos) in token_hw.items():
            meaning, ebt = hw_data.get(hw, ("", 0))
            cache[token] = LemmaResult(
                token=token, headword=hw, pos=pos,
                meaning=meaning, ebt_count=ebt, found=True,
            )

        # Tokens not in lookup table → try direct headword match
        misses = [t for t in tokens if t not in found_keys]
        for chunk in _chunks(misses, self._CHUNK):
            ph = ",".join("?" * len(chunk))
            for row in self._conn.execute(
                f"SELECT lemma_clean, pos, meaning_1, ebt_count "
                f"FROM dpd_headwords WHERE lemma_clean IN ({ph})",
                chunk,
            ).fetchall():
                lc = row["lemma_clean"]
                cache[lc] = LemmaResult(
                    token=lc, headword=lc, pos=row["pos"] or "?",
                    meaning=row["meaning_1"] or "", ebt_count=row["ebt_count"] or 0,
                    found=True,
                )

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


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _stub(token: str) -> LemmaResult:
    return LemmaResult(token=token, headword=token, pos="?", meaning="", ebt_count=0, found=False)
