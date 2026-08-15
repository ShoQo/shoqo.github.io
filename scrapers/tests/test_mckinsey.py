"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.base import ScrapeError
from scrapers.companies.mckinsey import McKinseyScraper

COMPANY = {"id": "mckinsey", "name": "McKinsey & Company"}

# Trimmed to the fields we read, from a live /api/jobs/search.
GLOBAL_ROLE = {
    "jobID": "15178",
    "title": "Associate",
    "friendlyURL": "associate-15178",
    "cities": ["Tokyo", "London", "Boston"],
    "interest": "Consulting",
    "postedToLinkedInDate": "2023-05-26",
}
TOKYO_ONLY = {
    "jobID": "105275",
    "title": "Data Scientist - Quantumblack, AI by McKinsey",
    "friendlyURL": "datascientist-quantumblackaibymckinsey-105275",
    "cities": ["Tokyo"],
    "interest": "Analytics",
}
INTERNSHIP = {
    "jobID": "15275",
    "title": "Business Analyst Intern",
    "friendlyURL": "businessanalystintern-15275",
    "cities": ["Tokyo", "Osaka"],
    "interest": "Consulting",
}

ALL = [GLOBAL_ROLE, TOKYO_ONLY, INTERNSHIP]

TOKYO = {"cities": ["Tokyo"]}


def response(docs, total=None):
    return {
        "numFound": len(docs) if total is None else total,
        "httpStatus": "OK",
        "docs": docs,
    }


def run(options, pages=None):
    scraper = McKinseyScraper(COMPANY, options)
    queue = list(pages) if pages is not None else [response(ALL)] * 10

    with mock.patch(
        "scrapers.companies.mckinsey.fetch_json", side_effect=lambda url, **_: queue.pop(0)
    ) as fetch:
        return list(scraper.fetch()), fetch


def urls(fetch):
    return [call[0][0] for call in fetch.call_args_list]


class RequestTest(unittest.TestCase):
    def test_filters_go_on_the_query_string(self):
        _, fetch = run({"queries": [{"label": "Full-time", "filters": TOKYO}]})
        self.assertIn("cities=Tokyo", urls(fetch)[0])
        self.assertIn("lang=en", urls(fetch)[0])

    # The endpoint keeps the first value of a repeated parameter instead of
    # OR-ing, so several cities have to be several requests.
    def test_a_list_filter_becomes_one_request_per_value(self):
        _, fetch = run(
            {"queries": [{"label": "Full-time", "filters": {"cities": ["Tokyo", "Osaka"]}}]},
            pages=[response(ALL), response([TOKYO_ONLY])],
        )
        self.assertEqual(len(urls(fetch)), 2)
        self.assertIn("cities=Tokyo", urls(fetch)[0])
        self.assertIn("cities=Osaka", urls(fetch)[1])

    def test_start_is_a_one_based_page_number(self):
        _, fetch = run(
            {"queries": [{"label": "Full-time"}]},
            pages=[response(ALL, total=4), response([TOKYO_ONLY], total=4)],
        )
        self.assertEqual(len(urls(fetch)), 2)
        self.assertIn("start=1", urls(fetch)[0])
        self.assertIn("start=2", urls(fetch)[1])

    def test_paging_stops_once_the_total_is_covered(self):
        _, fetch = run({"queries": [{"label": "Full-time"}]}, pages=[response(ALL)])
        self.assertEqual(len(urls(fetch)), 1)


class McKinseyTest(unittest.TestCase):
    def test_job_fields(self):
        jobs, _ = run({"queries": [{"label": "Full-time", "filters": TOKYO}]})
        job = next(j for j in jobs if j.id.endswith("105275"))
        self.assertEqual(job.title, "Data Scientist - Quantumblack, AI by McKinsey")
        self.assertEqual(
            job.url,
            "https://www.mckinsey.com/careers/search-jobs/jobs/"
            "datascientist-quantumblackaibymckinsey-105275",
        )
        self.assertEqual(job.type, "Full-time")
        # postedToLinkedInDate is a syndication date, so no date is published.
        self.assertIsNone(job.posted_at)
        self.assertEqual(job.extra["interest"], "Analytics")

    def test_a_role_open_everywhere_is_summarised_like_bains_own_results(self):
        jobs, _ = run({"location_label": "Tokyo", "queries": [{"label": "Full-time"}]})
        by_id = {j.id.rsplit(":", 1)[1]: j.location for j in jobs}
        self.assertEqual(by_id["15178"], "Tokyo + 2 offices")
        self.assertEqual(by_id["105275"], "Tokyo")

    def test_without_a_label_every_office_is_listed(self):
        jobs, _ = run({"queries": [{"label": "Full-time"}]})
        job = next(j for j in jobs if j.id.endswith("15178"))
        self.assertEqual(job.location, "Tokyo, London, Boston")

    def test_each_query_labels_its_own_jobs(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Intern"},
                    {"label": "Full-time", "title_exclude": "Intern"},
                ]
            }
        )
        labels = {j.id.rsplit(":", 1)[1]: j.type for j in jobs}
        self.assertEqual(labels["15275"], "Internship")
        self.assertEqual(labels["15178"], "Full-time")

    def test_first_query_wins_when_a_job_matches_two(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Analyst"},
                    {"label": "Full-time"},
                ]
            }
        )
        ids = [j.id.rsplit(":", 1)[1] for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "job emitted twice")

    def test_missing_queries_raises(self):
        with self.assertRaises(ScrapeError):
            list(McKinseyScraper(COMPANY, {}).fetch())

    def test_empty_first_page_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[response([], total=12)])

    # A page past the end answers docs: null; that must not crash mid-paging.
    def test_a_null_docs_page_ends_paging(self):
        jobs, fetch = run(
            {"queries": [{"label": "Full-time"}]},
            pages=[response(ALL, total=9), {"numFound": 0, "httpStatus": "OK", "docs": None}],
        )
        self.assertEqual(len(urls(fetch)), 2)
        self.assertEqual(len(jobs), 3)

    def test_an_error_status_raises(self):
        with self.assertRaises(ScrapeError):
            run(
                {"queries": [{"label": "x"}]},
                pages=[{"numFound": 0, "httpStatus": "BAD_REQUEST", "statusMessage": "nope"}],
            )


if __name__ == "__main__":
    unittest.main()
