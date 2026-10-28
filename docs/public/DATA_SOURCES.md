# Data sources and coverage

Seven ingestors draw from four source organizations. Collection frequency describes our pipeline, not how recently the publisher observed or revised its data. Current schedules/status are dated in [operations](../technical/OPERATIONS.md).

| Ingested dataset | Configured coverage | Collection and limitations |
|---|---|---|
| RTD GTFS schedules | Stops, routes, trips, stop times, calendars, shapes in the published feed | Nightly extraction. Latest schedule is expanded for analysis; it is not a historical version-matched timetable for every past observation. |
| RTD GTFS realtime | Trip Updates and Vehicle Positions | 15-minute Cloud Scheduler sampling as verified October 26, 2026. Not every trip/stop/mode appears; updates can be predictions and staging selects one row per trip/snapshot. |
| Denver crashes | Denver ArcGIS crash records; ingestor defaults to a five-year source window | Nightly extraction. Location/reporting quality varies. The mart counts a 365-day window ending on the latest crash date in staging, not necessarily today. |
| Denver sidewalks | Inventoried Denver sidewalk segments | Nightly extraction of a slowly changing source. Missing inventory is not proof there is no sidewalk; nearby line length does not verify surface quality, safe crossings, connectivity, or accessibility. |
| NOAA GHCND daily weather | Denver International Airport, station `USW00003017`; precipitation, snow, min/max/average temperature | Rolling 30-day collection through yesterday. Publication delays and missing fields vary. One airport station cannot describe every neighborhood's weather. |
| Census ACS five-year estimates | Configured 2023 vintage, Denver County tract geography | Re-extracted nightly; annual source releases do not automatically change the configured vintage. Estimates describe a multi-year population, with uncertainty; no rider-level demographics are observed. |
| Census TIGERweb tract boundaries | Configured 2020 boundaries for Denver County | Attempted in nightly static collection as a nonfatal reference-data step. Boundaries are not annually changing observations. |

## Weather missingness

The former Central Park station (`USW00023062`) is no longer the default. The October 2026 repair aligned ingestion and dbt on the airport station and preserved older raw files. Weather units are mm/Celsius. Missing precipitation is null in source data and `unknown` in route-day summaries; unavailable snow can remain null. Comparisons exclude unknown weather, and a missing dry baseline can yield a null delta.

There is no fixed promise that NOAA data becomes complete after a specified number of days. Check the station, metric, and requested dates. See [weather collection](../guides/NOAA_Data_Collection_Strategy.md).

## Geographic and analytical limits

RTD stops/routes can extend beyond Denver County. Census and city infrastructure coverage is narrower; nearby Denver tracts may be associated with a stop within about half a mile, including near county boundaries. Missing values can reflect coverage, unmatched identifiers, incomplete sources, or processing problems and should be investigated rather than assigned one cause automatically.

Crash buffers include all qualifying reported crashes nearby, not only crashes involving transit riders. Sidewalk access and vulnerability scores are relative to the observed dataset. Combining them with reliability does not remove their uncertainty.

The project does not ingest service alerts, fares/revenue, passenger counts, crowding, or verified accessible walking routes. Bus/rail inclusion depends on published feed coverage; no fixed list of current rail lines is maintained in this document.

## Terms and attribution

The configured endpoints are in `src/whyline/ingest/` and the output contract is in [data contracts](../contracts/CONTRACTS.md). Public availability does not imply unrestricted reuse of every source. Review [RTD's open-data terms](https://www.rtd-denver.com/open-records/open-spatial-information/gtfs-realtime-license-agreement), [Denver's catalog and dataset-specific terms](https://opendata-geospatialdenver.hub.arcgis.com/), and the applicable NOAA/Census agency notices when redistributing data.
