"""Tiny POST-with-retry helper for transient network failures.

Asset generation fires many HTTP calls at the LLM / Seedream gateway; a single
flaky read/connect timeout used to fail the whole story build. Wrapping the POST
with one automatic retry on *transient* errors (timeouts, dropped connections)
makes the pipeline resilient to one-off gateway hiccups without masking real
HTTP error responses (4xx/5xx are returned as-is for the caller to handle).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Container
from typing import Any

import requests

log = logging.getLogger(__name__)

# Transient network faults (no response received) — always retried.
_TRANSIENT = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)

# Transient *server* responses — the gateway answered but is momentarily
# overloaded/unavailable. These are safe to retry with backoff; a 4xx (bad
# request / auth) is NOT and is handed back unchanged.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def post_with_retry(
    url: str,
    *,
    retries: int = 2,
    backoff: float = 2.0,
    session: requests.Session | None = None,
    retry_statuses: Container[int] = _RETRY_STATUSES,
    **kwargs: Any,
) -> requests.Response:
    """``requests.post`` (or ``session.post``) with retries on transient failures.

    Retries on transient network errors (timeouts, dropped connections) AND on
    transient server responses (429/5xx). retries=2 means up to 3 attempts total.
    Sleeps ``backoff * attempt`` seconds between tries. On exhaustion, returns the
    last response (so the caller raises its normal HTTP error) or re-raises the
    last network exception.
    """
    poster = (session or requests).post
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = poster(url, **kwargs)
        except _TRANSIENT as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            _sleep("network " + type(exc).__name__, url, attempt, retries, backoff)
            continue
        if resp.status_code in retry_statuses and attempt < retries:
            _sleep(f"HTTP {resp.status_code}", url, attempt, retries, backoff)
            continue
        return resp
    raise last_exc  # pragma: no cover — loop always returns or raises above


def _sleep(reason: str, url: str, attempt: int, retries: int, backoff: float) -> None:
    wait = backoff * (attempt + 1)
    log.warning(
        "[http] %s on POST %s (attempt %d/%d), retrying in %.1fs …",
        reason, url, attempt + 1, retries + 1, wait,
    )
    time.sleep(wait)
