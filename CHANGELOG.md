# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **A contrast guarantee for the palette, enforced by tests.** Every colour the
  site uses for text now clears WCAG AA (4.5:1) on all three surfaces text can
  land on — white cards, the page body, the tinted chips — and
  `tests/test_token_parity.py` recomputes those ratios on every run. The same
  test fails if `web/svg.py` or `static/helpers.js` drift from the stylesheet,
  which nothing checked before: `FAINT`, `UP` and `DOWN` are the only values that
  two files must agree on, and nothing enforced it.
- `--down-ink` (`#04684f`), the green used for text meaning "price fell". `--down`
  (`#009e73`, the colorblind-safe Okabe-Ito green) stays the chart fill and stroke
  colour, where WCAG asks 3:1 for non-text rather than 4.5:1.
- `--warn` / `--warn-soft` and `--shadow-lift` tokens, replacing the same amber
  hex repeated across three rules, and `.up` / `.down` / `.flat` / `.tnum`
  utilities shared by the dashboard, the server-rendered pages and the charts.
- **The dashboard footer is now styled.** `.site-foot`, the wrapper around the
  footer card, had no CSS rule at all, so the closing band of the page was
  unstyled — the only class in `static/index.html` without a selector.
  `verify.py`'s stylesheet-coverage check goes 64/65 → 65/65.

### Changed
- **The faint grey is now readable everywhere, not just on white.** The grey
  carries 12–13px labels (`.hint`, `.view-sub`, `.foot-note`, table captions, KPI
  labels) and measured 3.77:1 on white / 4.19:1 on the page background; it is now
  `#656f68`, 4.6:1 on the darkest surface and 5.2:1 on white. Text meaning "price
  fell" moves from `--down` (3.4:1) to `--down-ink` (6.8:1) in the KPI tiles, item
  tables, category bars, badges and the dashboard's `.down` utility — bars, dots
  and chart lines keep the brighter green.
- **The methodology page no longer ends in roughly 3,000px of blank space.** This
  is a behaviour change: `min-height: 420px` was written for the dashboard's chart
  view but applied to every `.view`, and `methodology.html` has eight of them. The
  floor is now scoped to `#view`. Grepping every template shows `.view` is used
  nowhere else outside the SPA shell, so exactly one page loses the floor — the one
  that was 3,000px too tall.
- `color-scheme: light` is declared, so Chrome/Edge no longer darken form controls
  and scrollbars when the OS is in dark mode.
- Polish visible on every page: a sticky topbar on the server-rendered views; a
  `.pagehead` / `.lede` typography pass; KPI and stat tiles that reveal an accent
  rail and lift on hover; the dashboard chart canvas on the same card surface as
  every other panel; roomier table rows with a sticky-header hairline that cannot
  scroll away; consistent radii and hover states; footer links underlined with a
  gradient so hovering never shifts text.
- `static/explainer.html` uses the shared design tokens (spacing, radii, type
  scale) instead of raw pixel values.

### Fixed
- `static/explainer.html` set `background: var(--panel)` — a token that does not
  exist — so its `<main>` card painted transparent, and its table header row was
  not inside a `<thead>`, so the global header styling never applied and those
  cells had no padding.
- **`ruff check .` was failing on a clean checkout** (7 findings), none of them in
  the files this change touches: the tracked dev helpers `_dump.py` and
  `_routes.py` opened files without context managers, `_routes.py` imported an
  unused `re`, `app.py` and `services/insights.py` had unsorted imports, and
  `services/readmodels.py` called `zip()` without `strict=`. A red gate hides the
  next real finding, so all seven are fixed rather than tolerated.
- **`black --check .` was failing on a clean checkout** as well, for an unrelated
  reason: `requirements-dev.txt` set open floors (`black>=24.0`, `ruff>=0.6`), so
  CI installed whatever was newest, while the committed code is black 24.8.0
  output — the rev pinned in `.pre-commit-config.yaml`. black 25/26 reformats 11
  files, none of them related to this change (`git archive HEAD` + the same
  command reproduces the identical list, so the drift predates it). Both tools are
  now pinned to the pre-commit revs; reformatting 11 unrelated files to please a
  newer black would have been the wrong fix.
- **Two generated scratch files were committed to the repository and are now
  untracked** (left on disk and added to `.gitignore`): `_app_dump.txt`, a 21KB
  numbered dump of `app.py` written by the `_dump.py` dev helper, and
  `verify_full_output.txt`, a 107-byte log containing nothing but a Windows
  `timeout` usage error. `verify_results.txt`, rewritten by every `verify.py` run,
  is ignored before it can join them. Reverting the removals is
  `git reset HEAD _app_dump.txt verify_full_output.txt`.

### Not claimed, honestly
- **No dark theme.** The palette is light-only; `color-scheme: light` only stops
  UA widgets from following the OS, it is not a dark mode.
- `prefers-reduced-motion` is honoured (animations and transitions are disabled),
  but Windows High Contrast / `forced-colors` is neither tested nor handled.
- **`--down-ink` has no human design review.** The ratios are measured and the
  declarations are asserted, but nobody has judged `#04684f` text beside `#009e73`
  bars for feel — contrast proves legibility, not harmony.
- Verification here was headless Chrome renders plus `verify.py`, `test_web.py`,
  pytest, the Node helper tests and mypy. Nobody has opened these pages in a real
  browser during this change, so font smoothing, scrollbars, real `:hover` /
  `:focus-visible` and narrow-width sticky behaviour remain eyeball-check work.
- **The parity tests are not CSS coverage.** They read the stylesheets as text and
  prove that colours agree, declarations exist and ratios hold; nothing here checks
  overrides, specificity or that a rule is actually applied, and no stylelint /
  csstree pass runs.

### Known issues (pre-existing, not introduced here)
- Long tables pin their headers to `.table-wrap`'s own scrollport, not the page:
  `overflow-x: auto` makes the wrapper the scrolling ancestor, so a column header
  does not follow the page scroll. The horizontal row-head pinning the `/data` hint
  promises does work, and the dashboard's `.tablebox` is unaffected because it owns
  a `max-height: 420px` scroller. Fixing the vertical case means dropping the sticky
  header or making the wrapper the scroller; reported rather than changed here.


## [0.5.0] - 2026-09-19

### Added
- **Admin/write protection** (`core/auth.py`): `/api/admin/*` and
  `POST /ingest/next` are closed by default — with `ADMIN_TOKEN` unset only
  strict-loopback callers (local dev, test client) may write and everyone else
  gets `403`; when set, the token is required on every call
  (`X-Admin-Token` or `Authorization: Bearer`), compared with
  `hmac.compare_digest`. `ADMIN_ALLOW_LOCAL=0` closes loopback too.
- **Deployment**: `render.yaml` Blueprint (web service, `/healthz` health
  check, `PYTHON_VERSION`, `FORCE_HTTPS`, `sync: false` admin token) validated
  against Render's published JSON schema, plus `boot.py` — an idempotent
  boot-time seeder for ephemeral free-tier filesystems (seeds an empty DB,
  keeps existing data otherwise).
- Rate-limit response headers (`X-RateLimit-*`) so clients can see their budget.
- `smoke_prod.py` — real-host post-deploy verification (health, readiness,
  public reads, admin protection, security headers, SSE, rate-limit headers);
  exits non-zero and lists failures, supports `--token`/`$ADMIN_TOKEN`,
  `--no-write` and `--wait` for cold instances. Exposed as
  `make smoke-prod URL=...`.
- **Front-end logic tests** (`tests/test_js_helpers.js`, run with `node`): 50
  assertions over the pure helpers that drive the intelligence layer —
  category aggregation, top movers (ordering, no riser/faller crossover),
  the rules-based narrative's exact numbers, sparkline geometry and colour,
  panel edge cases (empty window, all-rise window) and HTML escaping of
  untrusted item names. Wired into CI (a new step) and `make js-test` /
  `make qa`. Verified non-vacuous: a deliberately mutated helper fails the
  suite.
- `?nolive=1` static render mode (live pill shows "Live off"): lets `shot.py`
  take dashboard screenshots — an always-open SSE stream kept headless Chrome
  from ever reaching "network idle", so `--screenshot` hung and `shot.py`
  crashed; it now completes and reports the screenshot size. The alerts DOM
  check is data-aware (chips or the "No alerts" empty state are both valid).
- **Redesigned the site footer** into a four-column card (brand + provenance
  note, live dataset stats, explore links, "under the hood" summary) with a
  bottom bar for licence, disclaimer and status endpoints. The stats are filled
  from `/api/live` at boot and kept fresh by the SSE channel; a failed fetch
  never disturbs the dashboard. Responsive down to mobile.
- **Basket widened from 11 to 28 everyday goods**: tomato, garlic, ginger,
  banana, apple, Irri-6 rice, vegetable ghee, chana/mash/masoor lentils, gram
  flour (besan), packed tea, yogurt, beef, mutton, high-speed diesel and LPG —
  with realistic Jan-2023 PKR anchors and category-appropriate volatility.
  Seed now produces 5,124 approved price points over 183 weeks. Every count in
  tests and verification scripts is derived from `model.ITEMS`, so the basket
  can grow again without breaking anything; the methodology page's basket
  table and the economics explainer's headline/table were regenerated from
  the live data (basket +120.6%, ≈25.4% p.a.; biggest riser: packed tea).
- `shot.py` now captures at 1280×1900 so the redesigned footer is included in
  the README hero screenshot.
- README: CI status badge and a current hero screenshot (the dashboard.png
  render is regenerated by `shot.py`, so it reflects the shipped UI).
- Removed `dashboard_green.png`: a stale, unreferenced render of an older
  color theme (the only tracked screenshot, contradicting the current
  stylesheet); the committed hero is now the live-generated `dashboard.png`
  (previously it was gitignored, so the README image would not have existed
  on GitHub).
- Tests: `tests/test_auth.py` (6 cases covering both postures) and
  `test_rate_limit_enforced`, a negative control that proves the limiter still
  returns the structured 429 envelope.
- README: environment-variable reference table, **Known limitations**, and
  post-deploy smoke-test instructions.

### Changed
- **"Inflation intelligence" layer** (all computed client-side from the visible
  pivot numbers — no backend change, no invented data):
  - **What changed & why** panel: top risers/fallers for the selected window,
    per-category equal-weight bars, and a rules-based plain-language summary
    that cites only the numbers rendered next to it (labelled as such — not AI).
  - **Categories tab**: equal-weight average change per category with up/down
    counts.
  - **My basket tab**: personal basket (ticks saved on the device) showing
    "Your basket: +X% over this window", plus a per-item **watchlist** — while
    the page is open, watched items moving ≥ the alert threshold raise a toast
    and a browser notification (device-local; no account, no email).
  - **Search answer cards**: searching an item shows current price, previous
    price, change, category, last-updated date and an inline sparkline.
  - **1W / 1M presets** alongside 3M/6M/1Y/All; **JSON export** button next to
    CSV (items + metrics + series for the current view); **freshness dot** on
    the latest-week badge (green ≤10 days old, amber when the weekly series
    ages); mobile rules for the new panels.
- `shot.py` DOM checks are now deterministic (static render + virtual-time
  budget) and cover the footer and why-panel.
- **Not added, honestly**: provincial/city comparison — the dataset is a single
  national series, so per-city numbers would be fabricated. Email/push alert
  delivery — needs a backend; the client-side watchlist covers the common case.
- Test isolation: the shared `client` fixture now resets the app singleton's
  rate limiter and response cache per test instead of relying on a clean
  process — the limiter itself stays exercised.
- Dashboard "Update data" now sends the admin token when configured, prompts
  once on `401`, and surfaces the API's error message instead of reporting a
  phantom success on `403`/`429`/`500`.

### Fixed
- CI quality gates that were failing on `main`: removed the syntactically
  invalid `verify_all.py`, fixed 9 ruff findings and 10 mypy errors
  (implicit-`Optional` defaults), and omitted developer scripts from the
  coverage source so the 80% gate reflects the shipped app (39 tests, ~90%).
- Documentation drift: dropped references to `test_pipeline.py`, which is not
  in the repository.
- **CI verified on the real runners**: both matrix legs (Ubuntu, Python
  3.12/3.13) now pass every step — the 19 consecutive runs before these fixes
  were red (lint/format, mypy, tests, live web checks).
- Test isolation (config): the config tests no longer depend on the ambient
  shell — an exported `PORT` used to break
  `test_config_env_file_beats_defaults` locally while passing in CI. A
  `clean_config_env` fixture strips every key `Config` reads, and the test now
  also asserts the documented precedence (real env var > `.env` > default).
- **Note:** the Docker packaging described under 0.4.0 (`Dockerfile`,
  `docker-compose.yml`, `docker/Caddyfile`) is *not* present in this
  repository, so the README no longer implies it is. Adding it for real is
  tracked as follow-up work.

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