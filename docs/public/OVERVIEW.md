# What Is WhyLine Denver?

WhyLine Denver is a free, open platform that helps people understand how well Denver's public transit system is actually working — and where it's letting people down.

---

## The Problem

Denver's Regional Transportation District (RTD) publishes a lot of data about its buses and trains. But that data is scattered across different systems, formatted in ways that require technical expertise to use, and difficult to connect to other information like weather, traffic safety, or who lives near each bus stop.

Transit planners have data. Riders have experiences. Advocates have arguments. But connecting those three things — especially across multiple data sources — has historically required expensive software or dedicated data teams.

WhyLine Denver exists to change that.

---

## What It Does

WhyLine Denver automatically collects transit data from multiple public sources, combines it, and makes it available through a simple question-and-answer interface.

You can ask questions like:
- "Which bus routes are most delayed during snowstorms?"
- "Which neighborhoods have both unreliable transit and high poverty?"
- "How many crashes happen within a block of transit stops on Colfax Avenue?"

The system translates your question into a database query, runs it, and shows you the results as a table, chart, or map. You can download the data as a spreadsheet to use in your own analysis.

---

## Four Things It Measures

**Reliability**: How often do buses and trains arrive on time? A vehicle is considered "on time" if it arrives within 5 minutes of its scheduled time. WhyLine Denver tracks on-time performance by route, by stop, by time of day, and by weather condition — going back months.

**Safety**: How close are traffic crashes to transit stops? Crash data from Denver's open data portal is matched to every stop, counting how many crashes occurred within 100 meters and 250 meters. This helps identify stops that may need better infrastructure for pedestrians and cyclists.

**Equity**: Are vulnerable communities being served well? WhyLine Denver combines transit reliability data with Census information about poverty, car ownership, and transit commuting to identify where unreliable service falls hardest on people who depend on it most.

**Access**: Can people actually get to transit stops? Using Denver's sidewalk network data, the system measures how much walkable infrastructure exists near each stop — identifying stops that are technically on a route but difficult to reach on foot.

---

## Who It's For

**Transit planners and city staff**: See patterns across the entire network. Find which routes consistently underperform, how weather affects service, and where the combination of poor service and high vulnerability creates the most urgent need for improvement.

**Riders and community members**: Check how your route performs. Find out whether the service you depend on runs reliably. See data about your neighborhood in plain language.

**Journalists and advocates**: Get numbers to support stories about transit equity, infrastructure gaps, or service reliability — without needing a data analyst.

---

## How It Stays Current

The system updates automatically. RTD bus and train locations are captured every 5 minutes, all day, every day. Weather and crash data refresh nightly. Schedule information updates whenever RTD publishes a new timetable.

The dashboard shows a "data freshness" timestamp so you always know how recent the information is.

---

## What It Doesn't Do

WhyLine Denver is an analysis platform, not a trip planner. It tells you how the system has been performing historically — it doesn't give real-time arrival predictions or help you plan a route.

It also doesn't include:
- Ridership or passenger counts
- Fare or payment data
- Information about buses outside the Denver RTD service area

---

## Open and Free

WhyLine Denver is an open-source project. The data it uses comes from public sources (RTD, Denver's open data portal, NOAA, the U.S. Census). The analysis code is publicly available on GitHub. Anyone can inspect how the metrics are calculated, propose improvements, or adapt the platform for another city.
