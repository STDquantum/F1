#!/usr/bin/env python3
"""Crawl public Formula 1 Results pages and preserve every HTML table."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from urllib3.exceptions import InsecureRequestWarning

BASE = "https://www.formula1.com"
YEAR_RE = re.compile(r"/en/results/(\d{4})/")
RACE_RE = re.compile(r"/en/results/(\d{4})/races/(\d+)/([^/?#]+)")
# The specialized drivers/teams/awards crawlers handle the other tabs.
# Keeping this base crawler focused on races avoids probing invalid legacy
# section URLs and keeps expected 404s out of the failure report.
SECTIONS = ("races",)
USER_AGENT = "Mozilla/5.0 (compatible; f1-results-research/1.0; +https://www.formula1.com/)"


def existing_records(root: Path) -> list[dict[str, Any]]:
    split_dir = root.parent / "site_data"
    split_rows: list[dict[str, Any]] = []
    for path in sorted(split_dir.glob("[0-9][0-9][0-9][0-9].js")):
        text = path.read_text(encoding="utf-8")
        prefix = "window.__F1_YEAR_DATA__="
        if not text.startswith(prefix) or not text.endswith(";"):
            continue
        try:
            rows = json.loads(text[len(prefix):-1])
        except json.JSONDecodeError:
            continue
        split_rows.extend(row for row in rows if "url" in row and "table_index" in row)
    if split_rows:
        return split_rows

    page = root.parent / "index.html"
    if not page.exists():
        return []
    text = page.read_text(encoding="utf-8")
    start_marker = "window.__STATIC_RECORDS__="
    end_marker = ";window.__STATIC_FAILURES__="
    start = text.find(start_marker)
    if start < 0:
        return []
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end < 0:
        return []
    try:
        rows = json.loads(text[start:end])
    except json.JSONDecodeError:
        return []
    return [row for row in rows if "url" in row and "table_index" in row]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def absolute(base: str, href: str | None) -> str | None:
    if not href or href.startswith(("javascript:", "mailto:", "#")):
        return None
    return urljoin(base, href).split("#", 1)[0]


def allowed(url: str) -> bool:
    p = urlparse(url)
    return p.netloc in {"www.formula1.com", "formula1.com"}


class Crawler:
    def __init__(self, root: Path, delay: float, refresh: bool, verify_ssl: bool = True) -> None:
        self.root = root
        self.cache = root / "cache"
        self.pages = root / "pages"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.pages.mkdir(parents=True, exist_ok=True)
        self.delay = max(0.0, delay)
        self.refresh = refresh
        self.verify_ssl = verify_ssl
        self.last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})

    def _cache_path(self, url: str) -> Path:
        return self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".html")

    def get(self, url: str) -> str:
        path = self._cache_path(url)
        if path.exists() and not self.refresh:
            return path.read_text(encoding="utf-8")
        for attempt in range(1, 6):
            wait = self.delay - (time.time() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self.session.get(url, timeout=(20, 90), verify=self.verify_ssl)
                self.last_request = time.time()
                response.raise_for_status()
                text = response.text
                path.write_text(text, encoding="utf-8")
                return text
            except requests.HTTPError as exc:
                # A missing historical section/page is a stable condition;
                # retry only throttling and server-side failures.
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and 400 <= status < 500 and status != 429:
                    raise RuntimeError(f"HTTP {status}: {url}") from exc
                if attempt == 5:
                    raise RuntimeError(f"failed after 5 attempts: {url}: {exc}") from exc
                time.sleep(min(30, 2 ** attempt))
            except requests.RequestException as exc:
                if attempt == 5:
                    raise RuntimeError(f"failed after 5 attempts: {url}: {exc}") from exc
                time.sleep(min(30, 2 ** attempt))
        raise AssertionError("unreachable")


def links(soup: BeautifulSoup, base_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        u = absolute(base_url, a.get("href"))
        if u and allowed(u) and u not in seen:
            seen.add(u)
            found.append(u)
    return found


def extract_images(cell: Tag, page_url: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for img in cell.select("img[src], img[data-src]"):
        src = absolute(page_url, img.get("src") or img.get("data-src"))
        if src:
            parent_style = img.parent.get("style", "") if isinstance(img.parent, Tag) else ""
            result.append({"src": src, "alt": clean(img.get("alt", "")), "srcset": img.get("srcset", ""), "background": img.get("style", "") or parent_style})
    for svg in cell.select("svg"):
        title = svg.find("title")
        alt = clean(title.get_text(" ", strip=True)) if title else ""
        svg_markup = str(svg)
        # BeautifulSoup's HTML parser lowercases SVG's case-sensitive XML
        # names. Restore the names required by browsers before embedding it.
        for old, new in (("viewbox", "viewBox"), ("clippath", "clipPath"), ("fillrule", "fillRule"), ("cliprule", "clipRule"), ("strokewidth", "strokeWidth"), ("strokelinecap", "strokeLinecap"), ("strokelinejoin", "strokeLinejoin")):
            svg_markup = svg_markup.replace(old, new)
        encoded = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
        parent_style = svg.parent.get("style", "") if isinstance(svg.parent, Tag) else ""
        result.append({"src": f"data:image/svg+xml;base64,{encoded}", "alt": alt, "srcset": "", "background": parent_style})
    return result


def race_key(url: str) -> tuple[str, str, str] | None:
    m = RACE_RE.search(urlparse(url).path)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def table_record(table: Tag, page: dict[str, Any], index: int) -> dict[str, Any]:
    rows: list[list[str]] = []
    row_links: list[list[list[str]]] = []
    row_images: list[list[list[dict[str, str]]]] = []
    for tr in table.select("tr"):
        cells = tr.select(":scope > th, :scope > td")
        if not cells:
            continue
        values: list[str] = []
        for c in cells:
            value = c.get_text(" ", strip=True)
            for svg_title in c.select("svg title"):
                value = value.replace(svg_title.get_text(" ", strip=True), "")
            values.append(clean(value))
        rows.append(values)
        row_links.append([[absolute(page["url"], a.get("href")) for a in c.select("a[href]") if absolute(page["url"], a.get("href"))] for c in cells])
        row_images.append([extract_images(c, page["url"]) for c in cells])
    if not rows:
        return {**page, "table_index": index, "columns": [], "rows": []}
    header = rows[0]
    has_th = bool(table.select_one("tr > th"))
    if not has_th:
        header = [f"column_{i + 1}" for i in range(max(map(len, rows)))]
        data = rows
        data_links = row_links
        data_images = row_images
    else:
        data = rows[1:]
        data_links = row_links[1:]
        data_images = row_images[1:]
    width = max([len(header), *(len(r) for r in data)], default=len(header))
    header += [f"column_{i + 1}" for i in range(len(header), width)]
    output_rows: list[dict[str, Any]] = []
    for values, cell_links, cell_images in zip(data, data_links, data_images):
        values += [""] * (width - len(values))
        cell_links += [[]] * (width - len(cell_links))
        cell_images += [[]] * (width - len(cell_images))
        for i, name in enumerate(header):
            if name.strip().lower() in {"driver", "winner"}:
                values[i] = re.sub(r"\s+[A-Z]{3}$", "", values[i]).strip()
        item: dict[str, Any] = {header[i]: values[i] for i in range(width)}
        for i, urls in enumerate(cell_links):
            if urls:
                item[f"{header[i]}__links"] = urls
            if cell_images[i]:
                item[f"{header[i]}__images"] = cell_images[i]
        output_rows.append(item)
    return {**page, "table_index": index, "columns": header, "rows": output_rows}


def parse_tables(html: str, page: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    title = clean(soup.title.get_text(" ", strip=True)) if soup.title else ""
    visible = list(soup.stripped_strings)
    date_text = ""
    circuit = ""
    title_pos = next((i for i, value in enumerate(visible) if value == title), -1)
    if title_pos >= 0:
        date_pos = next((i for i in range(title_pos + 1, len(visible)) if re.search(r"\b\d{1,2}\s*-\s*\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\b", visible[i])), None)
        if date_pos is not None:
            date_text = visible[date_pos]
            circuit = visible[date_pos + 1] if date_pos + 1 < len(visible) else ""
    page = {**page, "title": title, "event_date": date_text, "circuit": circuit}
    tables = soup.select("table")
    return [table_record(table, page, i) for i, table in enumerate(tables)]


def page_meta(url: str, year: int, section: str, race: dict[str, str] | None = None, session: str | None = None, driver: dict[str, str] | None = None, team: dict[str, str] | None = None, award: dict[str, str] | None = None) -> dict[str, Any]:
    return {"year": year, "section": section, "race": race, "driver": driver, "team": team, "award": award, "session": session, "url": url}


def unique(seq: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(seq))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=1950)
    ap.add_argument("--end-year", type=int, default=None)
    ap.add_argument("--limit-races", type=int, default=None)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--insecure", action="store_true", help="关闭 TLS 证书校验；仅在本机代理证书导致连接失败时使用")
    ap.add_argument("--output", type=Path, default=Path("data"))
    args = ap.parse_args()
    end_year = args.end_year or time.gmtime().tm_year
    if args.start_year > end_year:
        ap.error("--start-year must not exceed --end-year")
    if args.insecure:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    crawler = Crawler(args.output, args.delay, args.refresh, verify_ssl=not args.insecure)
    records_path = args.output / "records.jsonl"
    failures_path = args.output / "failures.jsonl"
    if not records_path.exists():
        seed = existing_records(args.output)
        if seed:
            records_path.parent.mkdir(parents=True, exist_ok=True)
            records_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in seed), encoding="utf-8")
    completed: set[str] = set()
    if records_path.exists() and not args.refresh:
        for line in records_path.read_text(encoding="utf-8").splitlines():
            try:
                completed.add(json.loads(line)["url"] + "#" + str(json.loads(line)["table_index"]))
            except (ValueError, KeyError):
                pass
    failures = failures_path.open("a", encoding="utf-8")
    with records_path.open("a", encoding="utf-8") as out:
        for year in range(args.start_year, end_year + 1):
            index_url = f"{BASE}/en/results/{year}/races"
            try:
                html = crawler.get(index_url)
            except RuntimeError as exc:
                failures.write(json.dumps({"url": index_url, "error": str(exc)}, ensure_ascii=False) + "\n")
                continue
            soup = BeautifulSoup(html, "lxml")
            season_urls = [f"{BASE}/en/results/{year}/{section}" for section in SECTIONS]
            race_urls = []
            for u in links(soup, index_url):
                key = race_key(u)
                # Current pages link directly to .../slug/race-result; some
                # older layouts may expose the six-part race landing page.
                parts = urlparse(u).path.strip("/").split("/")
                if key and key[0] == str(year) and (
                    len(parts) == 6 or (len(parts) == 7 and parts[-1] == "race-result")
                ):
                    race_urls.append(u.rstrip("/"))
            race_urls = unique(race_urls)
            if args.limit_races is not None:
                race_urls = race_urls[:args.limit_races]
            targets: list[tuple[str, dict[str, Any]]] = [(u, page_meta(u, year, section)) for section, u in zip(SECTIONS, season_urls)]
            for race_url in race_urls:
                key = race_key(race_url)
                assert key
                race = {"race_id": key[1], "slug": key[2], "url": race_url}
                try:
                    race_html = crawler.get(race_url)
                except RuntimeError as exc:
                    failures.write(json.dumps({"url": race_url, "error": str(exc)}, ensure_ascii=False) + "\n")
                    continue
                race_soup = BeautifulSoup(race_html, "lxml")
                detail_urls = []
                for u in links(race_soup, race_url):
                    if f"/en/results/{year}/races/{key[1]}/{key[2]}/" in u:
                        detail_urls.append(u.rstrip("/"))
                targets.append((race_url, page_meta(race_url, year, "races", race, "race-result")))
                for u in unique(detail_urls):
                    session = u.rstrip("/").rsplit("/", 1)[-1]
                    targets.append((u, page_meta(u, year, "races", race, session)))
            for url, meta in unique_targets(targets):
                try:
                    page_html = crawler.get(url)
                    parsed = parse_tables(page_html, meta)
                    (crawler.pages / (hashlib.sha256(url.encode()).hexdigest() + ".json")).write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                    for record in parsed:
                        marker = record["url"] + "#" + str(record["table_index"])
                        if marker not in completed or args.refresh:
                            out.write(json.dumps(record, ensure_ascii=False) + "\n")
                            out.flush()
                except (RuntimeError, OSError, ValueError) as exc:
                    failures.write(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False) + "\n")
    failures.close()
    print(f"完成。数据: {records_path.resolve()}；失败记录: {failures_path.resolve()}")
    return 0


def unique_targets(targets: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    seen: set[str] = set()
    result = []
    for url, meta in targets:
        if url not in seen:
            seen.add(url)
            result.append((url, meta))
    return result


if __name__ == "__main__":
    sys.exit(main())
