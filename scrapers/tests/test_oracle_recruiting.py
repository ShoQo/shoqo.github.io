"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.base import ScrapeError
from scrapers.companies.oracle_recruiting import OracleRecruitingScraper

COMPANY = {"id": "goldman-sachs", "name": "Goldman Sachs"}

OPTIONS = {
    "host": "hdpc.fa.us2.oraclecloud.com",
    "site_number": "CX_2",
    "job_url_template": "https://higher.gs.com/roles/{id}",
}

CATEGORIES = {
    "items": [
        {
            "categoriesFacet": [
                {"Id": 300000016154101, "Name": "Analyst", "TotalCount": 207},
                {"Id": 300000016154115, "Name": "Summer Analyst", "TotalCount": 148},
                {"Id": 300000016154099, "Name": "Senior Analyst", "TotalCount": 50},
            ]
        }
    ]
}

INTERN = {
    "Id": 170821,
    "Title": "2027 | Japan | Tokyo | Global Investment Research | Summer Analyst",
    "PostedDate": "2025-07-01",
    "PrimaryLocation": "Minato-Ku, Tokyo, Japan",
    "PrimaryLocationCountry": "JP",
}
ENTRY = {
    "Id": 181358,
    "Title": "Global Banking & Markets - Trade Processing, Analyst, Tokyo",
    "PostedDate": "2026-08-10",
    "PrimaryLocation": "Minato-Ku, Tokyo, Japan",
    "PrimaryLocationCountry": "JP",
}
US_JOB = {
    "Id": 155957,
    "Title": "Controllers, Product Control, Analyst, New York",
    "PostedDate": "2026-08-15",
    "PrimaryLocation": "New York, NY, United States",
    "PrimaryLocationCountry": "US",
}

ALL = [INTERN, ENTRY, US_JOB]


def response(requisitions):
    return {"items": [{"TotalJobsCount": len(requisitions), "requisitionList": requisitions}]}


def run(options, pages=None):
    """Fake the endpoint: category lookups answer from CATEGORIES, searches from `pages`."""
    scraper = OracleRecruitingScraper(COMPANY, {**OPTIONS, **options})
    queue = list(pages) if pages is not None else [response(ALL)] * 10

    def fake(url, **_):
        if "expand=categoriesFacet" in url:
            return CATEGORIES
        return queue.pop(0)

    with mock.patch(
        "scrapers.companies.oracle_recruiting.fetch_json", side_effect=fake
    ) as fetch:
        return list(scraper.fetch()), fetch


def urls(fetch):
    return [call[0][0] for call in fetch.call_args_list]


class CategoryResolutionTest(unittest.TestCase):
    def test_names_are_resolved_to_ids_and_joined(self):
        _, fetch = run(
            {"queries": [{"label": "Internship", "categories": ["Summer Analyst", "Analyst"]}]}
        )
        search = urls(fetch)[1]
        self.assertIn(
            "selectedCategoriesFacet=300000016154115%3B300000016154101", search
        )

    def test_categories_are_fetched_once_across_queries(self):
        _, fetch = run(
            {
                "queries": [
                    {"label": "Internship", "categories": ["Summer Analyst"]},
                    {"label": "Entry", "categories": ["Analyst"]},
                ]
            }
        )
        lookups = [u for u in urls(fetch) if "expand=categoriesFacet" in u]
        self.assertEqual(len(lookups), 1)

    def test_unknown_category_name_raises_with_the_valid_ones(self):
        with self.assertRaises(ScrapeError) as ctx:
            run({"queries": [{"label": "x", "categories": ["Vice Chancellor"]}]})
        self.assertIn("Vice Chancellor", str(ctx.exception))
        self.assertIn("Summer Analyst", str(ctx.exception))


class OracleRecruitingTest(unittest.TestCase):
    def test_country_filter_drops_other_countries(self):
        jobs, _ = run({"countries": ["JP"], "queries": [{"label": "All"}]})
        self.assertNotIn("155957", [j.id.rsplit(":", 1)[1] for j in jobs])

    def test_each_query_labels_its_own_jobs(self):
        jobs, _ = run(
            {
                "countries": ["JP"],
                "queries": [
                    {"label": "Internship", "title_include": r"Summer"},
                    {"label": "Full-time, entry level", "title_include": r"\bAnalyst\b"},
                ],
            }
        )
        labels = {j.id.rsplit(":", 1)[1]: j.type for j in jobs}
        self.assertEqual(labels["170821"], "Internship")
        self.assertEqual(labels["181358"], "Full-time, entry level")

    def test_first_query_wins_when_a_job_matches_two(self):
        jobs, _ = run(
            {
                "countries": ["JP"],
                "queries": [
                    {"label": "Internship", "title_include": r"Summer Analyst"},
                    {"label": "Full-time", "title_include": r"\bAnalyst\b"},
                ],
            }
        )
        ids = [j.id.rsplit(":", 1)[1] for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "requisition emitted twice")
        self.assertEqual({j.id.rsplit(":", 1)[1]: j.type for j in jobs}["170821"], "Internship")

    def test_flex_field_facet_still_supported(self):
        _, fetch = run(
            {
                "queries": [
                    {
                        "label": "Program",
                        "facet_field": "AttributeChar6",
                        "facet_values": ["New Analyst", "New Associate"],
                    }
                ]
            },
            pages=[response(ALL)],
        )
        self.assertIn(
            "selectedFlexFieldsFacets=AttributeChar6%7CNew%20Analyst%3BNew%20Associate",
            urls(fetch)[0],
        )

    def test_job_fields(self):
        jobs, _ = run({"countries": ["JP"], "queries": [{"label": "Internship"}]})
        job = next(j for j in jobs if j.id.endswith("170821"))
        self.assertEqual(job.url, "https://higher.gs.com/roles/170821")
        self.assertEqual(job.location, "Minato-Ku, Tokyo, Japan")
        self.assertEqual(job.posted_at, "2025-07-01")

    def test_missing_queries_raises(self):
        scraper = OracleRecruitingScraper(COMPANY, OPTIONS)
        with self.assertRaises(ScrapeError):
            list(scraper.fetch())

    def test_empty_first_page_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, pages=[response([])])


if __name__ == "__main__":
    unittest.main()
