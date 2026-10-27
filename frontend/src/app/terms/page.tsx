import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/landing/LegalPage";
import { GITHUB, GLOSSARY } from "@/lib/links";

export const metadata: Metadata = {
  title: "Terms of Use | WhyLine Denver",
  description: "The terms that apply when you use the WhyLine Denver website, dashboard and downloads.",
};

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Use" updated="October 27, 2026">
      <p>
        These terms apply to your use of whylinedenver.com, its dashboard, API and downloads (the “Service”). By using the
        Service you agree to them. If you don’t agree, please don’t use the Service.
      </p>

      <h2>An independent, unofficial project</h2>
      <p>
        WhyLine Denver is an unofficial website. It is not endorsed by, sponsored by or affiliated with the Regional
        Transportation District (RTD), the City and County of Denver, NOAA, the U.S. Census Bureau or any other data
        provider, and its views are not theirs. Names of these organizations are used only to identify where data comes from.
      </p>

      <h2>What the Service is for</h2>
      <p>
        WhyLine is an analysis tool for looking at how transit service has performed. It is not a trip planner, a live
        arrivals service or an official source of service information. For current service and alerts, use RTD’s own
        channels.
      </p>

      <h2>Data accuracy</h2>
      <p>
        Results come from public feeds that are sampled, delayed and sometimes incomplete, and from queries that may be
        written by an AI model. They can be wrong. Review the SQL before relying on a result, read the{" "}
        <a href={GLOSSARY}>metric definitions</a>, and check important findings against original sources. Don’t use the
        Service for safety-critical decisions.
      </p>

      <h2>Acceptable use</h2>
      <p>You agree not to:</p>
      <ul>
        <li>overload, disrupt or attempt to bypass the Service’s query limits or security controls;</li>
        <li>use automated tools to send large volumes of requests, except reasonable use of the published downloads;</li>
        <li>submit personal information about other people, or content that is unlawful or harmful;</li>
        <li>use the data to identify individuals, households or businesses;</li>
        <li>present results as official RTD or government statistics, or suggest a data provider endorses your work.</li>
      </ul>
      <p>We may limit or block access that harms the Service or other users.</p>

      <h2>Your use of results and downloads</h2>
      <p>
        You may use query results and downloads for any lawful purpose, subject to the terms of the original data providers,
        which are summarized on the <Link href="/attribution">data attribution</Link> page. When you publish work based on
        the data, credit the original sources and note that WhyLine is an unofficial tool.
      </p>

      <h2>Open-source code</h2>
      <p>
        The WhyLine Denver source code is available on <a href={GITHUB}>GitHub</a> under the MIT License. That license
        governs use of the code. These terms govern use of the hosted Service.
      </p>

      <h2>No warranty</h2>
      <p>
        The Service and all data are provided <strong>“as is” and “as available”</strong>, without warranties of any kind,
        express or implied, including accuracy, completeness, availability, merchantability, fitness for a particular purpose
        and non-infringement. The Service may change, pause or end at any time, and data providers may change or withdraw
        their data without notice.
      </p>

      <h2>Limitation of liability</h2>
      <p>
        To the fullest extent permitted by law, WhyLine Denver and its contributors are not liable for any indirect,
        incidental, special, consequential or punitive damages, or for any loss of data, profits or goodwill, arising from
        your use of or inability to use the Service or its data. The Service is free; where liability can’t be excluded, it
        is limited to the amount you paid to use the Service, which is zero.
      </p>

      <h2>Indemnity</h2>
      <p>
        You agree to defend and indemnify WhyLine Denver and its contributors against claims arising from your misuse of the
        Service or your breach of these terms.
      </p>

      <h2>Governing law</h2>
      <p>
        These terms are governed by the laws of the State of Colorado, without regard to conflict-of-law rules. Any dispute
        will be brought in the state or federal courts located in the City and County of Denver, Colorado.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. The date at the top shows the latest version, and continued use after a change means you
        accept it.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms can be raised by opening an issue on <a href={`${GITHUB}/issues`}>GitHub</a>. Our{" "}
        <Link href="/privacy">Privacy Policy</Link> explains how information is handled.
      </p>
    </LegalPage>
  );
}
