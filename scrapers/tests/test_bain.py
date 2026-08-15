"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.base import ScrapeError
from scrapers.companies.bain import BainScraper

COMPANY = {"id": "bain", "name": "Bain & Company"}

# Trimmed to the fields we read, from a live /en/api/jobsearch/keyword/get.
GLOBAL_ROLE = {
    "JobId": "10397",
    "JobTitle": "Associate Consultant",
    "Link": "/careers/find-a-role/position/?jobid=10397",
    "Location": ["Amsterdam ", " Boston ", " Tokyo "],
    "Categories": ["Management Consulting"],
    "EmployeeType": "Permanent Full-Time",
}
TOKYO_ONLY = {
    "JobId": "102727",
    "JobTitle": "Expert Senior Manager, Data Scientist",
    "Link": "/careers/find-a-role/position/?jobid=102727",
    "Location": ["Tokyo"],
    "Categories": ["Analytics, Data, & Research"],
    "EmployeeType": "Permanent Full-Time",
}
INTERNSHIP = {
    "JobId": "10463",
    "JobTitle": "Summer Associate",
    "Link": "/careers/work-with-us/internships-programs/summer-associate/",
    "Location": ["Boston ", " Tokyo "],
    "Categories": ["Management Consulting"],
    "EmployeeType": "Intern (Full-Time)",
}

ALL = [GLOBAL_ROLE, TOKYO_ONLY, INTERNSHIP]

TOKYO = {"offices": ["268"]}


def response(results, total=None):
    return {"totalResults": len(results) if total is None else total, "results": results}


def run(options, pages=None):
    scraper = BainScraper(COMPANY, options)
    queue = list(pages) if pages is not None else [response(ALL)] * 10

    with mock.patch(
        "scrapers.companies.bain.fetch_json", side_effect=lambda url, **_: queue.pop(0)
    ) as fetch:
        return list(scraper.fetch()), fetch


def urls(fetch):
    return [call[0][0] for call in fetch.call_args_list]


class RequestTest(unittest.TestCase):
    def test_filters_use_the_sites_own_group_syntax(self):
        _, fetch = run(
            {
                "queries": [
                    {
                        "label": "Internship",
                        "filters": {"employmenttype": ["E50", "E10"], "offices": ["268"]},
                    }
                ]
            }
        )
        self.assertIn(
            "filters=employmenttype%28E50%2CE10%29%7Coffices%28268%29%7C", urls(fetch)[0]
        )

    def test_a_referer_is_sent_since_the_endpoint_refuses_direct_access(self):
        _, fetch = run({"queries": [{"label": "Full-time", "filters": TOKYO}]})
        self.assertEqual(
            fetch.call_args_list[0][1]["referer"], "https://www.bain.com/careers/find-a-role/"
        )

    def test_pages_by_start_until_the_total_is_covered(self):
        _, fetch = run(
            {"queries": [{"label": "Full-time"}]},
            pages=[response(ALL, total=15), response([TOKYO_ONLY], total=15)],
        )
        self.assertEqual(len(urls(fetch)), 2)
        self.assertIn("start=0", urls(fetch)[0])
        self.assertIn("start=10", urls(fetch)[1])


class BainTest(unittest.TestCase):
    def test_job_fields(self):
        jobs, _ = run({"queries": [{"label": "Full-time", "filters": TOKYO}]})
        job = next(j for j in jobs if j.id.endswith("102727"))
        self.assertEqual(job.title, "Expert Senior Manager, Data Scientist")
        self.assertEqual(
            job.url, "https://www.bain.com/careers/find-a-role/position/?jobid=102727"
        )
        self.assertEqual(job.type, "Full-time")
        # No posting date is published; inventing one would misorder the feed.
        self.assertIsNone(job.posted_at)
        self.assertEqual(job.extra["employment_type"], "Permanent Full-Time")

    def test_a_role_open_everywhere_is_summarised_like_bains_own_results(self):
        jobs, _ = run({"location_label": "Tokyo", "queries": [{"label": "Full-time"}]})
        by_id = {j.id.rsplit(":", 1)[1]: j.location for j in jobs}
        self.assertEqual(by_id["10397"], "Tokyo + 2 offices")
        self.assertEqual(by_id["102727"], "Tokyo")

    def test_without_a_label_every_office_is_listed(self):
        jobs, _ = run({"queries": [{"label": "Full-time"}]})
        job = next(j for j in jobs if j.id.endswith("10397"))
        self.assertEqual(job.location, "Amsterdam, Boston, Tokyo")

    def test_each_query_labels_its_own_jobs(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Summer"},
                    {"label": "Full-time"},
                ]
            }
        )
        labels = {j.id.rsplit(":", 1)[1]: j.type for j in jobs}
        self.assertEqual(labels["10463"], "Internship")
        self.assertEqual(labels["10397"], "Full-time")

    def test_first_query_wins_when_a_job_matches_two(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Associate"},
                    {"label": "Full-time"},
                ]
            }
        )
        ids = [j.id.rsplit(":", 1)[1] for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "job emitted twice")

    def test_missing_queries_raises(self):
        with self.assertRaises(ScrapeError):
            list(BainScraper(COMPANY, {}).fetch())

    def test_empty_first_page_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[response([], total=12)])

    def test_the_forbidden_answer_raises(self):
        forbidden = {"error": "Forbidden: Direct API access is not allowed."}
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[forbidden])


if __name__ == "__main__":
    unittest.main()
