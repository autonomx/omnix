# syntax=docker/dockerfile:1
# Omnix gateway image (WP-11.1): API replicas, the gateway worker, the job
# worker and the migration job all run from it. No CUDA and no models; the
# speech and image services have their own images.
#
#   docker build -f deploy/docker/gateway.Dockerfile -t omnix-gateway .
#   docker build -f deploy/docker/gateway.Dockerfile --build-arg OMNIX_LOCK=tracing -t omnix-gateway .

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
# gateway, or tracing (the gateway lock plus the optional OpenTelemetry packages).
ARG OMNIX_LOCK=gateway
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
# The runtime venv has no pip or setuptools: the builder's pip installs into it.
RUN python -m venv --without-pip /opt/omnix/venv
COPY requirements/${OMNIX_LOCK}.lock.txt /tmp/runtime.lock.txt
RUN python -m pip --python /opt/omnix/venv/bin/python install --require-hashes -r /tmp/runtime.lock.txt \
    && find /opt/omnix/venv -name "__pycache__" -type d -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE} AS runtime
ARG OMNIX_SOFTWARE_REVISION=unknown
# ffmpeg encodes audiobook exports; curl is not installed, the health check
# uses Python. Base tags lag distribution security fixes: take them at build time.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 omnix \
    && useradd --system --uid 10001 --gid omnix --home-dir /var/lib/omnix --shell /usr/sbin/nologin omnix \
    && install -d -o omnix -g omnix -m 0750 /var/lib/omnix /app/resources

ENV PATH=/opt/omnix/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    OMNIX_SOFTWARE_REVISION=${OMNIX_SOFTWARE_REVISION} \
    OMNIX_LOG_FORMAT=json \
    HOME=/var/lib/omnix

COPY --from=builder /opt/omnix/venv /opt/omnix/venv
WORKDIR /app
COPY src/app /app/src/app
COPY src/__init__.py src/main.py src/launch.py /app/src/
COPY scripts /app/scripts

# The image runs with a read-only root filesystem: runtime data lives in
# /app/resources (a volume), the home directory in /var/lib/omnix and
# temporary files in /tmp (volumes or tmpfs).
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["python", "scripts/container_healthcheck.py", "http://127.0.0.1:8000/health"]
CMD ["python", "scripts/run_omnix_gateway.py", "--host", "0.0.0.0", "--port", "8000", "--api-replicas", "0"]
