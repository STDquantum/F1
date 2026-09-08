"""Build a small static shell and one on-demand data file per season."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
data = ROOT / "data"
records = [json.loads(x) for x in (data / "records.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
failures_path = data / "failures.jsonl"
failures = [json.loads(x) for x in failures_path.read_text(encoding="utf-8").splitlines() if x.strip()] if failures_path.exists() else []
failures = [x for x in failures if "404" not in x.get("error", "")]

by_year: dict[int, list[dict]] = defaultdict(list)
for record in records:
    by_year[int(record["year"])].append(record)

site_data = ROOT / "site_data"
site_data.mkdir(exist_ok=True)

def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

year_counts = {}
for year in sorted(by_year):
    rows = by_year[year]
    (site_data / f"{year}.js").write_text("window.__F1_YEAR_DATA__=" + compact(rows) + ";", encoding="utf-8")
    year_counts[str(year)] = {
        "tables": len(rows),
        "pages": len({x.get("url") for x in rows}),
        "sections": {section: sum(x.get("section") == section for x in rows) for section in ("races", "drivers", "teams", "awards")},
    }

manifest = {"years": sorted(by_year, reverse=True), "total_tables": len(records), "total_pages": len({x.get("url") for x in records}), "failures": len(failures), "year_counts": year_counts}
(site_data / "index.js").write_text("window.__F1_MANIFEST__=" + compact(manifest) + ";", encoding="utf-8")

template = (ROOT / "template.html").read_text(encoding="utf-8")
new_index = ROOT / "index.new.html"
new_index.write_text(template, encoding="utf-8")
new_index.replace(ROOT / "index.html")
print(f"已生成 {ROOT / 'index.html'}，拆分为 {len(by_year)} 个年份数据文件，共 {len(records)} 张表格、{len(failures)} 条失败记录。")
