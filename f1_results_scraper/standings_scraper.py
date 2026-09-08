#!/usr/bin/env python3
"""Download yearly Drivers, Teams, and Awards tables."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scraper import BASE, Crawler, existing_records, links, page_meta, parse_tables, unique


CONFIG = {
    "drivers": {
        "index": "drivers",
        "pattern": re.compile(r"/en/results/(\d{4})/drivers/([^/]+)/([^/?#]+)$"),
        "meta": lambda year, url, match: page_meta(
            url, year, "drivers", session="driver-detail",
            driver={"driver_id": match.group(2), "slug": match.group(3), "url": url},
        ),
    },
    "teams": {
        "index": "team",
        "pattern": re.compile(r"/en/results/(\d{4})/team/([^/?#]+)$"),
        "meta": lambda year, url, match: page_meta(
            url, year, "teams", session="team-detail",
            team={"slug": match.group(2), "url": url},
        ),
    },
}
AWARDS = {
    "fastest-laps": "fastest lap",
    "pole-positions": "pole position",
    "driver-of-the-day": "driver of the day",
    "fastest-pit-stops": "fastest pit stop",
}


def detail_match(url: str, kind: str):
    return CONFIG[kind]["pattern"].search(urlparse(url).path.rstrip("/"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=1950)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--output", type=Path, default=Path("data"))
    args = ap.parse_args()

    crawler = Crawler(args.output, args.delay, args.refresh, verify_ssl=not args.insecure)
    records_path = args.output / "records.jsonl"
    failures_path = args.output / "failures.jsonl"
    records: dict[str, dict] = {}
    if records_path.exists():
        for line in records_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                records[row["url"] + "#" + str(row["table_index"])] = row
            except (ValueError, KeyError, TypeError):
                pass
    else:
        records = {row["url"] + "#" + str(row["table_index"]): row for row in existing_records(args.output)}

    failures = failures_path.open("a", encoding="utf-8")
    try:
        for year in range(args.start_year, args.end_year + 1):
            for kind, config in CONFIG.items():
                index_url = f"{BASE}/en/results/{year}/{config['index']}"
                targets = [(index_url, page_meta(index_url, year, kind))]
                try:
                    index_html = crawler.get(index_url)
                    soup = BeautifulSoup(index_html, "lxml")
                    details = unique(
                        u.rstrip("/") for u in links(soup, index_url)
                        if (match := detail_match(u, kind)) and match.group(1) == str(year)
                    )
                    for url in details:
                        match = detail_match(url, kind)
                        targets.append((url, config["meta"](year, url, match)))
                    print(f"{year} {kind}: {len(details)} detail pages", flush=True)
                except RuntimeError as exc:
                    if "404" not in str(exc):
                        failures.write(json.dumps({"url": index_url, "error": str(exc)}, ensure_ascii=False) + "\n")
                    continue

                for url, meta in targets:
                    try:
                        parsed = parse_tables(crawler.get(url), meta)
                        page_file = args.output / "pages" / (hashlib.sha256(url.encode()).hexdigest() + ".json")
                        page_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                        for record in parsed:
                            records[record["url"] + "#" + str(record["table_index"])] = record
                    except (RuntimeError, OSError, ValueError) as exc:
                        if "404" not in str(exc):
                            failures.write(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False) + "\n")

            for slug, marker in AWARDS.items():
                url = f"{BASE}/en/results/{year}/awards/{slug}"
                meta = page_meta(url, year, "awards", session="award-results", award={"slug": slug, "url": url})
                try:
                    parsed = parse_tables(crawler.get(url), meta)
                    # Historical missing award pages can fall back to another
                    # table instead of returning 404; accept only the intended title.
                    if not parsed or marker not in str(parsed[0].get("title", "")).lower():
                        continue
                    page_file = args.output / "pages" / (hashlib.sha256(url.encode()).hexdigest() + ".json")
                    page_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                    for record in parsed:
                        records[record["url"] + "#" + str(record["table_index"])] = record
                except (RuntimeError, OSError, ValueError) as exc:
                    if "404" not in str(exc):
                        failures.write(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False) + "\n")
    finally:
        failures.close()

    with records_path.open("w", encoding="utf-8") as out:
        for record in sorted(records.values(), key=lambda x: (int(x.get("year", 0)), x.get("url", ""), int(x.get("table_index", 0)))):
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"完成：{records_path.resolve()}，共 {len(records)} 张表。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
