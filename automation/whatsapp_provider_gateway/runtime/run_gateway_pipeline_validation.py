#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, pathlib, sys, datetime

BASE = pathlib.Path(__file__).resolve().parents[1]
AIOS = BASE.parents[1]
GATEWAY = BASE / 'runtime' / 'whatsapp_provider_gateway.py'
LEAD_PIPE = AIOS / 'automation' / 'lead_pipeline_os' / 'runtime' / 'lead_pipeline_engine.py'
CRM_SCORE = AIOS / 'automation' / 'crm_business_os' / 'runtime' / 'crm_lead_scorer.py'
SAMPLES = [
    BASE / 'samples' / 'twilio_inbound.txt',
    BASE / 'samples' / 'meta_cloud_inbound.json',
    BASE / 'samples' / 'respond_io_inbound.json',
    BASE / 'samples' / 'infobip_inbound.json',
    BASE / 'samples' / 'gupshup_inbound.json',
]

def run(cmd, data=None):
    p=subprocess.run(cmd,input=data,text=True,capture_output=True,check=True)
    return json.loads(p.stdout)

results=[]
for sample in SAMPLES:
    gateway=run([sys.executable,str(GATEWAY)], sample.read_text())
    lead_in={**gateway['crm']['contact'], **gateway['crm']['lead']}
    pipeline=run([sys.executable,str(LEAD_PIPE)], json.dumps(lead_in))
    score=run([sys.executable,str(CRM_SCORE)], json.dumps(lead_in))
    ok=all([
        gateway['crm'].get('contact'), gateway['crm'].get('lead'), gateway['crm'].get('message'), gateway['crm'].get('task'), gateway['crm'].get('dashboard_log'),
        pipeline.get('task'), pipeline.get('approval'), pipeline.get('dashboard_metrics'),
        score.get('Lead Score') is not None if isinstance(score,dict) else True,
    ])
    results.append({
        'sample': sample.name,
        'provider': gateway['provider_event']['provider'],
        'intent': gateway['classification']['intent'],
        'priority': gateway['classification']['priority'],
        'reply_mode': gateway['reply']['mode'],
        'lead_id': gateway['crm']['lead']['Lead ID'],
        'task_id': gateway['crm']['task']['Task ID'],
        'pipeline_task': pipeline['task']['Task ID'],
        'pipeline_gate': pipeline['safety_gate'],
        'pass': ok,
    })

calendar_gateway = run(
    [sys.executable, str(GATEWAY)],
    json.dumps({
        "event": "messages.received",
        "sessionId": "S1",
        "data": {
            "messages": {
                "key": {"id": "CAL-TEST", "fromMe": False, "remoteJid": "971555593714@lid", "cleanedSenderPn": "971555593714"},
                "messageBody": "أكيد I need a viewing today",
                "message": {"conversation": "أكيد I need a viewing today"},
                "pushName": "Omar Boss HSH",
            }
        }
    })
)
calendar_lead = {**calendar_gateway['crm']['contact'], **calendar_gateway['crm']['lead']}
calendar_pipeline = run([sys.executable, str(LEAD_PIPE)], json.dumps(calendar_lead))
results.append({
    'sample': 'mixed_language_calendar_case',
    'provider': calendar_gateway['provider_event']['provider'],
    'intent': calendar_gateway['classification']['intent'],
    'priority': calendar_gateway['classification']['priority'],
    'reply_mode': calendar_gateway['reply']['mode'],
    'lead_id': calendar_gateway['crm']['lead']['Lead ID'],
    'task_id': calendar_gateway['crm']['task']['Task ID'],
    'pipeline_task': calendar_pipeline['task']['Task ID'],
    'pipeline_gate': calendar_pipeline['safety_gate'],
    'calendar_hand_off': calendar_gateway.get('tool_plan', {}).get('calendar_hand_off'),
    'reply_language': calendar_gateway.get('reply_style', {}).get('language_mode'),
    'pass': (
        calendar_gateway['classification']['language'] == 'Mixed'
        and calendar_gateway.get('tool_plan', {}).get('calendar_hand_off') is True
        and calendar_pipeline['assignment']['Agent Command'] == '@client @calendar'
        and calendar_pipeline['approval']['Draft Message'].startswith('Hi Omar Boss HSH, please send the preferred time')
    ),
})
report={
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status':'PASS' if all(r['pass'] for r in results) else 'FAIL',
    'chain':'WhatsApp provider payload -> AIOS gateway -> CRM objects -> Lead pipeline task/approval/dashboard -> CRM scoring callable',
    'results':results,
}
out=BASE / 'reports' / 'GATEWAY_TO_PIPELINE_VALIDATION.json'
out.write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
