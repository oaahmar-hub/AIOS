#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, subprocess, sys, tempfile, datetime, os
import uuid

BASE = pathlib.Path(__file__).resolve().parents[1]
GATEWAY = BASE / 'runtime' / 'whatsapp_provider_gateway.py'
STATE = BASE / 'runtime' / 'conversation_state_engine.py'
SAMPLE = BASE / 'samples' / 'meta_cloud_inbound.json'
WHATSAPP_CHAT_DB = '/Users/hassanka/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite'
WHATSAPP_CONTACTS_DB = '/Users/hassanka/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ContactsV2.sqlite'


def run(cmd, data, env=None):
    p = subprocess.run(cmd, input=data, text=True, capture_output=True, check=True, env=env)
    return json.loads(p.stdout)


def meta_payload(phone: str, text: str, name: str = 'WhatsApp Client'):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "971500003714", "phone_number_id": "PHONE_NUMBER_ID"},
                    "contacts": [{"profile": {"name": name}, "wa_id": phone}],
                    "messages": [{"from": phone, "id": f"wamid.{phone[-6:]}-{uuid.uuid4().hex[:8]}", "timestamp": "1781652000", "type": "text", "text": {"body": text}}],
                },
            }],
        }],
    }


with tempfile.TemporaryDirectory() as td:
    db = pathlib.Path(td) / 'state.sqlite'
    env = os.environ.copy()
    env['AIOS_CONVERSATION_DB'] = str(db)
    env['AIOS_WHATSAPP_CHAT_DB'] = WHATSAPP_CHAT_DB
    env['AIOS_WHATSAPP_CONTACTS_DB'] = WHATSAPP_CONTACTS_DB

    raw = SAMPLE.read_text()
    g1 = run([sys.executable, str(GATEWAY)], raw, env=env)
    s1 = run([sys.executable, str(STATE), str(db)], json.dumps(g1))
    s2 = run([sys.executable, str(STATE), str(db)], json.dumps(g1))

    risky = json.loads(raw)
    risky['entry'][0]['changes'][0]['value']['messages'][0]['id'] = 'wamid.RISKY'
    risky['entry'][0]['changes'][0]['value']['messages'][0]['text']['body'] = 'I want to sign contract and pay deposit today'
    g2 = run([sys.executable, str(GATEWAY)], json.dumps(risky), env=env)
    s3 = run([sys.executable, str(STATE), str(db)], json.dumps(g2))

    after = json.loads(raw)
    after['entry'][0]['changes'][0]['value']['messages'][0]['id'] = 'wamid.AFTER'
    after['entry'][0]['changes'][0]['value']['messages'][0]['text']['body'] = 'Hello what is the price?'
    g3 = run([sys.executable, str(GATEWAY)], json.dumps(after), env=env)
    s4 = run([sys.executable, str(STATE), str(db)], json.dumps(g3))

    local_history = run(
        [sys.executable, str(GATEWAY)],
        json.dumps(meta_payload('971545832330', 'Hi, please help me continue this thread.', 'Jess HSH Assstant')),
        env=env,
    )

    seed_first = run(
        [sys.executable, str(GATEWAY)],
        json.dumps(meta_payload('971501234567', 'Hello, can you help with Palm Jumeirah options?', 'Dubai Buyer')),
        env=env,
    )
    run([sys.executable, str(STATE), str(db)], json.dumps(seed_first))
    seed_second = run(
        [sys.executable, str(GATEWAY)],
        json.dumps(meta_payload('971501234567', 'Yes, I want the next options only.', 'Dubai Buyer')),
        env=env,
    )
    state_second = run([sys.executable, str(STATE), str(db)], json.dumps(seed_second))

    mixed_lang = run(
        [sys.executable, str(GATEWAY)],
        json.dumps(meta_payload('971555593714', 'أكيد I want a viewing today', 'Omar Boss HSH')),
        env=env,
    )

report = {
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': 'PASS' if (
        s1['state_decision']['send_allowed']
        and s2['state_decision']['final_mode'] == 'DUPLICATE_SUPPRESSED'
        and s3['state_decision']['final_mode'] == 'OMAR_APPROVAL_REQUIRED'
        and s4['state_decision']['final_mode'] == 'HUMAN_TAKEOVER_ACTIVE'
        and local_history.get('conversation_context', {}).get('has_prior_history')
        and local_history.get('conversation_context', {}).get('history', {}).get('whatsapp_messages')
        and seed_second.get('conversation_context', {}).get('has_prior_history')
        and seed_second.get('conversation_context', {}).get('history', {}).get('aios_messages')
        and mixed_lang.get('classification', {}).get('language') == 'Mixed'
        and mixed_lang.get('tool_plan', {}).get('calendar_hand_off') is True
    ) else 'FAIL',
    'tests': {
        'safe_first_message': s1['state_decision'],
        'duplicate_suppression': s2['state_decision'],
        'risky_message_approval_gate': s3['state_decision'],
        'human_takeover_blocks_later_safe_message': s4['state_decision'],
        'local_whatsapp_history_loaded': local_history.get('conversation_context', {}),
        'aios_turn_to_turn_continuity_loaded': seed_second.get('conversation_context', {}),
        'mixed_language_calendar_case': {
            'classification': mixed_lang.get('classification', {}),
            'reply_style': mixed_lang.get('reply_style', {}),
            'tool_plan': mixed_lang.get('tool_plan', {}),
            'continuity': mixed_lang.get('continuity', {}),
        },
    },
    'state_metrics': state_second['dashboard_metrics'],
}
(BASE / 'reports' / 'CONVERSATION_STATE_VALIDATION.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
print(json.dumps(report, indent=2, ensure_ascii=False))
