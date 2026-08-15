"""Run with: python -m unittest discover scrapers/tests"""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.base import ScrapeError
from scrapers.companies.talent_nexus import TalentNexusScraper

COMPANY = {"id": "morgan-stanley", "name": "Morgan Stanley"}

OPTIONS = {"host": "morganstanley.tal.net", "board": 1}

LINK = (
    "https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/brand-2/xf-fda6a251267f"
    "/candidate/so/pm/1/pl/1/opp/{slug}/en-GB"
)


def row(opp_id: str, title: str, city: str, slug: str) -> str:
    return f"""
      <tr class="opp_{opp_id} search_res details_row" data-oppid="{opp_id}"
          data-lat="" data-title="{title}">
        <td class="comm_list_tbody">
          <a class="subject" href="{LINK.format(slug=slug)}"> {title} </a>
        </td>
        <td class="comm_list_tbody"> {city} </td>
      </tr>"""


# The real board wraps the rows in navigation and filter markup; the parser is
# anchored on data-oppid, so the surrounding chrome is left out here.
BOARD = f"""<html><body>
  <table class="table solr_search_list" summary='results match'>
    <thead><tr class="opp_"><th>Title</th><th>City</th></tr></thead>
    <tbody>
      {row("21333", "2027 Investment Banking Summer Associate Program (Tokyo)", "Tokyo",
           "21333-2027-Investment-Banking-Summer-Associate-Program-Tokyo")}
      {row("21332", "2027 Japan Summer Analyst Program (Tokyo)", "Tokyo",
           "21332-2027-Japan-Summer-Analyst-Program-Tokyo")}
      {row("21242", "2027 Investment Banking Full-Time Analyst Programme (Paris)", "Paris",
           "21242-2027-Investment-Banking-Full-Time-Analyst-Programme-Paris")}
      {row("21465", "2026 EMEA Morgan Stanley Virtual Event Series", "",
           "21465-2026-EMEA-Morgan-Stanley-Virtual-Event-Series")}
    </tbody>
  </table>
</body></html>"""


def run(options, page=BOARD):
    scraper = TalentNexusScraper(COMPANY, {**OPTIONS, **options})
    with mock.patch(
        "scrapers.companies.talent_nexus.fetch_text", return_value=page
    ) as fetch:
        return list(scraper.fetch()), fetch


class TalentNexusTest(unittest.TestCase):
    def test_board_is_read_in_one_request(self):
        _, fetch = run({"queries": [{"label": "Internship"}]})
        self.assertEqual(
            fetch.call_args[0][0],
            "https://morganstanley.tal.net/vx/candidate/jobboard/vacancy/1/adv/",
        )

    def test_city_filter_drops_other_cities_and_undated_events(self):
        jobs, _ = run({"cities": ["Tokyo"], "queries": [{"label": "Internship"}]})
        self.assertEqual(
            sorted(j.id.rsplit(":", 1)[1] for j in jobs), ["21332", "21333"]
        )

    def test_job_fields_and_link_without_the_session_token(self):
        jobs, _ = run({"cities": ["Tokyo"], "queries": [{"label": "Internship"}]})
        job = next(j for j in jobs if j.id.endswith("21333"))
        self.assertEqual(job.title, "2027 Investment Banking Summer Associate Program (Tokyo)")
        self.assertEqual(
            job.url,
            "https://morganstanley.tal.net/vx/candidate/so/pm/1/pl/1/opp/"
            "21333-2027-Investment-Banking-Summer-Associate-Program-Tokyo/en-GB",
        )
        self.assertEqual(job.location, "Tokyo")
        self.assertEqual(job.type, "Internship")
        # The board publishes no posting date; inventing one would misorder the feed.
        self.assertIsNone(job.posted_at)

    def test_each_query_labels_its_own_opportunities(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Summer|Internship"},
                    {"label": "Full-time, entry level"},
                ]
            }
        )
        labels = {j.id.rsplit(":", 1)[1]: j.type for j in jobs}
        self.assertEqual(labels["21333"], "Internship")
        self.assertEqual(labels["21242"], "Full-time, entry level")

    def test_first_query_wins_when_an_opportunity_matches_two(self):
        jobs, _ = run(
            {
                "queries": [
                    {"label": "Internship", "title_include": "Summer"},
                    {"label": "Full-time, entry level"},
                ]
            }
        )
        ids = [j.id.rsplit(":", 1)[1] for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "opportunity emitted twice")
        self.assertEqual({j.id.rsplit(":", 1)[1]: j.type for j in jobs}["21333"], "Internship")

    def test_missing_queries_raises(self):
        scraper = TalentNexusScraper(COMPANY, OPTIONS)
        with self.assertRaises(ScrapeError):
            list(scraper.fetch())

    def test_a_board_without_rows_raises(self):
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, page="<html><body>Maintenance</body></html>")

    def test_a_row_without_a_link_raises(self):
        broken = BOARD.replace('<a class="subject"', "<a")
        with self.assertRaises(ScrapeError):
            run({"queries": [{"label": "x"}]}, page=broken)


if __name__ == "__main__":
    unittest.main()
