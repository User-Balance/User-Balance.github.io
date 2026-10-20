#!/usr/bin/env python3
"""Validate the local archive before a Pages push; uses Python standard library."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import re
import sys
import argparse

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
        self.style = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        for key in ('href', 'src', 'poster'):
            if key in a:
                self.refs.append(a[key])
        if 'srcset' in a:
            for match in re.finditer(r'(?:^|,\s*)([^\s,]+)(?:\s+[\d.]+[wx])?', a['srcset']):
                if not a['srcset'].lstrip().startswith('data:'):
                    self.refs.append(match.group(1))
        if 'style' in a:
            self.refs.extend(css_refs(a['style']))
        if tag == 'title':
            self.title = True
        if tag == 'script':
            self.script = True
            self.scripts.append('')
        if tag == 'style':
            self.style = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.title = False
        if tag == 'script':
            self.script = False
        if tag == 'style':
            self.style = False

    def handle_data(self, data):
        if self.title and data.strip():
            self.has_title = True
        if self.script:
            self.scripts[-1] += data
        if self.style:
            self.refs.extend(css_refs(data))

def css_refs(text):
    return [match.group(2).strip() for match in re.finditer(r'url\(\s*([\'"]?)(.*?)\1\s*\)', text, re.I)
            if match.group(2).strip() and not match.group(2).strip().startswith(('#', 'data:'))]

def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.root.resolve()
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
    resources = {path: page.refs for path, page in pages.items()}
    for path in (ROOT / 'assets').rglob('*.css'):
        resources[path.resolve()] = css_refs(path.read_text())
    for path, refs in resources.items():
        for ref in refs:
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
            if local != ROOT and ROOT not in local.parents:
                errors.append(f'{path.name}: link escapes public site root {ref}')
                continue
            if not local.exists():
                errors.append(f'{path.name}: missing local link {ref}')
            elif target.fragment and local in pages and unquote(target.fragment) not in pages[local].ids:
                errors.append(f'{path.name}: missing anchor {ref}')
    manifest = json.loads((ROOT / 'archive.json').read_text())
    for article in manifest['articles']:
        if not (ROOT / article['path']).exists():
            errors.append('Missing archived article: ' + article['path'])
    for path in (ROOT / 'scripts').glob('*.py'):
        compile(path.read_text(), str(path), 'exec')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'PASS: {len(pages)} HTML pages; {len(manifest["articles"])} archived articles; local links, anchors, titles and file markers.')
    print('External references, GPU commands and live SSH deployment are not exercised by this check.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
