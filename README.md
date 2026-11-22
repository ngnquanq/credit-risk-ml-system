# Documentation site (`docs-site` branch)

This branch holds only the documentation website for [credit-risk-ml-system](https://github.com/ngnquanq/credit-risk-ml-system). It shares no history with `master`. The content stays in `docs/` on `master`, the single source of truth, and is pulled in at build time.

- **Stack:** [Astro Starlight](https://starlight.astro.build). Be Vietnam Pro and JetBrains Mono, red/white/grey/black like the portals. Search (Pagefind), light and dark mode.
- **Published at:** <https://ngnquanq.github.io/credit-risk-ml-system/>, by `.github/workflows/deploy-docs.yml` on every push to this branch.

## Where things live

| Path | What |
|---|---|
| `scripts/sync-docs.mjs` | `PAGES`: which files from `docs/` become which site pages. It also rewrites links, copies images and turns Mermaid fences into diagrams. |
| `src/content/docs/` | Pages that exist only on the site: the home page, the technical report and the references |
| `src/styles/theme.css` | Colors, fonts, tables, diagrams |
| `astro.config.mjs` | Sidebar, site settings, Mermaid rendering |
| `CITATION.cff` | Citation metadata. GitHub shows "Cite this repository" only when this file is on the default branch. |

## Run locally

```bash
npm ci
npm run dev        # syncs from ../credit-risk-ml-system/docs, then serves http://localhost:4321/credit-risk-ml-system/
npm run build      # static site in dist/
```

Set `DOCS_SOURCE` to read `docs/` from another checkout.

## Publish a new page

1. Write or update it in `docs/` on `master`.
2. Add it to `PAGES` in `scripts/sync-docs.mjs` and to the sidebar in `astro.config.mjs` on this branch.
3. Push this branch. The workflow rebuilds from the latest `master`.

Changes on `master` alone do not trigger a rebuild. Push this branch, or run the workflow by hand from the Actions tab.
