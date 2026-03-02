# Metrics Glossary

Plain-English definitions of every metric in WhyLine Denver. If you see a column name in the dashboard that isn't defined here, please open an issue.

---

## Reliability Metrics

### On-time performance (`pct_on_time`)

The fraction of scheduled stop arrivals where the vehicle arrived within 5 minutes of the scheduled time. Expressed as a decimal between 0 and 1 (or 0% to 100%).

- **0.95** means 95% of arrivals were on time
- **0.60** means 40% of arrivals were late by more than 5 minutes
- The 5-minute threshold (300 seconds) is a standard used in transit planning. It reflects the practical tolerance most riders have for a "late" bus.

**Where you'll see it**: `mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`

---

### Mean delay (`mean_delay_sec`)

The average number of seconds a vehicle arrives after its scheduled time, across all measured arrivals for a given route, day, or stop. Negative values mean the vehicle was ahead of schedule.

- **A mean delay of 120** means the average bus arrived 2 minutes late
- **A mean delay of -30** means the average bus arrived 30 seconds early
- Running ahead of schedule can be as problematic as running late — early buses miss passengers who are timing their arrival based on the schedule

**Where you'll see it**: `mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`

---

### 90th percentile delay (`p90_delay_sec`)

The delay value that 90% of observations fall below. A "worst-case typical" measure — it filters out true outliers while still representing the experience of riders who get unlucky.

- If `p90_delay_sec = 600`, then 90% of arrivals were within 10 minutes of schedule, but 10% were more than 10 minutes late
- Useful for understanding worst-case reliability, not just average performance

**Where you'll see it**: `mart_reliability_by_route_day`, `mart_reliability_by_stop_hour`

---

### Headway adherence rate (`headway_adherence_rate`)

The fraction of observed gaps between consecutive vehicles that fell within 50% of the scheduled gap. For frequent-service routes (buses every 10 minutes or less), headway adherence matters more than strict on-time performance because riders don't always know the schedule — they just show up and wait.

- **A rate of 0.80** means 80% of vehicle gaps matched the expected spacing
- **Bunching** (two buses arriving close together, then a long gap) shows up as low headway adherence
- Even a route with 90% on-time performance can have severe bunching

**Where you'll see it**: `mart_reliability_by_stop_hour`

---

### Weather impact (`delta_pct_on_time`)

The change in on-time percentage compared to dry-weather performance. Calculated as the average on-time rate during a given weather condition minus the baseline (dry/no precipitation) rate.

- **-0.15** in snow means on-time performance drops 15 percentage points when it snows
- Helps identify which routes are most vulnerable to weather disruptions

**Where you'll see it**: `mart_weather_impacts`

---

### Precipitation category (`precip_bin`)

Daily precipitation classified into four levels:
- **none**: 0mm (dry day)
- **light**: trace to 5mm (light rain or flurries)
- **mod** (moderate): 5–20mm (steady rain or light snow)
- **heavy**: more than 20mm (significant storm)

Precipitation is measured in millimeters from NOAA's daily weather summary. The categories are derived from the raw totals at Denver's main weather station.

---

## Safety Metrics

### Crash proximity (`crash_100m_cnt`, `crash_250m_cnt`)

The number of recorded traffic crashes within 100 meters (about 1 city block) and 250 meters (about 2-3 blocks) of a transit stop. Crashes are counted over the most recent 365 days.

- These are all crashes, not just transit-related ones
- The 100m and 250m radii represent the area a pedestrian walks to reach a stop from their origin
- Higher counts indicate areas with elevated risk for transit riders walking to or from stops

**Where you'll see it**: `mart_crash_proximity_by_stop`

---

### Serious injury crash count (`severe_100m_cnt`, `severe_250m_cnt`)

Crashes resulting in serious injury (not property damage or minor injury only). A subset of total crash counts. Defined by the Denver Police Department's severity classification in the source data.

---

### Fatal crash count (`fatal_100m_cnt`, `fatal_250m_cnt`)

Crashes resulting in at least one fatality. The most severe category.

---

### Crash score (`crash_score_0_100`)

A 0–100 normalized version of crash proximity used in the priority hotspot calculation. 100 means the highest crash exposure among all stops in Denver; 0 means the lowest. This normalization allows combining crash exposure with other metrics on a common scale.

**Where you'll see it**: `mart_priority_hotspots`

---

## Equity and Vulnerability Metrics

### Vulnerability score (`vuln_score_0_100`)

A composite 0–100 score that combines three census indicators for the neighborhoods within a half-mile of a transit stop:

1. **Percentage of households without a car** (`pct_hh_no_vehicle`): People in these households depend on transit to get around.
2. **Percentage of workers who commute by transit** (`pct_transit_commute`): Reflects how much the neighborhood relies on transit for access to employment.
3. **Poverty rate** (`pct_poverty`): The share of residents below the federal poverty line, from the Census American Community Survey.

Each indicator is population-weighted (tracts with more people have more influence) and averaged. The combined score is then normalized to 0–100 across all Denver stops.

- **100** = highest vulnerability in Denver (most car-free, most transit-dependent, highest poverty)
- **0** = lowest vulnerability

**Where you'll see it**: `mart_vulnerability_by_stop`, `mart_priority_hotspots`

---

### Priority score (`priority_score`) and rank (`priority_rank`)

A composite measure that combines vulnerability, crash exposure, and reliability into a single ranking. The formula:

**Priority score = (0.5 × vulnerability) + (0.3 × crash exposure) + (0.2 × unreliability)**

Each component is normalized to 0–100 before combining. The weights reflect a deliberate prioritization: serving vulnerable populations is the most important factor (50%), followed by safety risk (30%), and reliability gaps (20%).

`priority_rank` is the ordinal ranking from 1 (highest priority) to N (lowest). Useful for "top 10 stops most in need of attention" queries.

**Where you'll see it**: `mart_priority_hotspots`

---

## Access Metrics

### Sidewalk length within 200m (`sidewalk_len_m_within_200m`)

The total length, in meters, of sidewalk segments within 200 meters of a transit stop. Includes all classified sidewalk segments in Denver's infrastructure inventory, regardless of condition or type.

**Where you'll see it**: `mart_access_score_by_stop`

---

### Access score (`access_score_0_100`)

The sidewalk length within 200m, normalized to a 0–100 scale across all Denver stops.

- **100** = the most sidewalk coverage of any stop in Denver
- **0** = the least (or none)
- Low scores indicate stops that may be difficult to walk to or from, even if transit service is frequent

**Where you'll see it**: `mart_access_score_by_stop`

---

## Reference Fields

### Service date (`service_date_mst`)

The calendar date, in Mountain Standard/Daylight Time, on which a transit service day occurred. Transit service days are defined by the GTFS schedule — a "Tuesday service" on the schedule corresponds to `service_date_mst` regardless of what UTC date the event occurred on.

All reliability metrics are reported by service_date_mst, not UTC date. This ensures that late-night service on a Monday (which may technically be Tuesday UTC) is attributed to Monday's service day.

---

### Stop ID (`stop_id`)

RTD's internal identifier for a transit stop. Comes directly from the GTFS `stops.txt` file. Used as the joining key across most stop-level metrics.

---

### Route ID (`route_id`)

RTD's internal identifier for a transit route (e.g., "1" for Route 1, "15L" for the 15 Limited). Comes from the GTFS `routes.txt` file.

---

### Build run date (`build_run_at`)

The date on which the analytics pipeline last computed a given mart. For snapshot tables (crashes, access, vulnerability, priority), this tells you when the analysis was last refreshed. For time-series tables, it reflects when each partition was last built.
