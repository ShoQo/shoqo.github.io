"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.base import ScrapeError
from scrapers.companies.phenom import PhenomScraper

COMPANY = {"id": "bcg", "name": "Boston Consulting Group"}

OPTIONS = {"host": "careers.bcg.com"}

# Trimmed to the fields we read, from a live POST /widgets response.
CONSULTANT = {
    "jobSeqNo": "BCG1US56744EXTERNALENGLOBAL",
    "jobId": "56744",
    "title": "Consultant, JPN",
    "type": "Full-Time",
    "category": "Consulting",
    "city": "Tokyo",
    "country": "Japan",
    "location": "Tokyo, Japan",
    "multi_location": ["Tokyo, Japan"],
    "postedDate": "2026-06-17T00:00:00.000+0000",
}
INTERN = {
    "jobSeqNo": "BCG1US57807EXTERNALENGLOBAL",
    "jobId": "57807",
    "title": "JPN, 海外大, Autumn＆BCF選考, 2027 Summer Intern_Bachelor or Master",
    "type": "Full-Time",
    "location": "Tokyo, Japan",
    "multi_location": ["Tokyo, Japan"],
    "postedDate": "2026-07-10T00:00:00.000+0000",
}
TWO_OFFICES = {
    "jobSeqNo": "BCG1US57000EXTERNALENGLOBAL",
    "jobId": "57000",
    "title": "Lead IT Architect, Japan - Platinion",
    "type": "Full-Time",
    "location": "Tokyo, Japan",
    "multi_location": ["Tokyo, Japan", "Osaka, Japan"],
    "postedDate": "2026-01-12T00:00:00.000+0000",
}

ALL = [CONSULTANT, INTERN, TWO_OFFICES]


def response(jobs, total=None):
    return {
        "refineSearch": {
            "status": 200,
            "totalHits": len(jobs) if total is None else total,
            "data": {"jobs": jobs, "aggregations": []},
        }
    }


def run(options, pages=None):
    scraper = PhenomScraper(COMPANY, {**OPTIONS, **options})
    queue = list(pages) if pages is not None else [response(ALL)] * 10

    with mock.patch(
        "scrapers.companies.phenom.post_json", side_effect=lambda url, body, **_: queue.pop(0)
    ) as post:
        return list(scraper.fetch()), post


def bodies(post):
    return [call[0][1] for call in post.call_args_list]


class RequestTest(unittest.TestCase):
    def test_filters_go_out_as_selected_fields(self):
        _, post = run(
            {"queries": [{"label": "Entry", "filters": {"country": ["Japan"], "city": ["Tokyo"]}}]}
        )
        body = bodies(post)[0]
        self.assertEqual(body["selected_fields"], {"country": ["Japan"], "city": ["Tokyo"]})
        self.assertEqual(body["ddoKey"], "refineSearch")
        self.assertEqual(body["from"], 0)

    def test_pages_by_from_until_total_is_covered(self):
        _, post = run(
            {"queries": [{"label": "Entry"}]},
            pages=[response(ALL, total=150), response([CONSULTANT], total=150)],
        )
        self.assertEqual([b["from"] for b in bodies(post)], [0, 100])

    def test_keywords_are_passed_through(self):
        _, post = run({"queries": [{"label": "Entry", "keywords": "data scientist"}]})
        self.assertEqual(bodies(post)[0]["keywords"], "data scientist")


class PhenomTest(unittest.TestCase):
    def test_job_fields(self):
        jobs, _ = run({"queries": [{"label": "Full-time"}]})
        job = next(j for j in jobs if j.id.endswith("56744EXTERNALENGLOBAL"))
        self.assertEqual(job.title, "Consultant, JPN")
        self.assertEqual(
            job.url, "https://careers.bcg.com/global/en/job/BCG1US56744EXTERNALENGLOBAL"
        )
        self.assertEqual(job.location, "Tokyo, Japan")
        self.assertEqual(job.type, "Full-time")
        self.assertEqual(job.posted_at, "2026-06-17")

    def test_a_job_open_in_two_offices_lists_both(self):
        jobs, _ = run({"queries": [{"label": "Full-time"}]})
        job = next(j for j in jobs if j.id.endswith("57000EXTERNALENGLOBAL"))
        self.assertEqual(job.location, "Tokyo, Japan, Osaka, Japan")

    def test_internships_are_labelled_by_title_since_type_never_says_so(self):
        # BCG stamps every posting "Full-Time", internships included.
        self.assertEqual({j["type"] for j in ALL}, {"Full-Time"})
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Intern(?!ational)|インターン"},
                    {"label": "Full-time"},
                ]
            }
        )
        labels = {j.id.rsplit(":", 1)[1]: j.type for j in jobs}
        self.assertEqual(labels["BCG1US57807EXTERNALENGLOBAL"], "Internship")
        self.assertEqual(labels["BCG1US56744EXTERNALENGLOBAL"], "Full-time")

    def test_first_query_wins_when_a_job_matches_two(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Intern(?!ational)"},
                    {"label": "Full-time"},
                ]
            }
        )
        ids = [j.id.rsplit(":", 1)[1] for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "job emitted twice")

    def test_missing_queries_raises(self):
        scraper = PhenomScraper(COMPANY, OPTIONS)
        with self.assertRaises(ScrapeError):
            list(scraper.fetch())

    def test_empty_first_page_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[response([], total=20)])

    def test_response_without_the_widget_key_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[{"eagerLoadRefineSearch": {}}])


if __name__ == "__main__":
    unittest.main()
