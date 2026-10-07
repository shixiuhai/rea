#!/usr/bin/env python3
"""Export the *open* (unsigned) book list to a readable .txt.

This does not need a signature. Example:
    python examples/export_open_books.py --out out/books.txt
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fqnovel import FqnovelClient  # noqa: E402

BOOK_ID_KEYS = ("book_id", "bookId", "bookid")
NAME_KEYS = ("book_name", "bookName", "title", "name")
AUTHOR_KEYS = ("author", "author_name", "authorName")


def collect_books(obj):
    books = {}

    def pick(o, keys):
        for k in keys:
            v = o.get(k)
            if isinstance(v, (str, int)) and str(v):
                return str(v)
        return None

    def walk(o):
        if isinstance(o, dict):
            bid = pick(o, BOOK_ID_KEYS)
            if bid and bid.isdigit() and len(bid) > 10:
                name = pick(o, NAME_KEYS) or books.get(bid, {}).get("name", "")
                author = pick(o, AUTHOR_KEYS) or books.get(bid, {}).get("author", "")
                cur = books.setdefault(bid, {"name": "", "author": ""})
                if name:
                    cur["name"] = name
                if author:
                    cur["author"] = author
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return books


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/books.txt")
    args = ap.parse_args()

    c = FqnovelClient()
    sources = [("bookstore/homepage", c.book_list_store_home()),
               ("bookmall/tab", c.book_list_tab(stream_count=10))]
    books = {}
    for label, r in sources:
        n = len(collect_books(r.json))
        books.update(collect_books(r.json))
        print(f"[export] {label}: HTTP {r.status}, {n} books")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    lines = [f"# fqnovel open book list ({len(books)} books)\n"]
    for bid, info in books.items():
        lines.append(f"{info['name'] or '(no title)'}\t{info['author'] or ''}\t{bid}\n")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))
    print(f"[export] wrote {len(books)} books -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
