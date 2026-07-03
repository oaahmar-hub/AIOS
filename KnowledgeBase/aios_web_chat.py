from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from aios_entrypoint import route_request

HOST = '127.0.0.1'
PORT = 8787

HTML = b'''<!doctype html><html><head><meta charset="utf-8"><title>AIOS Web Chat</title><style>body{font-family:Arial,sans-serif;max-width:860px;margin:40px auto;padding:0 18px}textarea{width:100%;height:110px}button{padding:10px 14px;margin-top:8px}.box{border:1px solid #ccc;border-radius:10px;padding:12px;margin:16px 0;white-space:pre-wrap}.ok{color:#0a7}.fail{color:#c00}</style></head><body><h1>AIOS Web Chat</h1><p>Temporary live inbound channel for AIOS activation.</p><textarea id="q" placeholder="Type request..."></textarea><br><button onclick="sendQ()">Send</button><div id="status"></div><div id="out" class="box"></div><script>async function sendQ(){const q=document.getElementById('q').value;document.getElementById('status').textContent='Sending...';const r=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:q})});const j=await r.json();document.getElementById('status').textContent=r.ok?'PASS':'FAIL';document.getElementById('out').textContent=JSON.stringify(j,null,2);}</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str = 'application/json'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == '/':
            self._send(200, HTML, 'text/html; charset=utf-8')
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if urlparse(self.path).path != '/api/route':
            self._send(404, b'{"error":"not found"}')
            return
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            self._send(400, b'{"error":"invalid json"}')
            return
        request = str(payload.get('request', '')).strip()
        if not request:
            self._send(400, b'{"error":"missing request"}')
            return
        result = route_request(request)
        body = json.dumps({
            'live_request': request,
            'router': result.route,
            'source': result.source,
            'action': result.action,
            'response': result.result,
        }, ensure_ascii=False, indent=2).encode('utf-8')
        self._send(200, body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'AIOS web chat listening on http://{HOST}:{PORT}')
    server.serve_forever()


if __name__ == '__main__':
    main()
