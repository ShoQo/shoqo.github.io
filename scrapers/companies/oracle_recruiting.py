"""Oracle Recruiting Cloud (Oracle HCM "candidate experience") job boards.

Goldman Sachs runs higher.gs.com on this, and so do hundreds of other large
employers, so this module is generic: host, site number, filters and link
format all come from `data/companies.json`. Adding another Oracle-backed
company is a config entry, not a new file.

The public search endpoint is:

    https://<host>/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&finder=findReqs;siteNumber=<site>,limit=200,offset=0

It returns `items[0].requisitionList` plus a `TotalJobsCount`, so we page
through with `offset` until we have them all.

One company usually needs several passes over that endpoint (internships,
new-grad roles, experienced roles), so `queries` is a list: each entry gets its
own server-side facet selection plus title filters, and stamps its `label` onto
every job it produces. Results are merged and de-duplicated by requisition id,
first query winning, so a role that matches two queries is labelled once.

Category names are resolved to ids at run time from the endpoint's own facet
listing, so config stays readable ("Analyst") and survives id changes.

Location filtering happens here rather than server-side: the API's location
facet needs opaque internal geography ids that change, while
`PrimaryLocationCountry` is a plain ISO country code on every requisition.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, fetch_json

PAGE_SIZE = 200
MAX_PAGES = 20  # safety net: 4000 requisitions, well past any single employer


class OracleRecruitingScraper(Scraper):
    name = "oracle_recruiting"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        # Name -> id map for the categories facet, fetched once per run.
        self._categories: dict[str, str] | None = None

    def fetch(self) -> Iterable[Job]:
        host = self._require("host")
        site_number = self.options.get("site_number", "CX_2")
        url_template = self._require("job_url_template")
        countries = {c.upper() for c in self.options.get("countries", [])}

        queries = self.options.get("queries")
        if not queries:
            raise ScrapeError(f"{self.company_id}: scraper option 'queries' is required")

        jobs: list[Job] = []
        seen: set[str] = set()

        for query in queries:
            include = _compile(query.get("title_include"))
            exclude = _compile(query.get("title_exclude"))
            label = query.get("label")
            selection = self._selection(host, site_number, query)

            for requisition in self._all_requisitions(host, site_number, selection):
                requisition_id = str(requisition.get("Id") or "")
                title = (requisition.get("Title") or "").strip()
                if not requisition_id or not title:
                    raise ScrapeError(f"requisition missing Id/Title: {requisition!r}")

                if requisition_id in seen:
                    continue
                if countries and requisition.get("PrimaryLocationCountry", "").upper() not in countries:
                    continue
                if include and not include.search(title):
                    continue
                if exclude and exclude.search(title):
                    continue

                seen.add(requisition_id)
                jobs.append(
                    Job(
                        id=self.job_id(requisition_id),
                        company_id=self.company_id,
                        title=title,
                        url=url_template.format(id=requisition_id),
                        location=requisition.get("PrimaryLocation") or None,
                        type=label,
                        posted_at=requisition.get("PostedDate") or None,
                    )
                )

        return jobs

    def _selection(self, host: str, site_number: str, query: dict[str, Any]) -> str:
        """Server-side facet filters for one query, as finder parameters.

        `categories` is the "experience level" facet GS exposes as
        EXPERIENCE_LEVEL (Analyst, Summer Analyst, Vice President, ...);
        `facet_field`/`facet_values` reach any custom flex field. Values within
        one facet are OR'd; the endpoint rejects two flex fields at once, so
        anything spanning facets is filtered client-side instead.
        """
        parts = []

        categories = query.get("categories")
        if categories:
            ids = self._category_ids(host, site_number, categories)
            parts.append(("selectedCategoriesFacet", ";".join(ids)))

        field, values = query.get("facet_field"), query.get("facet_values")
        if field and values:
            parts.append(("selectedFlexFieldsFacets", f"{field}|{';'.join(values)}"))

        return "".join(f",{k}={urllib.parse.quote(v, safe='')}" for k, v in parts)

    def _category_ids(self, host: str, site_number: str, names: list[str]) -> list[str]:
        """Resolve category names to the opaque ids the finder expects."""
        if self._categories is None:
            endpoint = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            payload = fetch_json(
                f"{endpoint}?onlyData=true&expand=categoriesFacet"
                f"&finder=findReqs;siteNumber={site_number},limit=1"
            )
            items = (payload or {}).get("items") or []
            facet = items[0].get("categoriesFacet") if items else None
            if not facet:
                raise ScrapeError(f"{endpoint}: no categoriesFacet to resolve {names!r} against")
            self._categories = {c["Name"]: str(c["Id"]) for c in facet if c.get("Name")}

        missing = [n for n in names if n not in self._categories]
        if missing:
            raise ScrapeError(
                f"unknown category {missing!r}; endpoint offers "
                f"{sorted(self._categories)!r}"
            )
        return [self._categories[n] for n in names]

    def _all_requisitions(
        self, host: str, site_number: str, selection: str
    ) -> list[dict[str, Any]]:
        endpoint = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

        requisitions: list[dict[str, Any]] = []
        offset = 0

        for _ in range(MAX_PAGES):
            url = (
                f"{endpoint}?onlyData=true&expand=requisitionList.secondaryLocations"
                f"&finder=findReqs;siteNumber={site_number},"
                f"limit={PAGE_SIZE},offset={offset},sortBy=POSTING_DATES_DESC"
                f"{selection}"
            )
            payload = fetch_json(url)

            items = (payload or {}).get("items") or []
            if not items:
                raise ScrapeError(f"{endpoint}: no items in response (site {site_number})")

            page = items[0]
            total = page.get("TotalJobsCount") or 0
            batch = page.get("requisitionList") or []

            if offset == 0 and not batch:
                raise ScrapeError(
                    f"{endpoint}: 0 requisitions of {total} for selection {selection!r}"
                )

            requisitions.extend(batch)
            offset += PAGE_SIZE
            if offset >= total or not batch:
                return requisitions

        raise ScrapeError(f"{endpoint}: more than {MAX_PAGES} pages, refusing to keep paging")

    def _require(self, key: str) -> str:
        value = self.options.get(key)
        if not value:
            raise ScrapeError(f"{self.company_id}: scraper option '{key}' is required")
        return value


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    return re.compile(pattern) if pattern else None


SCRAPER = OracleRecruitingScraper
