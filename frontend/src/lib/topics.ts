/** What people can ask about: the landing page's topic list and the dashboard's topics panel. */
export interface Topic {
  name: string;
  /** Tailwind classes for the topic's line color and its light tint */
  line: string;
  tint: string;
  body: string;
  example: string;
  source: string;
}

export const TOPICS: Topic[] = [
  {
    name: "Reliability",
    line: "bg-wl-teal",
    tint: "bg-wl-teal-tint",
    body: "On-time share, waits and bunching, missed trips, crowding, and how far to trust the arrival countdown, by route, stop and hour.",
    example: "Which routes missed the most scheduled trips last week?",
    source: "From RTD GTFS schedules and GTFS-Realtime",
  },
  {
    name: "Weather",
    line: "bg-wl-gold",
    tint: "bg-wl-gold-tint",
    body: "How on-time performance shifts on days with rain or snow.",
    example: "Do snowy days lower on-time performance on route 0?",
    source: "From NOAA daily observations at Denver International Airport",
  },
  {
    name: "Safety",
    line: "bg-wl-red",
    tint: "bg-wl-red-tint",
    body: "Reported traffic crashes within 250 meters of each stop.",
    example: "Which stops have the most crashes nearby?",
    source: "From Denver Open Data crash records",
  },
  {
    name: "Equity and access",
    line: "bg-wl-navy",
    tint: "bg-wl-navy-tint",
    body: "Where weak service overlaps with neighborhoods that rely on transit, and how much sidewalk is near each stop.",
    example: "Which high-need stops have the least sidewalk around them?",
    source: "From U.S. Census ACS 2023 and Denver’s sidewalk inventory",
  },
];
