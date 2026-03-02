# Data Sources

WhyLine Denver uses five public data sources, all freely available without any licensing restrictions on non-commercial use.

---

## RTD GTFS Static (Schedules)

**What it is**: The official published timetables for all RTD routes — every bus, light rail, and commuter rail line in Denver. This is the "on time" standard that all reliability measurements are compared against.

**What it covers**: Routes, stops, trip schedules, stop sequences, service calendars (which days each trip runs), and geographic shapes (the paths buses take).

**Where it comes from**: RTD's GTFS static feed at `rtd-denver.com/files/gtfs/google_transit.zip`. RTD is required to publish this under the General Transit Feed Specification, a public standard.

**How often updated**: Nightly. RTD typically publishes new schedules when service changes (usually quarterly, or with major schedule updates).

**Known limitations**:
- Does not include real-time information — only planned schedules
- Historical schedule data is not retained by RTD; WhyLine Denver keeps a daily snapshot per extract date
- Does not include frequency-based service (some routes publish headways rather than exact times)

**License**: [RTD Open Data License](https://www.rtd-denver.com/open-data-license)

---

## RTD GTFS-RT (Real-time Vehicle Positions and Delays)

**What it is**: A live feed of where every RTD vehicle is right now, updated every minute or less by RTD's systems. WhyLine Denver captures this feed every 5 minutes.

**What it covers**: For each active vehicle: which route it's on, which trip it's running, estimated arrival time at upcoming stops, and how many seconds ahead of or behind schedule it is. Also includes GPS coordinates for each vehicle.

**Where it comes from**: RTD's GTFS Realtime feeds at `rtd-denver.com/files/gtfs-rt/TripUpdate.pb` (delays) and `rtd-denver.com/files/gtfs-rt/VehiclePosition.pb` (positions). GTFS-RT is a Google-developed open standard used by transit agencies worldwide.

**How often updated**: Snapshots captured every 5 minutes, 24 hours a day. The data in WhyLine Denver reflects these captures; there is typically a 5–15 minute lag between a bus arriving at a stop and that event appearing in the reliability metrics.

**Known limitations**:
- Not all stops on every trip are always reported. Coverage varies by route.
- GPS accuracy can vary; vehicle positions are not always exact.
- Delay values are estimates from RTD's operations systems. They can be inaccurate, especially at the beginning of a trip or when a vehicle is significantly off-schedule.
- Only captures the moment the snapshot runs. If a bus runs late between snapshots, that event may not be recorded.
- Does not include on-demand or paratransit services (Access-a-Ride, etc.).

**License**: [RTD Open Data License](https://www.rtd-denver.com/open-data-license)

---

## Denver Open Data — Traffic Crashes

**What it is**: Records of all traffic accidents reported in Denver, going back 5 years. Each record includes the location, date and time, severity, type of collision, and whether pedestrians or cyclists were involved.

**What it covers**: Crashes with fatalities, serious injuries, injuries, and property-damage-only incidents. Includes street address and geographic coordinates (latitude and longitude).

**Where it comes from**: Denver's open data portal via an ArcGIS feature service. Data is compiled from Denver Police Department reports.

**How often updated**: Nightly. There is typically a 24-hour lag between an incident and its appearance in the data.

**Known limitations**:
- Only includes crashes that were reported to Denver Police. Minor incidents may go unreported.
- Some records are missing precise coordinates and can only be matched to a street address, not a specific location.
- The most recent 30 days of data may be less complete than older data, as police reports are sometimes delayed.
- Does not include crashes on highways managed by CDOT (Colorado Department of Transportation) that pass through Denver.
- Bike and pedestrian involvement flags are self-reported in the crash record and may be inconsistent.

**License**: [Denver Open Database License](https://www.denvergov.org/opendata/terms)

---

## Denver Open Data — Sidewalks

**What it is**: Denver's inventory of sidewalk segments across the city. Includes the location (as a line segment), type, material, condition status, and year built.

**What it covers**: Classified sidewalk segments in the city of Denver's right-of-way.

**Where it comes from**: Denver's open data portal, maintained by Denver Public Works and the Department of Transportation and Infrastructure.

**How often updated**: Nightly. The underlying dataset changes infrequently — sidewalk infrastructure doesn't change day-to-day.

**Known limitations**:
- Coverage is not complete for all areas of Denver. Some neighborhoods, particularly newer developments and unincorporated areas, may have incomplete records.
- Condition information (whether a sidewalk is in good repair) is not consistently included.
- Does not include private sidewalks or paths within parks and open spaces.
- The dataset reflects what Denver has surveyed and inventoried; actual conditions on the ground may differ.

**License**: [Denver Open Database License](https://www.denvergov.org/opendata/terms)

---

## NOAA — Daily Weather Summaries

**What it is**: Daily summaries of weather observations at Denver International Airport's weather station (station ID USW00023062).

**What it covers**: Daily totals and averages for: precipitation (rain, mm), snowfall (mm), minimum temperature, maximum temperature, and average temperature. Also includes a derived field categorizing precipitation as none, light, moderate, or heavy.

**Where it comes from**: NOAA's Climate Data Online API (CDO). This is the National Oceanic and Atmospheric Administration's historical climate data service.

**How often updated**: Nightly, with a 3–7 day lag. NOAA finalizes daily weather records a few days after the observation date to ensure quality control. Data from the last week may be incomplete.

**Known limitations**:
- One station covers all of Denver. Weather conditions vary across the metro area — a storm that dumps 8 inches in the foothills may produce less at DIA.
- Does not capture intra-day weather events (a brief afternoon thunderstorm may not significantly affect the daily precipitation total even if it disrupted afternoon rush service).
- Snow totals can be unreliable in windy conditions due to measurement challenges.
- Temperature data is from the airport, which may differ from urban neighborhoods due to the urban heat island effect.

**License**: Public domain (U.S. government data)

---

## U.S. Census — American Community Survey (ACS)

**What it is**: The Census Bureau's ongoing survey of U.S. households, published annually as 5-year estimates. WhyLine Denver uses the 2023 5-year estimates at the census tract level for Denver County (FIPS: 08031).

**What it covers**: For each census tract: number of households without a car, total households, number of workers commuting by transit, total workers, persons below the poverty line, total population. Derived percentages are calculated from these counts.

**How often updated**: Annually. The 2023 ACS was published in late 2024. This data does not reflect changes from the past year or two.

**Known limitations**:
- 5-year estimates average survey responses from 2019–2023. They reflect the period broadly, not a specific moment.
- At the census tract level, margins of error can be significant, especially for small tracts or rare characteristics. Treat tract-level percentages as approximate.
- The 2020 COVID pandemic affected commuting patterns significantly; the 2023 estimates include years of disrupted transit ridership.
- Does not capture students, seasonal residents, or the unhoused population.
- Census tract boundaries are updated with each decennial census. WhyLine Denver uses 2020 tract boundaries, which may differ from pre-2020 maps.

**License**: Public domain (U.S. government data)

---

## U.S. Census — TIGER/Line Tract Boundaries

**What it is**: The geographic boundary files for Denver County census tracts. These are the shapes (polygons) used to match census data to transit stop locations.

**Where it comes from**: Census TIGER Web API, using 2020 census tract boundaries.

**How often updated**: Decennial (every 10 years). The 2020 boundaries are the current version.

**License**: Public domain (U.S. government data)

---

## What WhyLine Denver Does Not Include

- **Ridership/passenger counts**: RTD does not make boardings and alightings available in real-time or through GTFS.
- **Fare or revenue data**: Not available in any public RTD dataset.
- **Service quality beyond punctuality**: Customer complaints, cleanliness, accessibility compliance, operator behavior.
- **Light rail or commuter rail stations**: The data pipeline captures all GTFS routes, including light rail and commuter rail. However, spatial metrics (crash proximity, sidewalk access) are calculated for all stops regardless of mode.
- **Incidents and service alerts**: RTD's GTFS-RT service alerts feed is not currently ingested.
- **Regional bus routes outside Denver County**: Some RTD routes extend into Jefferson County, Adams County, and other jurisdictions. Stop-level equity data uses Denver County census tracts only; stops in other counties may have missing or incomplete equity scores.
