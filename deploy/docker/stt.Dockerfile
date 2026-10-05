# syntax=docker/dockerfile:1
# Omnix speech-to-text service image (WP-11.1). CUDA runtime base with Python 3.11 and
# requirements/stt.linux.lock.txt (one Torch version). No model weights are baked
# in: `python -m app.models download --service stt` fills the Hugging
# Face cache in the /models volume (pinned commits, SHA-256 checked), and the
# service then loads offline.
#
#   docker build -f deploy/docker/stt.Dockerfile -t omnix-stt .

ARG CUDA_IMAGE=nvidia/cuda:12.4.1-runtime-ubuntu22.04

FROM ${CUDA_IMAGE} AS python
ENV DEBIAN_FRONTEND=noninteractive
# Ubuntu 22.04 ships Python 3.10; Omnix supports 3.11 (deadsnakes). Base tags
# lag distribution security fixes: take them at build time.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates gpg-agent software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.11 python3.11-venv libsndfile1 ffmpeg \
    && apt-get purge -y --auto-remove software-properties-common gpg-agent \
    && rm -rf /var/lib/apt/lists/*

FROM python AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential python3.11-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python3.11 -m venv /opt/omnix/venv
COPY requirements/stt.linux.lock.txt /tmp/runtime.lock.txt
RUN /opt/omnix/venv/bin/python -m pip install --require-hashes -r /tmp/runtime.lock.txt \
    && /opt/omnix/venv/bin/python -m pip uninstall -y pip \
    && find /opt/omnix/venv -name "__pycache__" -type d -prune -exec rm -rf {} +

FROM python AS runtime
ARG OMNIX_SOFTWARE_REVISION=unknown
RUN groupadd --system --gid 10001 omnix \
    && useradd --system --uid 10001 --gid omnix --home-dir /var/lib/omnix --shell /usr/sbin/nologin omnix \
    && install -d -o omnix -g omnix -m 0750 /var/lib/omnix /models /app/resources
ENV PATH=/opt/omnix/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    HOME=/var/lib/omnix \
    HF_HOME=/models/huggingface \
    HF_HUB_OFFLINE=1 \
    OMNIX_LOG_FORMAT=json \
    OMNIX_SOFTWARE_REVISION=${OMNIX_SOFTWARE_REVISION} \
    OMNIX_STT_PORT=5201
COPY --from=builder /opt/omnix/venv /opt/omnix/venv
WORKDIR /app
COPY src/app /app/src/app
COPY src/nemotron_eou_stt_server.py /app/src/nemotron_eou_stt_server.py
COPY scripts/container_healthcheck.py /app/scripts/container_healthcheck.py
USER 10001:10001
VOLUME ["/models"]
EXPOSE 5201
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD ["python", "scripts/container_healthcheck.py", "http://127.0.0.1:5201/health"]
CMD ["python", "src/nemotron_eou_stt_server.py"]
