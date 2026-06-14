import Link from "next/link";

export default function Home() {
  return (
    <main>
      <section className="card">
        <h1>SupportLens AI v1</h1>
        <p>Tenant-isolated, citation-backed support answers from approved documentation.</p>
        <nav className="grid">
          <Link href="/chat">Chat</Link>
          <Link href="/admin/sources">Admin Sources</Link>
          <Link href="/operator">Operator</Link>
        </nav>
      </section>
    </main>
  );
}
