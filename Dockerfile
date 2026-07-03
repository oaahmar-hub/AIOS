FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AIOS_API_HOST=0.0.0.0

WORKDIR /app

COPY . /app

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python3 -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8888') + '/api/health', timeout=4)); raise SystemExit(0 if data.get('status') == 'ready' else 1)"

CMD ["python3", "-m", "aios_runtime_production_up", "--host", "0.0.0.0", "--port", "8888"]
