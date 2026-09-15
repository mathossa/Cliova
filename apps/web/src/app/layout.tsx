import type { Metadata } from "next";
import "./globals.css";
import "../features/command-center/command-center-live.css";
import "../features/command-center/strategic-map.css";

export const metadata: Metadata = {
  title: "Cliova World Command",
  description: "Simulation-first persistent civilization command center",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
