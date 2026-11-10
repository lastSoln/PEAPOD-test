FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine ./engine
COPY app ./app
COPY static ./static
# The bundled dataset: active places only, built by scripts/build_dataset.py. Read-only at runtime.
COPY data/places.sqlite ./data/places.sqlite
RUN chmod 444 /app/data/places.sqlite && mkdir -p /data

# Saved runs and feedback. Mount a persistent disk at /data or they are lost on redeploy.
ENV PEAPOD_PLACES_DB=/app/data/places.sqlite BENCH_DB=/data/bench.sqlite PORT=8000
EXPOSE 8000

# BENCH_PASSWORD must be set in the host's environment; the app refuses to start without it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
