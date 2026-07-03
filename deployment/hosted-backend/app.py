#!/usr/bin/env python3
"""AIOS hosted backend wrapper.

Deployment purpose:
- Move command API and WhatsApp gateway off Omar's Mac.
- Keep the existing AIOS architecture intact.
- Provide stable HTTP endpoints for the web platform and provider webhooks.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
import base64
import hmac
import hashlib
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AIOS_ROOT = Path(os.getenv("AIOS_ROOT", "/app/AIOS"))
LOCAL_KB_RAW = os.getenv("AIOS_LOCAL_KB", "").strip()
LOCAL_KB = Path(LOCAL_KB_RAW).expanduser() if LOCAL_KB_RAW else None
if LOCAL_KB and LOCAL_KB.exists():
    sys.path.insert(0, str(LOCAL_KB))
elif (AIOS_ROOT / "KnowledgeBase").exists():
    sys.path.insert(0, str(AIOS_ROOT / "KnowledgeBase"))

LOCAL_RUNTIME_RAW = os.getenv("AIOS_LOCAL_RUNTIME", "").strip()
LOCAL_RUNTIME = Path(LOCAL_RUNTIME_RAW).expanduser() if LOCAL_RUNTIME_RAW else None
RUNTIME_CANDIDATES = []
if LOCAL_RUNTIME:
    RUNTIME_CANDIDATES.append(LOCAL_RUNTIME)
RUNTIME_CANDIDATES.extend(
    [
        AIOS_ROOT / "automation" / "central_orchestrator" / "runtime",
        Path(__file__).resolve().parent / "AIOS" / "automation" / "central_orchestrator" / "runtime",
    ]
)
for candidate in RUNTIME_CANDIDATES:
    if candidate.exists():
        sys.path.insert(0, str(candidate))
        break

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))
OPENAI_ENDPOINT = os.getenv("WA_SIMPLE_OPENAI_ENDPOINT", "https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4")
WASENDER_SEND_URL = "https://www.wasenderapi.com/api/send-message"
ALLOWED_ORIGIN = os.getenv("AIOS_ALLOWED_ORIGIN", "*")
NO_MATCH_REPLY = "NO MATCH FOUND"
AUTH_USER = os.getenv("AIOS_BASIC_AUTH_USER", "").strip()
AUTH_PASSWORD = os.getenv("AIOS_BASIC_AUTH_PASSWORD", "").strip()
WEBHOOK_SECRET = os.getenv("AIOS_WEBHOOK_SECRET", "").strip()
# Fail-closed by default: when API auth is not configured, protected routes refuse to
# serve instead of falling open. Set AIOS_REQUIRE_AUTH=0 only for local/dev smoke tests.
REQUIRE_AUTH = os.getenv("AIOS_REQUIRE_AUTH", "1").strip().lower() not in {"0", "false", "no", "off"}
MAX_BODY_BYTES = int(os.getenv("AIOS_MAX_BODY_BYTES", "1048576"))  # 1 MiB cap on request bodies


PUBLIC_GET_PATHS = {"/health", "/api/health", "/api/runtime-truth", "/api/runtime-report"}
WEBHOOK_PATHS = {"/webhook/whatsapp/simple"}
AUDIT_LOG_PATH = AIOS_ROOT / "data" / "permission_audit_log.jsonl"


def now_ms() -> int:
    return int(time.time() * 1000)


def log_event(event: str, **fields: object) -> None:
    print(json.dumps({"ts": now_ms(), "event": event, **fields}, ensure_ascii=False, default=str), flush=True)


def iso_utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def request_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_audit_entry(entry: dict) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def audit_rows(limit: int = 100) -> list[dict]:
    if not AUDIT_LOG_PATH.exists():
        return []
    rows = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:]


def post_json(url: str, body: dict, headers: dict | None = None, timeout: int = 60) -> tuple[int, dict, str]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return exc.code, parsed, raw


def route_request(request: str) -> dict:
    try:
        from aios_entrypoint import route_request as local_route_request

        result = local_route_request(request)
        return {
            "ok": True,
            "route": result.route,
            "source": result.source,
            "action": result.action,
            "result": result.result,
        }
    except Exception as exc:
        return {
            "ok": False,
            "route": "backend_unavailable",
            "error": str(exc),
            "note": "Deploy AIOS KnowledgeBase package with the backend to enable local routing.",
        }


def router_match_found(routed: dict) -> bool:
    if not routed.get("ok"):
        return False
    result = routed.get("result")
    if isinstance(result, list):
        return len(result) > 0
    if isinstance(result, dict):
        if isinstance(result.get("matches"), list):
            return len(result["matches"]) > 0
        if result.get("source") or result.get("action"):
            return True
    return bool(result)


def retrieval_gate(message: str) -> dict:
    try:
        from aios_brain_router import classify_retrieval_intent

        decision = classify_retrieval_intent(message)
        routed = route_request(message)
        return {
            "retrieval_intent": decision.retrieval_intent,
            "source_used": decision.target,
            "query_used": message,
            "required": decision.retrieval_intent
            in {
                "ownership_lookup",
                "property_lookup",
                "inventory_lookup",
                "document_lookup",
                "operations_lookup",
                "followup_lookup",
                "contact_lookup",
                "project_lookup",
                "developer_lookup",
            },
            "executed": True,
            "match_found": router_match_found(routed),
            "routed": routed,
        }
    except Exception as exc:
        return {
            "retrieval_intent": "unknown",
            "source_used": "router_unavailable",
            "query_used": message,
            "required": True,
            "executed": False,
            "match_found": False,
            "error": str(exc),
        }


def normalize_phone(value: object) -> str:
    text = str(value or "").split("@", 1)[0]
    return re.sub(r"\D+", "", text)


def normalize_outbound_whatsapp_target(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "@" in raw:
        return raw
    digits = normalize_phone(raw)
    if digits:
        return f"{digits}@s.whatsapp.net"
    return raw


def _coalesce(value):
    if value is None:
        return ""
    return str(value).strip()


def _is_na_sender(value: str) -> bool:
    if not value:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"na", "n/a", "none", "null", "unknown"}


def dig(obj, *path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _collect_sender_candidates(payload: dict, data: dict, msg: dict, key: dict):
    candidates = []
    add = candidates.append
    if isinstance(msg, dict):
        add(msg.get("from"))
        add(msg.get("to"))
        add(msg.get("sender"))
        add(msg.get("sender_jid"))
        add(msg.get("senderPn"))
        add(msg.get("chatId"))
        if isinstance(msg.get("key"), dict):
            inner_key = msg.get("key") or {}
            add(inner_key.get("remoteJid"))
            add(inner_key.get("chat"))
            add(inner_key.get("from"))
            add(inner_key.get("remoteJid"))
    if isinstance(payload, dict):
        add(payload.get("from"))
        add(payload.get("to"))
        add(payload.get("sender"))
        add(payload.get("chatId"))
        add(payload.get("phone"))
        source = payload.get("source")
        if isinstance(source, dict):
            add(source.get("sender"))
            add(source.get("phone"))
            add(source.get("jid"))
    if key and isinstance(key, dict):
        add(key.get("cleanedSenderPn"))
        add(key.get("remoteJid"))
        add(key.get("from"))
        add(key.get("chat"))
    if isinstance(data, dict):
        add(data.get("from"))
        add(dig(data, "sender", "jid"))
        add(dig(data, "sender", "phone"))
        add(dig(data, "session", "from"))
    for value in candidates:
        text = _coalesce(value)
        if text:
            return text, candidates
    return "", candidates


def extract_whatsapp_payload(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else {}
    msg = data.get("messages") if isinstance(data, dict) else None
    if isinstance(msg, list) and msg:
        msg = msg[0]
    if not isinstance(msg, dict):
        msg = data if isinstance(data, dict) else payload
    key = msg.get("key") if isinstance(msg, dict) else {}
    key = key if isinstance(key, dict) else {}
    sender, sender_candidates = _collect_sender_candidates(payload, data, msg, key)
    if not sender:
        sender = _coalesce(key.get("cleanedSenderPn")) or _coalesce(payload.get("From"))
    sender_digits = normalize_phone(sender)
    raw_jid = str(sender or "")
    sender_lower = raw_jid.lower()
    is_na_sender = _is_na_sender(raw_jid)
    if "@g.us" in sender_lower:
        sender_quality = "group"
    elif sender_digits:
        sender_quality = "digit"
    elif sender_lower.startswith("@") or sender_lower.endswith("@lid"):
        sender_quality = "jid"
    elif is_na_sender:
        sender_quality = "na"
    elif raw_jid:
        sender_quality = "textual"
    else:
        sender_quality = "missing"
    text = (
        msg.get("messageBody")
        or msg.get("body")
        or (((msg.get("message") or {}).get("conversation")) if isinstance(msg.get("message"), dict) else "")
        or payload.get("message")
        or payload.get("text")
        or ""
    )
    from_me = bool(msg.get("fromMe") or key.get("fromMe"))
    message_text = str(text or "").strip()
    ignored = from_me or "@g.us" in raw_jid or "newsletter" in raw_jid.lower() or not message_text
    ignored_reason = ""
    if from_me:
        ignored_reason = "from_me"
    elif "@g.us" in raw_jid:
        ignored_reason = "group"
    elif "newsletter" in raw_jid.lower():
        ignored_reason = "newsletter"
    elif not message_text:
        ignored_reason = "empty_message"
    sender_for_send = raw_jid if "@" in raw_jid else (sender_digits or raw_jid)
    return {
        "sender": sender_for_send,
        "sender_quality": sender_quality,
        "sender_candidates": sender_candidates[:10],
        "text": message_text,
        "ignored": ignored,
        "ignored_reason": ignored_reason,
        "is_na_sender": is_na_sender,
        "raw_jid": raw_jid,
    }


def generate_reply(message: str, sender: str) -> str:
    proof = retrieval_gate(message)
    if proof.get("required"):
        log_event(
            "retrieval_audit_trail",
            sender=sender,
            user_visible=False,
            source_used=proof.get("source_used"),
            query_used=proof.get("query_used"),
            match_found=proof.get("match_found"),
            retrieval_intent=proof.get("retrieval_intent"),
        )
    if proof.get("required") and (not proof.get("executed") or not proof.get("match_found")):
        return NO_MATCH_REPLY
    context = (
        "AIOS LIVE WHATSAPP RESPONSE CONTRACT\n"
        "MESSAGE -> Conversation History -> Relationship Detection -> Intent Detection -> Permission Layer -> "
        "Knowledge Retrieval -> Omar Personality Engine -> Safe Reply Generation.\n"
        "NO ANSWER WITHOUT RETRIEVAL. Internal proof fields are: SOURCE USED, QUERY USED, MATCH FOUND. "
        "If MATCH FOUND is false, reply exactly NO MATCH FOUND.\n"
        "Short, human, Omar-style. No private owner/internal data. No generic chatbot loops.\n\n"
        f"RETRIEVAL_PROOF:\n{json.dumps(proof, ensure_ascii=False)}\n\n"
        f"LATEST_MESSAGE:\n{message}"
    )
    status, parsed, raw = post_json(OPENAI_ENDPOINT, {"message": context, "from": sender, "history": "Hosted backend session"}, timeout=60)
    reply = str(parsed.get("reply") or parsed.get("text") or parsed.get("output") or "").strip() if isinstance(parsed, dict) else ""
    if status < 200 or status >= 300 or not reply:
        raise RuntimeError(f"reply generation failed status={status} body={raw[:300]}")
    if "hello, how can i help you" in reply.lower():
        raise RuntimeError("generic fallback blocked")
    return reply


def send_whatsapp(to: str, text: str) -> dict:
    token = os.getenv("WASENDER_API_KEY", "").strip()
    if not token:
        raise RuntimeError("WASENDER_API_KEY is not configured")
    target = normalize_outbound_whatsapp_target(to)
    status, parsed, raw = post_json(
        WASENDER_SEND_URL,
        {"to": target, "text": text},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=60,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"Wasender send failed status={status} body={raw[:300]}")
    return parsed


def runtime_truth() -> dict:
    return {
        "ok": True,
        "service": "aios-hosted-backend",
        "entrypoint": "/app/app.py",
        "bind_host": HOST,
        "port_env_present": "PORT" in os.environ,
        "port": PORT,
        "public_health_paths": sorted(PUBLIC_GET_PATHS),
        "mac_dependency": False,
        "aios_root_configured": bool(str(AIOS_ROOT)),
        "knowledgebase_import_available": (AIOS_ROOT / "KnowledgeBase").exists() or bool(LOCAL_KB and LOCAL_KB.exists()),
        "ts": now_ms(),
    }


def runtime_report() -> dict:
    return {
        "ok": True,
        "status": "online",
        "classification": "PARTIAL",
        "reason": "Hosted backend is online; external provider credentials and downstream integrations are validated separately.",
        "checks": {
            "bind_host_0_0_0_0": HOST == "0.0.0.0",
            "uses_railway_port_env": "PORT" in os.environ,
            "health_endpoint": "/api/health",
            "runtime_truth_endpoint": "/api/runtime-truth",
            "runtime_report_endpoint": "/api/runtime-report",
        },
        "modules": ["command_center", "whatsapp_gateway", "router_bridge", "property_intelligence", "operations"],
        "ts": now_ms(),
    }


def evaluate_permission_api(payload: dict) -> dict:
    text = str(payload.get("request") or payload.get("text") or payload.get("message") or "").strip()
    channel = str(payload.get("channel") or "website").strip() or "website"
    identity_type = str(payload.get("identity_type") or payload.get("identity") or "Unknown").strip() or "Unknown"
    try:
        from aios_interaction_architecture_runtime import evaluate_permission_request, permission_runtime_contract
    except Exception as exc:
        return {
            "ok": False,
            "request": text,
            "channel": channel,
            "blocked": True,
            "hits": ["permission_runtime_unavailable"],
            "rules": ["Permission Runtime"],
            "reason": f"Hosted backend could not load the centralized permission runtime: {exc}",
            "allowed_alternatives": ["Try again when hosted runtime package is refreshed", "Ask Omar to review manually"],
            "safety_gate": "HOLD_FOR_OMAR_APPROVAL",
            "eye_state": "restricted",
            "source_runtime": "backend_unavailable",
        }

    runtime_contract = permission_runtime_contract()
    decision = evaluate_permission_request(text, channel=channel, identity_type=identity_type)
    decision_id = "PERM-" + uuid.uuid4().hex[:12].upper()
    decision.update(
        {
            "decision_id": decision_id,
            "evaluated_at": iso_utc_now(),
            "request_hash": request_hash(text),
            "runtime_fingerprint": runtime_contract["fingerprint"],
            "audit_logged": False,
            "api": {
                "route": "/api/permission/evaluate",
                "server": "aios-hosted-backend",
                "source_of_truth": runtime_contract["source_of_truth"],
                "runtime_version": runtime_contract["version"],
            },
        }
    )
    if decision.get("blocked"):
        audit_entry = {
            "decision_id": decision_id,
            "logged_at": decision["evaluated_at"],
            "channel": channel,
            "identity_type": identity_type,
            "request_hash": decision["request_hash"],
            "request_preview": text[:160],
            "blocked": decision.get("blocked"),
            "hits": decision.get("hits", []),
            "rules": decision.get("rules", []),
            "reason": decision.get("reason", ""),
            "allowed_alternatives": decision.get("allowed_alternatives", []),
            "safety_gate": decision.get("safety_gate", ""),
            "eye_state": decision.get("eye_state", ""),
            "source_runtime": decision.get("source_runtime", ""),
        }
        append_audit_entry(audit_entry)
        decision["audit_logged"] = True
        decision["audit"] = {
            "decision_id": decision_id,
            "log": str(AUDIT_LOG_PATH.relative_to(AIOS_ROOT)),
        }
    return decision


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self._send(200, {"ok": True})

    def _authorized(self) -> bool:
        if not AUTH_USER or not AUTH_PASSWORD:
            # Not fully configured → fail closed in production; open only if explicitly opted out.
            return not REQUIRE_AUTH
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        user, sep, password = decoded.partition(":")
        return bool(sep) and hmac.compare_digest(user, AUTH_USER) and hmac.compare_digest(password, AUTH_PASSWORD)

    def _webhook_authorized(self, payload: dict) -> bool:
        if not WEBHOOK_SECRET:
            return False
        supplied = (
            self.headers.get("X-AIOS-Webhook-Secret", "")
            or self.headers.get("X-Webhook-Secret", "")
            or str(payload.get("webhook_secret") or "")
        )
        return hmac.compare_digest(str(supplied), WEBHOOK_SECRET)

    def _auth_failed(self) -> None:
        raw = json.dumps({"ok": False, "error": "unauthorized"}).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("WWW-Authenticate", 'Basic realm="AIOS Private Beta"')
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path not in PUBLIC_GET_PATHS and not self._authorized():
            self._auth_failed()
            return
        if self.path in PUBLIC_GET_PATHS:
            if self.path == "/api/runtime-truth":
                self._send(200, runtime_truth())
            elif self.path == "/api/runtime-report":
                self._send(200, runtime_report())
            else:
                self._send(200, {"ok": True, "status": "online", "service": "aios-hosted-backend", "ts": now_ms()})
        elif self.path == "/api/permission/audit":
            self._send(
                200,
                {
                    "ok": True,
                    "generated_at": iso_utc_now(),
                    "audit_log": str(AUDIT_LOG_PATH.relative_to(AIOS_ROOT)),
                    "restricted_decision_count": len(audit_rows(limit=10000)),
                    "entries": audit_rows(limit=100),
                },
            )
        elif self.path in {"/api/status", "/api/runtime/status"}:
            self._send(
                200,
                {
                    "ok": True,
                    "website": "ready",
                    "backend": "online",
                    "mac_dependency": False,
                    "modules": ["command_center", "whatsapp_gateway", "router_bridge", "property_intelligence", "operations"],
                },
            )
        else:
            self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._send(400, {"ok": False, "error": "invalid_content_length"})
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self._send(413, {"ok": False, "error": "payload_too_large"})
            return
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw}
        try:
            if self.path in WEBHOOK_PATHS:
                if not self._webhook_authorized(payload):
                    self._auth_failed()
                    return
            elif not self._authorized():
                self._auth_failed()
                return
            if self.path == "/api/permission/evaluate":
                self._send(200, evaluate_permission_api(payload))
            elif self.path == "/api/ask":
                request = str(payload.get("request") or payload.get("message") or "").strip()
                self._send(200, route_request(request))
            elif self.path == "/webhook/whatsapp/simple":
                parsed = extract_whatsapp_payload(payload)
                if parsed["ignored"]:
                    self._send(200, {"ok": True, "ignored": True})
                    return
                reply = generate_reply(parsed["text"], parsed["sender"])
                send_result = send_whatsapp(parsed["sender"], reply)
                self._send(200, {"ok": True, "reply": reply, "send": send_result})
            else:
                self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            log_event("request_error", path=self.path, error=str(exc), trace=traceback.format_exc()[-1200:])
            self._send(500, {"ok": False, "error": "internal_error"})

    def log_message(self, *_args):
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log_event(
        "aios_backend_start",
        host=HOST,
        port=PORT,
        require_auth=REQUIRE_AUTH,
        api_auth_configured=bool(AUTH_USER and AUTH_PASSWORD),
        webhook_secret_set=bool(WEBHOOK_SECRET),
        allowed_origin=ALLOWED_ORIGIN,
    )
    if REQUIRE_AUTH and not (AUTH_USER and AUTH_PASSWORD):
        log_event("security_warning", message="Protected API routes are fail-closed (401): set AIOS_BASIC_AUTH_USER and AIOS_BASIC_AUTH_PASSWORD to enable /api/ask, /api/status, /api/runtime/status, /api/permission/evaluate, /api/permission/audit.")
    if not WEBHOOK_SECRET:
        log_event("security_warning", message="Webhook has no AIOS_WEBHOOK_SECRET; webhook POSTs are fail-closed with 401 until a secret is configured.")
    if ALLOWED_ORIGIN == "*":
        log_event("security_warning", message="AIOS_ALLOWED_ORIGIN is '*'; set it to your frontend origin for beta/production.")
    server.serve_forever()


if __name__ == "__main__":
    main()
