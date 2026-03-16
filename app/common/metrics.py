"""
Prometheus metrics for the RAG service.

All metrics are defined at module level so they are singletons registered
with the default prometheus_client registry.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# HTTP metrics
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# Application-level metrics
# ---------------------------------------------------------------------------

query_cache_hits_total = Counter(
    "query_cache_hits_total",
    "Total number of query cache hits",
    ["tenant_id"],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total number of LLM tokens consumed",
    ["provider", "token_type"],
)

documents_ingested_total = Counter(
    "documents_ingested_total",
    "Total number of documents successfully ingested",
    ["tenant_id"],
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    """Record HTTP request metrics."""
    status_str = str(status_code)
    http_requests_total.labels(method=method, path=path, status_code=status_str).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration_seconds)


def inc_cache_hit(tenant_id: str) -> None:
    """Increment the query cache hit counter for a tenant."""
    query_cache_hits_total.labels(tenant_id=tenant_id).inc()


def inc_tokens(provider: str, input_tokens: int, output_tokens: int) -> None:
    """Increment LLM token counters."""
    llm_tokens_total.labels(provider=provider, token_type="input").inc(input_tokens)
    llm_tokens_total.labels(provider=provider, token_type="output").inc(output_tokens)
