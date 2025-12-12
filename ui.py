"""FastAPI-powered UI for querying the local Vespa application."""

from __future__ import annotations

import logging
import os
import textwrap
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Sequence

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from gateway_register import register_with_gateway
from pydantic import BaseModel
from vespa.application import Vespa

try:  # Optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


class SearchRequest(BaseModel):
    query: str
    limit: int | None = None


class BM25SearchRequest(BaseModel):
    query: str
    dataset_id: str | None = None
    filters: Dict[str, Any] | None = None
    top_k: int | None = None


BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger("simple-search")

if load_dotenv:
    # Load .env from repo root if present; no-op if file is missing
    load_dotenv()

RESULT_LIMIT = int(os.getenv("VESPA_RESULT_LIMIT", "10"))
MAX_RESULT_LIMIT = int(os.getenv("VESPA_MAX_RESULT_LIMIT", "100"))
MIN_RESULT_LIMIT = 1

SERVICE_NAME = os.getenv("SERVICE_NAME", "simple-search")
SERVICE_BASE_URL = os.getenv("SERVICE_BASE_URL", "http://127.0.0.1:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL")
GATEWAY_PREFIX = os.getenv("GATEWAY_PREFIX", "")
REGISTER_RETRIES = int(os.getenv("REGISTER_RETRIES", "5"))
REGISTER_DELAY = float(os.getenv("REGISTER_DELAY", "1.0"))


@lru_cache
def get_vespa_client() -> Vespa:
    """Instantiate (and cache) the Vespa client."""
    host = os.getenv("VESPA_HOST")
    url = host or os.getenv("VESPA_URL", "http://localhost")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"
    port = int(os.getenv("VESPA_PORT", "8080"))
    return Vespa(url=url, port=port)


def _resolve_limit(candidate: int | None) -> int:
    """Clamp the requested limit to a safe, positive range."""
    limit = candidate if candidate is not None else RESULT_LIMIT
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = RESULT_LIMIT
    return max(MIN_RESULT_LIMIT, min(MAX_RESULT_LIMIT, limit_value))


def run_vespa_query(query: str, limit: int | None = None) -> Dict[str, Any]:
    """Execute the Vespa search using the provided query string."""
    effective_limit = _resolve_limit(limit)
    client = get_vespa_client()
    with client.syncio(connections=1) as session:
        response = session.query(
            yql=f"select * from sources * where userQuery() limit {effective_limit}",
            query=query,
            ranking="bm25",
        )

    response_json = _safe_json(response)
    print(response_json)  # Debug output
    root = response_json.get("root", {}) or {}
    hits = getattr(response, "hits", []) or []
    formatted_hits = [_format_hit(hit) for hit in hits]

    total_available = _extract_total_hits(response_json)
    latency_ms = _extract_latency(response_json)

    return {
        "query": query,
        "hits": formatted_hits,
        "returned": len(formatted_hits),
        "limit": effective_limit,
        "total_available": total_available,
        "latency_ms": latency_ms,
        "coverage": root.get("coverage") or {},
    }


def _format_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    fields = hit.get("fields", {})
    text = fields.get("text") or ""
    snippet = " ".join(text.split())
    snippet = textwrap.shorten(snippet, width=360, placeholder="…")
    raw_document_id = fields.get("documentid") or hit.get("id")
    display_document_id = fields.get("id") or _normalize_document_id(raw_document_id)

    return {
        "id": display_document_id,
        "document_id": display_document_id,
        "vespa_document_id": raw_document_id,
        "sddocname": fields.get("sddocname"),
        "source": hit.get("source"),
        "url": fields.get("url"),
        "text": text or None,
        "snippet": snippet,
        "relevance": round(float(hit.get("relevance", 0.0)), 4),
        "fields": fields or {},
    }


def _format_bm25_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    fields = hit.get("fields", {}) or {}
    raw_document_id = fields.get("documentid") or hit.get("id")
    display_document_id = fields.get("id") or _normalize_document_id(raw_document_id)

    return {
        "id": display_document_id,
        "content": fields.get("text") or "",
        "score": float(hit.get("relevance", 0.0)),
        "meta": {
            "url": fields.get("url"),
            "vespa_document_id": raw_document_id,
            "source": hit.get("source"),
            "fields": fields,
        },
    }


def _extract_total_hits(response_json: Dict[str, Any]) -> int:
    root = response_json.get("root", {})
    fields = root.get("fields", {})
    return fields.get("totalCount", len(root.get("children", []) or []))


def _extract_latency(response_json: Dict[str, Any]) -> float:
    timing = response_json.get("timing", {})
    total = timing.get("total") or timing.get("querytime")
    return round(float(total), 3) if total is not None else 0.0


def _safe_json(response: Any) -> Dict[str, Any]:
    for attr in ("json", "get_json"):
        if not hasattr(response, attr):
            continue
        candidate = getattr(response, attr)
        try:
            data = candidate() if callable(candidate) else candidate
        except TypeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _normalize_document_id(document_id: Any) -> str | None:
    if not isinstance(document_id, str):
        return None
    if "::" in document_id:
        tail = document_id.rsplit("::", 1)[-1]
        return tail or document_id
    return document_id


def _matches_filters(fields: Dict[str, Any], filters: Dict[str, Any] | None) -> bool:
    """
    Keep only hits where provided filters match known fields.

    Unknown filter keys are ignored to avoid surprising empty result sets.
    """
    if not filters:
        return True

    for key, expected in filters.items():
        if expected is None:
            continue
        if key not in fields:
            continue

        value = fields.get(key)
        if isinstance(expected, (list, tuple, set, frozenset, Sequence)) and not isinstance(
            expected, (str, bytes)
        ):
            if str(value) not in {str(item) for item in expected}:
                return False
        elif str(value) != str(expected):
            return False

    return True


def run_bm25_api_query(
    query: str, *, dataset_id: str | None, filters: Dict[str, Any] | None, top_k: int | None
) -> Dict[str, Any]:
    """BM25 search tailored for RAG clients."""
    effective_limit = _resolve_limit(top_k)
    client = get_vespa_client()

    with client.syncio(connections=1) as session:
        response = session.query(
            yql=f"select * from sources * where userQuery() limit {effective_limit}",
            query=query,
            ranking="bm25",
        )

    response_json = _safe_json(response)
    hits = getattr(response, "hits", []) or []
    filtered_hits = [
        _format_bm25_hit(hit) for hit in hits if _matches_filters(hit.get("fields", {}) or {}, filters)
    ]

    if len(filtered_hits) > effective_limit:
        filtered_hits = filtered_hits[:effective_limit]

    return {
        "query": query,
        "dataset_id": dataset_id,
        "filters": filters or {},
        "hits": filtered_hits,
        "returned": len(filtered_hits),
        "limit": effective_limit,
        "total_available": _extract_total_hits(response_json),
        "latency_ms": _extract_latency(response_json),
        "coverage": response_json.get("root", {}).get("coverage") or {},
    }


app = FastAPI(title="Simple Search UI", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
async def _register_gateway_on_startup() -> None:
    """Register this service's routes into the gateway when configured via env."""
    routes = [
        {
            "name": "search-ui",
            "method": "POST",
            "gateway_path": "/search",
            "upstream_path": "/search",
            "summary": "UI search endpoint",
            "description": "BM25 search formatted for UI consumers",
        },
        {
            "name": "search-bm25",
            "method": "POST",
            "gateway_path": "/search/bm25",
            "upstream_path": "/search/bm25",
            "summary": "RAG BM25 endpoint",
            "description": "BM25 search tailored for RAG clients",
        },
    ]
    try:
        await register_with_gateway(
            service_name=SERVICE_NAME,
            base_url=SERVICE_BASE_URL,
            gateway_url=GATEWAY_URL,
            routes=routes,
            prefix=GATEWAY_PREFIX,
            retries=REGISTER_RETRIES,
            delay=REGISTER_DELAY,
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Gateway registration failed: %s", exc)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_limit": RESULT_LIMIT,
            "max_limit": MAX_RESULT_LIMIT,
        },
    )


@app.post("/search")
async def search(request: SearchRequest) -> Dict[str, Any]:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        payload = run_vespa_query(query, limit=request.limit)
    except Exception as exc:  # noqa: BLE001 - surface Vespa issues cleanly
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return payload


@app.post("/search/bm25")
async def search_bm25(request: BM25SearchRequest) -> Dict[str, Any]:
    """Third-party friendly BM25 API for RAG pipelines."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        payload = run_bm25_api_query(
            query,
            dataset_id=request.dataset_id,
            filters=request.filters,
            top_k=request.top_k,
        )
    except Exception as exc:  # noqa: BLE001 - surface Vespa issues cleanly
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return payload
