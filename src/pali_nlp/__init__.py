"""
pali-nlp: NLP companion for the pali-canon Obsidian vault.

Reads vault mūla files, lemmatizes Pali tokens against the DPD database,
and writes vocabulary concordance tables and graded-reader rankings back
as Markdown artefacts.

Environment:
    PALI_VAULT  — absolute path to the pali-canon vault root
    PALI_DPD    — absolute path to dpd.db (default: data/dpd.db)
"""
