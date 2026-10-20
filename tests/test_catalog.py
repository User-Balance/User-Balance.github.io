"""Behaviour checks for automatic discovery and transactional HTML import."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from build_catalog import build
from import_html import import_document


INDEX = '''<!doctype html><html><head><title>Portal</title></head><body>
<span id="article-total">00</span><span id="article-count-suffix"> / 00</span>
<span id="all-filter-count">0</span><p id="result-status">共 0 篇手册</p>
<div class="article-grid"><!-- PORTAL_ARTICLES_START --><!-- PORTAL_ARTICLES_END --></div>
</body></html>'''


def document(title="Tutorial", extra="", body="<p>Example.</p>"):
    return f'<!doctype html><html><head><title>{title}</title>{extra}</head><body>{body}</body></html>'


class Elements(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.ids, self.cards, self.links = [], [], []
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "article":
            self.cards.append(attrs)
        if tag == "a":
            self.links.append(attrs.get("href"))


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "site"
        self.root.mkdir()
        (self.root / "index.html").write_text(INDEX, encoding="utf-8")
        (self.root / "assets").mkdir()
        (self.root / "assets/article-nav.css").write_text(".archive-nav{display:flex}")
        (self.root / "scripts").mkdir()
        shutil.copy2(REPO / "scripts/check_site.py", self.root / "scripts/check_site.py")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, raw=None):
        path = self.root / name
        path.write_text(raw or document(), encoding="utf-8")
        return path

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_discovers_five_topics_and_ignores_reserved_pages(self):
        self.write("ai-infra.html", document("AI Infra 全景"))
        self.write("mi355x.html", document("AMD 算子"))
        self.write("b200.html", document("NVIDIA 架构"))
        self.write("sshd.html", document("SSH 运维"))
        self.write("reading.html", document("阅读笔记"))
        self.write("404.html")
        self.write("legacy-home.html")
        records = build(self.root)
        self.assertEqual(len(records), 5)
        self.assertEqual({r["path"]: r["category_id"] for r in records}, {
            "ai-infra.html": "infra", "mi355x.html": "gpu", "b200.html": "gpu", "sshd.html": "ops", "reading.html": "general",
        })
        rendered = (self.root / "index.html").read_text()
        self.assertIn('id="article-total">05<', rendered)
        self.assertEqual(len(Elements(rendered).cards), 5)
        self.assertNotIn("legacy-home", (self.root / "sitemap.xml").read_text())

    def test_metadata_overrides_existing_but_preserves_original_date(self):
        old = {"articles": [{"path": "note.html", "title": "Edited title", "category": "GPU 与算子", "source_date": "2026-10-01", "tags": ["FP8"], "custom": "kept"}]}
        (self.root / "archive.json").write_text(json.dumps(old))
        self.write("note.html", document("Original title", '<meta name="portal-description" content="A new abstract">'))
        article = build(self.root)[0]
        self.assertEqual(article["title"], "Edited title")
        self.assertEqual(article["source_date"], "2026-10-01")
        self.assertEqual(article["tags"], ["FP8"])
        self.assertEqual(article["custom"], "kept")
        self.assertEqual(article["description"], "A new abstract")
        self.write("note.html", document("Original", '<meta name="portal-title" content="Revised"><meta name="portal-category" content="ops"><meta name="portal-date" content="2026-10-02">'))
        article = build(self.root)[0]
        self.assertEqual((article["title"], article["category_id"], article["source_date"]), ("Revised", "ops", "2026-10-02"))

    def test_catalogue_and_navigation_are_idempotent_and_preserve_scripts(self):
        script = '<script>const value = "A < B"; window.demo = () => value;</script>'
        self.write("note.html", document(body=script))
        build(self.root)
        before = self.snapshot()
        build(self.root)
        self.assertEqual(self.snapshot(), before)
        raw = (self.root / "note.html").read_text()
        self.assertEqual(Elements(raw).ids.count("portal-archive-nav"), 1)
        self.assertEqual(raw.count('href="assets/article-nav.css"'), 1)
        self.assertIn(script, raw)

    def test_existing_navigation_is_upgraded_once(self):
        self.write("note.html", document(extra='<link rel="stylesheet" href="assets/article-nav.css">', body='<nav class="archive-nav"><a href="index.html">Back</a></nav>'))
        build(self.root)
        build(self.root)
        raw = (self.root / "note.html").read_text()
        self.assertEqual(raw.count("<nav "), 1)
        self.assertEqual(Elements(raw).ids.count("portal-archive-nav"), 1)

    def test_escaping_prevents_metadata_from_creating_markup(self):
        self.write("note.html", document(extra='<meta name="portal-title" content="&lt;script&gt;bad&lt;/script&gt; &amp; &quot;title&quot;"><meta name="portal-tags" content="a&quot; onclick=&quot;bad, &lt;b&gt;">'))
        build(self.root)
        rendered = (self.root / "index.html").read_text()
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<b>", rendered)
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", rendered)
        cards = Elements(rendered).cards
        self.assertEqual(len(cards), 1)
        self.assertNotIn("onclick", cards[0])
        self.assertIn('<script>bad</script>', cards[0]["data-search"])

    def test_new_and_deleted_articles_update_cards_sitemap_and_count(self):
        self.write("first.html")
        build(self.root)
        self.write("second.html")
        self.assertEqual(len(build(self.root)), 2)
        (self.root / "first.html").unlink()
        records = build(self.root)
        self.assertEqual([r["path"] for r in records], ["second.html"])
        self.assertNotIn("first.html", (self.root / "index.html").read_text())
        self.assertNotIn("first.html", (self.root / "sitemap.xml").read_text())
        self.assertIn('id="all-filter-count">1<', (self.root / "index.html").read_text())

    def test_untracked_date_is_stable_after_file_mtime_changes(self):
        note = self.write("note.html")
        os.utime(note, (1704067200, 1704067200))
        self.assertEqual(build(self.root)[0]["source_date"], "2024-01-01")
        os.utime(note, (1735689600, 1735689600))
        self.assertEqual(build(self.root)[0]["source_date"], "2024-01-01")

    def test_build_failure_does_not_mutate_articles(self):
        self.write("note.html")
        (self.root / "index.html").write_text(document("Missing markers"))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "marker"):
            build(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_import_builds_complete_ready_to_publish_catalogue(self):
        source = Path(self.temp.name) / "new.html"
        source.write_text(document("New tutorial"))
        name, changed = import_document(source, self.root, title='GEMM & "tiles"', category="gpu", source_date="2026-10-20", tags="FP8,128")
        self.assertEqual(name, "new.html")
        self.assertIn("index.html", changed)
        article = json.loads((self.root / "archive.json").read_text())["articles"][0]
        self.assertEqual(article["title"], 'GEMM & "tiles"')
        self.assertEqual(article["tags"], ["FP8", "128"])
        self.assertEqual(article["source_date"], "2026-10-20")
        self.assertIn("portal-archive-nav", (self.root / "new.html").read_text())

    def test_import_rejects_incomplete_reserved_and_local_private_data(self):
        source = Path(self.temp.name) / "bad.html"
        before = self.snapshot()
        cases = ["<h1>Fragment</h1>", document(body='<a href="file:///tmp/data">local</a>'), document(body="-----BEGIN OPENSSH PRIVATE KEY-----"), document(body="/Users/example/secret")]
        for raw in cases:
            with self.subTest(raw=raw):
                source.write_text(raw)
                with self.assertRaises(ValueError):
                    import_document(source, self.root)
                self.assertEqual(self.snapshot(), before)
        source.write_text(document())
        for name in ("index.html", "404.html", "legacy-home.html", "../escape.html"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                import_document(source, self.root, name=name)
        self.assertEqual(self.snapshot(), before)

    def test_missing_asset_is_rejected_without_publishing_partial_file(self):
        source = Path(self.temp.name) / "missing.html"
        source.write_text(document(body='<img src="missing-chart.png" alt="Missing">'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "validation failed"):
            import_document(source, self.root)
        self.assertEqual(self.snapshot(), before)

    def test_missing_css_srcset_or_poster_is_rejected_transactionally(self):
        source = Path(self.temp.name) / 'visual.html'
        before = self.snapshot()
        cases = [
            document(body='<video poster="missing-poster.png"></video>'),
            document(body='<img srcset="missing-small.png 1x, missing-large.png 2x" alt="chart">'),
            document(extra='<style>.chart {background-image:url("missing-bg.svg")}</style>'),
            document(body='<div style="background:url(missing-bg.svg)">chart</div>'),
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                source.write_text(raw)
                with self.assertRaisesRegex(ValueError, 'validation failed'):
                    import_document(source, self.root)
                self.assertEqual(self.snapshot(), before)

    def test_publisher_prepare_only_adds_article_without_git_or_network(self):
        source = Path(self.temp.name) / 'future-guide.html'
        source.write_text(document('Future Guide'))
        result = subprocess.run([sys.executable, str(REPO/'scripts/publish_html.py'),
            str(source), '--root', str(self.root), '--prepare-only',
            '--title', '后续教程', '--category', 'general', '--date', '2026-10-20'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        articles = json.loads((self.root/'archive.json').read_text())['articles']
        self.assertEqual(articles[0]['title'], '后续教程')
        self.assertIn('future-guide.html', (self.root/'index.html').read_text())
        self.assertFalse((self.root/'.git').exists())


if __name__ == "__main__":
    unittest.main()
