# XMRegistry

Public registry of XMIntake destinations, schemas, and scenarios, served at
<https://registry.xmarin.dev> (`https://xmintake.github.io/registry/` redirects there).

Everything here is reviewed and signed by XMRegistry (Ed25519). XMIntake verifies each
destination, schema, and scenario against [`XMRegistry.public-key.pem`](XMRegistry.public-key.pem)
before installing it, and only accepts schemas published here.

| Path | Content |
|---|---|
| `destinations/{publisher}/{id}.destination.json` | Signed destinations |
| `schemas/{publisher}/{id}.schema.json` | Signed intake schemas |
| `scenarios/{publisher}/{id}.scenario.json` | Signed scenarios |
| `catalog/` | Generated catalog for the browse site (`browse.json`, `index.json`, `publishers.json`) and editorial files (`categories.json`, `featured.json`) |
| `meta/`, `spec/` | Meta-schema and destination spec |
| `index.html`, `404.html`, `assets/` | Browse site |

## Publishing

Publishers register and publish from the XMIntake app. Every request is reviewed before it
appears here; this repository is written only by the maintainers' publish pipeline.

Each push runs **Verify and deploy**: it checks every signature and that only public content
is present, then deploys GitHub Pages. If verification fails, the site keeps serving the last
good deploy.
