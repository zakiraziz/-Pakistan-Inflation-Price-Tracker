"""
sources.py
----------
Pluggable data sources. Each source fetches price points as a list of dicts:
    {"item": str, "date": "YYYY-MM-DD", "price": float, "method": str}

A source whose `.name` is set describes the *provenance* stored with every
price point.
"""

from __future__ import annotations

import csv
from datetime import date

from model import ITEMS, price_at


# ---------------------------------------------------------------------------
class _BaseSource:
    name = "base"
    method = "unknown"

    def fetch(self):
        raise NotImplementedError

    def __iter__(self):
        return iter(self.fetch())


# ---------------------------------------------------------------------------
class SeedSource(_BaseSource):
    """Deterministic baseline/internal source (the reproducible generator).

    This is what `seed.py` uses to build the trusted baseline. By default it
    emits points that PASS the validator so the baseline is pre-approved.
    """

    name = "seed"
    method = "generator"

    def __init__(self, start: date | None = None, end: date | None = None):
        from model import END_DATE, START_DATE

        self.start = start or START_DATE
        self.end = end or END_DATE

    def fetch(self):
        from model import weekly_dates

        out = []
        for item in ITEMS:
            for day in weekly_dates(self.start, self.end):
                out.append(
                    {
                        "item": item[0],
                        "date": day.isoformat(),
                        "price": price_at(day, item),
                        "method": self.method,
                    }
                )
        return out


# ---------------------------------------------------------------------------
class CSVSource(_BaseSource):
    """Read collected/manual/scraped prices from a CSV file.

    Header expected:  item,date,price[,method][,source]
    """

    name = "csv"
    method = "csv-import"

    def __init__(self, path: str):
        self.path = path

    def fetch(self):
        out = []
        with open(self.path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out.append(
                    {
                        "item": str(row["item"]).strip(),
                        "date": str(row["date"]).strip(),
                        "price": float(row["price"]),
                        "method": str(row.get("method") or "").strip() or self.method,
                    }
                )
        return out


# ---------------------------------------------------------------------------
class PBSWebSource(_BaseSource):
    """Scaffold for scraping the official Pakistan Bureau of Statistics.

    NOTE: requires (a) outbound network access and (b) permission to fetch the
    data — PBS publishes CSV/HTML releases. Wire your chosen endpoint into
    `fetch()` and return parsed rows. It is intentionally NOT invoked by
    default so the pipeline never fails offline.
    """

    name = "pbs-web"
    method = "html/csv scrape"

    def __init__(self, endpoint: str = ""):
        self.endpoint = endpoint

    def fetch(self):
        if not self.endpoint:
            raise NotImplementedError(
                "PBSWebSource needs an endpoint + network access + the "
                "publisher's permission. Configure endpoint to enable it."
            )
        # TODO: requests.get(self.endpoint) -> parse -> [{item,date,price,method}]
        return []
