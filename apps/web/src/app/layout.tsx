import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cliova Simulation Lab",
  description: "Simulation-first civilization sandbox",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
