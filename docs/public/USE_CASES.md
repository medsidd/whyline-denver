# Use Cases

Real scenarios showing how different people use WhyLine Denver to answer transit questions.

---

## For Transit Planners

### Finding the Routes That Need Help Most

You're building a case for a service improvement proposal and need to show which routes consistently underperform — especially in neighborhoods where riders have few other options.

**Step 1: Find the worst-performing routes**

Open the dashboard and ask: *"Which bus routes have the lowest on-time performance over the past 90 days?"*

The dashboard returns a ranked list of routes by on-time percentage. You can sort, download the full table as a CSV, and see the SQL query that produced it.

**Step 2: Cross-reference with vulnerability**

Ask: *"Which stops on Route 15 have the highest vulnerability scores?"*

The dashboard pulls from the priority hotspot analysis — combining on-time performance with Census data on car ownership, transit commute rates, and poverty. A stop that is both unreliable and serves a transit-dependent population shows up as a priority hotspot.

**Step 3: Add safety context**

Ask: *"How many traffic crashes happened within 250 meters of stops on Route 15 in the past year?"*

You now have three dimensions — reliability, equity, and safety — for a specific route. Export all three as CSVs to attach to your proposal.

---

### Measuring Weather's Effect on Service

You want to know whether the agency's winter service plan is working, or whether snow is disproportionately degrading reliability on certain routes.

Ask: *"How does on-time performance change by weather category for each route?"*

The dashboard pulls from `mart_weather_impacts`, which compares on-time rates during no-precipitation days against light, moderate, and heavy precipitation days. Routes where heavy snow causes a large drop in reliability are candidates for winter service priority.

You can also ask: *"Which routes show the biggest delay increase during heavy snow?"*

The results show the average delay delta (in seconds) per route, letting you rank which routes are most weather-sensitive.

---

### Prioritizing Infrastructure Investments

You have capital budget for sidewalk improvements near bus stops and need to rank which stops should be addressed first.

Ask: *"Which stops have the lowest sidewalk access scores and the highest vulnerability?"*

WhyLine Denver combines sidewalk density (within 200 meters of each stop) with the vulnerability score to produce a ranked list of stops where poor pedestrian access coincides with high transit dependency.

This analysis pulls from `mart_access_score_by_stop` and `mart_vulnerability_by_stop`. Download the result and you have a data-backed prioritization list.

---

## For City Council Members and Policy Staff

### Understanding Which Neighborhoods Bear the Most Burden

You're preparing for a council presentation on transit equity and need plain-English data showing where service is worst and who lives there.

Ask: *"Which census tracts have the highest priority hotspot scores?"*

The priority hotspot score combines three things: how unreliable service is at nearby stops, how vulnerable the population is (poverty, car ownership, transit reliance), and how many traffic crashes occur nearby. Tracts with high priority scores are where the most work is needed.

Ask: *"Show me the top 10 stops by priority hotspot score with their route names and neighborhoods."*

The result gives you a table you can drop directly into a slide deck. Each row represents a stop where unreliable transit is harming people who depend on it most.

---

### Responding to a Constituent Complaint

A constituent calls to say bus service on their corridor is terrible. You want to check whether the data backs this up before responding.

Ask: *"What is the on-time performance for Route 44 in the past 60 days?"*

You get a day-by-day breakdown. If on-time performance is below 75%, you have quantitative evidence to take to the agency.

Ask: *"Are there crash hotspots near stops on Route 44?"*

If crashes cluster near specific stops, you have a safety dimension to raise alongside reliability.

---

### Comparing Neighborhoods

Two neighborhoods are competing for a transit improvement grant. You need to make an objective case for one.

Ask: *"Compare the average on-time performance for stops in Census tract 08031001600 versus 08031002000."*

Or, if you don't know the tract IDs:

Ask: *"Which neighborhoods around Federal Boulevard have the highest vulnerability scores?"*

The dashboard will match stops to tracts and return the comparison. You can export the underlying data to verify the analysis independently.

---

## For Journalists and Advocates

### Investigating a Service Reliability Story

You've heard from riders that a particular bus route is chronically late. You want data to back up the story.

Ask: *"What is the on-time percentage for Route 28 by hour of day for the past 90 days?"*

The dashboard returns hourly reliability. If the morning peak is particularly bad, you have a story: the route is least reliable exactly when most riders depend on it.

Ask: *"How does Route 28 compare to the system average on-time rate?"*

This gives you the comparison angle: not just "Route 28 is late" but "Route 28 is 20 percentage points below the system average."

---

### Connecting Transit Gaps to Demographics

You want to report on whether bus service is worse in lower-income parts of Denver.

Ask: *"Which routes serving areas with high poverty rates have the lowest on-time performance?"*

WhyLine Denver combines reliability data with Census poverty rates at the stop level. The result is a ranked list of routes where poor service and high poverty overlap.

Ask: *"Show me stops where more than 30% of households have no car and on-time performance is below 70%."*

This gives you a list of specific stops — with addresses — where transit-dependent riders are receiving the least reliable service. These are your story locations.

---

### Researching Crash Safety Near Transit Stops

You're reporting on pedestrian safety at bus stops following a high-profile crash.

Ask: *"Which bus stops have the most traffic crashes within 100 meters in the past 5 years?"*

The result ranks stops by crash count and includes severity breakdown (fatal, serious injury, injury, property damage). You can export the full list and map it yourself, or ask follow-up questions about specific stops.

Ask: *"How many crashes involving pedestrians happened within 250 meters of light rail stations?"*

This gives you the numbers for a story about pedestrian risk in the transit network's immediate surroundings.

---

## For Riders

### Checking If Your Route Runs on Time

You ride the same bus every morning and want to know if the delays you experience are typical or unusual.

Ask: *"How reliable is Route 15 during morning rush hours?"*

The dashboard shows on-time percentage by hour. You can see whether morning delays are a consistent pattern or occasional outliers.

Ask: *"Does Route 15 run worse in winter?"*

The weather impact analysis shows how your route's reliability changes in different weather conditions.

---

### Finding the Most Reliable Way to Get to Work

You have two bus options to get downtown and want to know which is more reliable.

Ask: *"Compare on-time performance between Route 16 and Route 28 for weekday mornings."*

The result gives you a side-by-side comparison. Combined with your own knowledge of walking distance and travel time, you can make an informed choice.

---

### Understanding Why the City Prioritizes Certain Routes

You've read that the city is investing in improving Route 44. You want to understand why.

Ask: *"What is the priority hotspot score for stops on Route 44?"*

The priority hotspot analysis shows the combination of factors — reliability, vulnerability, and safety — that make a route a priority. If the score is high, the investment is going where it's most needed.

---

## A Note on Data Freshness

All of these questions draw on data that is updated regularly but not instantaneously:

| Data | Typical freshness |
|------|------------------|
| Bus and train positions (reliability) | 5–15 minutes behind real-time |
| Crash records | 24–48 hours behind Denver Police reports |
| Weather conditions | 3–7 days (NOAA finalization period) |
| Census demographics | Annual (2023 ACS, published late 2024) |

For questions about current conditions, check RTD's own app or website. WhyLine Denver is best for historical analysis, patterns over time, and understanding system-wide trends — not for real-time trip planning.
