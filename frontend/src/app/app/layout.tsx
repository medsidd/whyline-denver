import { pageMetadata } from "@/lib/seo";

// The dashboard page is a client component, so its metadata lives here.
export const metadata = pageMetadata({
  title: "Dashboard | WhyLine Denver",
  description:
    "Ask a question about Denver transit in plain English or pick a ready-made one, check the SQL, then see a chart, map or table.",
  path: "/app",
});

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return children;
}
