"""Web search: provider (Tavily) + cache + sanitization, returning clean WebResults."""

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal, Protocol

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError
from app.research.cache import RedisSearchCache, SearchCache, cache_key, get_redis
from app.research.sanitize import clean_snippet, domain_of, normalize_url

logger = logging.getLogger(__name__)


class WebSearchNotConfiguredError(ServiceUnavailableError):
    code = "web_search_not_configured"
    message = "Live web research is not configured. Set TAVILY_API_KEY in backend/.env."


class WebSearchError(ServiceUnavailableError):
    code = "web_search_error"
    message = "The web search provider request failed."


@dataclass(frozen=True)
class SearchOptions:
    max_results: int = 5
    topic: Literal["general", "news"] = "general"
    time_range: Literal["day", "week", "month", "year"] | None = None
    include_domains: tuple[str, ...] = ()
    exclude_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class WebResult:
    url: str
    title: str
    snippet: str
    domain: str
    score: float
    published_date: str | None
    retrieved_at: datetime
    query: str
    from_cache: bool = False

    def to_cache(self) -> dict[str, Any]:
        data = asdict(self)
        data["retrieved_at"] = self.retrieved_at.isoformat()
        data.pop("from_cache")
        return data

    @classmethod
    def from_cached(cls, data: dict[str, Any]) -> "WebResult":
        return cls(
            **{**data, "retrieved_at": datetime.fromisoformat(data["retrieved_at"])},
            from_cache=True,
        )


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, options: SearchOptions) -> list[dict[str, Any]]: ...


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str, depth: str, timeout: int) -> None:
        from tavily import AsyncTavilyClient

        self._client = AsyncTavilyClient(api_key=api_key)
        self._depth = depth
        self._timeout = timeout

    async def search(self, query: str, options: SearchOptions) -> list[dict[str, Any]]:
        try:
            response = await self._client.search(
                query=query,
                search_depth=self._depth,
                topic=options.topic,
                time_range=options.time_range,
                max_results=options.max_results,
                include_domains=list(options.include_domains) or None,
                exclude_domains=list(options.exclude_domains) or None,
                include_answer=False,  # we want raw evidence, not someone else's summary
                include_raw_content=False,
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning("Tavily search failed (%s): %s", type(exc).__name__, exc)
            raise WebSearchError(f"Web search failed: {type(exc).__name__}.") from exc
        return list(response.get("results") or [])


@dataclass
class WebSearchService:
    provider: SearchProvider
    cache: SearchCache
    settings: Settings
    calls: int = field(default=0, init=False)  # provider calls made (credits spent)

    async def search(self, query: str, options: SearchOptions | None = None) -> list[WebResult]:
        options = options or SearchOptions(max_results=self.settings.web_search_max_results)
        query = " ".join(query.split())[:400]
        key = cache_key(
            self.provider.name, query, {**asdict(options), "depth": self.settings.web_search_depth}
        )

        cached = await self.cache.get(key)
        if cached is not None:
            return [WebResult.from_cached(item) for item in cached]

        self.calls += 1
        raw = await self.provider.search(query, options)
        retrieved_at = datetime.now(UTC)
        results: list[WebResult] = []
        seen: set[str] = set()
        for item in raw:
            url = normalize_url(item.get("url"))
            snippet = clean_snippet(item.get("content"), self.settings.web_snippet_max_chars)
            if url is None or url in seen or not snippet:
                continue  # unsafe scheme, duplicate, or empty content
            seen.add(url)
            results.append(
                WebResult(
                    url=url,
                    title=clean_snippet(item.get("title"), 200) or domain_of(url),
                    snippet=snippet,
                    domain=domain_of(url),
                    score=float(item.get("score") or 0.0),
                    published_date=item.get("published_date"),
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        await self.cache.set(
            key, [r.to_cache() for r in results], self.settings.web_search_cache_ttl_seconds
        )
        return results


def get_web_search_service() -> WebSearchService | None:
    """A fresh service per use (its call counter is per research run); None if no key."""
    settings = get_settings()
    key = settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else ""
    if not key:
        return None
    return WebSearchService(
        provider=_tavily(key, settings.web_search_depth, settings.web_search_timeout_seconds),
        cache=RedisSearchCache(get_redis()),
        settings=settings,
    )


@lru_cache
def _tavily(api_key: str, depth: str, timeout: int) -> TavilySearchProvider:
    return TavilySearchProvider(api_key, depth, timeout)
