#!/usr/bin/env python3
"""Validate the local archive before a Pages push; uses Python standard library."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import re
import sys

ROOT = Path(__file__).resolve().parent.parent

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.refs = []
        self.title = False
        self.has_title = False
        self.scripts = []
        self.script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        for key in ('href', 'src'):
            if key in a:
                self.refs.append(a[key])
        if tag == 'title':
            self.title = True
        if tag == 'script':
            self.script = True
            self.scripts.append('')

    def handle_endtag(self, tag):
        if tag == 'title':
            self.title = False
        if tag == 'script':
            self.script = False

    def handle_data(self, data):
        if self.title and data.strip():
            self.has_title = True
        if self.script:
            self.scripts[-1] += data

def main():
    errors, pages = [], {}
    for path in ROOT.glob('*.html'):
        raw = path.read_text()
        page = Page()
        page.feed(raw)
        pages[path.resolve()] = page
        if len(page.ids) != len(set(page.ids)):
            errors.append(f'{path.name}: duplicate element id')
        if not page.has_title and not raw.startswith('---\n'):
            errors.append(f'{path.name}: missing title')
        if re.search(r'(?:file:///|/Users/|/home/[^/\s]+/|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----)', raw):
            errors.append(f'{path.name}: local filesystem path or private key marker')
    for path, page in pages.items():
        for ref in page.refs:
            if not ref or ref.startswith(('data:', 'mailto:', 'tel:')):
                continue
            target = urlsplit(ref)
            if target.scheme or target.netloc:
                if target.scheme not in ('https', 'http', 'data', 'mailto', 'tel'):
                    errors.append(f'{path.name}: unexpected link protocol {ref}')
                continue
            local = ((ROOT / unquote(target.path).lstrip('/')) if target.path.startswith('/') else (path.parent / unquote(target.path))).resolve() if target.path else path
            if local.is_dir():
                local = local / 'index.html'
            if not local.exists():
                errors.append(f'{path.name}: missing local link {ref}')
            elif target.fragment and local in pages and unquote(target.fragment) not in pages[local].ids:
                errors.append(f'{path.name}: missing anchor {ref}')
    manifest = json.loads((ROOT / 'archive.json').read_text())
    for article in manifest['articles']:
        if not (ROOT / article['path']).exists():
            errors.append('Missing archived article: ' + article['path'])
    for path in ROOT.glob('*.py'):
        compile(path.read_text(), str(path), 'exec')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'PASS: {len(pages)} HTML pages; {len(manifest["articles"])} archived articles; local links, anchors, titles and file markers.')
    print('External references, GPU commands and live SSH deployment are not exercised by this check.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
