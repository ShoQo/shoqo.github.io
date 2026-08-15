"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scrapers import run
from scrapers.base import Job, ScrapeError, Scraper

NOW = datetime(2026, 8, 16, 6, 0, 0, tzinfo=timezone.utc)

COMPANIES = {"companies": [{"id": "acme", "name": "Acme", "scraper": {"module": "acme"}}]}


def job(job_id: str, last_seen: str | None) -> dict:
    row = {
        "id": f"acme:{job_id}",
        "company_id": "acme",
        "title": f"Job {job_id}",
        "url": f"https://acme.example/{job_id}",
        "posted_at": "2026-01-01",
    }
    if last_seen:
        row["last_seen"] = last_seen
    return row


class FakeScraper(Scraper):
    """Returns whatever `fetch` was patched to return, or raises."""

    result: list[Job] | Exception = []

    def fetch(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def scrape(previous: dict, result, **kwargs):
    """Run scrape() against a temp data dir holding `previous` as jobs.json."""
    FakeScraper.result = result

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "companies.json").write_text(json.dumps(COMPANIES), encoding="utf-8")
        (root / "jobs.json").write_text(json.dumps(previous), encoding="utf-8")

        with (
            mock.patch.object(run, "COMPANIES_PATH", root / "companies.json"),
            mock.patch.object(run, "JOBS_PATH", root / "jobs.json"),
            mock.patch.object(run, "build", return_value=[FakeScraper(COMPANIES["companies"][0])]),
        ):
            return run.scrape(now=NOW, **kwargs)


def ids(jobs):
    return [j["id"] for j in jobs]


class OpenJobsOnlyTest(unittest.TestCase):
    def test_a_job_missing_from_the_listing_is_dropped(self):
        previous = {"updated_at": run._stamp(NOW), "jobs": [job("closed", run._stamp(NOW))]}
        live = Job(id="acme:open", company_id="acme", title="Open", url="https://acme.example/open")

        jobs, failed = scrape(previous, [live])

        self.assertEqual(ids(jobs), ["acme:open"])
        self.assertEqual(failed, [])

    def test_live_jobs_are_stamped_with_the_run_time(self):
        live = Job(id="acme:open", company_id="acme", title="Open", url="https://acme.example/open")

        jobs, _ = scrape({"jobs": []}, [live])

        self.assertEqual(jobs[0]["last_seen"], "2026-08-16T06:00:00Z")


class StaleCarryoverTest(unittest.TestCase):
    def test_recent_jobs_survive_a_failing_scraper(self):
        recent = run._stamp(NOW - timedelta(days=2))
        previous = {"updated_at": recent, "jobs": [job("recent", recent)]}

        jobs, failed = scrape(previous, ScrapeError("site changed"))

        self.assertEqual(ids(jobs), ["acme:recent"])
        self.assertEqual(failed, ["acme"])

    def test_jobs_unseen_past_the_cutoff_are_dropped(self):
        old = run._stamp(NOW - timedelta(days=8))
        previous = {"updated_at": run._stamp(NOW), "jobs": [job("old", old)]}

        jobs, failed = scrape(previous, ScrapeError("site changed"))

        self.assertEqual(jobs, [])
        self.assertEqual(failed, ["acme"])

    def test_stale_days_is_configurable(self):
        seen = run._stamp(NOW - timedelta(days=2))
        previous = {"updated_at": seen, "jobs": [job("recent", seen)]}

        jobs, _ = scrape(previous, ScrapeError("site changed"), stale_days=1)

        self.assertEqual(jobs, [])

    def test_jobs_without_last_seen_fall_back_to_the_feed_timestamp(self):
        previous = {"updated_at": run._stamp(NOW - timedelta(days=1)), "jobs": [job("legacy", None)]}

        jobs, _ = scrape(previous, ScrapeError("site changed"))

        self.assertEqual(ids(jobs), ["acme:legacy"])

    def test_undateable_jobs_are_treated_as_closed(self):
        previous = {"jobs": [job("undated", None)]}

        jobs, _ = scrape(previous, ScrapeError("site changed"))

        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
