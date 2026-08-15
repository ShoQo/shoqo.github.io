"""Phenom People career sites.

BCG runs careers.bcg.com on this, as do many other large employers, so this
module is generic: host, page identifiers, filters and link format all come
from `data/companies.json`.

The site's own search box posts to a single widget endpoint:

    POST https://<host>/widgets   {"ddoKey": "refineSearch", "from": 0, ...}

The answer is `refineSearch.data.jobs` plus a `totalHits`, so we page with
`from`. Unusually for these boards there is no page-size cap worth working
around; we still page rather than asking for everything at once.

`selected_fields` is the same structure the site's facet checkboxes send:
a field name mapped to the values to keep, values within a field OR'd. Field
names are per employer; BCG's are country, city, state, category and type.

Note that `type` is not a seniority or contract signal at BCG: everything is
"Full-Time", internships included. Sorting those out is what `title_include`
and `title_exclude` are for.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, post_json

PAGE_SIZE = 100
MAX_PAGES = 50  # safety net: 5000 jobs, past any single employer's board

DEFAULT_JOB_URL = "https://{host}/global/en/job/{id}"


class PhenomScraper(Scraper):
    name = "phenom"

    def fetch(self) -> Iterable[Job]:
        host = self._require("host")
        url_template = self.options.get("job_url_template", DEFAULT_JOB_URL)

        queries = self.options.get("queries")
        if not queries:
            raise ScrapeError(f"{self.company_id}: scraper option 'queries' is required")

        jobs: list[Job] = []
        seen: set[str] = set()

        for query in queries:
            include = _compile(query.get("title_include"))
            exclude = _compile(query.get("title_exclude"))
            label = query.get("label")

            for posting in self._all_jobs(host, query):
                # jobSeqNo is the id the public job page is keyed on; jobId is
                # the requisition number, which the same posting can reuse
                # across locales.
                job_key = str(posting.get("jobSeqNo") or "")
                title = (posting.get("title") or "").strip()
                if not job_key or not title:
                    raise ScrapeError(f"job missing jobSeqNo/title: {posting!r}")

                if job_key in seen:
                    continue
                if include and not include.search(title):
                    continue
                if exclude and exclude.search(title):
                    continue

                seen.add(job_key)
                jobs.append(
                    Job(
                        id=self.job_id(job_key),
                        company_id=self.company_id,
                        title=title,
                        url=url_template.format(id=job_key, host=host),
                        location=_location(posting),
                        type=label,
                        posted_at=_iso_date(posting.get("postedDate")),
                    )
                )

        return jobs

    def _all_jobs(self, host: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"https://{host}/widgets"

        postings: list[dict[str, Any]] = []
        start = 0

        for _ in range(MAX_PAGES):
            payload = post_json(url, self._body(query, start))

            search = (payload or {}).get("refineSearch")
            data = (search or {}).get("data")
            if not isinstance(data, dict) or "jobs" not in data:
                raise ScrapeError(f"{url}: no refineSearch.data.jobs in response")

            total = search.get("totalHits") or 0
            batch = data.get("jobs") or []

            if start == 0 and not batch:
                raise ScrapeError(f"{url}: 0 jobs of {total} for {query.get('label')!r}")

            postings.extend(batch)
            start += PAGE_SIZE
            if start >= total or not batch:
                return postings

        raise ScrapeError(f"{url}: more than {MAX_PAGES} pages, refusing to keep paging")

    def _body(self, query: dict[str, Any], start: int) -> dict[str, Any]:
        """The payload the site's own search sends, minus its tracking fields."""
        return {
            "lang": self.options.get("lang", "en_global"),
            "country": self.options.get("locale_country", "global"),
            "pageName": "search-results",
            "pageId": self.options.get("page_id", "page11"),
            "ddoKey": "refineSearch",
            "deviceType": "desktop",
            "siteType": "external",
            "jdsource": "facets",
            "global": True,
            "jobs": True,
            "counts": True,
            "clearAll": False,
            "isSliderEnable": False,
            "sortBy": query.get("sort_by", ""),
            "keywords": query.get("keywords", ""),
            "selected_fields": query.get("filters") or {},
            "locationData": {},
            "from": start,
            "size": PAGE_SIZE,
        }

    def _require(self, key: str) -> str:
        value = self.options.get(key)
        if not value:
            raise ScrapeError(f"{self.company_id}: scraper option '{key}' is required")
        return value


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    return re.compile(pattern) if pattern else None


def _location(posting: dict[str, Any]) -> str | None:
    """A posting open in several offices lists them all; `location` holds one."""
    places = posting.get("multi_location") or []
    return ", ".join(places) or posting.get("location") or None


def _iso_date(stamp: Any) -> str | None:
    """postedDate is ISO with milliseconds, e.g. 2026-08-13T00:00:00.000+0000."""
    if not isinstance(stamp, str) or len(stamp) < 10:
        return None
    date = stamp[:10]
    return date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else None


SCRAPER = PhenomScraper
