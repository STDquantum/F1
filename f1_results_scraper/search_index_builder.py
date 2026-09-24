"""Build lightweight per-year search shards for the static results site."""
from __future__ import annotations

import json
from pathlib import Path


def build_search_index(by_year: dict[int, list[dict]], site_data: Path) -> tuple[int, int]:
    """Write compact search shards from race-result tables; return count and bytes."""
    output = site_data / "search_index"
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, int | str]] = []
    total_entries = 0
    total_bytes = 0

    for year, tables in sorted(by_year.items(), reverse=True):
        entries: list[dict[str, int | str]] = []
        seen: set[tuple[str, str]] = set()
        for table in tables:
            if table.get("section") != "races" or table.get("session") != "race-result":
                continue
            race = table.get("race") or {}
            race_name = str(table.get("title") or race.get("slug") or "")
            for row in table.get("rows", []):
                driver = str(row.get("Driver", "")).strip()
                if not driver:
                    continue
                url = str(table.get("url", ""))
                key = (url, driver)
                if key in seen:
                    continue
                seen.add(key)
                entries.append({
                    "y": int(year),
                    "g": race_name,
                    "d": driver,
                    "t": str(row.get("Team", "")).strip(),
                    "c": str(row.get("Chassis", "")).strip(),
                    "u": url,
                })

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
