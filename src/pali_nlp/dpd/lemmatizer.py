"""
DPD (Digital Pāḷi Dictionary) lemmatizer.

Uses the Simsapa DPD SQLite database installed at:
    ~/Library/Application Support/simsapa/assets/dpd.sqlite3

On __enter__, loads all 78k dpd_headwords rows into an in-memory dict
so every headword lookup is O(1) with no SQL round-trips.

Lookup strategy for an inflected token:
  1. lookup table (1.1M rows, PK-indexed on lookup_key) → grammar JSON
     → headword string → in-memory headword dict for meaning/ebt_count
  2. Fallback: direct match in headword dict (token is already a headword)
  3. Stub: token returned as its own headword with no gloss

Bulk path (lookup_many with ≥20 unique tokens): chunked IN queries
against the lookup table (500 tokens/chunk), all headword data from
the in-memory dict — no per-token SQL round-trips after the bulk pass.
After the bulk pass, any remaining cache misses receive stubs directly
(no re-querying tables we already scanned).
"""

from __future__ import annotations

import json
import os
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LemmaResult:
    token: str
    headword: str
    pos: str
    meaning: str
    ebt_count: int
    found: bool


_SIMSAPA_DEFAULT = (
    Path.home() / "Library" / "Application Support" / "simsapa" / "assets" / "dpd.sqlite3"
)
_CHUNK = 500  # safely below SQLite's 999-variable limit


def _default_db_path() -> Path:
    env = os.environ.get("PALI_DPD")
    return Path(env) if env else _SIMSAPA_DEFAULT


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _stub(token: str) -> LemmaResult:
    return LemmaResult(token=token, headword=token, pos="?", meaning="", ebt_count=0, found=False)


class DPDLemmatizer:
    """
    Stateful lemmatizer backed by the DPD SQLite database.

    Usage:
        with DPDLemmatizer() as lem:
            results = lem.lookup_many(["bhikkhuno", "dhammaṁ", "nibbānaṁ"])
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._conn: sqlite3.Connection | None = None
        # In-memory headword index: lemma_clean → (pos, meaning_1, ebt_count)
        self._hw_map: dict[str, tuple[str, str, int]] = {}
        self._stub_mode = not self._db_path.is_file()
        if self._stub_mode:
            warnings.warn(
                f"DPD database not found at {self._db_path}. "
                "Running in stub mode — tokens returned as-is without glosses.",
                RuntimeWarning,
                stacklevel=2,
            )

    def __enter__(self) -> DPDLemmatizer:
        if not self._stub_mode:
            self._conn = sqlite3.connect(
                f"file:{self._db_path}?mode=ro", uri=True, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._load_headword_map()
        return self

    def __exit__(self, *_) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._hw_map.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, token: str) -> LemmaResult:
        if self._stub_mode or self._conn is None:
            return _stub(token)
        result = self._lookup_via_lookup_table(token)
        if result is None:
            result = self._lookup_via_hw_map(token)
        return result or _stub(token)

    def lookup_many(self, tokens: list[str]) -> list[LemmaResult]:
        """
        Batch lookup. For ≥20 unique tokens uses bulk SQL; remaining misses
        get stubs directly (no re-querying tables already scanned).
        """
        BATCH_THRESHOLD = 20
        unique = list(dict.fromkeys(tokens))
        cache: dict[str, LemmaResult] = {}

        if not self._stub_mode and self._conn is not None and len(unique) >= BATCH_THRESHOLD:
            self._bulk_prefetch(unique, cache)
            # Stub out everything the bulk pass couldn't resolve — no re-querying
            for tok in unique:
                if tok not in cache:
                    cache[tok] = _stub(tok)
        else:
            for tok in unique:
                cache[tok] = self.lookup(tok)

        return [cache[tok] for tok in tokens]

    def lookup_unique(self, tokens: list[str]) -> dict[str, LemmaResult]:
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
    # Private: initialisation
    # ------------------------------------------------------------------

    def _load_headword_map(self) -> None:
        """Load all 78k headwords into memory. Called once on __enter__."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT lemma_clean, pos, meaning_1, ebt_count FROM dpd_headwords"
        ).fetchall()
        for row in rows:
            lc = row["lemma_clean"]
            if lc and lc not in self._hw_map:
                self._hw_map[lc] = (
                    row["pos"] or "?",
                    row["meaning_1"] or "",
                    row["ebt_count"] or 0,
                )

    # ------------------------------------------------------------------
    # Private: per-token lookups (used when below bulk threshold)
    # ------------------------------------------------------------------

    def _lookup_via_lookup_table(self, token: str) -> LemmaResult | None:
        assert self._conn
        row = self._conn.execute(
            "SELECT grammar FROM lookup WHERE lookup_key = ? LIMIT 1", (token,)
        ).fetchone()
        if row is None:
            return None
        try:
            grammar = json.loads(row["grammar"] or "[]")
        except (json.JSONDecodeError, TypeError):
            return None
        if not grammar or not isinstance(grammar[0], list) or not grammar[0]:
            return None
        headword = grammar[0][0]
        pos = grammar[0][1] if len(grammar[0]) > 1 else "?"
        hw_pos, meaning, ebt = self._hw_map.get(headword, (pos, "", 0))
        return LemmaResult(
            token=token, headword=headword, pos=hw_pos,
            meaning=meaning, ebt_count=ebt, found=True,
        )

    def _lookup_via_hw_map(self, token: str) -> LemmaResult | None:
        if token not in self._hw_map:
            return None
        pos, meaning, ebt = self._hw_map[token]
        return LemmaResult(
            token=token, headword=token, pos=pos,
            meaning=meaning, ebt_count=ebt, found=True,
        )

    # ------------------------------------------------------------------
    # Private: bulk prefetch
    # ------------------------------------------------------------------

    def _bulk_prefetch(self, tokens: list[str], cache: dict[str, LemmaResult]) -> None:
        """
        Resolve tokens via chunked lookup-table IN queries.
        Headword data comes from the in-memory _hw_map (no extra SQL).
        Tokens matched directly as headwords are resolved via _hw_map too.
        """
        assert self._conn
        found_keys: set[str] = set()

        for chunk in _chunks(tokens, _CHUNK):
            ph = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT lookup_key, grammar FROM lookup WHERE lookup_key IN ({ph})",
                chunk,
            ).fetchall()
            for row in rows:
                key = row["lookup_key"]
                found_keys.add(key)
                try:
                    grammar = json.loads(row["grammar"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    continue
                if not grammar or not isinstance(grammar[0], list) or not grammar[0]:
                    continue
                headword = grammar[0][0]
                pos_from_grammar = grammar[0][1] if len(grammar[0]) > 1 else "?"
                hw_pos, meaning, ebt = self._hw_map.get(headword, (pos_from_grammar, "", 0))
                cache[key] = LemmaResult(
                    token=key, headword=headword, pos=hw_pos,
                    meaning=meaning, ebt_count=ebt, found=True,
                )

        # Tokens not in lookup table: try direct headword match in memory
        for tok in tokens:
            if tok not in found_keys and tok in self._hw_map:
                pos, meaning, ebt = self._hw_map[tok]
                cache[tok] = LemmaResult(
                    token=tok, headword=tok, pos=pos,
                    meaning=meaning, ebt_count=ebt, found=True,
                )
