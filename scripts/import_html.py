#!/usr/bin/env python3
"""Validate and import one complete HTML handbook, then rebuild the portal."""
from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from build_catalog import EXCLUDED, ROOT, build, read_metadata, valid_date


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.starts, self.ends = set(), set()

    def handle_starttag(self, tag, attrs):
        self.starts.add(tag)

    def handle_endtag(self, tag):
        self.ends.add(tag)


def validate_document(raw):
    document = Document()
    document.feed(raw)
    if not {"html", "head", "body"} <= (document.starts & document.ends):
        raise ValueError("Input must be a complete HTML document with html, head and body elements")
    if not read_metadata(raw).title:
        raise ValueError("Input must have a nonempty <title>")
    if re.search(r"file:/|/Users/|/home/[^/\s]+/|/private/|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----", raw, re.I):
        raise ValueError("Input contains a local filesystem path or private key marker")


def add_metadata(raw, values):
    for name, value in values.items():
        if value is None:
            continue
        # Remove only this explicitly supplied metadata field; the rest of the
        # document, including inline scripts and styles, is preserved bytewise.
        pattern = r'<meta\b(?=[^>]*\bname\s*=\s*["\']' + re.escape(name) + r'["\'])[^>]*>\s*'
        raw = re.sub(pattern, "", raw, flags=re.I)
        tag = f'<meta name="{name}" content="{escape(value, quote=True)}">\n'
        raw = re.sub(r"</head\s*>", lambda m: tag + m[0], raw, count=1, flags=re.I)
    return raw


def import_document(source, root=ROOT, name=None, title=None, category=None, description=None, source_date=None, tags=None):
    root, source = Path(root).resolve(), Path(source).resolve()
    name = name or source.name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.html", name) or name.lower() in EXCLUDED:
        raise ValueError("Article name must be a safe .html filename; index, 404 and legacy-home are reserved")
    if source_date:
        valid_date(source_date)
    raw = source.read_text(encoding="utf-8")
    validate_document(raw)
    raw = add_metadata(raw, {"portal-title": title, "portal-category": category, "portal-description": description, "portal-date": source_date, "portal-tags": tags})
    checker = root / "scripts" / "check_site.py"
    if not checker.is_file():
        raise ValueError("scripts/check_site.py is required for pre-publication validation")
    with tempfile.TemporaryDirectory(prefix="portal-import-") as temporary:
        stage = Path(temporary) / "site"
        shutil.copytree(root, stage, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".DS_Store"))
        imported = stage / name
        imported.write_text(raw, encoding="utf-8")
        # Preserve an untracked file's original date for the first catalogue.
        shutil.copystat(source, imported)
        build(stage)
        result = subprocess.run([sys.executable, str(stage / "scripts/check_site.py"), "--root", str(stage)], capture_output=True, text=True, check=False)
        if result.returncode:
            raise ValueError("Staged site validation failed; repository unchanged:\n" + result.stdout + result.stderr)
        # Only promote after every validation succeeds. The staging tree and any
        # rejected file are deleted by TemporaryDirectory on either path.
        updated = []
        for staged in sorted(stage.rglob("*")):
            if not staged.is_file() or "__pycache__" in staged.parts:
                continue
            relative = staged.relative_to(stage)
            destination = root / relative
            if destination.exists() and destination.read_bytes() == staged.read_bytes():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged, destination)
            updated.append(relative.as_posix())
    return name, updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to a complete HTML document")
    parser.add_argument("--root", type=Path, default=ROOT, help="Site repository directory")
    parser.add_argument("--name", help="Destination .html filename; defaults to the source filename")
    parser.add_argument("--title")
    parser.add_argument("--category", help="infra, gpu, ops, general, or a display category")
    parser.add_argument("--description")
    parser.add_argument("--date", dest="source_date", help="Source date in YYYY-MM-DD")
    parser.add_argument("--tags", help="Comma-separated search tags")
    args = parser.parse_args()
    try:
        name, updated = import_document(**vars(args))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Imported {name}; catalogue updated; {len(updated)} files changed. Ready for review and Git commit.")


if __name__ == "__main__":
    main()
