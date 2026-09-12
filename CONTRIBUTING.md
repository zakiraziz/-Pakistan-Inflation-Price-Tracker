# Contributing

Thanks for considering a contribution. This project follows a few rules that
keep it easy to review and safe to run.

## Getting set up

```bash
git clone <repo-url> && cd <repo>
python -m venv .venv
make setup          # installs runtime + dev dependencies
make seed           # build the approved baseline database
make test           # pytest (coverage gate: 80%)
make dev            # http://127.0.0.1:5010
```

On Windows use `.venv\Scripts\python` (the Makefile handles this for `make`
targets).

## Ground rules

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
  — `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`. Explain *why*
  in the body when the change is not obvious.
- **Small PRs**: one logical change per pull request.
- **Tests**: behaviour changes need a test that fails without them. Test
  names read like specs, e.g.
  `test_inflation_api_returns_annualized_percent_for_valid_range`.
- **Style**: `make format` (black) and `make lint` (ruff) must pass; types
  via `make type` (mypy). Pre-commit hooks run these for you:
  `pip install pre-commit && pre-commit install`.
- **No secrets**: configuration comes from environment variables
  (see `.env.example`).
- **Data integrity**: ingestion changes must go through
  `ingest/pipeline.py` so provenance and approval status are recorded.
  Never write directly to `prices` in feature code.

## Pull request checklist

- [ ] `make qa` passes locally (lint, types, coverage, live web checks)
- [ ] New/changed endpoints are covered by tests
- [ ] Public data endpoints only read `status = 'approved'` rows
- [ ] `CHANGELOG.md` updated (Under / Added / Changed / Fixed)
- [ ] Docs updated if behaviour or configuration changed

## Reporting issues

Include: what you did, what you expected, what happened, and — for data
questions — the exact query and the `source`/`status` of the affected rows.

## License

MIT — see [LICENSE](LICENSE).