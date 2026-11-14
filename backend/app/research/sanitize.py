"""Cleaning of untrusted web results: URLs and text snippets."""

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAM = re.compile(r"^(utm_.*|fbclid|gclid|dclid|mc_cid|mc_eid|ref|ref_src|igshid)$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮﻿]")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING_MARKS = re.compile(r"(^|\s)#{1,6}\s")
_WHITESPACE = re.compile(r"\s+")


def normalize_url(url: str | None) -> str | None:
    """Canonical http(s) URL for de-duplication, or None if not a safe web URL.

    Drops fragments and tracking parameters, lowercases scheme/host, trims the trailing
    slash - so "https://X.com/a/?utm_source=t#top" and "https://x.com/a" are one source.
    Rejects javascript:, data:, file: and other non-web schemes outright.
    """
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _TRACKING_PARAM.match(key.lower())
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def domain_of(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host.removeprefix("www.")


def clean_snippet(text: str | None, max_chars: int) -> str:
    """Plain, single-line, length-limited text (markdown and control chars removed)."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _CONTROL.sub("", text)
    text = _MARKDOWN_IMAGE.sub("", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _HEADING_MARKS.sub(r"\1", text)
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + " …"


def escape_for_prompt(text: str, tag: str) -> str:
    """Stop untrusted text from opening/closing our prompt delimiters."""
    return text.replace(f"<{tag}", f"&lt;{tag}").replace(f"</{tag}", f"&lt;/{tag}")
