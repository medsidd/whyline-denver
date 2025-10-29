FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (requires project metadata for -e .)
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Application source (remaining directories)
COPY app ./app
COPY dbt ./dbt
COPY .streamlit ./.streamlit
COPY deploy/streamlit-service/nginx.conf /etc/nginx/nginx.conf
COPY deploy/streamlit-service/start.sh /start.sh

# Static placeholders and assets for nginx
RUN mkdir -p /usr/share/nginx/html/docs \
    && mkdir -p /usr/share/nginx/html/data \
    && mkdir -p /usr/share/nginx/html/assets
COPY app/placeholders/index.html /usr/share/nginx/html/index.html
COPY app/placeholders/docs/index.html /usr/share/nginx/html/docs/index.html
COPY app/placeholders/data/index.html /usr/share/nginx/html/data/index.html
COPY app/assets/favicon.ico /usr/share/nginx/html/favicon.ico
COPY app/assets/whylinedenver-logo.svg /usr/share/nginx/html/assets/whylinedenver-logo.svg

RUN chmod +x /start.sh

EXPOSE 8080
CMD ["/start.sh"]
