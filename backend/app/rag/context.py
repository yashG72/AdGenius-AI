"""Context assembly: pick chunks within a token budget, number them for citation.

Retrieved text is UNTRUSTED (anyone in the org can upload a document saying "ignore
your instructions"). It is wrapped in clearly delimited <source> blocks and the system
prompt tells the model to treat it purely as data.
"""

from app.ingestion.chunking import count_tokens
from app.rag.types import RetrievedChunk, Source


def select_sources(
    chunks: list[RetrievedChunk], *, max_chunks: int, token_budget: int
) -> list[Source]:
    sources: list[Source] = []
    used = 0
    seen_texts: set[str] = set()
    for chunk in chunks:
        if len(sources) >= max_chunks:
            break
        key = " ".join(chunk.text.split()).lower()
        if key in seen_texts:  # identical text from duplicated documents
            continue
        tokens = count_tokens(chunk.text)
        if used + tokens > token_budget and sources:
            continue  # skip oversized chunk, a smaller later one may still fit
        seen_texts.add(key)
        sources.append(Source(number=len(sources) + 1, chunk=chunk))
        used += tokens
    return sources


def _escape(text: str) -> str:
    # Stop document text from closing/opening our delimiters.
    return text.replace("<source", "&lt;source").replace("</source", "&lt;/source")


def render_sources(sources: list[Source]) -> str:
    blocks = []
    for source in sources:
        chunk = source.chunk
        page = f' page="{chunk.source_page}"' if chunk.source_page is not None else ""
        blocks.append(
            f'<source id="{source.number}" file="{_escape(chunk.original_filename)}"{page}>\n'
            f"{_escape(chunk.text)}\n</source>"
        )
    return "\n\n".join(blocks)
