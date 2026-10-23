"use client";

import { useMemo, useState } from "react";

type Sample = { score: number; confidence: number; sources: number; posts: string[] };

export function sampleSentiment(ticker: string): Sample {
  let hash = 2166136261;
  for (const char of ticker.toUpperCase()) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0;
  const score = 2 + (hash % 601) / 100;
  const confidence = 58 + ((hash >>> 8) % 36);
  const sources = 12 + ((hash >>> 16) % 72);
  const direction = score >= 6 ? "optimismo" : score < 4 ? "cautela" : "expectativa mixta";
  return { score, confidence, sources, posts: [
    `Muestra simulada: hay ${direction} sobre ${ticker.toUpperCase()} en la sesión.`,
    `Muestra simulada: los participantes comentan la volatilidad de ${ticker.toUpperCase()}.`,
  ] };
}

export function SentimentCard({ ticker }: { ticker: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const sample = useMemo(() => sampleSentiment(ticker ?? "MERCADO"), [ticker]);
  const label = sample.score < 4 ? "BAJISTA MODERADO" : sample.score < 6 ? "NEUTRAL" : "ALCISTA MODERADO";
  const tone = sample.score < 4 ? "text-loss" : sample.score < 6 ? "text-muted" : "text-gain";
  return (
    <section className="shrink-0 rounded border border-line bg-panel p-3" aria-label="Sentimiento de muestra">
      <header className="mb-1 flex items-center justify-between">
        <h2 className="font-heading text-[11px] font-bold tracking-wide text-accent">02 · SENTIMIENTO</h2>
        <span className="text-[8px] text-amber-400">DATOS DE MUESTRA</span>
      </header>
      <div className={`font-heading text-[16px] font-bold ${tone}`}>{label}</div>
      <div className="mt-1 flex items-center justify-between text-[8px] text-muted">
        <span>FUENTE SIMULADA · {ticker ?? "MERCADO"}</span>
        <span className="tabular text-[14px] text-fg">{sample.score.toFixed(1)}<small className="text-muted"> / 10</small></span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded bg-line"><div className={`h-full ${sample.score < 4 ? "bg-loss" : sample.score < 6 ? "bg-accent" : "bg-gain"}`} style={{ width: `${sample.score * 10}%` }} /></div>
      <div className="mt-2 flex items-center justify-between text-[9px] text-muted">
        <span>Confianza de muestra: {sample.confidence}% · {sample.sources} fuentes simuladas</span>
        <button type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded} className="text-accent hover:underline">{expanded ? "Ocultar" : "Detalles"}</button>
      </div>
      {expanded && <div className="mt-2 space-y-1 border-t border-line pt-2 text-[10px] text-muted">
        <p className="font-bold text-amber-400">DATOS DE MUESTRA · FUENTE SIMULADA</p>
        {sample.posts.map((post) => <p key={post}>{post}</p>)}
        <p>No representa opiniones reales ni asesoría financiera.</p>
      </div>}
    </section>
  );
}
