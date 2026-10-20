#!/usr/bin/env python3
"""Import a finished HTML guide, validate the portal, then commit and publish it."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from import_html import import_document

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_REPO = 'User-Balance/User-Balance.github.io'
SITE = 'https://user-balance.github.io/'


def run(args, root, capture=False):
    result = subprocess.run(args, cwd=root, text=True, capture_output=capture, check=True,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GH_PROMPT_DISABLED': '1'})
    return result.stdout.strip() if capture else ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT)
    for option in ('name', 'title', 'category', 'description', 'date', 'tags'):
        parser.add_argument('--'+option)
    parser.add_argument('--prepare-only', action='store_true', help='Import and validate without commit or push.')
    args = parser.parse_args()
    root = args.root.resolve()
    source = args.source.resolve()
    if not source.is_file():
        raise ValueError(f'HTML input not found: {source}')
    if args.prepare_only:
        lock = None
    else:
        origin = run(['git', 'remote', 'get-url', 'origin'], root, True).removesuffix('.git').lower()
        allowed = {'https://github.com/'+EXPECTED_REPO.lower(), 'git@github.com:'+EXPECTED_REPO.lower()}
        if origin not in allowed:
            raise ValueError('Refusing to publish to a repository other than '+EXPECTED_REPO)
        if run(['git', 'branch', '--show-current'], root, True) != 'main':
            raise ValueError('Use the portal main checkout; automatic publishing does not switch branches.')
        if run(['git', 'status', '--porcelain'], root, True):
            raise ValueError('Portal checkout has pending changes. Review and finish them before importing another guide.')
        gitdir = Path(run(['git', 'rev-parse', '--absolute-git-dir'], root, True))
        lock = gitdir / 'portal-publish.lock'
        try:
            lock.mkdir()
        except FileExistsError:
            raise ValueError('Another portal publication may be running; inspect the repository publication lock.')
    try:
        if not args.prepare_only:
            run(['git', 'fetch', 'origin', 'main'], root)
            run(['git', 'merge', '--ff-only', 'origin/main'], root)
        filename, updated = import_document(source, root=root, name=args.name, title=args.title,
            category=args.category, description=args.description, source_date=args.date, tags=args.tags)
        run([sys.executable, str(root/'scripts/check_site.py'), '--root', str(root)], root)
        if args.prepare_only:
            print('Prepared and validated locally: '+filename)
            return 0
        run(['git', 'diff', '--check'], root)
        # Stage exactly the files produced by the import/build transaction.
        allowed = {'index.html', 'archive.json', 'sitemap.xml', filename}
        allowed.update(p.name for p in root.glob('*.html'))
        if any(path not in allowed for path in updated):
            raise ValueError('Import modified a file outside the article/catalogue publication scope.')
        if run(['git', 'diff', '--cached', '--name-only'], root, True):
            raise ValueError('Another process staged changes during import; leaving files for review.')
        if updated:
            run(['git', 'add', '--', *updated], root)
        if not run(['git', 'diff', '--cached', '--name-only'], root, True):
            print('No content changes; ensuring the local main commit is published.')
        else:
            run(['git', 'commit', '-m', 'Archive HTML guide: '+filename], root)
        run(['git', 'push', 'origin', 'main'], root)
        print('Pushed: '+SITE+filename)
        print('GitHub Pages rebuilds automatically. Check the build commit and public URL before reporting completion.')
        return 0
    finally:
        if lock is not None:
            lock.rmdir()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('Publication stopped: '+str(exc), file=sys.stderr)
        raise SystemExit(1)
