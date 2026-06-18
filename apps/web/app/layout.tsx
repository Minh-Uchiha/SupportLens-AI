import type { Metadata } from "next";
import Link from "next/link";
import "./styles.css";

export const metadata: Metadata = {
  title: "SupportLens AI",
  description: "Citation-backed support copilot",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="app-header">
          <Link className="brand-mark" href="/">
            <span className="brand-icon">SL</span>
            <span>
              <strong>SupportLens</strong>
              <small>AI support ops</small>
            </span>
          </Link>
          <nav className="app-nav" aria-label="Primary navigation">
            <Link href="/chat">Chat</Link>
            <Link href="/admin/sources">Sources</Link>
            <Link href="/operator">Operator</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
