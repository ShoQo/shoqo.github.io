"""Talent Nexus (tal.net) campus job boards.

Morgan Stanley recruits students on morganstanley.tal.net, a separate system
from the experienced-hire Eightfold board, so its internships and graduate
programs need their own pass. Other employers use tal.net too, so host and
board number come from `data/companies.json`.

The board renders server-side, no JSON endpoint behind it:

    https://<host>/vx/candidate/jobboard/vacancy/<board>/adv/

Every opportunity is one `<tr data-oppid=...>` in a results table, all on one
page, so a single request is the whole board. The filter checkboxes on that
page post opaque `f_Item_Opportunity_<n>_lk` ids that differ per employer and
change, so the city is filtered here instead, off the table's own City column.

Listing links carry a per-session `xf-<token>` path segment. We strip it: the
same opportunity is reachable at the plain `/vx/candidate/...` path, which is
what a shared link should be.

The board publishes no posting date, so `posted_at` stays empty rather than
being invented from a fetch time.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, fetch_text

DEFAULT_BOARD = 1

# https://host/vx/lang-en-GB/mobile-0/brand-2/xf-abc123/candidate/... ->
# https://host/vx/candidate/...
SESSION_PATH = re.compile(r"(/vx/)(?:[^/]+/)*?(candidate/)")


class TalentNexusScraper(Scraper):
    name = "talent_nexus"

    def fetch(self) -> Iterable[Job]:
        host = self._require("host")
        board = self.options.get("board", DEFAULT_BOARD)
        cities = {c.casefold() for c in self.options.get("cities", [])}

        queries = self.options.get("queries")
        if not queries:
            raise ScrapeError(f"{self.company_id}: scraper option 'queries' is required")

        opportunities = self._opportunities(host, board)

        jobs: list[Job] = []
        seen: set[str] = set()

        for query in queries:
            include = _compile(query.get("title_include"))
            exclude = _compile(query.get("title_exclude"))
            label = query.get("label")

            for row in opportunities:
                if row["id"] in seen:
                    continue
                if cities and row["city"].casefold() not in cities:
                    continue
                if include and not include.search(row["title"]):
                    continue
                if exclude and exclude.search(row["title"]):
                    continue

                seen.add(row["id"])
                jobs.append(
                    Job(
                        id=self.job_id(row["id"]),
                        company_id=self.company_id,
                        title=row["title"],
                        url=row["url"],
                        location=row["city"] or None,
                        type=label,
                        posted_at=None,
                    )
                )

        return jobs

    def _opportunities(self, host: str, board: Any) -> list[dict[str, str]]:
        url = f"https://{host}/vx/candidate/jobboard/vacancy/{board}/adv/"
        parser = _ResultsParser()
        parser.feed(fetch_text(url))

        if not parser.rows:
            raise ScrapeError(f"{url}: no opportunity rows, board layout changed?")

        rows = []
        for row in parser.rows:
            if not row["title"] or not row["url"]:
                raise ScrapeError(f"{url}: opportunity missing title/link: {row!r}")
            rows.append({**row, "url": SESSION_PATH.sub(r"\1\2", row["url"], count=1)})
        return rows

    def _require(self, key: str) -> str:
        value = self.options.get(key)
        if not value:
            raise ScrapeError(f"{self.company_id}: scraper option '{key}' is required")
        return value


class _ResultsParser(HTMLParser):
    """Reads the board's results table into {id, title, url, city} rows.

    A row is any `<tr>` carrying `data-oppid`; its cells are Title then City.
    Anchored on that attribute rather than on the surrounding markup, which is
    the part a template change is most likely to touch.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._row: dict[str, str] | None = None
        self._cells: list[str] = []
        self._text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr" and attributes.get("data-oppid"):
            self._row = {"id": attributes["data-oppid"], "url": ""}
            self._cells = []
        elif self._row is None:
            return
        elif tag == "td":
            self._text = []
        elif tag == "a" and "subject" in (attributes.get("class") or ""):
            self._row["url"] = attributes.get("href") or ""

    def handle_data(self, data: str) -> None:
        if self._text is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return
        if tag == "td" and self._text is not None:
            self._cells.append(" ".join("".join(self._text).split()))
            self._text = None
        elif tag == "tr":
            self._row["title"] = self._cells[0] if self._cells else ""
            self._row["city"] = self._cells[1] if len(self._cells) > 1 else ""
            self.rows.append(self._row)
            self._row = None


def _compile(pattern: str | None) -> re.Pattern[str] | None:
    return re.compile(pattern) if pattern else None


SCRAPER = TalentNexusScraper
