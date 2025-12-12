"""
Lightweight helper to register this service's routes into the gateway.

Env vars:
- SERVICE_NAME: unique service identifier (default: "simple-search")
- SERVICE_BASE_URL: upstream base URL the gateway should call (default: "http://127.0.0.1:8000")
- GATEWAY_URL: gateway base URL (e.g. "http://127.0.0.1:30090"); if empty, registration is skipped
- GATEWAY_PREFIX: optional path prefix to avoid collisions (e.g. "/ai-search")
- REGISTER_RETRIES / REGISTER_DELAY: retry policy
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, Iterable, List

import httpx

logger = logging.getLogger(__name__)


def _apply_prefix(path: str, prefix: str | None) -> str:
    """Ensure gateway_path carries the configured prefix."""
    clean_path = path if path.startswith("/") else f"/{path}"
    if not prefix:
        return clean_path
    clean_prefix = prefix.strip("/")
    return f"/{clean_prefix}{clean_path}"


async def register_with_gateway(
    *,
    service_name: str,
    base_url: str,
    gateway_url: str | None,
    routes: Iterable[Dict[str, str]],
    prefix: str | None = None,
    retries: int = 5,
    delay: float = 1.0,
) -> bool:
    """
    Register service routes into the gateway. Returns True on success, False otherwise.

    routes expects items with keys: name, method, gateway_path, upstream_path, summary, description.
    """
    if not gateway_url:
        logger.info("GATEWAY_URL not set; skipping gateway registration.")
        return False

    prefixed_routes: List[Dict[str, str]] = []
    for route in routes:
        gateway_path = _apply_prefix(route["gateway_path"], prefix)
        prefixed_routes.append({**route, "gateway_path": gateway_path})

    payload = {"name": service_name, "base_url": base_url, "routes": prefixed_routes}
    endpoint = gateway_url.rstrip("/") + "/gateway/register"

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(endpoint, json=payload)
                resp.raise_for_status()
            logger.info(
                "Gateway registered: service=%s base_url=%s routes=%s (prefix=%s)",
                service_name,
                base_url,
                len(prefixed_routes),
                prefix or "",
            )
            return True
        except Exception as exc:  # pragma: no cover - best-effort logging
            logger.warning(
                "Gateway registration failed (attempt %s/%s): %s",
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                await asyncio.sleep(delay)

    logger.error("Gateway registration exhausted retries; continuing without gateway mapping.")
    return False
