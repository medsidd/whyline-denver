# whyline-denver
WhyLine Denver turns raw public datasets into a governed, dual-engine analytics experience where anyone can ask transit questions in plain English and get safe, cost-capped SQL answers, charts, and downloadable data — powered by a dbt semantic layer and switchable DuckDB/BigQuery backends.

# WhyLine Denver (setup)

Dual-engine transit analytics (DuckDB first, BigQuery optional). This repo currently contains **setup only**.

## Quickstart (local)
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env 

