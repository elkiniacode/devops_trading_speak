import "@fontsource-variable/archivo/wdth.css";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "FinAlly",
  description: "AI trading workstation: live prices, a simulated portfolio and an AI copilot.",
};

export const viewport: Viewport = {
  themeColor: "#070909",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
  <html lang="en">
      <body>{children}</body>
    </html>
  );
}
