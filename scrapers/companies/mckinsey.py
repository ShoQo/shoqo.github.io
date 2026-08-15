"""McKinsey & Company roles (mckinsey.com/careers/search-jobs).

The search page is a Next.js app; the jobs come from McKinsey's own API
gateway, which needs no key or referer:

    GET https://gateway.mckinsey.com/apigw-x0cceuow60/v1/api/jobs/search
        ?lang=en&cities=Tokyo&pageSize=100&start=1

Two things about that endpoint are worth knowing before touching this file:

`start` is a 1-based page number, not an offset. Page 1 and page 0 return the
same first page; a page past the end answers `numFound: 0` with `docs: null`
rather than an empty list.

Repeating a parameter does not OR its values, it keeps the first one:
`cities=Osaka&cities=London` returns only the Osaka results. So a filter value
that is a list is fanned out into one request per value and the results merged.

`interest` ("Consulting", "Analytics", …) is a practice, not a seniority, and
there is no seniority or contract field, so a Tokyo pass includes Associate
Partner roles. Sorting those out is what `title_include`/`title_exclude` are
for, as with `phenom`.

The only date published is `postedToLinkedInDate`, which is when the role was
syndicated to LinkedIn: missing on many rows and sometimes in the future. It
would misorder the feed, so `posted_at` stays empty.

Most postings are one role open in every office McKinsey has: the Associate
listing names 112. `location_label` renders those the way `bain` does,
"Tokyo + 111 offices".
"""

from __future__ import annotations

import itertools
import re
import urllib.parse
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, fetch_json

BASE_URL = "https://gateway.mckinsey.com/apigw-x0cceuow60/v1"
SEARCH_PATH = "/api/jobs/search"

DEFAULT_JOB_URL = "https://www.mckinsey.com/careers/search-jobs/jobs/{slug}"

PAGE_SIZE = 100
MAX_PAGES = 50


class McKinseyScraper(Scraper):
    name = "mckinsey"

    def fetch(self) -> Iterable[Job]:
        base = self.options.get("base_url", BASE_URL)
        lang = self.options.get("lang", "en")
        url_template = self.options.get("job_url_template", DEFAULT_JOB_URL)
        label_for_office = self.options.get("location_label")

        queries = self.options.get("queries")
        if not queries:
            raise ScrapeError(f"{self.company_id}: scraper option 'queries' is required")

        jobs: list[Job] = []
        seen: set[str] = set()

        for query in queries:
            include = _compile(query.get("title_include"))
            exclude = _compile(query.get("title_exclude"))
            label = query.get("label")

            for doc in self._all_docs(base, lang, query):
                job_id = str(doc.get("jobID") or "")
                title = (doc.get("title") or "").strip()
                slug = doc.get("friendlyURL")
                if not job_id or not title or not slug:
                    raise ScrapeError(f"doc missing jobID/title/friendlyURL: {doc!r:.200}")

                if job_id in seen:
                    continue
                if include and not include.search(title):
                    continue
                if exclude and exclude.search(title):
                    continue

                seen.add(job_id)
                jobs.append(
                    Job(
                        id=self.job_id(job_id),
                        company_id=self.company_id,
                        title=title,
                        url=url_template.format(slug=slug, id=job_id),
                        location=_location(doc.get("cities"), label_for_office),
                        type=label,
                        posted_at=None,
                        extra={"interest": doc.get("interest") or None},
                    )
                )

        return jobs

    def _all_docs(self, base: str, lang: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for filters in _expand(query.get("filters") or {}):
            docs.extend(self._pages(base, lang, query, filters))
        return docs

    def _pages(
        self, base: str, lang: str, query: dict[str, Any], filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []

        for page in range(1, MAX_PAGES + 1):
            params = {"lang": lang, "pageSize": PAGE_SIZE, "start": page, **filters}
            if query.get("keywords"):
                params["query"] = query["keywords"]
            url = f"{base}{SEARCH_PATH}?{urllib.parse.urlencode(params)}"

            payload = fetch_json(url)
            if not isinstance(payload, dict) or "numFound" not in payload:
                raise ScrapeError(f"{url}: no numFound in response ({payload!r:.120})")
            if payload.get("httpStatus") not in (None, "OK"):
                raise ScrapeError(f"{url}: {payload.get('httpStatus')} {payload.get('statusMessage')}")

            total = payload.get("numFound") or 0
            # A page past the end answers docs: null, so `or []` is load-bearing.
            batch = payload.get("docs") or []

            if page == 1 and not batch:
                raise ScrapeError(f"{url}: 0 docs of {total} for {query.get('label')!r}")

            found.extend(batch)
            if not batch or len(found) >= total:
                return found

        raise ScrapeError(f"{base}: more than {MAX_PAGES} pages, refusing to keep paging")


def _expand(filters: dict[str, Any]) -> list[dict[str, str]]:
    """One filter dict per combination, since the API keeps only the first value.

    `{"cities": ["Tokyo", "Osaka"]}` becomes two requests; a plain string value
    is passed through as the single choice for its key.
    """
    keys = list(filters)
    choices = [[v] if isinstance(v, str) else list(v) for v in filters.values()]
    return [dict(zip(keys, combo)) for combo in itertools.product(*choices)]


def _location(cities: Any, label: str | None) -> str | None:
    """A role open firm-wide lists every office; a full join is unreadable."""
    offices = [c.strip() for c in cities or [] if c and c.strip()]
    if label and len(offices) > 1:
        return f"{label} + {len(offices) - 1} offices"
    if label:
        return label
    return ", ".join(offices) or None


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    return re.compile(pattern) if pattern else None


SCRAPER = McKinseyScraper
