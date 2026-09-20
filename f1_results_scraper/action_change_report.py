#!/usr/bin/env python3
"""Summarize the tables that changed most during an Actions data refresh."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


JS_PREFIX = "window.__F1_YEAR_DATA__="


@dataclass(frozen=True)
class TableChange:
    title: str
    kind: str
    changed: int
    modified: int
    added: int
    removed: int
    old_rows: int
    new_rows: int


def load_tables(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith(JS_PREFIX):
        text = text[len(JS_PREFIX) :]
        if text.endswith(";"):
            text = text[:-1]
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of tables in {path}")
    return data


def table_key(table: dict[str, Any]) -> str:
    return f"{table.get('url', '')}#{table.get('table_index', 0)}"


def visible_row(table: dict[str, Any], row: Any) -> str:
    if not isinstance(row, dict):
        return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    columns = table.get("columns")
    if isinstance(columns, list) and columns:
        value = [row.get(str(column), "") for column in columns]
    else:
        value = {
            key: item
            for key, item in row.items()
            if not key.endswith("__links") and not key.endswith("__images")
        }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def row_counter(table: dict[str, Any]) -> Counter[str]:
    return Counter(visible_row(table, row) for row in table.get("rows", []))


def table_title(table: dict[str, Any], key: str) -> str:
    title = str(table.get("title") or "").strip()
    session = str(table.get("session") or "").strip()
    if title:
        return title
    if session:
        return session.replace("-", " ").title()
    return key.split("#", 1)[0] or "Untitled table"


def compare_tables(before: Iterable[dict[str, Any]], after: Iterable[dict[str, Any]]) -> list[TableChange]:
    old = {table_key(table): table for table in before}
    new = {table_key(table): table for table in after}
    changes: list[TableChange] = []

    for key in old.keys() | new.keys():
        old_table = old.get(key)
        new_table = new.get(key)
        old_count = row_counter(old_table) if old_table else Counter()
        new_count = row_counter(new_table) if new_table else Counter()
        removed_raw = sum((old_count - new_count).values())
        added_raw = sum((new_count - old_count).values())

        # A removed row paired with an added row represents one modified row.
        modified = min(removed_raw, added_raw)
        removed = removed_raw - modified
        added = added_raw - modified
        changed = modified + removed + added
        if changed == 0:
            continue

        current = new_table or old_table or {}
        if old_table is None:
            kind = "新增"
        elif new_table is None:
            kind = "删除"
        else:
            kind = "更新"
        changes.append(
            TableChange(
                title=table_title(current, key),
                kind=kind,
                changed=changed,
                modified=modified,
                added=added,
                removed=removed,
                old_rows=sum(old_count.values()),
                new_rows=sum(new_count.values()),
            )
        )

    return sorted(changes, key=lambda item: (-item.changed, item.title.casefold()))


def escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def markdown_report(changes: list[TableChange], limit: int) -> str:
    shown = changes[:limit]
    if not shown:
        return "#### 变化最大的表格\n\n本次未发现表格内容变化。\n"

    lines = [
        f"#### 变化最大的表格（前 {len(shown)} 条）",
        "",
    ]
    for rank, item in enumerate(shown, 1):
        lines.append(
            f"{rank}. **{escape_markdown(item.title)}** · {item.kind} · "
            f"变化 {item.changed} 行（新增 {item.added} / 修改 {item.modified} / 删除 {item.removed}）"
            f" · {item.old_rows}→{item.new_rows} 行"
        )
    lines.extend(["", f"共 {len(changes)} 张表发生变化。", ""])
    return "\n".join(lines)


def terminal_report(changes: list[TableChange], limit: int) -> str:
    shown = changes[:limit]
    heading = f"Top {len(shown)} changed tables" if shown else "Changed tables"
    lines = [heading]
    if not shown:
        lines.append("No table content changes detected.")
        return "\n".join(lines)

    rank_width = len(str(len(shown)))
    change_width = max(len("Changed"), *(len(str(item.changed)) for item in shown))
    rows_width = max(len("Rows"), *(len(f"{item.old_rows}->{item.new_rows}") for item in shown))
    lines.append(
        f"{'#':>{rank_width}}  {'Changed':>{change_width}}  {'Rows':>{rows_width}}  Type  Table"
    )
    lines.append("-" * min(120, max(72, len(lines[-1]))))
    for rank, item in enumerate(shown, 1):
        lines.append(
            f"{rank:>{rank_width}}  {item.changed:>{change_width}}  "
            f"{item.old_rows:>{rows_width - len(str(item.new_rows)) - 2}}->{item.new_rows}  "
            f"{item.kind:<4}  +{item.added} ~{item.modified} -{item.removed}  {item.title}"
        )
    lines.append(f"Total changed tables: {len(changes)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    changes = compare_tables(load_tables(args.before), load_tables(args.after))
    report = markdown_report(changes, args.limit)
    print(terminal_report(changes, args.limit))
    if args.markdown:
        args.markdown.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
