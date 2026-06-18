import Link from "next/link";
import { Activity, BotMessageSquare, DatabaseZap } from "lucide-react";

const destinations = [
  {
    href: "/chat",
    title: "Chat",
    label: "Ask with citations",
    description: "Run tenant-authorized support questions, inspect citations, and submit feedback.",
    icon: BotMessageSquare,
  },
  {
    href: "/admin/sources",
    title: "Admin Sources",
    label: "Configure knowledge",
    description: "Create sources, trigger sync jobs, review health, and keep retrieval fresh.",
    icon: DatabaseZap,
  },
  {
    href: "/operator",
    title: "Operator Dashboard",
    label: "Trace operations",
    description: "Watch usage, audit activity, trace stages, and source/model health signals.",
    icon: Activity,
  },
];

export default function Home() {
  return (
    <main className="home-page">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">Tenant-aware support intelligence</span>
          <h1>SupportLens AI</h1>
          <p>
            Answer support questions from approved knowledge, manage source freshness, and inspect the operational path behind every response.
          </p>
        </div>
      </section>

      <section className="nav-tile-grid" aria-label="SupportLens workspaces">
        {destinations.map((destination) => {
          const Icon = destination.icon;
          return (
            <Link className="nav-tile" href={destination.href} key={destination.href}>
              <span className="tile-icon" aria-hidden="true">
                <Icon size={24} />
              </span>
              <span className="tile-label">{destination.label}</span>
              <strong>{destination.title}</strong>
              <span>{destination.description}</span>
              <em>Open workspace</em>
            </Link>
          );
        })}
      </section>
    </main>
  );
}
