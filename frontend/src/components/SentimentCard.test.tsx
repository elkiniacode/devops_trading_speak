import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { sampleSentiment, SentimentCard } from "./SentimentCard";

describe("sample sentiment", () => {
  it("is deterministic, bounded, and independent of ticker case", () => {
    expect(sampleSentiment("aapl")).toEqual(sampleSentiment("AAPL"));
    const sample = sampleSentiment("NVDA");
    expect(sample.score).toBeGreaterThanOrEqual(2);
    expect(sample.score).toBeLessThanOrEqual(8.01);
    expect(sample.confidence).toBeLessThanOrEqual(93);
  });

  it("labels both summary and detail as simulated sample data", () => {
    render(<SentimentCard ticker="AAPL" />);
    expect(screen.getByText("DATOS DE MUESTRA")).toBeInTheDocument();
    expect(screen.getByText(/fuentes simuladas/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Detalles" }));
    expect(screen.getAllByText(/FUENTE SIMULADA/)).toHaveLength(2);
    expect(screen.getByText(/No representa opiniones reales/)).toBeInTheDocument();
  });
});
