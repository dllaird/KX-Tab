"""Kalshi public market-data API: paced, retrying GETs and cursor pagination."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterator

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
MIN_INTERVAL = 0.12   # seconds between requests across threads (~8/s; Kalshi limits unauthenticated clients)
RETRIES = 6

Getter = Callable[..., dict[str, Any]]


class NotFound(Exception):
    """The endpoint returned 404."""


_session = requests.Session()
_lock = threading.Lock()
_next_slot = 0.0


def _pace() -> None:
    global _next_slot
    with _lock:
        now = time.monotonic()
        wait = _next_slot - now
        _next_slot = max(now, _next_slot) + MIN_INTERVAL
    if wait > 0:
        time.sleep(wait)


def public_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a public endpoint; retries 429/5xx, raises NotFound on 404."""
    for attempt in range(RETRIES + 1):
        _pace()
        resp = _session.get(f"{BASE_URL}{path}", params=params, headers={"Accept": "application/json"}, timeout=30)
        if resp.status_code == 404:
            raise NotFound(path)
        if (resp.status_code == 429 or resp.status_code >= 500) and attempt < RETRIES:
            retry_after = resp.headers.get("Retry-After", "")
            time.sleep(float(retry_after) if retry_after.replace(".", "", 1).isdigit() else min(0.5 * 2 ** attempt, 8.0))
            continue
        resp.raise_for_status()
        return resp.json()
    raise AssertionError("unreachable")


def pages(get: Getter, path: str, params: dict[str, Any], key: str, limit: int = 1000,
          max_items: int | None = None) -> Iterator[dict]:
    """Yield items across cursor pages."""
    cursor, seen = None, 0
    while True:
        query = dict(params, limit=limit, **({"cursor": cursor} if cursor else {}))
        data = get(path, query)
        for item in data.get(key) or []:
            yield item
            seen += 1
            if max_items is not None and seen >= max_items:
                return
        cursor = data.get("cursor")
        if not cursor:
            return
