"""Goldman Sachs student programs and internships.

The public page is a Next.js app that renders nothing useful server-side; the
listing component fetches `/feeds/programs-and-internships.json` on the client.
We hit that feed directly, which is stable JSON instead of scraped markup.

Page: https://www.goldmansachs.com/careers/students/programs-and-internships
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from ..base import Job, ScrapeError, Scraper, fetch_json

BASE_URL = "https://www.goldmansachs.com"
FEED_URL = f"{BASE_URL}/feeds/programs-and-internships.json"


class GoldmanSachsScraper(Scraper):
    name = "goldman_sachs"

    def fetch(self) -> Iterable[Job]:
        feed = fetch_json(self.options.get("feed_url", FEED_URL))
        if not isinstance(feed, list) or not feed:
            raise ScrapeError(f"{FEED_URL}: expected a non-empty list of programs")

        # Tag ids as used by the site's own filters, e.g.
        # "gscom:program-region-careers/asia-pacific". Empty means every region.
        regions = set(self.options.get("regions", []))
        program_types = set(self.options.get("program_types", []))

        jobs = []
        for entry in feed:
            props = entry.get("cmsPageProps") or {}
            locations = _tags(props.get("programLocation"))
            types = _tags(props.get("programType"))

            if regions and not regions & {t["id"] for t in locations}:
                continue
            if program_types and not program_types & {t["id"] for t in types}:
                continue

            path = entry.get("path") or entry.get("slug")
            title = entry.get("title")
            if not path or not title:
                raise ScrapeError(f"program entry missing path/title: {entry!r}")

            jobs.append(
                Job(
                    id=self.job_id(path),
                    company_id=self.company_id,
                    title=title,
                    url=f"{BASE_URL}{path}",
                    location=", ".join(t["title"] for t in locations) or None,
                    type=", ".join(t["title"] for t in types) or None,
                    # The feed carries no publish date. lastModifiedDate is a
                    # CMS edit timestamp (GS bulk-edits pages, so it clusters
                    # on unrelated dates) and would be a lie as posted_at.
                    posted_at=None,
                    extra={
                        "updated_at": _iso_date(entry.get("lastModifiedDate")),
                        "eligibility": props.get("eligibilityDetails"),
                    },
                )
            )

        return jobs


def _tags(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [t for t in value if isinstance(t, dict) and t.get("id")]


def _iso_date(epoch_ms: Any) -> str | None:
    if not isinstance(epoch_ms, (int, float)):
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).date().isoformat()


SCRAPER = GoldmanSachsScraper
