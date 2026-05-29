"""
Walk the pali-canon vault mūla directory and extract Pali text segments.

Mūla files interleave bold Pali lines with italic English lines:
    **Evaṁ me sutaṁ—**
    *So I have heard.*

This module yields SuttaDoc objects — one per mūla file — with parsed
frontmatter and the list of raw Pali tokens extracted from bold segments.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml

# Matches **Pali text** (bold segments = Pali in the interleaved format)
_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.MULTILINE)

# YAML frontmatter block
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Punctuation to strip when tokenizing (keep diacritics, hyphens inside words)
_PUNCT_RE = re.compile(r"[,;:.!?()\[\]{}'\"…—\|·°]+")


@dataclass
class SuttaDoc:
    path: Path
    sutta_id: str          # from frontmatter `id:` field
    title: str             # from frontmatter `title:` field, or filename stem
    nikaya: str            # inferred from path (majjhima_nikaya, etc.)
    frontmatter: dict
    pali_tokens: list[str] = field(default_factory=list)
    raw_pali_text: str = ""


def _infer_nikaya(path: Path) -> str:
    parts = path.parts
    for p in parts:
        if p.endswith("_nikaya"):
            return p
    return "unknown"


def _parse_frontmatter(text: str) -> dict:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _extract_pali_tokens(text: str) -> tuple[str, list[str]]:
    """Return (concatenated_pali_text, token_list) from bold segments."""
    segments = _BOLD_RE.findall(text)
    raw = " ".join(segments)
    tokens = []
    for seg in segments:
        cleaned = _PUNCT_RE.sub(" ", seg)
        for tok in cleaned.split():
            tok = tok.strip("-").lower()
            if tok:
                tokens.append(tok)
    return raw, tokens


def iter_mula_docs(vault_root: Path | str) -> Iterator[SuttaDoc]:
    """Yield one SuttaDoc per mūla sutta file in the vault."""
    vault_root = Path(vault_root)
    mula_dir = vault_root / "mula" / "sutta"
    if not mula_dir.is_dir():
        raise FileNotFoundError(f"mula/sutta not found under {vault_root}")

    for md_file in sorted(mula_dir.rglob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        sutta_id = str(fm.get("id", md_file.stem))
        title = str(fm.get("title", md_file.stem))
        nikaya = _infer_nikaya(md_file)
        raw_pali, tokens = _extract_pali_tokens(text)
        yield SuttaDoc(
            path=md_file,
            sutta_id=sutta_id,
            title=title,
            nikaya=nikaya,
            frontmatter=fm,
            pali_tokens=tokens,
            raw_pali_text=raw_pali,
        )


def vault_root_from_env() -> Path:
    v = os.environ.get("PALI_VAULT")
    if not v:
        raise EnvironmentError("PALI_VAULT environment variable is not set")
    p = Path(v)
    if not p.is_dir():
        raise FileNotFoundError(f"PALI_VAULT={v} does not exist")
    return p
