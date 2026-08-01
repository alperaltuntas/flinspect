# Publishing the manual to GitHub Pages

The user manual (site source `manual/`, config `mkdocs.yml`) is built and
deployed by `.github/workflows/docs.yml` on every push to `main`, via the
standard `configure-pages` → `upload-pages-artifact` → `deploy-pages` chain.
The workflow is committed but **cannot enable Pages by itself** — one-time
repository setup, done in the GitHub UI by someone with admin access:

1. **Repo visibility / plan.** GitHub Pages on a private repository requires
   a paid plan (Pro / Team / Enterprise); on the Free plan the repo must be
   **public**. Check this first — everything else silently waits on it.
2. **Settings → Pages → Build and deployment → Source:** select
   **"GitHub Actions"** (not "Deploy from a branch").
3. Push to `main` (or run the `docs` workflow manually via **Actions → docs →
   Run workflow**). The first successful run creates the `github-pages`
   environment and deploys.
4. Verify the site at **<https://alperaltuntas.github.io/groundline/>**.
   (All internal links are relative, so a different Pages URL — e.g. after a
   repo rename — keeps working without touching the site source; update
   `site_url` in `mkdocs.yml` for correct sitemap/canonical URLs when that
   happens.)

Local preview, any time:

```bash
# in the groundline conda env (or your venv):
pip install -e '.[docs]'
mkdocs serve     # http://127.0.0.1:8000
```

Keeping the manual honest: the command outputs shown in the manual are
committed snippets under `manual/snippets/` — regenerate them with
`manual/snippets/render_snippets.sh` after changes that affect CLI output
(`tests/test_manual.py` pins representative ones against the real pipeline).
