"""Export the published course catalogue from an LMS SQL dump to data/courses.json.

Usage:
    python scripts/export_courses.py path/to/dump.sql [-o data/courses.json]

This is the development source of course data. Later (Phase 1, nightly sync) the same
JSON shape is produced from the LMS database instead of a dump file.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

INSERT_RE = re.compile(r"INSERT INTO `(?P<table>\w+)`\s*\((?P<cols>[^)]*)\)\s*VALUES\s*", re.I)
TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<str>'(?:[^'\\]|\\.|'')*')
      | (?P<null>NULL)
      | (?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
      | (?P<punc>[(),;])
    )""",
    re.S | re.X,
)
ESCAPES = {"0": "\0", "n": "\n", "r": "\r", "t": "\t", "b": "\b", "Z": "\x1a"}
TAG_RE = re.compile(r"<[^>]+>")
WANTED = {"courses", "categories", "course_levels"}
# courses.type in the LMS: 1 = course, 2 = quiz (3 = live class, not exported)
KINDS = {"1": "course", "2": "quiz"}


def _unescape(raw: str) -> str:
    body = raw[1:-1].replace("''", "'")
    return re.sub(r"\\(.)", lambda m: ESCAPES.get(m.group(1), m.group(1)), body)


def parse_values(text: str, pos: int) -> tuple[list[list], int]:
    """Parse `(v, v, ...), (...) ;` starting at pos. Returns rows and the end position."""
    rows: list[list] = []
    row: list | None = None
    while True:
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"Cannot parse SQL near: {text[pos:pos + 60]!r}")
        pos = m.end()
        if m.group("punc") == "(":
            row = []
        elif m.group("punc") == ")":
            rows.append(row or [])
            row = None
        elif m.group("punc") == ";":
            return rows, pos
        elif m.group("punc") == ",":
            continue
        elif m.group("str") is not None:
            row.append(_unescape(m.group("str")))
        elif m.group("null") is not None:
            row.append(None)
        else:
            row.append(m.group("num"))


def read_tables(sql: str) -> dict[str, list[dict]]:
    tables: dict[str, list[dict]] = {name: [] for name in WANTED}
    for m in INSERT_RE.finditer(sql):
        table = m.group("table")
        if table not in WANTED:
            continue
        cols = [c.strip().strip("`") for c in m.group("cols").split(",")]
        rows, _ = parse_values(sql, m.end())
        for row in rows:
            if len(row) != len(cols):
                raise ValueError(f"{table}: row has {len(row)} values, expected {len(cols)}")
            tables[table].append(dict(zip(cols, row)))
    return tables


def localized(value: str | None) -> str:
    """LMS stores names as JSON like {"en": "Title"}; return the English (or first) text."""
    if not value:
        return ""
    try:
        data = json.loads(value)
    except ValueError:
        return value.strip()
    if isinstance(data, dict):
        return str(data.get("en") or next((v for v in data.values() if v), "")).strip()
    return str(data).strip()


def clean_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    text = html.unescape(TAG_RE.sub(" ", html.unescape(value)))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()


def number(value: str | None) -> float:
    try:
        return float(value) if value not in (None, "") else 0.0
    except ValueError:
        return 0.0


def build_courses(tables: dict[str, list[dict]]) -> list[dict]:
    categories = {c["id"]: localized(c.get("title")) or localized(c.get("name")) for c in tables["categories"]}
    levels = {lv["id"]: localized(lv.get("title")) for lv in tables["course_levels"]}
    courses = []
    for row in tables["courses"]:
        title = localized(row.get("title"))
        if not title or not row.get("slug"):
            continue
        if row.get("publish") != "1" or row.get("status") != "1":
            continue
        kind = KINDS.get(row.get("type"))
        if kind is None:  # skip classes and any unknown type
            continue
        price = number(row.get("discount_price")) or number(row.get("price"))
        courses.append(
            {
                "id": int(row["id"]),
                "kind": kind,
                "title": title,
                "slug": row["slug"],
                "category": categories.get(row.get("category_id"), ""),
                "level": levels.get(row.get("level"), ""),
                "price": price,
                "lessons": int(number(row.get("total_lessons"))),
                "certificate": row.get("has_certificate") == "1",
                "about": clean_text(localized(row.get("about")) or localized(row.get("meta_description")), 1200),
                "outcomes": clean_text(localized(row.get("outcomes")) or localized(row.get("what_learn1")), 600),
            }
        )
    return courses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="LMS SQL dump file")
    parser.add_argument("-o", "--output", type=Path, default=Path("data/courses.json"))
    args = parser.parse_args()

    sql = args.dump.read_text(encoding="utf-8", errors="ignore")
    tables = read_tables(sql)
    courses = build_courses(tables)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(courses, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"Read {len(tables['courses'])} courses, {len(tables['categories'])} categories, "
        f"{len(tables['course_levels'])} levels. Wrote {len(courses)} published courses to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
