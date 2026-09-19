"""core/: config, security headers, error handling, readiness."""

from __future__ import annotations


def test_security_headers_are_set(client):
    r = client.get("/api/items")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_api_404_returns_json_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    body = r.get_json()
    assert body["error"]["code"] == 404
    assert isinstance(body["error"]["message"], str)


def test_browser_404_returns_html_page(client):
    r = client.get("/does-not-exist", headers={"Accept": "text/html"})
    assert r.status_code == 404
    assert b"Back to the tracker" in r.data


def test_readyz_reports_ready_when_data_exists(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ready"
    assert body["approved_points"] > 0


def test_config_reads_env_overrides(clean_config_env):
    from core.config import Config

    clean_config_env.setenv("PORT", "9001")
    clean_config_env.setenv("CACHE_TYPE", "RedisCache")
    cfg = Config.from_env()
    assert cfg.port == 9001
    assert cfg.cache_type == "RedisCache"


def test_config_env_file_beats_defaults(tmp_path, clean_config_env):
    from core import config as config_mod

    env_file = tmp_path / ".env"
    env_file.write_text("PORT=9002\n# comment\nBAD_LINE\n", encoding="utf-8")
    clean_config_env.setattr(config_mod, "BASE_DIR", tmp_path)
    cfg = config_mod.Config.from_env()
    assert cfg.port == 9002

    # Documented precedence: a real environment variable wins over the .env file.
    clean_config_env.setenv("PORT", "9003")
    assert config_mod.Config.from_env().port == 9003
