"""Conversation memory tests (isolated temp DB)."""
import importlib, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def _fresh():
    os.environ["AIOS_MEMORY_DB"] = tempfile.mktemp(suffix=".sqlite3")
    import conversation_memory as m
    importlib.reload(m)
    return m

def test_record_and_history_roundtrip():
    m = _fresh()
    m.record("971500000009", "user", "hi 1BR JVC")
    m.record("971500000009", "assistant", "Luma22 609")
    m.record("971500000009", "user", "price?")
    h = m.history("971500000009")
    assert "Customer: hi 1BR JVC" in h
    assert "You (Omar): Luma22 609" in h
    assert h.strip().endswith("Customer: price?")

def test_isolated_per_contact():
    m = _fresh()
    m.record("971500000001", "user", "A")
    m.record("971500000002", "user", "B")
    assert m.history("971500000001") == "Customer: A"
    assert m.history("971500000002") == "Customer: B"

def test_empty_and_junk_safe():
    m = _fresh()
    assert m.history("") == ""
    assert m.history("971500000003") == ""
    m.record("", "user", "x"); m.record("971500000003", "bogus", "x")
    assert m.history("971500000003") == ""

def test_retention_caps_disk():
    m = _fresh()
    for i in range(80):
        m.record("971500000004", "user", f"msg{i}")
    # prompt window is bounded
    assert len(m.history("971500000004", max_turns=12).splitlines()) == 12
    st = m.stats()
    assert st["ok"] and st["turns"] <= 60
