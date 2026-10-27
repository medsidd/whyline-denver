import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/landing/LegalPage";
import { GITHUB } from "@/lib/links";

export const metadata: Metadata = {
  title: "Privacy Policy | WhyLine Denver",
  description: "What WhyLine Denver collects, why, who processes it, and the choices you have.",
};

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="October 27, 2026">
      <p>
        WhyLine Denver (“WhyLine”, “we”) is a free, open-source website at whylinedenver.com for exploring public Denver
        transit data. This policy explains what information is handled when you use the website and dashboard, why, and who
        else processes it. WhyLine has no accounts and does not ask for your name, email address or other contact details.
      </p>

      <h2>Summary</h2>
      <ul>
        <li>We don’t sell or share personal information for advertising, and we don’t use advertising or tracking cookies.</li>
        <li>Questions you ask are sent to Google’s Gemini service to write SQL. Don’t include personal information in them.</li>
        <li>Your browser keeps your last question, query and filters locally so the dashboard can restore them.</li>
        <li>Our hosting providers keep standard request logs, and we use privacy-focused, cookie-free analytics.</li>
      </ul>

      <h2>Information we handle</h2>
      <h3>Questions and queries</h3>
      <p>
        When you ask a question in the dashboard, the question, your selected filters and a description of the data tables
        are sent from our server to Google’s Gemini API so it can write a SQL query. Ready-made questions don’t use Gemini.
        Generated answers are held in server memory for a short time so a repeated question can reuse them, and are cleared
        when the server restarts.
      </p>
      <p>
        When you run a query, our server records an operational log entry with the time, the query engine, the tables used,
        row count, response time and estimated data scanned. The question and SQL are stored only as one-way hashes, not as
        readable text. These entries don’t include your IP address.
      </p>

      <h3>Information stored in your browser</h3>
      <p>
        The dashboard saves your selected engine, filters, question, generated and edited SQL, and its explanation in your
        browser’s local storage under the key <code>whyline-dashboard</code>. This lets the dashboard pick up where you left
        off. It stays on your device, is not a cookie, and is not sent to us except when you use the dashboard. You can
        remove it by clearing this site’s data in your browser settings.
      </p>

      <h3>Request logs</h3>
      <p>
        Like most websites, our hosting providers automatically record technical details of each request, such as IP
        address, browser type, requested page, referring page and time. These logs are used to run, secure and debug the
        service, and are kept for a limited period set by the provider (for example, Google Cloud Logging keeps them for 30
        days by default).
      </p>

      <h3>Analytics</h3>
      <p>
        We use Vercel Web Analytics and Vercel Speed Insights to understand which pages are visited and how fast they load.
        They don’t use cookies. They collect information such as the page, referrer, approximate country, browser, operating
        system, device type and page-load performance. Vercel describes visitors with a short-lived identifier that is not
        used to track you across websites.
      </p>

      <h2>How we use information</h2>
      <ul>
        <li>To answer your questions and run the queries you choose.</li>
        <li>To keep the service working, prevent abuse and fix problems.</li>
        <li>To understand overall usage and performance so we can improve the site.</li>
      </ul>
      <p>We don’t use information from this site to build profiles of individuals or to make decisions about you.</p>

      <h2>Service providers</h2>
      <p>These companies process information on our behalf to run the service, under their own terms and privacy policies:</p>
      <ul>
        <li>
          <strong>Vercel</strong> hosts the website and provides analytics (
          <a href="https://vercel.com/legal/privacy-policy">privacy policy</a>).
        </li>
        <li>
          <strong>Google Cloud</strong> hosts the query service and stores the transit data in Cloud Run, Cloud Storage and
          BigQuery (<a href="https://policies.google.com/privacy">privacy policy</a>).
        </li>
        <li>
          <strong>Google Gemini API</strong> writes SQL from your questions. Google may keep prompts for a limited time to
          detect abuse and, depending on the service tier, may use them to improve its products (
          <a href="https://ai.google.dev/gemini-api/terms">Gemini API terms</a>).
        </li>
        <li>
          <strong>CARTO</strong> serves the dashboard’s map tiles directly to your browser, so it receives standard request
          details such as your IP address (<a href="https://carto.com/privacy">privacy policy</a>).
        </li>
      </ul>
      <p>We may also disclose information if required by law or to protect the service and its users.</p>

      <h2>Cookies and similar technologies</h2>
      <p>
        WhyLine doesn’t set cookies. The only browser storage it uses is the local storage described above, which is needed
        for the dashboard to remember your work. Because we don’t track you across sites, there is nothing to opt out of
        through Do Not Track or Global Privacy Control signals, and we treat both as a request not to sell or share data.
      </p>

      <h2>Your choices and rights</h2>
      <ul>
        <li>Clear this site’s data in your browser to delete everything the dashboard stored locally.</li>
        <li>Use ready-made questions if you prefer not to send text to Gemini.</li>
        <li>Block analytics with a content blocker; the site works without it.</li>
      </ul>
      <p>
        Depending on where you live, you may have rights to access, correct or delete personal information about you. Because
        we don’t collect names or accounts, we usually can’t link log records to a specific person, but we will respond to any
        request we can act on.
      </p>

      <h2>Children</h2>
      <p>
        WhyLine is a general-audience data tool and is not directed to children under 13. We don’t knowingly collect personal
        information from children.
      </p>

      <h2>Security</h2>
      <p>
        Traffic to the site is encrypted with HTTPS, queries are restricted to read-only access on approved tables, and
        access to our cloud resources is limited. No method of transmission or storage is completely secure.
      </p>

      <h2>Changes to this policy</h2>
      <p>
        We’ll update this page when our practices change and revise the date at the top. The history of this policy is
        public in the project’s repository.
      </p>

      <h2>Contact</h2>
      <p>
        Questions or requests about privacy can be sent by opening an issue on <a href={`${GITHUB}/issues`}>GitHub</a>. Please
        don’t post personal details in a public issue; say you have a privacy request and we’ll arrange a private channel.
        See also our <Link href="/terms">Terms of Use</Link>.
      </p>
    </LegalPage>
  );
}
