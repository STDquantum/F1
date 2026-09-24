"""Build a small static shell and one on-demand data file per season."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from search_index_builder import build_search_index

ROOT = Path(__file__).resolve().parent
data = ROOT / "data"
site_data = ROOT / "site_data"
YEAR_DATA_PREFIX = "window.__F1_YEAR_DATA__="


def existing_notes() -> dict[tuple[str, int], list[str]]:
    """Keep notes already captured when an older local cache lacks them."""
    notes_by_table: dict[tuple[str, int], list[str]] = {}
    for path in sorted(site_data.glob("[0-9][0-9][0-9][0-9].js")):
        text = path.read_text(encoding="utf-8").strip()
        if not text.startswith(YEAR_DATA_PREFIX) or not text.endswith(";"):
            continue
        try:
            tables = json.loads(text[len(YEAR_DATA_PREFIX) : -1])
        except json.JSONDecodeError:
            continue
        for table in tables:
            if "notes" in table:
                notes_by_table[(table["url"], int(table["table_index"]))] = table["notes"]
    return notes_by_table


def existing_event_info() -> dict[str, tuple[str, str]]:
    """Keep event metadata already backfilled into committed static files."""
    info_by_race: dict[str, tuple[str, str]] = {}
    for path in sorted(site_data.glob("[0-9][0-9][0-9][0-9].js")):
        text = path.read_text(encoding="utf-8").strip()
        if not text.startswith(YEAR_DATA_PREFIX) or not text.endswith(";"):
            continue
        try:
            tables = json.loads(text[len(YEAR_DATA_PREFIX) : -1])
        except json.JSONDecodeError:
            continue
        for table in tables:
            race = table.get("race")
            event_date = table.get("event_date", "")
            circuit = table.get("circuit", "")
            if race and event_date:
                info_by_race[str(race["race_id"])] = (event_date, circuit)
    return info_by_race


def existing_chassis() -> dict[str, dict[str, str]]:
    """Keep StatsF1 chassis enrichments when Formula1.com data is rebuilt."""
    by_url: dict[str, dict[str, str]] = {}
    for path in sorted(site_data.glob("[0-9][0-9][0-9][0-9].js")):
        text = path.read_text(encoding="utf-8").strip()
        if not text.startswith(YEAR_DATA_PREFIX) or not text.endswith(";"):
            continue
        try:
            tables = json.loads(text[len(YEAR_DATA_PREFIX) : -1])
        except json.JSONDecodeError:
            continue
        for table in tables:
            if table.get("session") != "race-result" or "Chassis" not in table.get("columns", []):
                continue
            by_url[table["url"]] = {
                str(row.get("Driver", "")): str(row.get("Chassis", ""))
                for row in table.get("rows", []) if row.get("Chassis")
            }
    return by_url


preserved_notes = existing_notes()
preserved_event_info = existing_event_info()
preserved_chassis = existing_chassis()
records_path = data / "records.jsonl"
if records_path.exists():
    records = [json.loads(x) for x in records_path.read_text(encoding="utf-8").splitlines() if x.strip()]
else:
    # A static-only checkout can still be rebuilt from the already-published
    # yearly files when the scraper's local JSONL cache is unavailable.
    records = []
    for path in sorted(site_data.glob("[0-9][0-9][0-9][0-9].js")):
        text = path.read_text(encoding="utf-8").strip()
        if text.startswith(YEAR_DATA_PREFIX) and text.endswith(";"):
            records.extend(json.loads(text[len(YEAR_DATA_PREFIX) : -1]))
    print(f"未找到 {records_path}，改用 {len(records)} 张现有静态表格重建。")
# A refreshed URL supersedes its earlier crawl.  This also repairs old output
# files that may already contain both an initial placeholder and later result.
latest_records: dict[tuple[str, int], dict] = {}
for record in records:
    latest_records[(record["url"], int(record["table_index"]))] = record
for key, record in latest_records.items():
    if key in preserved_notes and (
        "notes" not in record or (not record.get("notes") and preserved_notes[key])
    ):
        record["notes"] = preserved_notes[key]
    race = record.get("race")
    if race and not record.get("event_date") and str(race["race_id"]) in preserved_event_info:
        record["event_date"], record["circuit"] = preserved_event_info[str(race["race_id"])]
    chassis_by_driver = preserved_chassis.get(record.get("url", ""), {})
    if record.get("session") == "race-result" and chassis_by_driver:
        if "Chassis" not in record.get("columns", []):
            position = record["columns"].index("Team") + 1 if "Team" in record["columns"] else len(record["columns"])
            record["columns"].insert(position, "Chassis")
        for row in record.get("rows", []):
            row.setdefault("Chassis", chassis_by_driver.get(str(row.get("Driver", "")), ""))
records = list(latest_records.values())
failures_path = data / "failures.jsonl"
failures = [json.loads(x) for x in failures_path.read_text(encoding="utf-8").splitlines() if x.strip()] if failures_path.exists() else []
failures = [x for x in failures if "404" not in x.get("error", "")]

by_year: dict[int, list[dict]] = defaultdict(list)
for record in records:
    by_year[int(record["year"])].append(record)

site_data.mkdir(exist_ok=True)

def formatted(value: object) -> str:
    """Serialize generated browser data in a review-friendly layout."""
    return json.dumps(value, ensure_ascii=False, indent=2)

year_counts = {}
for year in sorted(by_year):
    rows = by_year[year]
    (site_data / f"{year}.js").write_text("window.__F1_YEAR_DATA__=" + formatted(rows) + ";", encoding="utf-8")
    year_counts[str(year)] = {
        "tables": len(rows),
        "pages": len({x.get("url") for x in rows}),
        "sections": {section: sum(x.get("section") == section for x in rows) for section in ("races", "drivers", "teams", "awards")},
    }

manifest = {"years": sorted(by_year, reverse=True), "total_tables": len(records), "total_pages": len({x.get("url") for x in records}), "failures": len(failures), "year_counts": year_counts}
(site_data / "index.js").write_text("window.__F1_MANIFEST__=" + formatted(manifest) + ";", encoding="utf-8")
search_entries, search_bytes = build_search_index(by_year, site_data)

template = (ROOT / "template.html").read_text(encoding="utf-8")
new_index = ROOT / "index.new.html"
new_index.write_text(template, encoding="utf-8")
new_index.replace(ROOT / "index.html")
print(f"已生成 {ROOT / 'index.html'}，拆分为 {len(by_year)} 个年份数据文件，共 {len(records)} 张表格、{len(failures)} 条失败记录；搜索索引 {search_entries:,} 条、{search_bytes:,} 字节。")
