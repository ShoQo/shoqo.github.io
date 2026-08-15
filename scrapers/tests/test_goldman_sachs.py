"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.companies.goldman_sachs import GoldmanSachsScraper
from scrapers.base import ScrapeError

COMPANY = {"id": "goldman-sachs", "name": "Goldman Sachs"}

FEED = [
    {
        "slug": "/careers/students/programs-and-internships/apac/2027-summer-analyst-program",
        "title": "2027 Summer Analyst Program",
        "path": "/careers/students/programs-and-internships/apac/2027-summer-analyst-program",
        "lastModifiedDate": 1772047738408,
        "cmsPageProps": {
            "programLocation": [
                {"id": "gscom:program-region-careers/asia-pacific", "title": "Asia-Pacific"}
            ],
            "programType": [{"id": "gscom:program-type/internship", "title": "Internship"}],
            "eligibilityDetails": "Penultimate-year students.",
        },
    },
    {
        "slug": "/careers/students/programs-and-internships/emea/new-analyst-program",
        "title": "New Analyst Program",
        "path": "/careers/students/programs-and-internships/emea/new-analyst-program",
        "lastModifiedDate": 1772047738408,
        "cmsPageProps": {
            "programLocation": [
                {
                    "id": "gscom:program-region-careers/europe-middle-east-and-africa",
                    "title": "Europe, Middle East and Africa",
                }
            ],
            "programType": [{"id": "gscom:program-type/full-time", "title": "Full-Time"}],
        },
    },
]


def run(options, feed=FEED):
    scraper = GoldmanSachsScraper(COMPANY, options)
    with mock.patch("scrapers.companies.goldman_sachs.fetch_json", return_value=feed):
        return list(scraper.fetch())


class GoldmanSachsTest(unittest.TestCase):
    def test_region_filter_keeps_only_matching_programs(self):
        jobs = run({"regions": ["gscom:program-region-careers/asia-pacific"]})
        self.assertEqual([j.title for j in jobs], ["2027 Summer Analyst Program"])

    def test_no_filter_returns_everything(self):
        self.assertEqual(len(run({})), 2)

    def test_job_fields(self):
        job = run({"regions": ["gscom:program-region-careers/asia-pacific"]})[0]
        self.assertEqual(job.company_id, "goldman-sachs")
        self.assertTrue(job.url.startswith("https://www.goldmansachs.com/careers/"))
        self.assertEqual(job.location, "Asia-Pacific")
        self.assertEqual(job.type, "Internship")
        # The feed has no publish date, so posted_at stays empty and the CMS
        # edit timestamp is surfaced separately as updated_at.
        self.assertIsNone(job.posted_at)
        self.assertEqual(job.extra["updated_at"], "2026-02-25")
        self.assertEqual(job.id, "goldman-sachs:careers-students-programs-and-internships-apac-2027-summer-analyst-program")

    def test_empty_feed_raises_instead_of_emptying_the_board(self):
        with self.assertRaises(ScrapeError):
            run({}, feed=[])

    def test_entry_missing_path_raises(self):
        broken = [{"title": "Mystery Program", "cmsPageProps": {}}]
        with self.assertRaises(ScrapeError):
            run({}, feed=broken)


if __name__ == "__main__":
    unittest.main()
