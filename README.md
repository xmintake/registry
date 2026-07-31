# XMRegistry (public)

Public CDN for XMIntake registry artifacts: signed destinations, intake schemas, catalog, and scenarios.

Served at:

- https://xmintake.github.io/registry/
- https://registry.xmarin.dev/

Operational tooling, publisher auth, and submission workflows live in the private **registry-ops** repository.

## Layout

```text
destinations/   ← signed .destination.json
schemas/        ← intake form schemas
catalog/        ← index.json, browse.json, categories, featured
scenarios/      ← signed scenario packs
XMRegistry.public-key.pem
```

Browse UI static assets (`index.html`, `assets/`) are deployed alongside artifacts via GitHub Pages.
