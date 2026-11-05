# Metrics spikes (WP16): findings, November 2, 2026

These are the short investigations from WP16 of the [metrics plan](metrics-implementation.md). Each checks whether a lower-priority source is available, usable and worth a work package. Endpoints were queried read-only on 2026-11-02; nothing is ingested.

| Spike | Verdict | Effort if pursued |
|---|---|---|
| Event schedules | Worth doing once a few months of crowding data exist | Small: one ingestor, one flag |
| Traffic speeds | Don't pursue; no free source for Denver's arterials | n/a |
| Air quality and heat | Cheap and free; add when a waiting-comfort measure is wanted | Small: extend the hourly weather ingestor |
| Peer agencies | Defer; costly and of little use to Denver riders | Large: a second poller |
| Stop amenities | Usable interim source in OpenStreetMap, but partial | Small: one ingestor |

## Event schedules

**Question:** do games and concerts explain crowding and delay spikes on routes near Ball Arena, Coors Field and Empower Field?

**Sources** (unauthenticated JSON):

| Team and venue | Endpoint | 2026 result |
|---|---|---|
| Rockies, Coors Field | `statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=115&startDate=…&endDate=…` | 159 games, 82 at home (April to September) |
| Avalanche, Ball Arena | `api-web.nhle.com/v1/club-schedule-season/COL/20262027` | 88 games, 44 at home |
| Nuggets, Ball Arena | `site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/den/schedule` | 80 events returned |
| Broncos, Empower Field | `site.api.espn.com/apis/site/v2/sports/football/nfl/teams/den/schedule` | 17 events |

**Limits:**
- These are league and media APIs, not open data. MLB's responses carry an MLB Advanced Media copyright notice, and ESPN's site API is undocumented. Publishing only a derived "home game that evening" flag (dates and times are facts) keeps the risk low; storing or republishing the raw responses doesn't.
- Concerts at Ball Arena, Red Rocks and Empower Field have no open feed.

**Recommendation:** add a small `event_schedules` ingestor and an `is_event_day` / `event_window` flag on route-hours near each venue once the crowding and missed-trip marts hold two to three months. That's enough evening games to compare like with like; five days of data can't.

## Traffic speeds

**Question:** is a slow bus segment slow because of traffic or because of transit operations?

**Findings:**
- CDOT's traveller data (COtrip) needs registration and covers state highways, not the city arterials most routes use.
- INRIX, HERE and TomTom speeds are paid.
- Uber Movement, once the free source, has closed.

WhyLine's own `mart_segment_speed_by_hour` already shows where buses crawl, and its delay ratio separates running slower than scheduled from a slow schedule.

**Recommendation:** don't pursue. Revisit if Denver or CDOT publish arterial speeds openly.

## Air quality and heat

**Question:** how uncomfortable is waiting at the stop?

**Findings:**
- Open-Meteo's air-quality API (`air-quality-api.open-meteo.com/v1/air-quality`, `hourly=pm2_5,us_aqi`) needs no key and is CC BY 4.0, the same terms as the weather source.
  - The check returned 48 hours for downtown Denver, with PM2.5 peaking at 33.9 µg/m³.
- Heat is already in `fct_weather_hourly` (`temp_c`).
- AirNow's official AQI needs a free key, and adds monitors but no stop-level detail.

**Recommendation:** when a waiting-comfort measure is wanted, for example "hours above 90 °F or AQI over 100 at the stop", extend `weather_hourly` with `pm2_5` and `us_aqi` from Open-Meteo: one more request per run. Air quality is city-wide at this resolution, so it adds context rather than stop-level differences.

## Peer agencies

**Question:** how does RTD's reliability compare with similar agencies?

**Findings:**
- **Feeds:** UTA (Salt Lake City), TriMet (Portland, free app ID) and the MBTA publish GTFS-RT.
- **Methods:** a fair comparison needs identical methods: the same poller, visit engine and on-time window. That means a second stream poller, archive and loader per agency, roughly doubling the realtime costs in [operations](../OPERATIONS.md).
- **Published figures:** each agency's own on-time numbers use different definitions, the same problem WP10 shows for RTD.

**Recommendation:** defer. A Denver rider gains little from it. If wanted later, poll one agency for a fixed month, rather than continuously.

## Stop amenities

**Question:** does my stop have a shelter, bench or light?

**Findings:**
- Searches found no RTD or Denver open dataset of stop amenities.
- OpenStreetMap, after its RTD bus stop import, tags 5,916 bus stops inside the RTD box.

| OpenStreetMap tag | Stops |
|---|---|
| `ref` (the RTD stop ID, for example `23485` Civic Center) | 3,089 |
| any `shelter` tag | 2,094 (858 `shelter=yes`) |
| any `bench` tag | 1,800 (1,257 `bench=yes`) |
| `shelter` and `ref` together | 1,307, about 16% of RTD's 8,155 current stops |

**Limits:**
- The data is crowd-sourced and uneven: absence means unknown, not "no shelter".
- It's licensed ODbL, so a published derived database has to stay ODbL, and OpenStreetMap must be credited.

**Recommendation:** for an interim amenity layer, ingest OpenStreetMap bus stops with `ref`, `shelter`, `bench`, `lit` and `bin`. Join them to stops by `ref`, show amenities only where tagged, and include a coverage figure. RTD's own inventory, via the deferred records request, would replace it.
