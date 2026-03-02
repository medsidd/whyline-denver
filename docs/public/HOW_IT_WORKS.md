# How WhyLine Denver Works

This page explains the journey from a bus on a Denver street to an answer in the dashboard — in plain language, without technical jargon.

---

## Collecting the Data

### Real-time bus and train locations

Every 5 minutes, an automated system connects to RTD's live feed and records where every bus and train in Denver is at that moment. For each vehicle, it captures:
- Which route it's on
- Which stop it just served or is approaching
- How many seconds ahead of or behind schedule it is

This happens around the clock, generating hundreds of thousands of records per day. Over months, it builds a detailed picture of how reliably each route runs.

### Nightly updates

While you sleep, WhyLine Denver automatically updates three other data sources:

**Schedules** (RTD GTFS): RTD publishes the official schedule for every bus and train — which stops they serve, at what times, on which days of the week. This is the "on time" yardstick everything else is measured against.

**Weather** (NOAA): Daily temperature, precipitation, and snowfall from Denver International Airport's weather station. This lets us ask questions like "How does snow affect Route 15L?"

**Crashes** (Denver Open Data): Traffic accident records from Denver's police and public works databases, with location, severity, and whether bikes or pedestrians were involved.

**Sidewalks** (Denver Open Data): Denver's inventory of sidewalk segments, including type, material, and whether they're accessible. This tells us whether each stop is physically reachable on foot.

**Demographics** (U.S. Census): Neighborhood-level data from the American Community Survey: household car ownership, transit commuting rates, and poverty rates. This is how the equity analysis connects transit quality to community need.

---

## Turning Raw Data into Answers

Raw data alone doesn't answer questions. A spreadsheet of GPS coordinates every 5 minutes doesn't tell you whether Route 40 runs late. WhyLine Denver does several things to make that data meaningful:

**Matching real-time observations to the schedule**: For each captured vehicle position, the system figures out which scheduled arrival it corresponds to, and calculates how late or early the vehicle was. This produces a delay measurement, in seconds, for each stop event.

**Aggregating to useful time periods**: Raw stop-by-stop delays get rolled up into daily on-time rates per route. So instead of millions of individual observations, you get one number per route per day: the fraction of stop arrivals within 5 minutes of schedule.

**Connecting to weather**: The daily on-time rate gets joined to that day's weather. This makes it possible to compare performance on snowy days vs. dry days for any route.

**Spatial joins**: Stop locations are matched to crash records and sidewalk segments within a given radius. This requires knowing the coordinates of every stop and then searching for nearby crashes or sidewalk gaps — a computation done once and stored in the database.

**Equity scoring**: Census demographic data is matched to stops by finding which census tracts fall within a half-mile of each stop. The poverty rate, car ownership rate, and transit commuting rate are averaged (weighted by population) to produce a vulnerability score for each stop.

---

## The Dashboard

When you use the WhyLine Denver dashboard, here's what happens:

**Step 1: You ask a question**

You type something like "Which routes are most delayed when it snows?" in plain English. The system sends your question to an AI, which translates it into a database query. The AI has access to descriptions of all the available data — it knows that `mart_reliability_by_route_day` contains daily on-time rates and has a `precip_bin` column that classifies weather — so it can write the right query for your question.

Before running anything, the query is checked for safety: it can only read data (no modifications), and it can only access the pre-approved analysis tables.

**Step 2: You review the query**

The dashboard shows you the exact database query that will run before you execute it. For anyone who knows SQL, this is fully readable and editable. For those who don't, the AI also provides a plain-English explanation of what the query does.

If you're running against the cloud database (BigQuery), you'll also see an estimate of how much data the query will scan — this is visible before execution to prevent accidental costly queries.

**Step 3: Results appear as tables, charts, and maps**

When you click "Run Query," the results appear as:

- **A table**: Every row and column, sortable and scrollable
- **A chart** (auto-detected): If your results contain dates and on-time rates, you get a time series. If they contain weather categories, you get a multi-panel chart. If they include route names and delays, you get a ranked bar chart.
- **A map** (if the data has locations): Stop-level results appear as dots on a map of Denver. The size and color of each dot reflects the metric value — darker or larger means worse performance.
- **A download button**: Export the results as a CSV to use in Excel, Tableau, or your own analysis tools.

---

## Two Ways to Query

**BigQuery mode**: Queries run against the live cloud database. Data is as fresh as the last update (usually within a few hours). Good for large-scale analysis or when you need the most current data. Requires cloud credentials.

**DuckDB mode**: Queries run against a local copy of the database, downloaded to your computer. Completely free, works offline, and very fast for moderate-sized queries. The data is a snapshot from the last sync (usually updated nightly). Good for exploration and development.

---

## Data Freshness

| What you're looking at | How fresh | Notes |
|-----------------------|-----------|-------|
| Bus/train arrival delays | Updated nightly | Real-time captures happen every 5 min; rolled into analytics overnight |
| Schedules (routes, stops, times) | Updated when RTD publishes | Typically monthly or when service changes |
| Weather | 3-7 day lag | NOAA finalizes historical records a few days after the date |
| Crashes | ~24 hour lag | Denver Open Data updates the following day |
| Demographics (poverty, car ownership) | Annual | From the 5-year American Community Survey |

The dashboard shows a freshness timestamp in the header so you always know how current the data is.
