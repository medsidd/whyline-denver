import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/landing/LegalPage";
import { CENSUS_NOTICE, GITHUB } from "@/lib/links";

export const metadata: Metadata = {
  title: "Data Attribution | WhyLine Denver",
  description: "Sources, licenses and required notices for the data used by WhyLine Denver.",
};

export default function AttributionPage() {
  return (
    <LegalPage title="Data Attribution" updated="October 27, 2026">
      <p>
        WhyLine Denver combines public data from the organizations below. Each source keeps its own terms, and public
        availability doesn’t mean every dataset can be reused without conditions. Review the linked terms before you
        redistribute data downloaded from WhyLine. None of these organizations endorses WhyLine Denver.
      </p>

      <h2>Regional Transportation District (RTD)</h2>
      <p>
        Schedule (GTFS) and realtime (GTFS-Realtime trip updates and vehicle positions) data are provided by RTD and used
        under the{" "}
        <a href="https://www.rtd-denver.com/open-records/open-spatial-information/gtfs-realtime-license-agreement">
          RTD GTFS-Realtime license agreement
        </a>
        . RTD owns the data and provides it “as is” without warranty. WhyLine Denver is an unofficial website: it is not
        endorsed by, sponsored by or affiliated with RTD, and its views are not RTD’s. RTD’s names, logos and trademarks are
        not used to brand this site.
      </p>

      <h2>City and County of Denver</h2>
      <p>
        Traffic crash records and the sidewalk inventory come from the{" "}
        <a href="https://opendata-geospatialdenver.hub.arcgis.com/">City and County of Denver Open Data Catalog</a> and are
        used under the terms published with each dataset. Location and reporting quality vary, and a missing sidewalk record
        doesn’t mean there is no sidewalk.
      </p>

      <h2>U.S. Census Bureau</h2>
      <p>
        <strong>{CENSUS_NOTICE}</strong>
      </p>
      <p>
        American Community Survey 2023 five-year estimates and TIGERweb tract boundaries are used under the{" "}
        <a href="https://www.census.gov/data/developers/about/terms-of-service.html">Census Data API terms of service</a>.
        Estimates describe areas, carry sampling uncertainty, and must not be used to identify any person, household or
        business.
      </p>

      <h2>NOAA</h2>
      <p>
        Daily weather observations for Denver International Airport (station USW00003017) come from NOAA’s National Centers
        for Environmental Information through the{" "}
        <a href="https://www.ncei.noaa.gov/cdo-web/">Climate Data Online</a> service. NOAA does not endorse this site.
        Days NOAA has not yet published are filled with modeled weather from{" "}
        <a href="https://open-meteo.com/">Open-Meteo</a>, licensed under{" "}
        <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>, until NOAA data arrives.
      </p>

      <h2>Software</h2>
      <p>
        WhyLine Denver’s code is released under the MIT License on <a href={GITHUB}>GitHub</a>. It is built with open-source
        software, including Next.js, React, dbt, MapLibre and deck.gl, each under its own license. Dashboard base
        maps are © <a href="https://carto.com/attributions">CARTO</a> and ©{" "}
        <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, credited on the map itself.
      </p>

      <h2>Report a problem</h2>
      <p>
        If you’re a data provider and believe your data is used incorrectly, or an attribution is missing, please open an
        issue on <a href={`${GITHUB}/issues`}>GitHub</a> and we’ll fix it. See also the{" "}
        <Link href="/terms">Terms of Use</Link>.
      </p>
    </LegalPage>
  );
}
