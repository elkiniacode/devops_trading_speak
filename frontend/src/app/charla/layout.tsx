// Archivo and globals.css come from the root layout; only the mono face is charla-specific.
import "@fontsource-variable/jetbrains-mono/wght.css";
import "./charla.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "IA Revolutions · Agentic Engineering",
  description: "Charla en vivo: quices desde tu celular, ranking y preguntas abiertas.",
};

export const viewport: Viewport = {
  themeColor: "#070909",
};

export default function CharlaLayout({ children }: { children: ReactNode }) {
  return (
    <div className="charla" lang="es">
      {children}
    </div>
  );
}
