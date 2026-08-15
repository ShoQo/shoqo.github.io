"""Shared plumbing for company scrapers.

Every company gets its own module under `scrapers/companies/` because career
sites share no common markup. What they do share is the output shape (`Job`)
and the HTTP helpers below, so a new company is one file plus one config entry.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass(frozen=True)
class Job:
    """One row on the job board. Field names match what `lib.js` reads."""

    id: str
    company_id: str
    title: str
    url: str
    location: str | None = None
    type: str | None = None
    posted_at: str | None = None
    # Anything company-specific that does not fit the common shape.
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra")
        data.update(extra)
        return {k: v for k, v in data.items() if v is not None}


class ScrapeError(RuntimeError):
    """Raised when a scraper cannot produce a trustworthy result."""


class Scraper(ABC):
    """Base class for a single company's scraper.

    Subclasses set `name` (matching their module filename) and implement
    `fetch`. Raising `ScrapeError` on a layout change is preferred over
    returning an empty list, so the runner can keep the previous jobs instead
    of silently emptying the board.
    """

    name: str = ""

    def __init__(self, company: dict[str, Any], options: dict[str, Any] | None = None):
        self.company = company
        self.company_id = company["id"]
        self.options = options or {}

    @abstractmethod
    def fetch(self) -> Iterable[Job]:
        ...

    def job_id(self, slug: str) -> str:
        """Stable id so the same posting keeps its identity between runs."""
        return f"{self.company_id}:{slug.strip('/').replace('/', '-')}"


def fetch_bytes(
    url: str,
    *,
    data: bytes | None = None,
    content_type: str | None = None,
    referer: str | None = None,
    retries: int = 3,
    timeout: int = 30,
) -> bytes:
    """GET with a browser UA, retrying transient failures with a linear backoff.

    Passing `data` makes it a POST. Retrying a POST is safe for the only thing
    we send one to: a search endpoint that happens to want a JSON body.

    `referer` is for endpoints that refuse requests not coming from their own
    page; Bain's answers "Forbidden: Direct API access is not allowed" without
    one.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if referer:
        headers["Referer"] = referer

    request = urllib.request.Request(url, data=data, headers=headers)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    payload = gzip.decompress(payload)
                return payload
        except (urllib.error.URLError, TimeoutError) as err:
            last_error = err
            if attempt < retries:
                time.sleep(attempt * 2)

    raise ScrapeError(f"GET {url} failed after {retries} attempts: {last_error}")


def fetch_json(url: str, **kwargs: Any) -> Any:
    return _decode(fetch_bytes(url, **kwargs), url)


def post_json(url: str, payload: Any, **kwargs: Any) -> Any:
    """POST a JSON body and decode the JSON answer."""
    raw = fetch_bytes(
        url,
        data=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        **kwargs,
    )
    return _decode(raw, url)


def _decode(raw: bytes, url: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise ScrapeError(f"{url} returned non-JSON: {err}") from err


def fetch_text(url: str, **kwargs: Any) -> str:
    return fetch_bytes(url, **kwargs).decode("utf-8", errors="replace")
