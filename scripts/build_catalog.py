#!/usr/bin/env python3
"""Discover root HTML articles and build the static portal. Standard library only."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://user-balance.github.io"
EXCLUDED = {"index.html", "404.html", "legacy-home.html"}
START, END = "<!-- PORTAL_ARTICLES_START -->", "<!-- PORTAL_ARTICLES_END -->"
CATEGORY_NAMES = {"infra": "AI 全景", "gpu": "GPU 与算子", "ops": "系统运维", "general": "其他手册"}


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title_parts = []
        self.in_title = False
        self.nav_present = False
        self.style_present = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name"):
            self.meta[attrs["name"].lower()] = attrs.get("content", "").strip()
        if tag == "title":
            self.in_title = True
        if attrs.get("id") == "portal-archive-nav":
            self.nav_present = True
        if tag == "link" and attrs.get("href") == "assets/article-nav.css":
            self.style_present = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return " ".join("".join(self.title_parts).split())


def read_metadata(raw):
    result = Metadata()
    result.feed(raw)
    return result


def parse_tags(value):
    if isinstance(value, list):
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
    return list(dict.fromkeys(tag.strip() for tag in re.split(r"[,，;；]", str(value or "")) if tag.strip()))


def category_id(category, title="", path=""):
    if category in CATEGORY_NAMES:
        return category
    text = f"{category} {title} {path}".lower()
    # Category itself wins over keywords that only occur in a title.
    for candidate in (category.lower(), text):
        if re.search(r"gpu|amd|nvidia|mi355|h20|b200|gemm|cuda|rocm|算子|显卡", candidate):
            return "gpu"
        if re.search(r"linux|ssh|运维|服务器|系统运维|kubernetes|docker|network", candidate):
            return "ops"
        if re.search(r"ai[ _-]?infra|基础设施|ai 全景|人工智能全景", candidate):
            return "infra"
    return "general"


def valid_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"Date must be YYYY-MM-DD: {value}") from exc


def source_date(path, root, metadata, previous):
    for value in (metadata.get("portal-date"), previous.get("source_date")):
        if value:
            return valid_date(value)
    # First committed date is independent of checkout/build time. Existing manifest
    # dates remain the fallback authority for files without explicit metadata.
    result = subprocess.run(
        ["git", "-C", str(root), "log", "--follow", "--format=%as", "--", path.name],
        text=True, capture_output=True, check=False,
    )
    lines = result.stdout.strip().splitlines()
    if result.returncode == 0 and lines:
        return valid_date(lines[-1])
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def article_record(path, root, previous):
    raw = path.read_text(encoding="utf-8")
    parsed = read_metadata(raw)
    meta = parsed.meta
    title = meta.get("portal-title") or previous.get("title") or parsed.title or path.stem
    category = meta.get("portal-category") or previous.get("category") or ""
    group = category_id(category, title, path.name)
    category = CATEGORY_NAMES.get(category, category) or CATEGORY_NAMES[group]
    description = meta.get("portal-description") or previous.get("description") or meta.get("description") or f"关于{title}的交互图解与学习手册。"
    tags = parse_tags(meta.get("portal-tags") or previous.get("tags") or meta.get("keywords"))
    if not tags:
        tags = [category]
    # Preserve extra editorial fields while removing stale paths from the output.
    return {
        **previous,
        "path": path.name,
        "title": title,
        "category": category,
        "category_id": group,
        "description": description,
        "tags": tags,
        "source_date": source_date(path, root, meta, previous),
    }, raw, parsed


def render_card(article, number):
    title = escape(article["title"], quote=True)
    path = escape(quote(article["path"]), quote=True)
    category = escape(article["category"], quote=True)
    group = escape(article["category_id"], quote=True)
    tags = "".join(f"<span>{escape(tag)}</span>" for tag in article["tags"])
    search = escape(" ".join([article["title"], article["category"], article["description"], *article["tags"]]), quote=True)
    return (
        f'      <article class="article-card" data-category="{group}" data-search="{search}">\n'
        f'        <div class="card-topline"><span class="category-tag {group}">{category}</span>'
        f'<span class="article-number">{number:03d}</span></div>\n'
        f'        <h3><a href="{path}">{title}</a></h3>\n'
        f'        <p>{escape(article["description"])}</p>\n'
        f'        <div class="tag-list">{tags}</div>\n'
        f'        <p class="verified">资料日期：{escape(article["source_date"])}</p>\n'
        f'        <div class="card-bottom"><span>交互图解 · 学习手册</span>'
        f'<a class="read-link" href="{path}" aria-label="阅读 {title}">阅读手册 '
        '<span aria-hidden="true">↗</span></a></div>\n'
        '      </article>'
    )


def replace_element_text(raw, element_id, text):
    pattern = r'(<([\w-]+)\b[^>]*\bid=["\']' + re.escape(element_id) + r'["\'][^>]*>)(.*?)(</\2>)'
    return re.sub(pattern, lambda m: m[1] + escape(text) + m[4], raw, flags=re.S)


def render_index(raw, articles):
    if raw.count(START) != 1 or raw.count(END) != 1 or raw.index(START) > raw.index(END):
        raise ValueError("index.html needs exactly one ordered PORTAL_ARTICLES_START/END marker pair")
    before, rest = raw.split(START, 1)
    _, after = rest.split(END, 1)
    cards = "\n".join(render_card(article, i) for i, article in enumerate(articles, 1))
    raw = before + START + "\n" + cards + "\n    " + END + after
    count = len(articles)
    for key, value in {
        "article-total": f"{count:02d}",
        "article-count-suffix": f" / {count:02d}",
        "all-filter-count": str(count),
        "result-status": f"共 {count} 篇手册",
    }.items():
        raw = replace_element_text(raw, key, value)
    return raw


def add_navigation(raw, article, parsed):
    if not parsed.style_present:
        raw, replaced = re.subn(r"</head\s*>", '<link id="portal-article-nav-style" rel="stylesheet" href="assets/article-nav.css">\n</head>', raw, count=1, flags=re.I)
        if not replaced:
            raise ValueError(f'{article["path"]}: missing </head>')
    if not parsed.nav_present:
        # Upgrade the existing archive bar rather than adding a second one.
        legacy = r'<nav\b(?=[^>]*\bclass=["\'][^"\']*\barchive-nav\b[^"\']*["\'])[^>]*>'
        raw, upgraded = re.subn(legacy, lambda m: m[0][:-1] + ' id="portal-archive-nav">', raw, count=1, flags=re.I)
        if not upgraded:
            nav = ('\n<nav id="portal-archive-nav" class="archive-nav" aria-label="学习手册导航">'
                   '<a href="index.html">← 技术学习手册 · 返回门户</a>'
                   f'<span>{escape(article["category"])} · 资料日期 {escape(article["source_date"])}</span></nav>\n')
            raw, inserted = re.subn(r"<body\b[^>]*>", lambda m: m[0] + nav, raw, count=1, flags=re.I)
            if not inserted:
                raise ValueError(f'{article["path"]}: missing <body>')
    return raw


def build(root=ROOT):
    root = Path(root).resolve()
    manifest_path = root / "archive.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    old = {article["path"]: article for article in previous.get("articles", [])}
    order = {name: index for index, name in enumerate(old)}
    paths = sorted((p for p in root.glob("*.html") if p.name.lower() not in EXCLUDED), key=lambda p: (order.get(p.name, len(order)), p.name))
    articles, page_updates = [], {}
    for path in paths:
        article, raw, parsed = article_record(path, root, old.get(path.name, {}))
        articles.append(article)
        page_updates[path] = add_navigation(raw, article, parsed)
    # Render everything before writing, so missing markers/invalid metadata do not
    # leave half of a generated catalogue behind.
    index = root / "index.html"
    page_updates[index] = render_index(index.read_text(encoding="utf-8"), articles)
    manifest = {**previous, "articles": articles}
    page_updates[manifest_path] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    urls = [f"  <url><loc>{SITE_URL}/</loc></url>"]
    urls.extend(f'  <url><loc>{SITE_URL}/{escape(quote(a["path"]))}</loc><lastmod>{a["source_date"]}</lastmod></url>' for a in articles)
    page_updates[root / "sitemap.xml"] = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
    for path, content in page_updates.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
    return articles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Site repository directory")
    args = parser.parse_args()
    try:
        articles = build(args.root)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Catalogue build failed: {exc}\n")
    print(f"Built {len(articles)} article cards, archive.json and sitemap.xml.")


if __name__ == "__main__":
    main()
