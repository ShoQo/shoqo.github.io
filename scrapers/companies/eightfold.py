"""Eightfold AI career sites ("PCSX" job search).

Morgan Stanley runs morganstanley.eightfold.ai on this, as do many other large
employers, so this module is generic: host, domain, filters and link format all
come from `data/companies.json`.

The search endpoint the site's own front end calls is:

    https://<host>/api/pcsx/search?domain=<domain>&start=0&num=10&sort_by=timestamp

It returns `data.positions` plus a `data.count`, so we page through with `start`
until we have them all. `num` is capped at 10 server-side whatever we ask for.

Older Eightfold tenants answer on `/api/apply/v2/jobs`; that path returns 403
"Not authorized for PCSX" here, so it is not a fallback worth trying.

Filters are repeated `filter_<name>=<value>` query parameters, OR'd within a
name and AND'd across names. Which names exist is per tenant and is listed in
`data.filterDef` of any response (for Morgan Stanley: country, city,
businessarea, employmenttype, pcsjoblevel, skills).

As with the Oracle scraper, `queries` is a list so one company can make several
labelled passes (internships, entry level, experienced); results are merged and
de-duplicated by position id, first query winning.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, fetch_json

# The endpoint silently clamps `num` to 10, so asking for more just wastes the
# larger page we thought we were getting.
PAGE_SIZE = 10
MAX_PAGES = 100  # safety net: 1000 positions, past any single country's board

DEFAULT_JOB_URL = "https://{host}/careers/job/{id}?domain={domain}"


class EightfoldScraper(Scraper):
    name = "eightfold"

    def fetch(self) -> Iterable[Job]:
        host = self._require("host")
        domain = self._require("domain")
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

            for position in self._all_positions(host, domain, query):
                position_id = str(position.get("id") or "")
                title = (position.get("name") or "").strip()
                if not position_id or not title:
                    raise ScrapeError(f"position missing id/name: {position!r}")

                if position_id in seen:
                    continue
                if include and not include.search(title):
                    continue
                if exclude and exclude.search(title):
                    continue

                seen.add(position_id)
                jobs.append(
                    Job(
                        id=self.job_id(position_id),
                        company_id=self.company_id,
                        title=title,
                        url=url_template.format(id=position_id, host=host, domain=domain),
                        location=", ".join(position.get("locations") or []) or None,
                        type=label,
                        posted_at=_iso_date(position.get("postedTs")),
                    )
                )

        return jobs

    def _all_positions(
        self, host: str, domain: str, query: dict[str, Any]
    ) -> list[dict[str, Any]]:
        positions: list[dict[str, Any]] = []
        start = 0

        for _ in range(MAX_PAGES):
            url = self._search_url(host, domain, query, start)
            payload = fetch_json(url)

            data = (payload or {}).get("data")
            if not isinstance(data, dict) or "positions" not in data:
                raise ScrapeError(f"{url}: no data.positions in response")

            count = data.get("count") or 0
            batch = data.get("positions") or []

            if start == 0 and not batch:
                raise ScrapeError(f"{url}: 0 positions of {count}")

            positions.extend(batch)
            start += PAGE_SIZE
            if start >= count or not batch:
                return positions

        raise ScrapeError(f"{host}: more than {MAX_PAGES} pages, refusing to keep paging")

    def _search_url(self, host: str, domain: str, query: dict[str, Any], start: int) -> str:
        params = [
            ("domain", domain),
            ("start", str(start)),
            ("num", str(PAGE_SIZE)),
            ("sort_by", query.get("sort_by", "timestamp")),
        ]
        if query.get("query"):
            params.append(("query", query["query"]))
        # Repeating a filter name is how the API expresses OR; a dict of lists
        # keeps that readable in config.
        for name, values in (query.get("filters") or {}).items():
            params.extend((f"filter_{name}", value) for value in values)

        return f"https://{host}/api/pcsx/search?{urllib.parse.urlencode(params)}"

    def _require(self, key: str) -> str:
        value = self.options.get(key)
        if not value:
            raise ScrapeError(f"{self.company_id}: scraper option '{key}' is required")
        return value


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    return re.compile(pattern) if pattern else None


def _iso_date(epoch_seconds: Any) -> str | None:
    if not isinstance(epoch_seconds, (int, float)):
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).date().isoformat()


SCRAPER = EightfoldScraper
