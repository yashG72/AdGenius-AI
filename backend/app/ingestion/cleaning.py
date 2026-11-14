"""Text normalization applied before chunking.

Extracted text is messy: ligatures ("ﬁ"), words hyphenated across PDF line breaks,
invisible control characters, runs of spaces and blank lines. Cleaning makes chunks
smaller (cheaper) and both keyword and semantic search more accurate.
"""

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏﻿]")
_HYPHENATED_BREAK = re.compile(r"([a-z])-\n([a-z])")
_SPACES = re.compile(r"[ \t ]+")
_SPACES_AROUND_NEWLINE = re.compile(r" *\n *")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # "ﬁ" -> "fi", full-width -> normal
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _HYPHENATED_BREAK.sub(r"\1\2", text)  # "adver-\ntising" -> "advertising"
    text = _SPACES.sub(" ", text)
    text = _SPACES_AROUND_NEWLINE.sub("\n", text)
    text = _MANY_NEWLINES.sub("\n\n", text)  # keep paragraph breaks, drop the rest
    return text.strip()
