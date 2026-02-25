FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash build-essential git \
    && pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install -r requirements.txt

ENTRYPOINT ["/bin/bash", "/app/deploy/cloud-run/entrypoint.sh"]
