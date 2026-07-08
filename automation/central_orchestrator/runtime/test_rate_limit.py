"""Rate limiter unit test."""
import importlib, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def test_rate_limiter_trips_after_max():
    os.environ["AIOS_RL_WINDOW_SEC"] = "10"
    os.environ["AIOS_RL_MAX"] = "5"
    import aios_live_api_server as srv
    importlib.reload(srv)
    ip = "203.0.113.7"
    allowed = sum(0 if srv._rate_limited(ip) else 1 for _ in range(5))
    assert allowed == 5           # first 5 pass
    assert srv._rate_limited(ip)  # 6th is limited

def test_rate_limiter_is_per_ip():
    import aios_live_api_server as srv
    for _ in range(10):
        srv._rate_limited("198.51.100.1")
    assert not srv._rate_limited("198.51.100.2")  # a different IP is unaffected
