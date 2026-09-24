"""Build lightweight per-year search shards for the static results site."""
from __future__ import annotations

import json
import re
from pathlib import Path


def build_search_index(by_year: dict[int, list[dict]], site_data: Path) -> tuple[int, int]:
    """Write compact per-year GP/driver search shards from every race session."""
    output = site_data / "search_index"
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, int | str]] = []
    total_entries = 0
    total_bytes = 0

    for year, tables in sorted(by_year.items(), reverse=True):
        entries: list[dict[str, int | str]] = []
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for table in tables:
            if table.get("section") != "races" or not table.get("race"):
                continue
            if "Driver" not in table.get("columns", []):
                continue
            race = table.get("race") or {}
            race_name = clean_race_name(str(table.get("title") or race.get("slug") or ""))
            url = str(table.get("url", ""))
            session = str(table.get("session") or "")
            session_label = session_display_name(url, session)
            for row in table.get("rows", []):
                driver = str(row.get("Driver", "")).strip()
                if not driver:
                    continue
                key = (str(race.get("race_id") or url), driver)
                entry = grouped.setdefault(key, {
                    "y": int(year), "g": race_name, "d": driver,
                    "t": "", "c": "", "u": url, "s": set(),
                })
                sessions = entry["s"]
                assert isinstance(sessions, set)
                sessions.add(session_label)
                # Use the race result as the default table when available.
                if session == "race-result":
                    entry["u"] = url
                    entry["g"] = race_name
                if row.get("Team") and (not entry["t"] or session == "race-result"):
                    entry["t"] = str(row.get("Team", "")).strip()
                if row.get("Chassis"):
                    entry["c"] = str(row.get("Chassis", "")).strip()

        session_order = {
            name: index for index, name in enumerate((
                "Race Result", "Sprint Race", "Sprint Qualifying", "Qualifying",
                "Overall Qualifying", "Qualifying 1", "Qualifying 2", "Qualifying 3",
                "Practice 1", "Practice 2", "Practice 3", "Practice 4", "Warm Up",
                "Starting Grid", "Sprint Grid", "Fastest Laps", "Pit Stop Summary",
            ))
        }
        entries = []
        for entry in grouped.values():
            sessions = entry.pop("s")
            assert isinstance(sessions, set)
            entry["s"] = " · ".join(sorted(sessions, key=lambda name: (session_order.get(name, 99), name)))
            entries.append(entry)  # type: ignore[arg-type]

        target = output / f"{year}.js"
        payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        target.write_text(
            f"window.__F1_SEARCH_SHARDS__=window.__F1_SEARCH_SHARDS__||{{}};"
            f"window.__F1_SEARCH_SHARDS__[{year}]={payload};",
            encoding="utf-8",
        )
        shard_bytes = target.stat().st_size
        total_entries += len(entries)
        total_bytes += shard_bytes
        manifest.append({
            "year": int(year),
            "file": f"site_data/search_index/{year}.js",
            "entries": len(entries),
            "bytes": shard_bytes,
        })

    manifest_path = output / "index.js"
    manifest_payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    manifest_path.write_text(f"window.__F1_SEARCH_MANIFEST__={manifest_payload};", encoding="utf-8")
    total_bytes += manifest_path.stat().st_size
    return total_entries, total_bytes


def session_display_name(url: str, session: str) -> str:
    """Convert official result URL/session keys to concise labels."""
    path = url.rstrip("/").lower()
    if path.endswith("/race-result"):
        return "Race Result"
    if path.endswith("/sprint-results"):
        return "Sprint Race"
    if path.endswith("/sprint-qualifying"):
        return "Sprint Qualifying"
    if path.endswith("/sprint-grid"):
        return "Sprint Grid"
    if path.endswith("/starting-grid"):
        return "Starting Grid"
    if path.endswith("/fastest-laps"):
        return "Fastest Laps"
    if path.endswith("/pit-stop-summary"):
        return "Pit Stop Summary"
    if "/practice/" in path:
        number = path.rsplit("/", 1)[-1]
        return "Warm Up" if number == "0" else f"Practice {number}"
    if "/qualifying/" in path:
        number = path.rsplit("/", 1)[-1]
        return "Overall Qualifying" if number == "0" else f"Qualifying {number}"
    if path.endswith("/qualifying"):
        return "Qualifying"
    return session.replace("-", " ").title() or "Race Session"


def clean_race_name(title: str) -> str:
    """Remove the session suffix from Formula1.com event page titles."""
    return re.sub(
        r"\s+-\s+(?:RACE RESULT|PRACTICE \d|WARM UP|QUALIFYING(?: \d)?|"
        r"STARTING GRID|FASTEST LAPS|PIT STOP SUMMARY|SPRINT(?: GRID| QUALIFYING| RESULTS?))$",
        "",
        title,
        flags=re.IGNORECASE,
    )


def build_from_existing_site_data(site_data: Path) -> tuple[int, int]:
    """Rebuild search shards from already-published yearly JS files."""
    by_year: dict[int, list[dict]] = {}
    prefix = "window.__F1_YEAR_DATA__="
    for path in site_data.glob("[0-9][0-9][0-9][0-9].js"):
        text = path.read_text(encoding="utf-8").strip()
        if not text.startswith(prefix) or not text.endswith(";"):
            continue
        by_year[int(path.stem)] = json.loads(text[len(prefix):-1])
    return build_search_index(by_year, site_data)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    count, size = build_from_existing_site_data(root / "site_data")
    print(f"Built search index: {count:,} entries, {size:,} bytes.")
