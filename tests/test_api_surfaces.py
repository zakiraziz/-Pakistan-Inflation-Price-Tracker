"""Coverage for the remaining API surfaces, alert logic, and CSV source."""
from __future__ import annotations

import csv
import os

import pytest


@pytest.fixture()
def client(tmp_db, monkeypatch):
    import seed
    con, path = tmp_db
    seed.load(con)
    import app as app_mod
    app_mod.app.config["TESTING"] = True
    yield app_mod.app.test_client()
    con.close()


def test_dashboard_and_read_apis(client):
    assert client.get("/").status_code == 200

    series = client.get("/api/series?start=2026-01-01").get_json()
    assert series and {"name", "date", "price"} <= set(series[0])

    idx = client.get("/api/index?start=2026-01-01").get_json()
    assert idx[0]["index"] == 100.0

    infl = client.get("/api/inflation?start=2026-01-01").get_json()
    assert infl["weeks"] >= 2 and infl["yoy_pct"] is not None

    piv = client.get("/api/pivot?start=2026-01-01&items=1,2").get_json()
    assert len(piv["items"]) == 2
    assert len(piv["items"][0]["prices"]) == len(piv["dates"])

    alerts = client.get("/api/alerts?threshold=50").get_json()
    assert isinstance(alerts, list)

    r = client.get("/api/series.csv?items=1,2")
    assert r.status_code == 200
    assert r.data.startswith(b"item,date,price")


def test_reject_specific_id_without_pending(client):
    r = client.post("/api/admin/reject", json={"ids": [1]})
    assert r.status_code == 200
    assert r.get_json()["rejected"] == 0


def test_alerts_only_consider_approved_data(client):
    from alert import compute_alerts, latest_alerts
    import db as db_mod

    con = db_mod.connect()
    # stage (do not approve) a huge jump -> alerts must ignore it
    con.execute("INSERT INTO prices (item_id, date, price, source, method, "
                "collected_at, status) VALUES (1, '2026-08-01', 99999.0, "
                "'test', 'unit-test', 'now', 'pending')")
    con.commit()
    compute_alerts(con, threshold=5.0)
    assert con.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"] == 0
    rows = latest_alerts(con, threshold=5.0)
    assert all(r["date"] <= "2026-06-28" for r in rows)
    con.close()


def test_csv_source_parses_points(tmp_path):
    from ingest.sources import CSVSource
    path = os.path.join(tmp_path, "points.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["item", "date", "price", "method"])
        writer.writeheader()
        writer.writerow({"item": "Rice", "date": "2026-01-01", "price": "100.5",
                         "method": "csv-import"})
    points = CSVSource(path).fetch()
    assert len(points) == 1
    assert points[0]["item"] == "Rice"
    assert points[0]["price"] == 100.5
    assert points[0]["method"] == "csv-import"


def test_pbs_source_requires_configuration():
    from ingest.sources import PBSWebSource
    with pytest.raises(NotImplementedError):
        PBSWebSource().fetch()


def test_healthz_reports_pending_queue(client):
    client.post("/ingest/next", json={"date": "2026-12-01", "auto_approve": False})
    body = client.get("/healthz").get_json()
    assert body["pending_points"] == 11
    assert body["status"] == "ok"