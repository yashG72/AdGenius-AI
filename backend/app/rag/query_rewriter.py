"""Query understanding + rewriting (LLM).

Users type things like "what can't we say in ads?". The documents say "Legal
restrictions: never make health claims". Rewriting bridges that vocabulary gap by
producing a clearer standalone query plus a few alternative phrasings; every variant is
searched and the results fused.

Safety nets: the ORIGINAL query is always searched too (a bad rewrite can't lose recall),
and if the LLM is missing or fails we simply search the original query.
"""

import logging

from pydantic import BaseModel, Field

from app.llm.client import StructuredLLM

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You improve search queries for a brand knowledge base containing brand \
guidelines, product specifications, customer personas, past campaigns and marketing documents.

Given a user's query:
1. Identify what information they need.
2. Write one clear, self-contained search query using the vocabulary such documents would use.
3. Write up to {max_variants} alternative phrasings that could match differently worded passages.
4. List the most important exact keywords (product names, terms, numbers).

Do NOT answer the question. Only produce search queries."""


class QueryPlan(BaseModel):
    intent: str = Field(description="One short sentence: what information is needed.")
    rewritten_query: str = Field(description="Clear, self-contained search query.")
    alternative_queries: list[str] = Field(
        default_factory=list, description="Alternative phrasings of the same need."
    )
    keywords: list[str] = Field(default_factory=list, description="Important exact terms.")


def _dedupe(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    unique = []
    for query in queries:
        normalized = " ".join(query.split()).strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            unique.append(normalized[:500])
    return unique


async def plan_queries(llm: StructuredLLM | None, query: str, max_variants: int) -> list[str]:
    """Return [original, rewritten, *alternatives, keyword query] (deduplicated, capped)."""
    if llm is None or max_variants == 0:
        return [query]
    try:
        plan = await llm.generate(
            QueryPlan,
            system=SYSTEM_PROMPT.format(max_variants=max_variants),
            user=f"User query: {query}",
        )
    except Exception as exc:
        logger.warning("Query rewriting failed, using the original query: %s", exc)
        return [query]

    variants = [plan.rewritten_query, *plan.alternative_queries]
    if plan.keywords:
        variants.append(" ".join(plan.keywords))  # helps the BM25 side of hybrid search
    return _dedupe([query, *variants])[: max_variants + 1]
