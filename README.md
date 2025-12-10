# WhyLine Denver

![CI](https://github.com/medsidd/whyline-denver/actions/workflows/ci.yml/badge.svg)
![Nightly Ingest](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-ingest.yml/badge.svg)
![Nightly BQ](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-bq.yml/badge.svg)
![Nightly DuckDB](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-duckdb.yml/badge.svg)

WhyLine Denver is a transit data platform that analyzes Denver's public transportation system using open data. It pulls together bus and train schedules, real-time vehicle positions, weather conditions, traffic crashes, sidewalk infrastructure, and demographic information to answer questions about where transit service breaks down and who gets affected the most.

The project combines automated data pipelines with a natural language query interface, so you can ask plain English questions like "Which routes run late during snowstorms?" and get back SQL, charts, and downloadable data. It's built for anyone who wants to understand how well public transit works—whether you're a transit planner, a data analyst, a journalist, or just someone who relies on the bus.

## What This Does

At its core, WhyLine Denver takes messy, scattered public data and turns it into something you can actually use. Here's what happens:

**Data Collection**: Every five minutes, automated jobs grab real-time bus and train locations from RTD (Denver's transit agency). Every night, the system pulls updated schedules, weather reports from NOAA, traffic crash data from Denver's open data portal, sidewalk infrastructure maps, and census demographics.

**Data Processing**: All that raw data flows through a series of transformations built with dbt (a SQL modeling tool). The pipeline cleans up duplicates, fixes timezones, matches real-time positions to scheduled stops, calculates delay metrics, and identifies patterns. It's structured as bronze (raw), silver (cleaned), and gold (analytics-ready) layers.

**Query Interface**: A Streamlit web app lets you ask questions in natural language. An LLM converts your question into SQL, but the query gets validated before running—no DELETE or UPDATE statements allowed, only SELECT queries against pre-approved analytical tables. You can switch between BigQuery (cloud-based, scales well) or DuckDB (runs locally, completely free).

**Analysis Ready**: The system produces seven analytical datasets focused on four areas: reliability (on-time performance), safety (crash proximity to stops), equity (service quality in low-income or car-free neighborhoods), and accessibility (sidewalk coverage near stops).

## Why This Exists

Public transit data is public, but it's not always accessible. GTFS feeds are technical and hard to parse. Real-time updates come in every few seconds but disappear unless you archive them. Weather, crashes, and demographics live in different databases with different formats.

WhyLine Denver exists to bridge that gap. It makes transit data easier to work with, easier to analyze, and easier to share. You don't need to write complex SQL joins or figure out GTFS specifications—you can just ask questions and get answers.

The project has a specific focus on equity. Transit-dependent populations—people without cars, people in poverty, people who rely on buses to get to work—often get worse service. WhyLine Denver makes those disparities visible by combining service reliability data with demographic information. It's designed to help advocates, planners, and policymakers see where improvements would matter most.

## Who This Is For

**Transit Planners and Agencies**: Analyze reliability patterns, identify problem routes, understand how weather impacts service, prioritize infrastructure investments based on ridership and vulnerability.

**Data Analysts and Researchers**: Access clean, well-documented transit datasets without building your own pipeline. Export CSVs or query directly. All transformations are version-controlled and reproducible.

**Journalists and Advocates**: Answer questions like "Which neighborhoods have the worst bus service?" or "How many crashes happen near transit stops?" without needing to know SQL. Download results as CSV and use them in your reporting.

**Software Engineers**: Learn how to build a modern data platform with dbt, BigQuery, DuckDB, automated pipelines, and LLM-powered interfaces. The codebase follows clean architecture patterns and includes comprehensive documentation.

**Anyone Curious About Transit**: Explore Denver's bus and train system. See which routes run on time, which ones don't, and whether your neighborhood gets good service.

## Key Features

**Natural Language Queries**: Ask questions in plain English. The system converts them to SQL, validates the query for safety, shows you the SQL before running it, and gives you results as tables, charts, and downloadable CSVs.

**Dual-Engine Architecture**: Run queries against BigQuery (cloud warehouse, good for large datasets and production use) or DuckDB (embedded database, runs locally, completely free, good for exploration and development).

**Automated Pipelines**: Real-time transit data gets captured every 5 minutes via Cloud Run jobs. Static data refreshes nightly via GitHub Actions. dbt runs transformations and validates data quality with 40+ tests.

**Cost Controls**: BigQuery queries are capped at 2GB scanned by default. You see cost estimates before running anything. The entire platform costs about $60/month to run (mostly Cloud Run job executions processing ~600 million real-time events per year).

**Data Quality Enforcement**: Every dataset passes through dbt tests that check for nulls, duplicates, valid foreign keys, and logical consistency. If a test fails, the pipeline stops and sends alerts.

**Equity-Focused Metrics**: Composite vulnerability scores combine household car ownership, transit commute rates, and poverty levels. Priority hotspot analysis identifies stops where poor service overlaps with high vulnerability.

**Fully Reproducible**: Clone the repo, run a few commands, and you have a working system. All dependencies are pinned. Environment setup is documented. Credentials are handled through standard GCP authentication.

## What's Included

The repository contains:

- **Ingestion scripts** (Python): 7 CLIs that fetch data from public APIs (GTFS, weather, crashes, sidewalks, Census)
- **dbt models** (SQL): 25 transformation models across staging (11), intermediate (7), and mart (7) layers
- **BigQuery loader** (Python): Parametric script that loads raw files into BigQuery with metadata tracking
- **Streamlit app** (Python): Web interface with natural language querying, visualizations, and CSV exports
- **DuckDB sync** (Python): Export BigQuery marts to Parquet and materialize locally for offline use
- **Automation**: Cloud Run Jobs (real-time every 5 min) + GitHub Actions workflows (nightly batch)
- **Documentation**: Architecture guides, data contracts, lineage diagrams, cost optimization case studies
- **Tests**: pytest unit/integration tests + 40+ dbt data quality tests

## Tech Stack

- **Languages**: Python 3.11, SQL
- **Data Warehouse**: BigQuery (serverless, columnar, geospatial), DuckDB (embedded, local)
- **Transformation**: dbt 1.8 (SQL modeling, testing framework)
- **Orchestration**: Cloud Run Jobs + Cloud Scheduler (real-time), GitHub Actions (nightly)
- **Storage**: Google Cloud Storage (object storage)
- **App**: Streamlit 1.37, Google Gemini API (LLM-to-SQL)
- **Testing**: pytest, dbt tests, pre-commit hooks

## Use Cases

Here are some questions you can answer with WhyLine Denver:

- Which bus routes have the worst on-time performance?
- How does snow affect transit reliability?
- Which neighborhoods have high poverty and bad bus service?
- How many traffic crashes happen within 100 meters of transit stops?
- What's the average delay during rush hour versus midday?
- Which stops have poor sidewalk access?
- Where should the city invest in infrastructure improvements to help the most vulnerable riders?

## Getting Started

### Quick Local Setup

```bash
# 1. Clone and set up environment
git clone https://github.com/medsidd/whyline-denver.git
cd whyline-denver
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env to add your GCP project, bucket, and API keys

# 3. Sync data and launch app
make sync-duckdb  # Download latest data snapshot
make app          # Opens at http://localhost:8501
```

You now have a local analytical database with 7 marts covering reliability, safety, equity, and accessibility.

### Production Deployment

For production deployment with Cloud Run and BigQuery:
- **Cloud Run Jobs**: See [deploy/cloud-run/README.md](deploy/cloud-run/README.md) for real-time ingestion setup
- **Streamlit App**: See [deploy/streamlit-service/README.md](deploy/streamlit-service/README.md) for app deployment
- **Performance Tuning**: See [docs/guides/performance.md](docs/guides/performance.md) for optimization recommendations

## Data Architecture

WhyLine Denver follows a medallion architecture (Bronze → Silver → Gold) to progressively refine raw data:

- **Bronze Layer**: 7 data sources → 13 raw tables in BigQuery
- **Silver Layer**: 11 staging models (deduplication, normalization) + 7 intermediate models (derived metrics)
- **Gold Layer**: 7 analytical marts organized by domain (Reliability, Safety, Equity, Access)

For detailed architecture documentation, pipeline diagrams, and data lineage, see:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Full pipeline documentation
- [dbt/models/README.md](dbt/models/README.md) - Complete model documentation
- [Data Lineage Diagrams](docs/diagrams/) - Visual pipeline and lineage diagrams
- [Interactive dbt Docs](https://medsidd.github.io/whyline-denver/) - Auto-generated documentation

## Data Sources & Licenses

WhyLine Denver uses only public, non-PII data:

| Source | Data | License |
|--------|------|---------|
| **RTD (Regional Transportation District)** | GTFS Static, GTFS Realtime | [Open Data License](https://www.rtd-denver.com/open-data-license) |
| **Denver Open Data** | Traffic crashes, sidewalk segments | [Open Database License](https://www.denvergov.org/opendata/terms) |
| **NOAA/NCEI** | Daily weather summaries | Public domain |
| **U.S. Census Bureau** | ACS 5-year estimates, TIGER/Line boundaries | Public domain |

All attributions appear in the app footer and are linked in data model documentation.

## FAQ

### Can I use this for my city?

Yes. To adapt WhyLine Denver for another city:

1. Replace RTD's GTFS URLs with your transit agency's feeds
2. Update crash/sidewalk ingestors to point to your city's open data portal
3. Change NOAA station ID to your local weather station
4. Adjust Census geography filters to your county/metro area
5. Redeploy dbt models (most work as-is if GTFS semantics are standard)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed adaptation guidelines.

### What's the annual cost?

Running WhyLine Denver costs approximately **$709/year** ($59/month) based on current verified billing data:

**Monthly Costs** (~$59/month):
- **Cloud Run**: $44/month (288 job executions/day processing real-time GTFS feeds)
- **BigQuery**: $10/month ($6.50 query costs + $0.15 storage for 26.72 GB)
- **Cloud Storage**: $4.50/month (4 GB for raw files and Parquet exports)
- **Artifact Registry**: $2/month (Docker image storage)
- **Other Services**: $0 (GitHub Actions free tier, Cloud Scheduler free tier)

**Total**: $59/month × 12 = **$709/year**

**Storage Breakdown**:
- BigQuery: 26.72 GB (raw_denver: 24.61 GB, stg_denver: 2.09 GB, mart_denver: 0.02 GB)
- GCS: 4 GB (raw extracts + Parquet exports)

*Note: Costs verified via `gcloud billing` commands on December 4, 2025. The [Cost Optimization Case Study](docs/case-studies/bigquery-cost-optimization-2025.md) documents an earlier architecture with higher costs before November 2025 optimizations.*

### Why DuckDB?

DuckDB enables free local exploration, offline querying, CI-friendly testing, and easy data sharing—stakeholders can download a single `warehouse.duckdb` file and run queries immediately without cloud credentials.

### How fresh is the data?

- **GTFS Realtime**: ~8-minute lag from API publish to BigQuery (micro-batches every 5 minutes)
- **GTFS Static**: Updated monthly when RTD publishes new schedules
- **Weather**: 3-7 day lag (NOAA finalization period)
- **Crashes**: 24-hour lag (nightly ingest)
- **Demographics**: Annual (ACS 5-year estimates)

Run `./scripts/qa_script.sh` to validate data freshness. See [docs/QA_Validation_Guide.md](docs/QA_Validation_Guide.md) for details.

## Contributing

If you're contributing:

- **Code Quality**: Use `make format` for linting (Ruff) and formatting (Black)
- **Testing**: Run `make test` before submitting PRs
- **Commits**: Follow [Conventional Commits](https://www.conventionalcommits.org/) format (`feat:`, `fix:`, `docs:`, etc.)
- **Type Hints**: All functions must have complete type annotations

See [.github/workflows/README.md](.github/workflows/README.md) for workflow documentation.

## Additional Resources

- **[Pipeline Architecture](docs/ARCHITECTURE.md)** - Deep dive into data flow and system design
- **[dbt Models Documentation](dbt/models/README.md)** - All 25 models with materialization strategies
- **[Interactive Data Catalog](https://medsidd.github.io/whyline-denver/)** - Auto-generated dbt documentation
- **[GitHub Workflows](.github/workflows/README.md)** - CI/CD pipeline documentation
- **[QA Validation Guide](docs/QA_Validation_Guide.md)** - Health check procedures
- **[Data Contracts](docs/contracts/CONTRACTS.md)** - Schema specifications and versioning
- **[App Configuration](docs/THEMING.md)** - Branding, theming, and LLM provider setup
- **[Performance Guide](docs/guides/performance.md)** - Optimization recommendations

---

**Questions?** Open an issue or check the workflow logs in GitHub Actions. For architectural decisions, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).