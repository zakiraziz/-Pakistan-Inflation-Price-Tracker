# Pakistan Inflation / Price Tracker (Z5)

A small full-stack service that **ingests price data, stores a time-series,
charts trends over time with date filters, alerts on price jumps, and explains
what the data shows about inflation** — for a representative basket of
everyday goods in Pakistan.

Built on the Z2 backend skills (backend + data pipeline) with a **Python /
Flask + SQLite + Chart.js** stack. SQLite is used instead of Postgres so the
project has **zero external-server dependency** and the pipeline runs anywhere
reproducibly.

## Features / Definition of Done

| Requirement | Status |
|---|---|
| **Data pipeline runs reproducibly** | ✅ `seed.py` regenerates the same DB from `model.py`; `test_pipeline.py` verifies determinism |
| **Charts render with filters** | ✅ Chart.js dashboard with date-range presets, category + item filters, and a "Basket cost index" view |
| **The explainer is clear and correct** | ✅ `explainer.md` (and `/static/explainer.html`) — stats computed from the data |

Bonus: ✅ price-jump alerts (week-over-week threshold) · ✅ basket comparison ·
✅ item search · ✅ one-click CSV export · ✅ "Update data" ingest button ·
✅ live KPI cards (incl. annualized + year-over-year inflation) ·
✅ Compare bar-chart view · ✅ Data table view.

## Production readiness

**Data provenance & approval workflow** — every price point stores *where it
came from* and *how it was collected*:

| Column | Meaning |
|---|---|
| `source` | which source produced it (`seed`, `csv`, `weekly-job`, `pbs-web`…) |
| `method` | how it was fetched/parsed (`generator`, `csv-import`, `html/csv scrape`) |
| `collected_at` | UTC timestamp of collection |
| `status` | `approved` / `pending` / `rejected` |
| `review_note` | why it was held (e.g. "suspicious +25% week-over-week") |

`validators.classify()` decides the status: normal swings are auto-approved,
implausible ones are held **pending** and are *excluded from every public
endpoint* until a human approves or rejects them:

```
POST /ingest/next {"auto_approve": false}   # stage everything for review
GET  /api/admin/pending                     # review queue
POST /api/admin/approve {"ids":[..]} | {"all":true}
POST /api/admin/reject  {"ids":[..]} | {"all":true}
```

Every batch is also written to the `ingestions` audit table
(source, method, ran_at, counts) — so the index is fully reproducible and
auditable.

**Architecture**

```mermaid
flowchart LR
  S[Sources<br/>seed · CSV · PBS scrape] --> V[validators<br/>sanity checks]
  V --> P[ingest.pipeline<br/>provenance + status]
  P --> DB[(items / prices /<br/>ingestions / alerts)]
  P --> A[alert.py<br/>price-jump alerts]
  SCH[scheduler.py<br/>APScheduler cron] --> P
  J[job.py / POST /ingest/next] --> P
  DB --> API[app.py<br/>cached + rate-limited API]
  API --> UI[dashboard<br/>KPIs · Trends · Compare · Data]
```

**Caching, rate limiting, health & logging**

- `flask-caching` caches the read APIs (SimpleCache by default; set
  `CACHE_TYPE=RedisCache` + `REDIS_URL` to move to Redis). Cached responses
  are invalidated on every ingest/approval, so data is never stale.
- `flask-limiter` rate-limits reads (`RATE_LIMIT_DEFAULT`) and writes
  (`RATE_LIMIT_WRITE`).
- `GET /healthz` reports status, item count, latest approved date, pending
  queue size and uptime (200 / 503) for uptime monitoring.
- `log.py` emits JSON-lines logs (`LOG_LEVEL`, `JSON_LINES=0` for text).

**Scheduling**

```bash
python scheduler.py --once   # one ingest run (CI-friendly)
python scheduler.py          # long-running APScheduler (Sat 06:00 UTC)
```

In production run the scheduler as its own process/container (or use cron /
GitHub Actions / Celery beat) rather than inside the web process.

**Configuration (env vars)**

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `5010` | web port |
| `CACHE_TYPE` / `CACHE_TTL` | `SimpleCache` / `300` | cache backend + TTL |
| `RATE_LIMIT_DEFAULT` / `RATE_LIMIT_WRITE` | `300/min` / `60/min` | rate limits |
| `LOG_LEVEL` / `JSON_LINES` | `INFO` / `1` | logging |

## Project layout

```
model.py          # item definitions + deterministic price generator (data source)
db.py             # storage layer: items, prices (+ provenance/status), ingestions, alerts
validators.py     # sanity checks -> approved / pending / rejected
ingest/           # sources (SeedSource, CSVSource, PBSWebSource) + pipeline
seed.py           # ingest step: rebuild an approved baseline (reproducible)
job.py            # weekly ingest job (validated pipeline + alerts), idempotent
scheduler.py      # APScheduler cron wrapper for the ingest job
alert.py          # price-jump alert logic (approved data only)
analyze.py        # headline stats (used by the explainer)
app.py            # Flask API: cached, rate-limited, /healthz, admin approval
log.py            # structured (JSON) logging
tests/            # pytest suite (fixtures, validators, pipeline, app/caching)
test_pipeline.py  # dependency-free end-to-end pipeline tests
test_web.py       # boots the real server and checks every route
shot.py           # headless-Chrome render QA (screenshot + DOM assertions)
static/           # dashboard (Chart.js) + standalone explainer page
explainer.md      # the written economics explainer
pyproject.toml    # pytest / coverage / ruff / black / mypy config
```

## Staged roadmap (honest status)

Done and verified in this repo: provenance + approval workflow, validated
ingestion pipeline (CSV + generator sources), APScheduler scheduling, caching
with invalidation, rate limiting, `/healthz`, structured logging, pytest +
coverage, CI config, lint/format/type config, pre-commit.

Needs infrastructure not present here (documented, designed for, not yet run):
- **Postgres + Alembic migrations** — the DDL is Postgres-compatible; provision
  a Postgres, point `DATABASE_URL` at it, and introduce Alembic as the schema
  manager (current code still self-migrates via `init_db()` for SQLite).
- **Redis cache backend** — set `CACHE_TYPE=RedisCache` (+ `REDIS_URL`).
- **Live PBS scraping** — `ingest/sources.py:PBSWebSource` is the scaffold;
  wire an endpoint with the publisher's permission + network access.
- **Forecasting / STL / change-point detection** and **Docker + deploy** are
  the next polish steps on this foundation.

## Quick start

```bash
# 1. create a virtualenv and install Flask
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows
# .venv/bin/python ...                                       # macOS/Linux

# 2. ingest data into SQLite (reproducible)
.venv/Scripts/python seed.py

# 3. (optional) simulate the "job that adds new data over time"
.venv/Scripts/python job.py --date 2026-09-12

# 4. run the server
.venv/Scripts/python app.py
# open http://127.0.0.1:5010
```

Run the checks:

```bash
.venv/Scripts/python test_pipeline.py   # all tests should pass
.venv/Scripts/python analyze.py         # headline numbers
```

## How the data pipeline works

1. **Ingest** — `seed.py` reads the deterministic generator in `model.py`
   (11 items, weekly prices Jan 2023 → mid/late 2026) and writes
   `data/inflation.db`. Deterministic means re-seeding reproduces the same data.
2. **Store** — tables `items`, `prices` (item_id, date, price) and `alerts`.
3. **Job** — `job.py` appends the *next* weekly observation for every item and
   recomputes alerts. It is idempotent, so you can schedule it via cron /
   Task Scheduler / GitHub Actions:
   - Windows Task Scheduler: `python job.py`
   - cron: `0 6 * * 6 cd <repo> && .venv/bin/python job.py`
4. **Serve** — `app.py` exposes the API and the dashboard.

## API

| Route | Description |
|---|---|
| `GET /` | dashboard |
| `GET /api/items` | list tracked items |
| `GET /api/series?start=&end=&items=` | filtered time-series (ISO dates, CSV item ids) |
| `GET /api/index?start=&end=&items=` | equal-weight basket cost index (100 at range start) |
| `GET /api/metrics?start=&end=&items=` | summary stats for the window (drives the KPI cards) |
| `GET /api/inflation?start=&end=&items=` | annualised / weekly / year-over-year inflation |
| `GET /api/pivot?start=&end=&items=` | item × date matrix + basket index (Trends/Compare/Data) |
| `GET /api/series.csv?...` | download the current view as CSV |
| `GET /api/alerts?threshold=5&start=&end=` | price-jump alerts within the window |
| `POST /ingest/next` | run the ingest job on demand (see the "Update data" button) |

## Dashboard

A full responsive dashboard (Flask + SQLite + Chart.js, Inter font):

- **Hero header** with a live "latest price" badge and an **Update data** ingest button.
- **KPI cards** — Basket cost change, **Annualised inflation**, **Year-over-year**,
  and **price-jump count** for the selected window.
- **Three views (tabs):**
  - **Trends** — line charts of each item's prices, or the whole-basket cost index.
  - **Compare** — horizontal bar chart of % change since the range start (who rose most).
  - **Data** — sortable table (start / latest / change per item).
- **Controls** — date presets (3M / 6M / 1Y / All) + custom range, alert threshold, CSV export.
- **Basket filters** — category chips, item checklist, and a live **search box**.
- **Alerts panel** — items that jumped ≥ the threshold week-on-week, largest jump highlighted.
- Loading spinners, friendly empty states, toasts, custom scrollbars, mobile layout.

## Checking it works

```bash
python seed.py                       # rebuild an approved baseline
pytest --cov --cov-fail-under=80     # unit + integration tests with coverage
python test_pipeline.py              # dependency-free pipeline checks
python test_web.py                   # boots the real server, hits every route
python scheduler.py --once           # one real ingestion run
python shot.py                       # (optional) headless-Chrome render QA
```

CI (`.github/workflows/ci.yml`) runs lint → format check → type check →
seed → tests with coverage → live web checks on every push.

## Deploying

Because everything is a single `app.py` with a flat-file DB:

- **Render / Railway** — set build command `pip install -r requirements.txt`,
  start command `python app.py`. Note: free tiers give an ephemeral
  filesystem — run `seed.py` as a one-off start command so `data/` (or an
  attached persistent disk) is populated, and schedule `job.py` externally.
- **Any VPS / free host** — copy the folder, install requirements, run
  `python app.py` behind a reverse proxy (e.g. Caddy/nginx).

## Data caveat

The series is a *representative manual dataset* modelled on Pakistan's real CPI
experience (high inflation in 2023 easing to disinflation by 2025–26, volatile
fresh produce, high energy pass-through) — it is *not* the official PBS series.
Swap `model.py` for a permitted public API/CSV to go live; the pipeline,
storage and charts don't change. Only collect data where permitted.