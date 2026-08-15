"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.base import ScrapeError
from scrapers.companies.eightfold import EightfoldScraper

COMPANY = {"id": "morgan-stanley", "name": "Morgan Stanley"}

OPTIONS = {"host": "morganstanley.eightfold.ai", "domain": "morganstanley.com"}

# Trimmed to the fields we read, from a live /api/pcsx/search response.
ENTRY = {
    "id": 549798719545,
    "displayJobId": "PT-JR040158",
    "name": "Associate, Fixed Income Operations, Tokyo",
    "locations": ["Tokyo, Japan"],
    "postedTs": 1786665600,
    "department": "Core Services",
    "positionUrl": "/careers/job/549798719545",
}
MULTI_SITE = {
    "id": 549797328598,
    "name": "Morgan Stanley Japan, Operations Group, Equity, Fixed Income and Shared Services",
    "locations": ["Tokyo, Japan", "Osaka, Osaka, Japan"],
    "postedTs": 1786492800,
}
SENIOR = {
    "id": 549798611191,
    "name": "Regional Surveillance Technical Officer, Vice President",
    "locations": ["Tokyo, Japan"],
    "postedTs": 1782950400,
}

ALL = [ENTRY, MULTI_SITE, SENIOR]


def response(positions, count=None):
    return {
        "status": 200,
        "error": {"message": "", "body": ""},
        "data": {"positions": positions, "count": len(positions) if count is None else count},
    }


def run(options, pages=None):
    scraper = EightfoldScraper(COMPANY, {**OPTIONS, **options})
    queue = list(pages) if pages is not None else [response(ALL)] * 10

    with mock.patch(
        "scrapers.companies.eightfold.fetch_json", side_effect=lambda url, **_: queue.pop(0)
    ) as fetch:
        return list(scraper.fetch()), fetch


def urls(fetch):
    return [call[0][0] for call in fetch.call_args_list]


class SearchUrlTest(unittest.TestCase):
    def test_filters_repeat_one_parameter_per_value(self):
        _, fetch = run(
            {
                "queries": [
                    {
                        "label": "Entry",
                        "filters": {
                            "country": ["Japan"],
                            "pcsjoblevel": ["professional", "vice president"],
                        },
                    }
                ]
            }
        )
        url = urls(fetch)[0]
        self.assertIn("filter_country=Japan", url)
        self.assertIn("filter_pcsjoblevel=professional", url)
        self.assertIn("filter_pcsjoblevel=vice+president", url)

    def test_pages_by_start_until_count_is_covered(self):
        _, fetch = run(
            {"queries": [{"label": "Entry"}]},
            pages=[response(ALL, count=13), response([SENIOR], count=13)],
        )
        starts = urls(fetch)
        self.assertEqual(len(starts), 2)
        self.assertIn("start=0", starts[0])
        self.assertIn("start=10", starts[1])

    def test_free_text_query_is_passed_through(self):
        _, fetch = run({"queries": [{"label": "Entry", "query": "software engineer"}]})
        self.assertIn("query=software+engineer", urls(fetch)[0])


class EightfoldTest(unittest.TestCase):
    def test_job_fields(self):
        jobs, _ = run({"queries": [{"label": "Full-time, entry level"}]})
        job = next(j for j in jobs if j.id.endswith("549798719545"))
        self.assertEqual(job.title, "Associate, Fixed Income Operations, Tokyo")
        self.assertEqual(
            job.url,
            "https://morganstanley.eightfold.ai/careers/job/549798719545"
            "?domain=morganstanley.com",
        )
        self.assertEqual(job.location, "Tokyo, Japan")
        self.assertEqual(job.type, "Full-time, entry level")
        self.assertEqual(job.posted_at, "2026-08-14")

    def test_several_locations_are_joined(self):
        jobs, _ = run({"queries": [{"label": "Entry"}]})
        job = next(j for j in jobs if j.id.endswith("549797328598"))
        self.assertEqual(job.location, "Tokyo, Japan, Osaka, Osaka, Japan")

    def test_each_query_labels_its_own_jobs(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Senior", "title_include": r"Vice President"},
                    {"label": "Full-time, entry level"},
                ]
            }
        )
        labels = {j.id.rsplit(":", 1)[1]: j.type for j in jobs}
        self.assertEqual(labels["549798611191"], "Senior")
        self.assertEqual(labels["549798719545"], "Full-time, entry level")

    def test_first_query_wins_when_a_position_matches_two(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Senior", "title_exclude": r"Operations"},
                    {"label": "Entry"},
                ]
            }
        )
        ids = [j.id.rsplit(":", 1)[1] for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "position emitted twice")

    def test_missing_queries_raises(self):
        scraper = EightfoldScraper(COMPANY, OPTIONS)
        with self.assertRaises(ScrapeError):
            list(scraper.fetch())

    def test_missing_host_raises(self):
        scraper = EightfoldScraper(COMPANY, {"domain": "x", "queries": [{"label": "y"}]})
        with self.assertRaises(ScrapeError):
            list(scraper.fetch())

    def test_empty_first_page_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[response([], count=12)])

    def test_response_without_data_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[{"status": 403, "message": "no"}])


if __name__ == "__main__":
    unittest.main()
