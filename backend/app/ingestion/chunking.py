"""Token-aware chunking with LangChain's RecursiveCharacterTextSplitter.

"Recursive" means it tries to split on paragraph breaks first, then lines, then
sentences, then words - so chunks end at natural boundaries where possible.
Sizes are measured in tokens (tiktoken cl100k), matching how LLM context is budgeted.
Overlap repeats the tail of one chunk at the start of the next, so a fact that sits on
a boundary is still retrievable from one chunk.

PDF pages are chunked independently: a chunk never spans two pages, so every chunk
cites exactly one page.
"""

from dataclasses import dataclass
from functools import lru_cache

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.cleaning import clean_text
from app.ingestion.extractors import PageText

ENCODING = "cl100k_base"


@dataclass(frozen=True)
class Chunk:
    index: int  # 0-based position within the document
    page: int | None
    text: str
    token_count: int


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING)


@lru_cache
def _splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def chunk_pages(pages: list[PageText], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    splitter = _splitter(chunk_size, chunk_overlap)
    chunks: list[Chunk] = []
    for page in pages:
        text = clean_text(page.text)
        if not text:
            continue
        for piece in splitter.split_text(text):
            chunks.append(
                Chunk(
                    index=len(chunks),
                    page=page.page,
                    text=piece,
                    token_count=count_tokens(piece),
                )
            )
    return chunks
