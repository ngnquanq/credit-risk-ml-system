# Documentation site (`docs-site` branch)

This branch holds only the documentation website for [credit-risk-ml-system](https://github.com/ngnquanq/credit-risk-ml-system). It shares no history with `master`. The content stays in `docs/` on `master`, the single source of truth, and is pulled in at build time.

- **Stack:** [Astro Starlight](https://starlight.astro.build). Be Vietnam Pro and JetBrains Mono, red/white/grey/black like the portals. Search (Pagefind), light and dark mode.
- **Published at:** <https://ngnquanq.github.io/credit-risk-ml-system/>, by `.github/workflows/deploy-docs.yml` on every push to this branch.

## Where things live

| Path | What |
|---|---|
| `scripts/sync-docs.mjs` | `PAGES`: which files from `docs/` become which site pages (52 today: ADRs, handoffs, security, runbooks, C4 reference). It also rewrites links, copies images and turns Mermaid fences into diagrams. |
| `scripts/make-guide-stubs.py` | Writes the 27 heading-only pages under `src/content/docs/guide/` that mirror the project README's table of contents. The README's detail is out of date, so only its headings are kept until it is reviewed. |
| `src/content/docs/architecture/` | The hand-drawn, readable C4 pages (at a glance, levels 1 to 3, runtime flows, deployment). Each starts with a small Mermaid map and offers the full generated view behind an **Expand** button |
| `src/components/Zoom.astro` | A generated diagram, fitted to the page, enlarged on click |
| `src/content/docs/` | Pages that exist only on the site: the home page, the technical report and the references |
| `src/styles/theme.css` | Colors, fonts, tables, diagrams |
| `astro.config.mjs` | Sidebar, site settings, Mermaid rendering |
| `CITATION.cff` | Citation metadata. GitHub shows "Cite this repository" only when this file is on the default branch. |

## Run locally

Inside the repository, on this branch:

```bash
git switch docs-site      # commit or stash work on other branches first
npm ci
npm run dev               # exports docs/ from origin/master, then serves http://localhost:4321/credit-risk-ml-system/
npm run build             # static site in dist/
```

`DOCS_REF=<branch or commit>` previews docs from another ref, for example a branch that is not merged yet. `DOCS_SOURCE=<dir>` reads an existing folder instead (the workflow uses this).

## Publish a new page

1. Write or update it in `docs/` on `master`.
2. Add it to `PAGES` in `scripts/sync-docs.mjs` and to the sidebar in `astro.config.mjs` on this branch.
3. Push this branch. The workflow rebuilds from the latest `master`.

Diagrams: click any diagram (or its **Expand** label) for a full-screen view with Fit, 100% and 200%, drag to pan, Esc to close.

Changes on `master` alone do not trigger a rebuild. Push this branch, or run the workflow by hand from the Actions tab.
