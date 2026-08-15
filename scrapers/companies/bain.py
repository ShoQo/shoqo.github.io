"""Bain & Company roles (bain.com/careers/find-a-role).

The page is a React app over Bain's own CMS endpoint, not a hosted ATS, so
unlike `eightfold` or `phenom` this module is Bain-specific:

    GET https://www.bain.com/en/api/jobsearch/keyword/get?filters=<f>&start=<n>

It answers `results` plus `totalResults`, ten per page, paged with `start`.
The endpoint refuses requests without a `Referer` from bain.com ("Forbidden:
Direct API access is not allowed"), so one is sent.

`filters` is the same string the site puts in its own URL bar:

    employmenttype(E50,E2510)|offices(268)|

Group names and ids come back in every response under `filters.filterBlocks`,
which is also where the office ids live (268 is Tokyo). Config names the groups
and ids directly; they are Bain's own and stable enough to paste from the site's
URL.

`EmployeeType` is a contract type (Permanent Full-Time, Intern, Program), not a
seniority, and there is no seniority field, so a Tokyo "Full-Time" pass includes
Senior Manager roles.

Most postings are a single role open in every office Bain has: the Associate
Consultant listing names 63. Joining all of them is unreadable on a job board,
so `location_label` renders them the way Bain's own results do, "Tokyo + 62
offices".
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, fetch_json

BASE_URL = "https://www.bain.com"
SEARCH_PATH = "/en/api/jobsearch/keyword/get"
REFERER = f"{BASE_URL}/careers/find-a-role/"

PAGE_SIZE = 10  # fixed server-side; take/pageSize/count are all ignored
MAX_PAGES = 50


class BainScraper(Scraper):
    name = "bain"

    def fetch(self) -> Iterable[Job]:
        base = self.options.get("base_url", BASE_URL)
        referer = self.options.get("referer", REFERER)
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

            for result in self._all_results(base, referer, query):
                job_id = str(result.get("JobId") or "")
                title = (result.get("JobTitle") or "").strip()
                link = result.get("Link")
                if not job_id or not title or not link:
                    raise ScrapeError(f"result missing JobId/JobTitle/Link: {result!r}")

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
                        url=urllib.parse.urljoin(base, link),
                        location=_location(result.get("Location"), label_for_office),
                        type=label,
                        # The endpoint publishes no posting date.
                        posted_at=None,
                        extra={"employment_type": result.get("EmployeeType") or None},
                    )
                )

        return jobs

    def _all_results(
        self, base: str, referer: str, query: dict[str, Any]
    ) -> list[dict[str, Any]]:
        filters = _filter_string(query.get("filters") or {})

        results: list[dict[str, Any]] = []
        start = 0

        for _ in range(MAX_PAGES):
            params = {"filters": filters, "start": start}
            if query.get("keywords"):
                params["searchValue"] = query["keywords"]
            url = f"{base}{SEARCH_PATH}?{urllib.parse.urlencode(params)}"

            payload = fetch_json(url, referer=referer)
            if not isinstance(payload, dict) or "results" not in payload:
                raise ScrapeError(f"{url}: no results in response ({payload!r:.120})")

            total = payload.get("totalResults") or 0
            batch = payload.get("results") or []

            if start == 0 and not batch:
                raise ScrapeError(f"{url}: 0 results of {total} for {query.get('label')!r}")

            results.extend(batch)
            start += PAGE_SIZE
            if start >= total or not batch:
                return results

        raise ScrapeError(f"{base}: more than {MAX_PAGES} pages, refusing to keep paging")


def _filter_string(filters: dict[str, list[str]]) -> str:
    """`{"offices": ["268"]}` -> `offices(268)|`, the site's own URL format."""
    return "".join(f"{group}({','.join(values)})|" for group, values in filters.items())


def _location(places: Any, label: str | None) -> str | None:
    """Bain's own results say "Tokyo + 62 offices"; a full join is unreadable."""
    offices = [p.strip() for p in places or [] if p and p.strip()]
    if label and len(offices) > 1:
        return f"{label} + {len(offices) - 1} offices"
    if label:
        return label
    return ", ".join(offices) or None


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    return re.compile(pattern) if pattern else None


SCRAPER = BainScraper
