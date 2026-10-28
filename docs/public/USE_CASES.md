# Questions to investigate

These are suggested workflows, not evidence that named users performed them or that particular local findings have been established. Start with the available dates/source coverage and [metric definitions](METRICS_GLOSSARY.md).

| Audience / question | Starting data | How to interpret it |
|---|---|---|
| Planner: which routes have lower on-time shares? | `mart_reliability_by_route_day` | Compare the same dates, event counts, and reported-delay coverage; sampled events are not all arrivals. |
| Service analyst: where is vehicle spacing inconsistent? | `mart_reliability_by_stop_hour` | Inspect headway matching and observation density; sparse samples may not reconstruct actual service gaps. |
| Advocate: where do service problems overlap with vulnerability? | `mart_priority_hotspots`, `mart_vulnerability_by_stop`, stop-hour reliability | Treat scores as a screening tool. Higher `reliability_score_0_100` means worse reliability; missing components count as zero in priority scoring. |
| Safety analyst: which stops have more nearby crashes? | `mart_crash_proximity_by_stop` | Check `as_of_date`; counts include all qualifying nearby crashes and are not per-rider or transit-causation measures. |
| Infrastructure planner: where is recorded sidewalk length low? | `mart_access_score_by_stop` | Verify inventory coverage, connectivity, crossings, and conditions in a separate review before proposing a walking-access intervention. |
| Journalist: is reliability associated with precipitation? | `mart_weather_impacts`, route-day reliability | Require observed transit/weather overlap and a dry baseline. Precipitation categories do not identify snow; averages do not prove causation. |
| Resident: how do observations near my stop vary by hour? | Stop-hour reliability + `mart_gtfs_stops` | Check the stop ID and date range; use an arrival/trip-planning service for current travel decisions. |

## A reproducible workflow

1. Choose a question, engine, and date range with available data.
2. Load/generate SQL and check its grouping, filters, missingness treatment, and score direction.
3. Run it and inspect table values as well as the chart/map.
4. Check counts, baseline availability, geographic gaps, and possible source selection bias.
5. Save CSV plus the SQL, engine, dates, and freshness/source notes before sharing.

The four built-in cards offer a starting point rather than exhaustive analysis. The weather card's current snow label does not match its moderate/heavy-precipitation filter; inspect the query before using it as a snow example.

Questions about ridership, fares, crowding, service alerts, causal weather effects, individual rider demographics, or verified accessible walking routes need additional data/methods. The dashboard cannot establish those from the current warehouse.
