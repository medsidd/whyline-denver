#!/usr/bin/env bash
set -euo pipefail

python -m whylinedenver.ingest.gtfs_static --local
python -m whylinedenver.ingest.gtfs_realtime --local --snapshots 3 --interval-sec 60
python -m whylinedenver.ingest.denver_crashes --local
python -m whylinedenver.ingest.denver_sidewalks --local
python -m whylinedenver.ingest.noaa_daily --local --start 2024-11-01 --end 2024-11-30
python -m whylinedenver.ingest.acs --local --year 2023 --geo tract
