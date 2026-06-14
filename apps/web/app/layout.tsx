import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "SupportLens AI",
  description: "Citation-backed support copilot",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
