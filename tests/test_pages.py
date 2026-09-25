"""Tests for the server-rendered pages, the analytics services and the v1 API.

The pages are asserted on real content (item names, statistics, provenance,
insight sections), not just status codes - a page that renders an empty shell
is a failure, not a pass.
"""

from __future__ import annotations

import pytest

import model

PAGES = [
    ("/items", "All tracked items"),
    ("/item/onion", "Onion"),
    ("/compare", "Choose what to compare"),
    ("/insights", "Headline"),
    ("/alerts", "What an alert does and does not tell you"),
    ("/data", "Observation matrix"),
    ("/status", "Approval state"),
    ("/docs", "Machine-readable contract"),
    ("/admin/review", "Why this queue exists"),
]


@pytest.mark.parametrize("path,marker", PAGES)
def test_every_page_renders_with_its_content(client, path, marker):
    r = client.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    body = r.get_data(as_text=True)
    assert marker in body, f"{path} is missing expected content: {marker!r}"
    # Every page is server-rendered: the shared shell must be present.
    assert "Price Pulse" in body
    assert 'id="main"' in body


@pytest.mark.parametrize("path,marker", [("/", "Pakistan Inflation"), ("/methodology", "Index")])
def test_legacy_pages_still_render(client, path, marker):
    """The dashboard and methodology page predate the shell and must keep working."""
    r = client.get(path)
    assert r.status_code == 200
    assert marker in r.get_data(as_text=True)


def test_pages_need_no_javascript(client):
    """The new pages must not depend on a CDN or client-side JS to show data."""
    for path, _marker in PAGES:
        body = client.get(path).get_data(as_text=True)
        assert "<script" not in body, f"{path} ships inline/remote script tags"


def test_items_page_lists_every_tracked_item(client):
    import services.readmodels as rm

    body = client.get("/items").get_data(as_text=True)
    for row in rm.all_items(__import__("db").connect()):
        assert row["name"] in body
    assert "spark" in body  # sparklines rendered server-side


def test_item_detail_page_has_stats_chart_and_provenance(client):
    body = client.get("/item/onion").get_data(as_text=True)
    assert "Price history" in body
    assert "<svg" in body                      # the chart is server-rendered
    assert "Calculated facts" in body
    assert "Possible contributing factors" in body
    assert "Provenance" in body
    assert "seed" in body                      # a real source value


def test_unknown_item_returns_404(client):
    r = client.get("/item/not-a-real-item")
    assert r.status_code == 404
    assert "does not exist" in r.get_data(as_text=True)


def test_freshness_banner_reports_dates_and_coverage(client):
    import db

    con = db.connect()
    last = con.execute(
        "SELECT MAX(date) AS d FROM prices WHERE status = 'approved'"
    ).fetchone()["d"]
    con.close()
    body = client.get("/items").get_data(as_text=True)
    assert "Data updated:" in body
    assert last in body


def test_review_flow_approves_pending_points(client):
    """A point held back by validation becomes public only after review.

    Note on `for_week` semantics:
        POST /ingest/next takes an arbitrary ISO date (e.g. "2026-12-05"), but
        snaps it to the model's 7-day Sunday alignment grid (`model.START_DATE + k * 7d`).
        Therefore, the returned `for_week` date (e.g. "2026-11-29") is the actual
        timestamp stored in the database, NOT the raw request date.
        Always compare against `ingested["for_week"]` rather than the input date.
    """
    n = len(model.ITEMS)
    ingested = client.post(
        "/ingest/next", json={"date": "2026-12-05", "auto_approve": False}
    ).get_json()
    week = ingested["for_week"]
    assert ingested["counts"]["pending"] == n

    # Held back: not in the public series, but visible on the review page.
    series = client.get("/api/series?start=2026-11-01").get_json()
    assert all(row["date"] < week for row in series)
    page = client.get("/admin/review").get_data(as_text=True)
    assert week in page
    assert "held for manual review" in page

    r = client.post("/admin/review/approve", data={"all": "1"}, follow_redirects=True)
    assert r.status_code == 200
    assert "approved" in r.get_data(as_text=True)
    assert client.get("/api/admin/pending").get_json() == []
    series = client.get("/api/series?start=2026-11-01").get_json()
    assert any(row["date"] == week for row in series)


def test_review_reject_keeps_points_out_of_the_index(client):
    n = len(model.ITEMS)
    ingested = client.post(
        "/ingest/next", json={"date": "2026-12-05", "auto_approve": False}
    ).get_json()
    week = ingested["for_week"]
    r = client.post("/admin/review/reject", data={"all": "1"}, follow_redirects=True)
    assert r.status_code == 200
    assert "rejected" in r.get_data(as_text=True)
    status = client.get("/api/status").get_json()["status"]
    assert status["pending_points"] == 0
    assert status["rejected_points"] >= n
    series = client.get("/api/series?start=2026-11-01").get_json()
    assert all(row["date"] != week for row in series)


def test_review_approves_only_the_selected_points(client):
    n = len(model.ITEMS)
    client.post("/ingest/next", json={"date": "2026-12-05", "auto_approve": False})
    pending = client.get("/api/admin/pending").get_json()
    assert len(pending) == n
    chosen = pending[0]
    r = client.post(
        "/admin/review/approve", data={"ids": [str(chosen["id"])]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    left = client.get("/api/admin/pending").get_json()
    assert len(left) == n - 1
    assert all(row["id"] != chosen["id"] for row in left)


def test_review_page_requires_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    assert client.get("/admin/review").status_code == 401
    assert client.get("/admin/review", headers={"X-Admin-Token": "s3cret"}).status_code == 200
    assert client.get("/admin/review", headers={"X-Admin-Token": "wrong"}).status_code == 401
    # The API aliases are protected identically - no bypass via /api/v1.
    assert client.get("/api/v1/admin/pending").status_code == 401


# ---------------------------------------------------------------------------
# Analytics + API contracts
# ---------------------------------------------------------------------------


def test_insights_separate_facts_from_context(client):
    payload = client.get("/api/insights").get_json()
    assert payload["window"]["items"] == len(model.ITEMS)
    basket = payload["basket"]
    assert basket["facts"], "the headline must carry calculated facts"
    assert "not established" in payload["method"]
    for card in payload["risers"] + payload["fallers"]:
        assert card["facts"]
        assert card["context"], "context factors must be labelled, not omitted"
        assert card["link"].startswith("/item/")
        assert card["slug"]


def test_insights_threshold_controls_breaches(client):
    low = client.get("/api/insights?threshold=1").get_json()
    high = client.get("/api/insights?threshold=95").get_json()
    assert len(low["breaches"]) >= len(high["breaches"])
    assert high["breaches"] == []


def test_item_detail_api_shape(client):
    body = client.get("/api/items/onion").get_json()
    assert body["item"]["slug"] == "onion"
    assert body["statistics"]["weeks"] > 1
    assert len(body["history"]) == body["statistics"]["weeks"]
    assert body["provenance"][0]["points"] > 0
    assert body["provenance"][0]["source"]
    assert body["contribution_pct"] is not None


def test_item_detail_api_unknown_slug_is_404_envelope(client):
    r = client.get("/api/items/nope")
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == 404


def test_compare_api_requires_both_starts(client):
    r = client.get("/api/compare")
    assert r.status_code == 400
    assert r.get_json()["error"]["hint"]


def test_compare_api_returns_deltas(client):
    body = client.get(
        "/api/compare?a_start=2025-01-04&a_end=2025-06-28"
        "&b_start=2026-01-03&b_end=2026-06-27"
    ).get_json()
    assert body["rows"]
    first = body["rows"][0]
    assert {"name", "slug", "a_pct", "b_pct", "delta"} <= set(first)
    assert first["delta"] == pytest.approx(first["b_pct"] - first["a_pct"], abs=0.01)


def test_status_api_exposes_provenance_and_audit_log(client):
    body = client.get("/api/status").get_json()
    assert body["status"]["approved_points"] > 0
    assert body["status"]["freshness"]
    assert body["provenance"][0]["method"]
    assert isinstance(body["ingestions"], list)


def test_export_json_is_self_describing(client):
    body = client.get("/api/export.json").get_json()
    assert body["meta"]["dataset"]
    assert body["meta"]["observations"] == len(body["observations"])
    assert body["meta"]["license"] == "MIT"
    assert len(body["items"]) == len(model.ITEMS)
    assert body["basket_index"]
    assert body["provenance"]


def test_alerts_csv_matches_alerts_count(client):
    rows = client.get("/api/alerts?threshold=5").get_json()
    csv_body = client.get("/api/alerts.csv?threshold=5").get_data(as_text=True)
    assert csv_body.splitlines()[0] == "item,category,date,previous_price,price,pct_change"
    assert len(csv_body.strip().splitlines()) - 1 == len(rows)


def test_series_csv_still_works(client):
    body = client.get("/api/series.csv").get_data(as_text=True)
    assert body.splitlines()[0] == "item,date,price"


def test_versioned_aliases_match_the_canonical_api(client):
    canonical = client.get("/api/metrics?start=2025-07-01").get_json()
    alias = client.get("/api/v1/metrics?start=2025-07-01")
    assert alias.status_code == 200
    assert alias.get_json() == canonical
    assert alias.headers["X-API-Version"]


def test_alias_ordering_registers_version_and_openapi(client):
    """Ensure late-registered /api/version and OpenAPI routes get aliased to /api/v1/*.

    Guards against an alias-pass ordering regression where /api/v1/version or
    /api/v1/openapi.json fail to register because aliasing ran before their endpoints.
    """
    v_canon = client.get("/api/version")
    v_alias = client.get("/api/v1/version")
    assert v_canon.status_code == 200
    assert v_alias.status_code == 200
    canon_data = v_canon.get_json()
    alias_data = v_alias.get_json()
    assert canon_data["api_version"] == alias_data["api_version"]
    assert canon_data["capabilities"] == alias_data["capabilities"]
    assert alias_data["requested_path"] == "/api/v1/version"

    spec_alias = client.get("/api/v1/openapi.json")
    assert spec_alias.status_code == 200
    assert spec_alias.get_json()["openapi"] == "3.1.0"


def test_version_endpoint_advertises_capabilities(client):
    body = client.get("/api/version").get_json()
    assert body["api_version"]
    assert body["capabilities"]["live_stream"] == "/api/stream"
    assert "/insights" in body["capabilities"]["pages"]


def test_openapi_documents_only_registered_paths(client):
    """Docs and routes must not drift: every documented path must exist."""
    import app as app_mod
    import services.openapi as openapi

    registered = {
        rule.rule.replace("<slug>", "onion") for rule in app_mod.app.url_map.iter_rules()
    }
    for path in openapi.documented_paths():
        want = path.replace("{slug}", "onion")
        assert want in registered, f"documented but not registered: {path}"

    spec = client.get("/api/v1/openapi.json").get_json()
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"]
    assert spec["paths"]
    # The admin surface must be documented as requiring a token.
    assert spec["paths"]["/api/admin/approve"]["post"]["security"] == [{"adminToken": []}]


def test_docs_page_lists_every_endpoint(client):
    import services.openapi as openapi

    body = client.get("/docs").get_data(as_text=True)
    for entry in openapi.ENDPOINTS:
        assert entry["path"] in body, f"/docs is missing {entry['path']}"


def test_svg_chart_degrades_gracefully(client):
    from web import svg

    assert "No approved observations" in svg.chart([])
    assert "Only one observation" in svg.chart([{"name": "x", "values": [1.0]}])
    chart = svg.chart([{"name": "x", "values": [1.0, 2.0, 3.0]}], ["a", "b", "c"])
    assert chart.startswith("<svg") and 'role="img"' in chart and "aria-label" in chart
    assert svg.sparkline([]) .startswith("<span")
    assert svg.bars([]).startswith("<p")
