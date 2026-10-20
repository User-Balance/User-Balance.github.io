# Portal publication workflow

The user has requested that future completed HTML learning guides for this project be added to this personal portal and published automatically.

- Destination: `User-Balance/User-Balance.github.io`; site: `https://user-balance.github.io/`.
- The public site contains HTML learning guides only. Do not restore the legacy homepage, blog, Jekyll layouts/posts, or the separate download/resources section.
- For a new completed guide, use `python3 scripts/publish_html.py /path/to/guide.html` with a useful title, category, description, source date, and tags. This registers the article, rebuilds the index and sitemap, checks links, commits, and pushes to `main`.
- Existing user authorization covers normal publication of the requested guides. Do not add another generic publication approval step. Stop only for actual missing access, conflicts, or content outside the authorized public scope.
- Verify content and interactions before publication, and verify the GitHub Pages build commit and public URL after pushing. Do not report a push as a completed deployment.
- Never publish private keys, tokens, internal environment reports, or unrelated workspace files. Do not scan the whole workspace for material to upload.
- Keep source and validation dates accurate. Do not turn estimates or source-level checks into claims of GPU or server testing.
- Use `scripts/build_catalog.py` to regenerate the portal after adding/removing root HTML articles. Do not hand-maintain article counts or duplicate cards.
- `index.html` and `404.html` are infrastructure pages, not articles. Optional metadata: `portal-title`, `portal-category`, `portal-description`, `portal-date`, `portal-tags`.
- Keep the existing relative article URLs stable. No force push. Keep credentials outside the repository.
