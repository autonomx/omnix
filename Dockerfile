# Browser gateway image. Model runtimes are installed in their dedicated environments.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# OMNIX_LOCK=tracing adds the optional OpenTelemetry packages (a superset of the gateway lock).
ARG OMNIX_LOCK=gateway
COPY requirements/${OMNIX_LOCK}.lock.txt /tmp/runtime.lock.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/runtime.lock.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/ready || exit 1

CMD ["python", "scripts/run_omnix_gateway.py", "--host", "0.0.0.0", "--port", "8000"]
