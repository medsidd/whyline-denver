"""WhyLine Denver FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env for local development (no-op in Cloud Run where env vars are injected)
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

# Ensure src/ is importable
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from api.routers import downloads, filters, health, query, sql

app = FastAPI(
    title="WhyLine Denver API",
    description="Backend API for the WhyLine Denver transit analytics dashboard.",
    version="1.0.0",
)

# CORS — only used during local dev; in production, Next.js rewrites proxy
# all /api/* requests server-side so the browser never hits this directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://www.whylinedenver.com",
        "https://*.vercel.app",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Register all routers under /api prefix
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(filters.router, prefix="/api", tags=["filters"])
app.include_router(sql.router, prefix="/api", tags=["sql"])
app.include_router(query.router, prefix="/api", tags=["query"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
