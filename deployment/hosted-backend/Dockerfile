FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Do NOT hardcode PORT — Railway/Render inject $PORT at runtime and the app reads it
# (os.getenv("PORT", "8080")). A hardcoded ENV PORT would override the platform port.

COPY app.py /app/app.py
COPY AIOS /app/AIOS

# Informational only; the platform routes to whatever port the app binds via $PORT.
EXPOSE 8080
CMD ["python", "/app/app.py"]
