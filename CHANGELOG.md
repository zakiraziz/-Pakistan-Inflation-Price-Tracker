# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-09-13

### Added
- Design system: spacing/type tokens, flat light theme, skeleton loaders,
  inline SVG icon set, visible focus rings.
- `/readyz` readiness endpoint alongside `/healthz`.
- Security response headers (CSP, `X-Frame-Options`, `nosniff`,
  `Referrer-Policy`) and structured JSON error responses for 404/429/500.
- Methodology page (`docs/methodology.md`, rendered at `/methodology`).
- Repo hygiene: `Makefile`, `.env.example`, `LICENSE` (MIT), `CHANGELOG.md`,
  `CONTRIBUTING.md`, pull-request template.
- Docker packaging: multi-stage `Dockerfile`, `docker-compose.yml`
  (app + Postgres + Redis + Caddy), `docker/Caddyfile` reverse proxy.

### Changed
- README rewritten: badges, hero screenshot, architecture, methodology link,
  testing and deployment guides.

## [0.3.0] - 2026-09-13

### Added
- Data provenance on every price point (`source`, `method`, `collected_at`,
  `status`, `review_note`) plus an `ingestions` audit table.
- Approval workflow: validated points auto-approve; implausible ones are held
  `pending` and excluded from all public endpoints until
  approve/reject (`/api/admin/*`).
- Pluggable ingestion framework (`ingest/`): `SeedSource`, `CSVSource`,
  `PBSWebSource` scaffold, and a validated `pipeline`.
- APScheduler-based scheduled ingestion (`scheduler.py`, weekly cron).
- Caching on read APIs (`flask-caching`) with invalidation on data change.
- Rate limiting (`flask-limiter`), `/healthz`, structured JSON logging.
- Analytics endpoints: `/api/pivot`, `/api/inflation`
  (annualised, weekly, year-over-year).
- Professional dashboard: KPI cards, Trends / Compare / Data tabs,
  item search, CSV export, one-click ingest button.
- pytest suite with fixtures and 80%+ coverage gate; live-server test
  (`test_web.py`); headless-Chrome render QA (`shot.py`).
- CI (`GitHub Actions`), `pyproject.toml` tooling config, pre-commit,
  `.editorconfig`.

### Fixed
- Charts failed to render because Chart.js `time` scales require a separate
  date adapter; switched to built-in category axes.

## [0.2.0] - 2026-09-11

### Added
- Interactive dashboard: date presets/filters, category and item filters,
  basket cost index, alerts panel, summary cards.
- Flask API (`/api/items`, `/api/series`, `/api/index`, `/api/metrics`,
  `/api/alerts`, `/api/series.csv`, `POST /ingest/next`).
- Weekly ingest job with idempotent, snap-to-grid behaviour.

## [0.1.0] - 2026-09-10

### Added
- Deterministic basket model (11 everyday goods, weekly PKR prices,
  2023–2026) mirroring Pakistan's inflation arc.
- SQLite storage (`items`, `prices`, `alerts`) and reproducible seeding.
- Economics explainer grounded in computed statistics.