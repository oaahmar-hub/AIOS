#!/usr/bin/env python3
"""Live WasenderAPI relay for AIOS WhatsApp auto-replies.

This service receives WasenderAPI webhook POSTs, normalizes them using the AIOS
gateway processor, and sends safe auto-replies back through WasenderAPI.

It is intentionally small and single-purpose so it can run alongside the
existing AIOS stack when n8n write access is unavailable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

from whatsapp_provider_gateway import process
from conversation_state_engine import DEFAULT_DB, apply_state


AUTOMATION_DIR = Path(__file__).resolve().parents[2]
LEAD_PIPELINE_RUNTIME = AUTOMATION_DIR / "lead_pipeline_os" / "runtime"
if str(LEAD_PIPELINE_RUNTIME) not in sys.path:
    sys.path.insert(0, str(LEAD_PIPELINE_RUNTIME))

try:
    from lead_pipeline_engine import build as build_pipeline  # type: ignore
except Exception:  # pragma: no cover - optional bridge
    build_pipeline = None


WASENDER_API_BASE = "https://www.wasenderapi.com"
WASENDER_SEND_PATH = "/api/send-message"
WASENDER_MESSAGE_INFO_PATH = "/api/messages/{msg_id}/info"
WASENDER_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
DEFAULT_BIND_HOST = os.getenv("AIOS_RELAY_HOST", "127.0.0.1")
DEFAULT_BIND_PORT = int(os.getenv("AIOS_RELAY_PORT", "8999"))
WEBHOOK_PATH = os.getenv("AIOS_WEBHOOK_PATH", "/webhook/whatsapp/provider/gateway")
CONVERSATION_DB = Path(os.getenv("AIOS_CONVERSATION_DB", str(DEFAULT_DB)))
SEND_LOCK = threading.Lock()
LAST_SEND_AT = 0.0
MIN_SEND_INTERVAL_SECONDS = 5.2
LOG_PATH = os.getenv(
    "AIOS_RELAY_LOG",
    os.path.join(os.path.dirname(__file__), "../reports/wasender_live_relay.log.jsonl"),
)


def _keychain_secret(service: str) -> str:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", service],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


API_KEY = os.getenv("WASENDER_API_KEY", "").strip() or _keychain_secret("AIOS Wasender API Key")
WEBHOOK_SECRET = os.getenv("WASENDER_WEBHOOK_SECRET", "").strip() or _keychain_secret("AIOS Wasender Webhook Secret")


def _append_log(obj: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(LOG_PATH)), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _append_bridge_log(obj: dict) -> None:
    bridge_log = os.path.join(os.path.dirname(os.path.abspath(LOG_PATH)), "wasender_live_relay.bridge.jsonl")
    os.makedirs(os.path.dirname(os.path.abspath(bridge_log)), exist_ok=True)
    with open(bridge_log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _parse_body(raw: bytes, content_type: str) -> dict:
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace").strip()
    if "application/json" in (content_type or "") or text.startswith("{"):
        return json.loads(text)
    parsed = parse_qs(text, keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}


def _verify_signature(handler: BaseHTTPRequestHandler, raw_body: bytes) -> bool:
    if not WEBHOOK_SECRET:
        return True
    header = (handler.headers.get("X-Webhook-Signature") or "").strip()
    return bool(header and header == WEBHOOK_SECRET)


def _send_reply(phone: str, text: str) -> tuple[bool, str]:
    if not API_KEY:
        return False, "missing_api_key"
    payload = json.dumps({"to": phone, "text": text}).encode("utf-8")
    req = Request(
        WASENDER_API_BASE + WASENDER_SEND_PATH,
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://wasenderapi.com",
            "Referer": "https://wasenderapi.com/whatsapp/manage/94234",
            "User-Agent": WASENDER_BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, f"{resp.status}:{body[:300]}"
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if getattr(e, "fp", None) else ""
        if e.code == 429:
            return False, f"http_error:429:{body[:300]}"
        return False, f"http_error:{e.code}:{body[:300]}"
    except URLError as e:
        return False, f"url_error:{e.reason}"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"error:{e}"


def _lookup_message_info(msg_id: str) -> tuple[bool, object]:
    if not API_KEY or not msg_id:
        return False, "missing_api_key_or_msg_id"
    req = Request(
        WASENDER_API_BASE + WASENDER_MESSAGE_INFO_PATH.format(msg_id=msg_id),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://wasenderapi.com",
            "Referer": "https://wasenderapi.com/",
            "User-Agent": WASENDER_BROWSER_UA,
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if getattr(e, "fp", None) else ""
        return False, f"http_error:{e.code}:{body[:300]}"
    except URLError as e:
        return False, f"url_error:{e.reason}"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"error:{e}"


def _message_status_from_detail(detail: str) -> tuple[str | None, str | None]:
    try:
        if not detail.startswith("200:"):
            return None, None
        payload = json.loads(detail.split("200:", 1)[1])
        data = payload.get("data") or {}
        msg_id = str(data.get("msgId") or data.get("id") or "")
        status = data.get("status")
        return msg_id or None, str(status) if status is not None else None
    except Exception:
        return None, None


def _poll_delivery_status(msg_id: str, attempts: int = 3, interval_seconds: float = 4.0) -> tuple[bool, str, object]:
    """Return whether the message reached device delivery/read.

    Wasender status codes:
    2 = sent from server but not yet delivered
    3 = delivered
    4 = read
    """
    last_detail: dict | str = "not_attempted"
    last_status: str | None = None
    for attempt in range(attempts):
        ok, detail = _lookup_message_info(msg_id)
        last_detail = detail
        if not ok:
            return False, "lookup_failed", detail
        data = detail.get("data") or {}
        last_status = str(data.get("status")) if data.get("status") is not None else None
        if last_status in {"3", "4"}:
            return True, last_status, detail
        if attempt + 1 < attempts:
            time.sleep(interval_seconds)
    return False, last_status or "unknown", last_detail


def _send_reply_with_retry(phone: str, text: str) -> tuple[bool, str]:
    global LAST_SEND_AT
    if not phone or not text:
        return False, "missing_destination_or_text"

    attempts = 0
    last_detail = "not_attempted"
    while attempts < 2:
        attempts += 1
        with SEND_LOCK:
            now = time.monotonic()
            wait_for = max(0.0, MIN_SEND_INTERVAL_SECONDS - (now - LAST_SEND_AT))
            if wait_for > 0:
                time.sleep(wait_for)
            success, detail = _send_reply(phone, text)
            if success:
                LAST_SEND_AT = time.monotonic()
                msg_id, sent_status = _message_status_from_detail(detail)
                if msg_id:
                    delivered, delivery_status, delivery_detail = _poll_delivery_status(msg_id)
                    if delivered:
                        return True, f"{detail} | delivery:{delivery_status}"
                    return True, f"{detail} | delivery:{delivery_status}"
                return True, detail
            last_detail = detail
            if "http_error:429" not in detail:
                return False, detail
            retry_after = 5.0
            try:
                marker = '"retry_after":'
                if marker in detail:
                    tail = detail.split(marker, 1)[1]
                    retry_after = float("".join(ch for ch in tail if ch.isdigit() or ch == ".")[:5] or "5")
            except Exception:
                retry_after = 5.0
        time.sleep(max(1.0, retry_after))
    return False, last_detail


class RelayHandler(BaseHTTPRequestHandler):
    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json_response(200, {"ok": True, "service": "wasender-live-relay"})
            return
        self._json_response(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != WEBHOOK_PATH:
            self._json_response(404, {"ok": False, "error": "not_found", "path": self.path})
            return

        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        if not _verify_signature(self, raw):
            _append_log({"event": "reject", "reason": "invalid_signature", "path": self.path})
            self._json_response(401, {"ok": False, "error": "invalid_signature"})
            return

        payload = _parse_body(raw, self.headers.get("Content-Type", ""))
        _append_log({"event": "inbound", "path": self.path, "payload": payload})
        try:
            result = process(payload)
        except Exception as e:
            _append_log({"event": "process_error", "error": str(e), "payload": payload})
            self._json_response(500, {"ok": False, "error": "process_failed", "detail": str(e)})
            return

        try:
            state_result = apply_state(result, CONVERSATION_DB)
        except Exception as e:
            _append_log({"event": "state_error", "error": str(e), "result": result})
            state_result = {
                "state_decision": {
                    "final_mode": "OMAR_APPROVAL_REQUIRED",
                    "send_allowed": False,
                    "reason": f"state_error:{e}",
                    "reply_text": "",
                },
                "dashboard_metrics": {"state_error": str(e)},
            }

        reply = result.get("reply") or {}
        event = result.get("provider_event") or {}
        state_decision = state_result.get("state_decision") or {}
        sent = None
        send_status = "not_attempted"

        if state_decision.get("final_mode") == "NON_ACTIONABLE_IGNORED":
            sent = {"success": False, "detail": "non_actionable_event_ignored", "to": str(event.get("from_phone") or "")}
            send_status = "ignored"
        elif state_decision.get("send_allowed") is True:
            destination = str(event.get("from_phone") or "").replace("+", "").replace(" ", "")
            reply_text = str(state_decision.get("reply_text") or reply.get("text") or "").strip()
            if destination and reply_text:
                success, detail = _send_reply_with_retry(destination, reply_text)
                sent = {"success": success, "detail": detail, "to": destination}
                send_status = "sent" if success else "failed"
            else:
                sent = {"success": False, "detail": "missing_destination_or_text", "to": destination}
                send_status = "failed"
        else:
            sent = {"success": False, "detail": "approval_required"}
            send_status = "held"

        pipeline = None
        if build_pipeline and state_decision.get("final_mode") not in {"NON_ACTIONABLE_IGNORED", "DUPLICATE_SUPPRESSED"} and result.get("classification", {}).get("actionable", True):
            try:
                lead_payload = dict(result.get("crm", {}).get("lead") or {})
                lead_payload["WhatsApp Phone"] = event.get("from_phone")
                lead_payload["Contact Phone"] = event.get("from_phone")
                lead_payload["Full Name"] = event.get("profile_name")
                lead_payload["Client Intent"] = result.get("classification", {}).get("intent")
                lead_payload["Category"] = result.get("classification", {}).get("category")
                lead_payload["Priority"] = result.get("classification", {}).get("priority")
                lead_payload["Language"] = result.get("classification", {}).get("language")
                lead_payload["Risk Flags"] = ", ".join(result.get("classification", {}).get("risk_flags") or [])
                lead_payload["Safe Auto Reply"] = result.get("classification", {}).get("safe_auto_reply")
                pipeline = build_pipeline(lead_payload)
            except Exception as e:  # pragma: no cover - bridge is optional
                pipeline = {"ok": False, "error": str(e)}

        response = {
            "ok": True,
            "send_status": send_status,
            "sent": sent,
            "conversation_context": result.get("conversation_context"),
            "classification": result.get("classification"),
            "safety_gate": state_decision.get("final_mode") or result.get("safety_gate"),
            "state_decision": state_decision,
            "dashboard_metrics": state_result.get("dashboard_metrics"),
            "reply": reply,
            "tool_plan": result.get("tool_plan"),
            "reply_style": result.get("reply_style"),
            "continuity": result.get("continuity"),
            "canonical_prompt_loaded": result.get("canonical_prompt_loaded"),
            "provider_event": event,
            "pipeline": pipeline,
        }
        _append_log({"event": "processed", "result": response})
        if pipeline is not None:
            _append_bridge_log({"event": "pipeline", "lead_id": (pipeline or {}).get("lead_update", {}).get("Lead ID"), "result": pipeline})
        self._json_response(200, response)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    server = ThreadingHTTPServer((DEFAULT_BIND_HOST, DEFAULT_BIND_PORT), RelayHandler)
    _append_log(
        {
            "event": "startup",
            "host": DEFAULT_BIND_HOST,
            "port": DEFAULT_BIND_PORT,
            "webhook_path": WEBHOOK_PATH,
        }
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
