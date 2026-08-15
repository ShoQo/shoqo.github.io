"""Maps a config `scraper.module` string to a Scraper class."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from .base import Scraper

PACKAGE = "scrapers.companies"


def get_scraper(module_name: str) -> type[Scraper]:
    try:
        module = importlib.import_module(f"{PACKAGE}.{module_name}")
    except ModuleNotFoundError as err:
        raise LookupError(
            f"no scraper module '{module_name}' (available: {', '.join(available())})"
        ) from err

    scraper = getattr(module, "SCRAPER", None)
    if scraper is None or not issubclass(scraper, Scraper):
        raise LookupError(f"{PACKAGE}.{module_name} must expose SCRAPER = <Scraper subclass>")
    return scraper


def available() -> list[str]:
    package = importlib.import_module(PACKAGE)
    return sorted(m.name for m in pkgutil.iter_modules(package.__path__))


def build(company: dict[str, Any]) -> list[Scraper]:
    """Instantiate the scrapers configured on a companies.json entry.

    A company can list several: Morgan Stanley recruits experienced hires and
    students on two unrelated platforms, so one company entry needs one scraper
    per board. `scraper` (one object) and `scrapers` (a list) both work.
    """
    configs = company.get("scrapers") or ([company["scraper"]] if company.get("scraper") else [])
    return [get_scraper(c["module"])(company, c.get("options")) for c in configs]
