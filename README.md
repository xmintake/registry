# XMRegistry (public)

Public CDN for XMIntake registry artifacts: signed destinations, intake schemas, catalog, and scenarios.

Served at:

- https://xmintake.github.io/registry/
- https://registry.xmarin.dev/

Publisher submissions merge here via **registry-service** (GitHub App). Signing and promotion run in **GitHub Actions** on this repo.

## Layout

```text
destinations/              ← signed .destination.json (CDN)
schemas/                   ← intake form schemas
catalog/                   ← index.json, browse.json, categories, featured
publishers/                ← publisher profiles + allowedIdentities
submissions/pending/       ← unsigned drafts on PR branches / until promote
tools/                     ← validate, promote, sign, generate-catalog
scenarios/                 ← signed scenario packs
XMRegistry.public-key.pem
.github/workflows/
  submission-pr-checks.yml           ← validates pending folders on PRs
  submission-publish-on-merge.yml    ← sign + promote when submission PR merges
  promote-pending-manual.yml         ← workflow_dispatch for backfill / ops
  deploy-pages.yml                   ← GitHub Pages
```

Browse UI static assets (`index.html`, `assets/`) are deployed alongside artifacts via GitHub Pages.

The `/register` route on the browse site explains publisher registration and links to XMIntake (`https://xmintake.xmarin.dev/x/registry/register`); registration itself runs in the app with verified Google sign-in.

## Submission workflow

1. XMIntake → **registry-service** opens a PR with files under `submissions/pending/{slug}/{id}/`.
2. **Submission PR checks** validates the pending folder.
3. On merge, **Submission publish on merge** signs the destination, copies schema, updates catalog, removes the pending folder, and pushes to `main`.
4. **Deploy registry Pages** publishes the CDN (~minutes).

Requires **Repository secret** `XMREGISTRY_PRIVATE_KEY` (Settings → Secrets and variables → Actions → **Repository secrets**). See [registry-service MANUAL_SETUP](https://github.com/xmarin/registry-service/blob/main/docs/MANUAL_SETUP.md).

If a submission merged before workflows were installed, run **Actions → Promote pending submissions (manual)** on `main` (leave path empty to promote all pending folders).
