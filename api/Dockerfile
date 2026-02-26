FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# Copy pyproject.toml (needed for -e . install) and src/ first for layer caching
COPY pyproject.toml ./
COPY src ./src

# Copy only the API requirements (no streamlit/pydeck/folium in this image)
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r api/requirements.txt

# Copy API source and dbt artifacts (needed for DbtArtifacts at startup)
COPY api ./api
COPY dbt/target ./dbt/target

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
