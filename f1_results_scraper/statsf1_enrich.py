#!/usr/bin/env python3
"""Add StatsF1 chassis and eligible race-entry notes to static race results.

StatsF1's next-event link (>>) provides a chronological route through the
championship. Routine runs start at the previous season's saved final event,
then follow links through the requested season. Pages are cached and fetched
politely so an interrupted crawl can be resumed without repeating requests.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "site_data"
START = "https://www.statsf1.com/en/1950/grande-bretagne/engages.aspx"
PROGRESS = DATA / "statsf1_progress.json"
PREFIX = "window.__F1_YEAR_DATA__="
SKIP_NOTE = re.compile(r"^(?:substitute(?:,\s*(?:reserve|third) driver)?|reserve driver|third driver)$", re.I)
EVENT_SLUG_ALIASES = {
    "abou-dhabi": "abu-dhabi", "afrique-du-sud": "south-africa",
    "allemagne": "germany", "arabie-saoudite": "saudi-arabia",
    "argentine": "argentina", "autriche": "austria", "azerbaidjan": "azerbaijan",
    "bahrein": "bahrain", "belgique": "belgium", "bresil": "brazil",
    "chine": "china", "emilie-romagne": "emilia-romagna", "espagne": "spain",
    "etats-unis": "united-states", "etats-unis-ouest": "usa-west",
    "grande-bretagne": "great-britain", "hongrie": "hungary", "italie": "italy",
    "japon": "japan", "malaisie": "malaysia", "mexique": "mexico",
    "pays-bas": "netherlands", "russie": "russia", "saint-marin": "san-marino",
    "singapour": "singapore",
    "suisse": "switzerland", "turquie": "turkey",
}
DRIVER_ALIASES = {
    "nino farina": {"giuseppe farina"},
    "manny ayulo": {"manuel ayulo"},
    "anthony joseph foyt": {"a j foyt", "aj foyt"},
    "toulo de graffenried": {"emmanuel de graffenried"},
    "paco godia": {"francisco godia", "francisco godia sales"},
    "kenneth mcalpine": {"ken mcalpine"},
    "adolfo schewelm cruz": {"adolfo schwelm cruz"},
    "timmy mayer": {"tim mayer"},
    "giacomo russo": {"geki russo", "geki"},
    "jyrki jarvilehto": {"jj lehto", "j j lehto", "jyrki lehto"},
    "massimiliano papis": {"max papis"},
    "toranosuke takagi": {"tora takagi"},
    "nelson piquet": {"nelsinho piquet"},
    "tom belso": {"tom bels"},
    "ingo hoffman": {"ingo hoffmann"},
    "gianmaria bruni": {"gimmi bruni", "gian maria bruni"},
}


def normalize_name(value: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\b[A-Z]{3}\b", " ", value)
    value = "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def note_mentions_driver(note: str, driver: str) -> bool:
    """Match full or initial-plus-surname references in short race footnotes."""
    name = normalize_name(driver).split()
    words = normalize_name(note).split()
    if not name:
        return False
    surname = name[-1]
    for index, word in enumerate(words):
        if word != surname:
            continue
        preceding = words[max(0, index - len(name) - 1):index]
        if len(name) == 1 or name[0] in preceding or name[0][0] in preceding:
            return True
    return False


def should_keep_note(note: str, entrants: set[str], result_drivers: set[str]) -> bool:
    """Drop a note only when it refers to an entrant absent from the result."""
    result_mention = any(note_mentions_driver(note, name) for name in result_drivers)
    absent_entrant_mention = any(
        note_mentions_driver(note, entrant)
        and not any(note_mentions_driver(note, result) for result in result_drivers)
        for entrant in entrants
    )
    return result_mention or not absent_entrant_mention


def parse_event(html: str, url: str) -> tuple[int, str, dict[str, str], list[str], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    match = re.search(r"/en/(\d{4})/([^/]+)/engages\.aspx", urlparse(url).path)
    if not match:
        raise ValueError(f"Not an entrants URL: {url}")
    year, slug = int(match.group(1)), match.group(2)
    table = next((t for t in soup.find_all("table") if "Chassis" in t.get_text(" ", strip=True)), None)
    if table is None:
        return year, slug, {}, [], None
    trs = table.find_all("tr")
    header_cells = trs[0].find_all(["th", "td"])
    chassis_col = driver_col = None
    offset = 0
    for cell in header_cells:
        label = " ".join(cell.stripped_strings).lower()
        span = int(cell.get("colspan", 1))
        if label == "driver":
            driver_col = offset
        elif label == "chassis":
            # StatsF1 splits constructor and model into two cells under a
            # colspan=2 Chassis header; the model itself is the second cell.
            chassis_col = offset + span - 1
        offset += span
    chassis: dict[str, str] = {}
    if chassis_col is not None and driver_col is not None:
        for tr in trs[1:]:
            cells = tr.find_all(["th", "td"])
            if len(cells) <= max(chassis_col, driver_col):
                continue
            driver = " ".join(cells[driver_col].stripped_strings).rstrip("* ")
            model = " ".join(cells[chassis_col].stripped_strings)
            if driver and model:
                chassis[normalize_name(driver)] = model
    # StatsF1 prints notes as marked text below the entrants table. Keep these
    # until the race-result roster is known so notes about a replacement who
    # actually raced can be retained.
    notes: list[str] = []
    note_nodes = table.find_all_next(["li", "p", "div"])
    for node in note_nodes:
        classes = " ".join(node.get("class", []))
        is_listinfo = node.name == "div" and "listinfo" in classes.lower()
        if node.name == "div" and not is_listinfo:
            continue
        if node.name in {"li", "p"} and node.find_parent(class_=re.compile(r"listinfo", re.I)):
            continue
        if node.find("a"):
            continue
        note = " ".join(node.stripped_strings).strip(" •*†‡\t")
        marked = bool(re.match(r"^[*†‡]\s*\S", " ".join(node.stripped_strings)))
        note_container = is_listinfo or bool(re.search(r"note|legend|foot", classes, re.I))
        if (marked or note_container or node.name == "li") and note and not SKIP_NOTE.fullmatch(note) and len(note) < 500 and note not in notes:
            notes.append(note)
    next_url = None
    for a in soup.find_all("a", href=True):
        label = " ".join(a.stripped_strings).strip()
        href = urljoin(url, a["href"])
        if label in {">>", "Next", "Next Grand Prix"} and "/engages.aspx" in href:
            next_url = href
            break
    return year, slug, chassis, notes, next_url


def load_records(years: set[int]) -> tuple[list[dict], bool]:
    records_path = ROOT / "data" / "records.jsonl"
    if records_path.exists():
        records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return records, True
    result: list[dict] = []
    for year in sorted(years):
        path = DATA / f"{year}.js"
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        if raw.startswith(PREFIX) and raw.endswith(";"):
            result.extend(json.loads(raw[len(PREFIX):-1]))
    return result, False


def write_year_file(year: int, rows: list[dict]) -> None:
    path = DATA / f"{year}.js"
    temp = DATA / f"{year}.js.tmp"
    payload = PREFIX + json.dumps(rows, ensure_ascii=False, indent=2) + ";"
    last_error: OSError | None = None
    for attempt in range(1, 6):
        try:
            temp.write_text(payload, encoding="utf-8")
            temp.replace(path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25 * attempt)
    assert last_error is not None
    raise last_error


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-url", default=None, help="Override the StatsF1 page to start from")
    ap.add_argument("--start-year", type=int, default=None, help="Start a one-time historical backfill from this season")
    ap.add_argument("--end-year", type=int, default=None, help="Season to update; defaults to current UTC year")
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()
    end_year = args.end_year or time.gmtime().tm_year
    cache = ROOT / "data" / "statsf1_pages"
    cache.mkdir(parents=True, exist_ok=True)
    result_year = args.start_year or end_year
    records, from_jsonl = load_records(set(range(result_year, end_year + 1)))
    progress = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {"year_last": {}}
    last_year = progress.setdefault("year_last", {})
    if args.start_url:
        url = args.start_url
    elif args.start_year is not None:
        if args.start_year <= 1950:
            url = START
        else:
            previous = last_year.get(str(args.start_year - 1), {})
            url = previous.get("url") or f"https://www.statsf1.com/en/{args.start_year - 1}/abou-dhabi/engages.aspx"
    else:
        # Bootstrap the marker on the first current-season run. Afterward the
        # exact previous-season final page is retained in progress metadata.
        previous = last_year.get(str(end_year - 1), {})
        url = previous.get("url") or f"https://www.statsf1.com/en/{end_year - 1}/abou-dhabi/engages.aspx"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.statsf1.com/",
    })
    seen: set[str] = set()
    count = 0
    race_cursor: dict[int, int] = {}
    assigned_races: dict[int, set[int]] = {}
    while url and url not in seen:
        seen.add(url)
        path = cache / (re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(url).path).strip("_") + ".html")
        if path.exists():
            html = path.read_text(encoding="utf-8")
        else:
            response = session.get(url, timeout=45)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            html = response.text
            path.write_text(html, encoding="utf-8")
            time.sleep(max(0.0, args.delay))
        year, slug, chassis, notes, next_url = parse_event(html, url)
        if year > end_year:
            break
        if not next_url and year < end_year:
            raise RuntimeError(f"StatsF1 next-event link not found; refusing to save a partial crawl: {url}")
        print(f"Visited {year} {slug}: {len(chassis)} chassis entries, {len(notes)} eligible notes", flush=True)
        # Save the prior season's end marker and follow its next link, but do
        # not reprocess prior-season result data during a routine action run.
        last_year[str(year)] = {"url": url, "next_url": next_url}
        first_result_year = result_year
        if year < first_result_year:
            url = next_url
            progress["last_event_url"] = url
            PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            continue
        candidates = [r for r in records if int(r.get("year", 0)) == year and r.get("session") == "race-result"]
        assigned = assigned_races.setdefault(year, set())
        position = race_cursor.get(year, 0)
        while position in assigned:
            position += 1
        canonical_slug = EVENT_SLUG_ALIASES.get(slug.lower(), slug.lower())
        # Formula1.com labels the 2023 São Paulo round as Brazil, while
        # StatsF1 uses the circuit city for that season's entrants page.
        if year == 2023 and slug.lower() == "sao-paulo":
            canonical_slug = "brazil"
        exact_index = next((i for i, r in enumerate(candidates)
                            if (r.get("race") or {}).get("slug", "").lower() == canonical_slug), None)
        race = candidates[exact_index] if exact_index is not None else None
        if exact_index is not None:
            # Some years insert a renamed round (for example Europe) out of
            # order in Formula1.com's list. Exact matches claim their row but
            # only advance the fallback cursor when they occur at that cursor.
            assigned.add(exact_index)
            if exact_index == position:
                position += 1
                while position in assigned:
                    position += 1
            race_cursor[year] = position
        else:
            if position < len(candidates):
                race = candidates[position]
                assigned.add(position)
                race_cursor[year] = position + 1
        if race:
            driver_col = next((c for c in race.get("columns", []) if c.lower().startswith("driver")), None)
            source_notes = list(notes)
            eligible_notes = source_notes
            if driver_col and source_notes:
                result_drivers = {
                    normalize_name(row.get(driver_col, ""))
                    for row in race.get("rows", []) if row.get(driver_col)
                }
                eligible_notes = [
                    note for note in source_notes
                    if should_keep_note(note, set(chassis), result_drivers)
                ]
            if driver_col and chassis:
                if "Chassis" not in race["columns"]:
                    insert_at = race["columns"].index("Team") + 1 if "Team" in race["columns"] else race["columns"].index(driver_col) + 1
                    race["columns"].insert(insert_at, "Chassis")
                for row in race.get("rows", []):
                    name = normalize_name(row.get(driver_col, ""))
                    model = chassis.get(name)
                    # Account for common historical name variants and StatsF1
                    # entries that reverse the given-name/surname order.
                    if not model:
                        aliases = DRIVER_ALIASES.get(name, set())
                        matches = {k for k in chassis if k in aliases}
                        tokens = set(name.split())
                        if len(tokens) >= 2:
                            matches.update(k for k in chassis if tokens == set(k.split())
                                           or (tokens.issubset(set(k.split())) and len(set(k.split()) - tokens) == 1)
                                           or (set(k.split()).issubset(tokens) and len(tokens - set(k.split())) == 1))
                        model_keys = matches
                        model_values = {chassis[k] for k in model_keys}
                        model = next(iter(model_values)) if len(model_values) == 1 else ""
                    row["Chassis"] = model or ""
                count += 1
            elif driver_col and "Chassis" in race.get("columns", []):
                # Remove an empty placeholder column if an upcoming event had
                # no entrant/chassis data on the previous run.
                if all(not row.get("Chassis") for row in race.get("rows", [])):
                    race["columns"].remove("Chassis")
                    for row in race.get("rows", []):
                        row.pop("Chassis", None)
            old = race.get("notes", [])
            rejected_notes = set(source_notes) - set(eligible_notes)
            old = [note for note in old if note not in rejected_notes]
            race["notes"] = list(dict.fromkeys([*old, *eligible_notes]))
        url = next_url
        progress["last_event_url"] = url
        PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if from_jsonl:
        records_path = ROOT / "data" / "records.jsonl"
        records_path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    else:
        by_year: dict[int, list[dict]] = {}
        for record in records:
            by_year.setdefault(int(record["year"]), []).append(record)
        for year, rows in by_year.items():
            write_year_file(year, rows)
    print(f"Updated {count} race-result tables through {end_year}.", flush=True)


if __name__ == "__main__":
    main()
