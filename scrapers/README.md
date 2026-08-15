# Scrapers

One module per company, because no two career sites share markup. Output shape
is common (`Job`), so the front end never cares where a row came from.

```
scrapers/
  base.py                    Job dataclass, Scraper base class, HTTP helpers
                             (fetch_json / fetch_text, post_json for Phenom)
  registry.py                config "module" string -> Scraper class
  run.py                     runs everything, writes ../data/jobs.json
  companies/oracle_recruiting.py  any Oracle Recruiting Cloud board, config-driven
  companies/eightfold.py     any Eightfold AI board, config-driven
  companies/talent_nexus.py  any tal.net campus board, config-driven
  companies/phenom.py        any Phenom People board, config-driven
  companies/bain.py          Bain roles (own CMS endpoint, not a hosted ATS)
  companies/goldman_sachs.py Goldman Sachs student programs (CMS feed, unused)
  tests/                     one test file per company, stdlib unittest
```

`goldman_sachs.py` reads the marketing pages under
goldmansachs.com/careers/students, which describe programs rather than list
openings. No config entry uses it; kept in case the brochure text is wanted
alongside the real requisitions.

## Shared modules

Neither of these is company-specific: both platforms power hundreds of large
employers, so a second employer on either is a config entry, not a new file.
Both de-duplicate by the platform's job id across `queries`, first query
winning, so a role matching two passes is labelled once.

### oracle_recruiting

Goldman Sachs runs higher.gs.com on Oracle Recruiting Cloud. Host, site number,
filters and link format all come from config.

| Option | Meaning |
|---|---|
| `host` | Oracle tenant, e.g. `hdpc.fa.us2.oraclecloud.com` |
| `site_number` | Career-site id, e.g. `CX_2` |
| `job_url_template` | Public link, `{id}` is the requisition id |
| `countries` | ISO codes kept, e.g. `["JP"]` |
| `queries` | List of labelled passes (below) |

Each entry in `queries` is one pass over the endpoint:

| Key | Meaning |
|---|---|
| `label` | Written to every matched job's `type` |
| `categories` | Experience-level facet values by name, OR'd |
| `facet_field` / `facet_values` | Custom flex-field facet, values OR'd |
| `title_include` / `title_exclude` | Regex applied to the title, last resort |

#### Finding facet values

`categories` is the facet GS's UI calls EXPERIENCE_LEVEL
(`higher.gs.com/results?EXPERIENCE_LEVEL=Analyst`). Names are resolved to the
finder's opaque ids at run time, so config stays readable. Dump the live list:

```bash
curl -s 'https://<host>/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=categoriesFacet&finder=findReqs;siteNumber=CX_2,limit=1' \
  | python3 -c 'import json,sys
for v in json.load(sys.stdin)["items"][0]["categoriesFacet"]:
    print(f"{v[\"Name\"]:24} {v[\"TotalCount\"]}")'
```

Swap `categoriesFacet` for `organizationsFacet`, `workLocationsFacet` or
`titlesFacet` to see the others. Custom fields need
`expand=flexFieldsFacet.values` plus `selectedFlexFieldsFacets=%22%22`; for GS
`AttributeChar6` is "Program" (Summer Analyst, New Analyst, ...), a campus-only
alternative to `categories`.

Two limits are baked in. The endpoint takes one facet field per request, so
location is filtered client-side on `PrimaryLocationCountry`. And the facet
listing returns only the top values, so a rarely used category name cannot be
resolved; the scraper raises with the names it did get rather than silently
dropping the filter.

Category membership is GS's own classification, not the job title. Several roles
titled "..., Associate, Tokyo" are tagged `Analyst` and so appear under entry
level, which is what the site's own EXPERIENCE_LEVEL filter does too.

### eightfold

Morgan Stanley's board is Eightfold AI. This module reads the same endpoint the
site's own front end calls, `https://<host>/api/pcsx/search`.

| Option | Meaning |
|---|---|
| `host` | Tenant, e.g. `morganstanley.eightfold.ai` |
| `domain` | Tenant's group id, e.g. `morganstanley.com` |
| `job_url_template` | Public link; `{id}`, `{host}`, `{domain}` are substituted |
| `queries` | List of labelled passes (below) |

| Query key | Meaning |
|---|---|
| `label` | Written to every matched job's `type` |
| `filters` | `{"country": ["Japan"], "pcsjoblevel": ["professional"]}` |
| `query` | Free-text search |
| `title_include` / `title_exclude` | Regex applied to the title, last resort |

Filters go out as repeated `filter_<name>=<value>` parameters: values under one
name are OR'd, different names are AND'd. Unlike the Oracle board, location is
filtered server-side, so no country post-filter is needed.

Every response carries the tenant's filter vocabulary in `data.filterDef`. Dump
it:

```bash
curl -s 'https://morganstanley.eightfold.ai/api/pcsx/search?domain=morganstanley.com&num=1' \
  | python3 -c 'import json,sys
d = json.load(sys.stdin)["data"]["filterDef"]
for f in d["smartFilters"] + d["allFilters"]:
    print(f["filterName"], [o[\"value\"] for o in f.get(\"options\") or []][:8])'
```

For Morgan Stanley that is `country`, `city`, `businessarea`, `employmenttype`,
`skills`, and `pcsjoblevel` (professional, vice president, executive director,
managing director). `professional` is the Analyst/Associate band, so it is what
the entry-level pass filters on.

Two things to know. `num` is clamped to 10 server-side, so a country with 40
openings costs 4 requests. And the older Eightfold endpoint
`/api/apply/v2/jobs` returns 403 "Not authorized for PCSX" on this tenant; it is
not a fallback.

Morgan Stanley's Eightfold board carries no internships or graduate programs.
Those live on tal.net, below.

### talent_nexus

Morgan Stanley recruits students on morganstanley.tal.net, a system unrelated to
its experienced-hire board. The whole board is one server-rendered page, so one
request is the whole listing:

```bash
curl -s 'https://morganstanley.tal.net/vx/candidate/jobboard/vacancy/1/adv/' \
  | grep -oE 'data-oppid="[0-9]+"|<td class="comm_list_tbody"> [^<]+'
```

| Option | Meaning |
|---|---|
| `host` | Tenant, e.g. `morganstanley.tal.net` |
| `board` | Vacancy id in the URL; MS has 1 = Global Programs, 2 = Campus Events |
| `cities` | City-column values kept, e.g. `["Tokyo"]` |
| `queries` | `label` plus `title_include` / `title_exclude`, as above |

The board's own filter checkboxes post opaque `f_Item_Opportunity_<n>_lk` ids
that differ per employer, so the city is filtered here instead, off the table's
City column. That column is empty for virtual events, which is convenient: a
`cities` filter drops them.

The board publishes no posting date, so these rows carry no `posted_at` and sort
below dated ones. Listing links carry a per-session `xf-<token>` path segment,
stripped so the saved URL is the shareable one.

### phenom

BCG runs careers.bcg.com on Phenom People. The site's search box posts to one
widget endpoint; we send the same body:

```bash
curl -s https://careers.bcg.com/widgets -H 'Content-Type: application/json' \
  -d '{"ddoKey":"refineSearch","lang":"en_global","country":"global","pageName":"search-results","pageId":"page11","from":0,"size":5,"jobs":true,"global":true,"siteType":"external","selected_fields":{"country":["Japan"]}}' \
  | python3 -c 'import json,sys
d = json.load(sys.stdin)["refineSearch"]
print(d["totalHits"], "hits")
for j in d["data"]["jobs"]:
    print(j["type"], "|", j["category"], "|", j["title"])'
```

| Option | Meaning |
|---|---|
| `host` | Tenant, e.g. `careers.bcg.com` |
| `job_url_template` | Public link; `{id}` is `jobSeqNo`, `{host}` the tenant |
| `lang` / `locale_country` / `page_id` | Site identifiers in the request body |
| `queries` | `label`, `filters`, `keywords`, `title_include` / `title_exclude` |

`filters` is the `selected_fields` object the site's own facet checkboxes send:
field name to values kept, values within a field OR'd. BCG's fields are
`country`, `city`, `state`, `category` and `type`.

The catch: `type` is not a contract or seniority signal at BCG. All 30 Japan
postings are "Full-Time", the summer and winter internships included, and there
is no level field at all, so `title_include` does the sorting. `Intern` needs
the `(?!ational)` guard rather than a `\b`, because BCG titles run words
together with underscores ("2027 Summer Intern_Bachelor or Master").

This is the one board we POST to, which is why `base.py` has `post_json`.

## Bain

Not a shared platform: bain.com/careers runs on Bain's own CMS, so
`companies/bain.py` is company-specific and its options are few.

```bash
curl -s -H 'Referer: https://www.bain.com/careers/find-a-role/' \
  'https://www.bain.com/en/api/jobsearch/keyword/get?filters=offices(268)|' \
  | python3 -c 'import json,sys
d = json.load(sys.stdin)
print(d["totalResults"], "results")
for b in d["filters"]["filterBlocks"]:
    print(b["filterGroup"], "|", b["filterTitle"])'
```

The `Referer` is not optional: without one the endpoint answers `{"error":
"Forbidden: Direct API access is not allowed."}`, which is why `base.py` grew a
`referer` argument.

`filters` in config is a group-to-ids mapping, serialised to the string the
site puts in its own URL bar, so a filter set can be copied straight off the
page:

```
?filters=employmenttype(E50,E2510,E00,E10)|offices(268)|
{ "employmenttype": ["E50", "E2510", "E00", "E10"], "offices": ["268"] }
```

Every response carries the ids under `filters.filterBlocks`; `offices` nests
them a level deeper, under `filterColumns` by region (268 is Tokyo). Employment
types are `E00` permanent full-time, `E10` temporary full-time, `E40` permanent
part-time, `E50` intern, `E840` temporary part-time, `E2510` program.

Employment type is a contract, not a seniority, and there is no seniority field,
so the Tokyo full-time pass includes Senior Manager roles. It is kept in `extra`
as `employment_type` since it is the one thing the labels flatten away.

Bain postings are mostly one role open in every office: the Associate Consultant
listing names 63. `location_label` renders that the way Bain's own results do,
"Tokyo + 62 offices", instead of a 63-city join.

## One company, several boards

A company entry takes either `scraper` (one) or `scrapers` (a list). Morgan
Stanley needs the list: experienced hires on Eightfold, students on tal.net.

If any one board fails, the whole company is treated as failed and its previous
jobs are carried over. Keeping only the boards that worked would look like every
posting on the other board had closed.

## Commands

```bash
python -m scrapers.run                        # write data/jobs.json
python -m scrapers.run --only goldman-sachs   # one company
python -m scrapers.run --dry-run              # print, write nothing
python -m scrapers.run --stale-days 3         # expire carried-over jobs sooner
python -m unittest discover -s scrapers/tests -t .
```

## Adding a company

1. Write `scrapers/companies/<name>.py`: subclass `Scraper`, implement `fetch()`
   returning `Job`s, end the file with `SCRAPER = YourScraper`.
2. Add the entry to `data/companies.json`:

```json
{
  "id": "acme",
  "name": "Acme",
  "url": "https://acme.example/careers",
  "scraper": { "module": "acme", "options": {} }
}
```

3. Add `scrapers/tests/test_<name>.py` with a saved sample of the response, so a
   site redesign shows up as a failing test rather than a silently empty board.

Before parsing HTML, check whether the site's own front end calls a JSON
endpoint. Goldman Sachs looks like a React page but its listing component fetches
`/feeds/programs-and-internships.json`; that is what we read. Morgan Stanley's
Eightfold board looked static too and turned out to call `/api/pcsx/search`.
tal.net genuinely has none, so `talent_nexus` parses the table.

## Only open jobs

`data/jobs.json` is rebuilt from what the scrapers just saw, not appended to, so
a posting that has disappeared from its company's listing is gone from the feed
on the next run. Every job carries `last_seen`, the run that found it live.

The one exception is the failure carryover below. Those jobs are kept for
`STALE_DAYS` (7, or `--stale-days N`) past their `last_seen` and then dropped:
after a week of not being able to confirm a posting exists, assume it closed.
A job with no datable `last_seen` at all is dropped rather than kept.

## Failure behaviour

`fetch()` should raise `ScrapeError` when the response no longer looks right
(empty list, missing fields) instead of returning nothing. `run.py` then keeps
that company's jobs from the previous run and exits non-zero, so the Action goes
red while the board stays intact.

Standard library only so far, including the one HTML board: `talent_nexus`
parses with `html.parser` anchored on a single `data-oppid` attribute. A page
that needs real CSS selectors will want `beautifulsoup4`; add a
`requirements.txt` and an install step in `.github/workflows/scrape.yml` when
that happens.
