# Frequently Asked Questions

---

## About the Data

### How current is the information?

It depends on the data source:

| Data | How current | Why |
|------|-------------|-----|
| Bus and train reliability | 5–15 minutes behind real-time | RTD broadcasts positions every minute; WhyLine captures a snapshot every 5 minutes |
| Traffic crashes | ~24–48 hours behind | Denver Police reports take time to process and appear in the open data portal |
| Weather conditions | 3–7 days behind | NOAA finalizes daily weather records a few days after the fact for quality control |
| Census demographics | Annual | The 2023 American Community Survey (published late 2024) is the most recent available |
| Bus schedules | Updated when RTD publishes | Schedule changes happen quarterly or with major service adjustments |

WhyLine Denver is designed for historical analysis and pattern-finding, not real-time trip planning. For live arrivals, use RTD's app or Google Maps.

---

### Where does the data come from?

All data comes from public sources — no scraping, no private agreements:

- **RTD** provides bus and train schedules (GTFS) and real-time vehicle positions (GTFS-RT), published under RTD's open data license
- **Denver Open Data Portal** provides traffic crash records and sidewalk infrastructure data, compiled from city agencies
- **NOAA** provides daily weather summaries from Denver International Airport's weather station
- **U.S. Census Bureau** provides neighborhood demographic data from the American Community Survey and TIGER tract boundaries

None of these sources require a license fee or special access agreement for non-commercial use. See [Data Sources](DATA_SOURCES.md) for the full breakdown.

---

### Why does the dashboard say on-time performance is X% when I know my bus is always late?

A few reasons this can happen:

**Coverage gaps in the realtime feed**: RTD's GTFS-RT feed doesn't always report every stop on every trip. If your stop or route has sparse coverage, the on-time calculation is based on fewer observations, which can make it look better or worse than reality.

**5-minute capture window**: WhyLine captures a snapshot every 5 minutes. If a bus arrives and departs between snapshots, that event isn't recorded.

**The "on-time" definition**: A vehicle is counted on-time if it arrives within 5 minutes of its scheduled time. A bus that's consistently 4 minutes late — frustrating for riders — still counts as on-time under this standard.

**Route direction and time of day**: Overall route numbers average all directions, all times of day, and all stops. Your specific stop in the specific direction you ride may perform differently. Try asking the dashboard for a specific time window or direction.

---

### Does the data include light rail and commuter rail?

Yes. The data pipeline ingests all RTD routes — bus, light rail (the "W," "E," "R," "C," "D," "H," "L" lines), and commuter rail (the "A" and "B" lines). However:

- GTFS-RT coverage varies by mode. Light rail and commuter rail vehicles may be reported with different frequency than buses.
- Spatial metrics like crash proximity and sidewalk access are calculated for all stops, but the interpretation differs for light rail stations (which have dedicated pedestrian infrastructure) versus bus stops.

---

### Why are some stops missing vulnerability or access data?

**Vulnerability data** (poverty, car ownership, transit commuting) comes from Census tract boundaries for Denver County (FIPS: 08031). Stops in adjacent counties — Jefferson, Adams, Arapahoe — fall outside Denver County and won't have Census data attached.

**Access scores** (sidewalk density) depend on Denver's sidewalk inventory. Some areas, particularly newer developments and unincorporated zones, have incomplete sidewalk records.

If a stop shows null values for these metrics, it's outside the data coverage area, not a data error.

---

### How are crash records matched to transit stops?

Crashes are matched spatially: any crash with a recorded location within 100 meters or 250 meters of a stop is counted for that stop. The matching uses geographic coordinates from both datasets.

Crashes without precise coordinates (only a street address, no lat/lon) are excluded from proximity calculations. This affects a small percentage of records — primarily older crash reports.

---

## About the Dashboard

### Do I need to know SQL to use this?

No. You can ask questions in plain English and the dashboard converts them to SQL automatically. The SQL is shown to you before the query runs, so you can see exactly what's being asked of the data — but you don't need to read or modify it.

If you're comfortable with SQL and want to write your own queries, you can edit the SQL directly in the SQL editor step.

---

### Is my data collected when I use the dashboard?

No personal data is collected. The dashboard doesn't require an account, doesn't track who you are, and doesn't store your queries beyond your current browser session. If you close the browser tab, your session resets.

The only data flowing through the system is the SQL queries you submit (converted from your questions) and the results returned. These are not logged or stored beyond the current session.

---

### Why does the dashboard sometimes say it can't answer a question?

A few possible reasons:

**The question is outside the data**: WhyLine Denver covers transit reliability, weather impacts, crash proximity, sidewalk access, and neighborhood demographics. Questions about fares, ridership counts, crowding, or individual trip planning fall outside what the data includes.

**The question requires data that isn't available**: If you ask about specific dates with no data (too far in the past, or the most recent few days when NOAA data is still finalizing), the query may return no results.

**The generated SQL needs refinement**: Natural language is ambiguous. If the first answer isn't what you expected, try rephrasing with more specific terms — route numbers, date ranges, or specific metric names from the [Metrics Glossary](METRICS_GLOSSARY.md).

---

### Can I download the data?

Yes. Any query result can be downloaded as a CSV file using the download button in the results step. You can also use the dashboard's export feature to download full mart tables as CSVs or Parquet files.

---

## About the Project

### Who built this and why?

WhyLine Denver is an open-source project built to make Denver's transit data more accessible. All the data it uses is public, but GTFS feeds are technical, real-time updates disappear unless archived, and crash/demographic/weather data sits in separate places with incompatible formats.

The project combines these sources into a single, queryable interface — with a focus on equity: making visible where unreliable service overlaps with high transit dependence.

It's not affiliated with RTD or the City of Denver. It's independently built and maintained. The code is on GitHub at [github.com/medsidd/whyline-denver](https://github.com/medsidd/whyline-denver).

---

### Is this project affiliated with RTD or the City of Denver?

No. WhyLine Denver uses publicly available data from RTD and the City of Denver, but it is not an official RTD or City product. It has no relationship with either organization.

---

### Can this be adapted for another city?

Yes. If your transit agency publishes GTFS feeds (most U.S. agencies do), the data pipeline can be adapted. You'd need to:

1. Replace RTD's GTFS feed URL with your agency's URL
2. Point crash and sidewalk ingestors to your city's open data portal
3. Change the NOAA station ID to your local weather station
4. Update Census geography filters to your county

Most of the transformation logic works as-is for standard GTFS data. See [docs/technical/guides/ADAPTING_TO_OTHER_CITIES.md](../technical/guides/ADAPTING_TO_OTHER_CITIES.md) if you want to do this yourself.

---

### What does it cost to run?

Running costs are dominated by Google Cloud (Cloud Run jobs for data capture, Cloud Storage for raw data and the data warehouse). BigQuery query costs are minimal because queries are constrained to pre-built summary tables.

The project runs on the free tier or low-cost tiers of most services it uses. See [docs/COST_OPTIMIZATION_DEC_2025.md](../COST_OPTIMIZATION_DEC_2025.md) for the full cost breakdown and optimization history.

Using the DuckDB engine (local queries without cloud access) has zero per-query cost.

---

### The data shows something that seems wrong. Who do I contact?

Open an issue on GitHub: [github.com/medsidd/whyline-denver/issues](https://github.com/medsidd/whyline-denver/issues)

Include:
- The question you asked (or the SQL query, if shown)
- What result you got
- What you expected to see or what seems wrong

Data quality issues upstream (in RTD's feeds, Denver's crash data, or NOAA records) can't be fixed in WhyLine Denver, but they can be flagged so others know about them.
