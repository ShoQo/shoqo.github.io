"""Run every configured company scraper and write data/jobs.json.

    python -m scrapers.run                     # all companies, writes data/jobs.json
    python -m scrapers.run --only goldman-sachs
    python -m scrapers.run --dry-run           # print, write nothing
    python -m scrapers.run --stale-days 3      # expire carried-over jobs sooner
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import Job
from .registry import build

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_PATH = ROOT / "data" / "companies.json"
JOBS_PATH = ROOT / "data" / "jobs.json"

# A listing that no longer returns a job is a closed job, so a successful run
# simply drops it. The only jobs that outlive their listing are the ones a
# failing scraper carries over; this is how long that is allowed to last before
# we assume they closed too.
STALE_DAYS = 7


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _stamp(now: datetime) -> str:
    return now.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(stamp: Any) -> datetime | None:
    if not isinstance(stamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _still_open(job: dict[str, Any], fallback: Any, cutoff: datetime) -> bool:
    """True while a carried-over job is young enough to still be believable.

    `last_seen` is the run that actually saw the job in its company's listing.
    Jobs written before that field existed fall back to the feed's own
    `updated_at`; with neither we cannot date the job, so we treat it as closed
    rather than keep a possibly dead posting on the board forever.
    """
    seen = _parse(job.get("last_seen")) or _parse(fallback)
    return seen is not None and seen >= cutoff


def scrape(
    company_ids: list[str] | None = None,
    *,
    stale_days: int = STALE_DAYS,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (jobs, failed_company_ids).

    Only jobs the scrapers just saw in a live listing are written, so a closed
    posting disappears on the next run. A company whose scraper fails keeps its
    previous jobs, so one broken site does not empty the board for everyone
    else, but only until they go `stale_days` without being seen.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=stale_days)
    seen_at = _stamp(now)

    companies = load_json(COMPANIES_PATH, {"companies": []})["companies"]
    previous_payload = load_json(JOBS_PATH, {"jobs": []})
    previous = previous_payload.get("jobs", [])
    previous_updated_at = previous_payload.get("updated_at")

    jobs: list[dict[str, Any]] = []
    failed: list[str] = []

    for company in companies:
        company_id = company["id"]
        if company_ids and company_id not in company_ids:
            continue

        try:
            # build() imports the company's module, so a module with a syntax
            # error or a bad import belongs inside the try with its fetch.
            scrapers = build(company)
            if not scrapers:
                print(f"skip   {company_id}: no scraper configured")
                continue
            # One failing board fails the whole company: keeping the boards that
            # did work would look like the other board's jobs all closed.
            found = [
                job.to_dict() if isinstance(job, Job) else job
                for scraper in scrapers
                for job in scraper.fetch()
            ]
        except Exception as err:  # any scraper bug must not kill the whole run
            carried = [j for j in previous if j.get("company_id") == company_id]
            stale = [j for j in carried if _still_open(j, previous_updated_at, cutoff)]
            expired = len(carried) - len(stale)
            failed.append(company_id)
            print(
                f"FAIL   {company_id}: {err} (keeping {len(stale)} previous jobs, "
                f"dropping {expired} unseen for {stale_days}+ days)",
                file=sys.stderr,
            )
            jobs.extend(stale)
            continue

        for job in found:
            job["last_seen"] = seen_at

        print(f"ok     {company_id}: {len(found)} jobs")
        jobs.extend(found)

    # Sources without a real posting date fall back to their own updated_at, so
    # the newest rows still float to the top of a mixed feed.
    jobs.sort(
        key=lambda j: (j.get("posted_at") or j.get("updated_at") or "", j.get("title") or ""),
        reverse=True,
    )
    return jobs, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", metavar="COMPANY_ID", help="limit to these companies")
    parser.add_argument("--dry-run", action="store_true", help="print results without writing")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=STALE_DAYS,
        metavar="N",
        help=f"drop jobs a failing scraper has not seen for N days (default {STALE_DAYS})",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    jobs, failed = scrape(args.only, stale_days=args.stale_days, now=now)

    payload = {"updated_at": _stamp(now), "jobs": jobs}

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        JOBS_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {JOBS_PATH.relative_to(ROOT)}: {len(jobs)} jobs")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
