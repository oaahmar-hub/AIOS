"""Deep health endpoint sanity (no network)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aios_live_api_server as server


def test_deep_health_shape_and_components():
    h = server.get_deep_health(check_brain=False)
    assert h["endpoint"] == "/api/health/deep"
    assert h["status"] in {"healthy", "degraded", "down"}
    for name in ("runtime", "resolver_db", "webhook_auth", "reply_mode", "wasender_send", "fallback_reply"):
        assert name in h["components"]
    assert isinstance(h["issues"], list)


def test_deep_health_flags_hold_mode(monkeypatch):
    monkeypatch.setattr(server, "WHATSAPP_REPLY_MODE", "hold")
    h = server.get_deep_health(check_brain=False)
    assert h["components"]["reply_mode"]["ok"] is False
    assert any("hold" in i for i in h["issues"])


def test_deep_health_brain_skipped_is_none():
    h = server.get_deep_health(check_brain=False)
    assert h["components"]["brain_n8n_openai"]["ok"] is None
