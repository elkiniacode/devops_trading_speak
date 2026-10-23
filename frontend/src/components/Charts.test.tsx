import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { quote } from "@/test/fixtures";

const series = {
  setData: vi.fn(),
  update: vi.fn(),
  createPriceLine: vi.fn(() => ({})),
  removePriceLine: vi.fn(),
};
const chart = {
  addSeries: vi.fn(() => series),
  timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  remove: vi.fn(),
};

// Lightweight Charts needs a real canvas; the components only need these calls.
vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => chart),
  CandlestickSeries: "Candlestick",
  LineSeries: "Line",
  HistogramSeries: "Histogram",
  AreaSeries: "Area",
  BaselineSeries: "Baseline",
  ColorType: { Solid: "solid" },
  CrosshairMode: { Magnet: 1 },
  LineStyle: { Dashed: 2 },
}));

const { MainChart } = await import("./MainChart");
const { PnlChart, snapshotPoints } = await import("./PnlChart");

describe("MainChart", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the selected stock, quote, and chart controls", () => {
    const points = [
      { time: 1_000, price: 190 },
      { time: 1_500, price: 190.5 },
      { time: 2_000, price: 191 },
    ];
    render(<MainChart ticker="AAPL" quote={quote("AAPL", 191, { reference_price: 190 })} points={points} mode="simulator" />);

    const el = screen.getByTestId("main-chart");
    expect(el).toHaveAttribute("data-ticker", "AAPL");
    expect(el).toHaveAttribute("data-points", "3");
    expect(series.createPriceLine).toHaveBeenCalledWith(expect.objectContaining({ price: 191, title: "LAST" }));
    expect(screen.getByText("since session start")).toBeInTheDocument();
    fireEvent.click(screen.getByText("TOOLS · INDICATORS & DRAWINGS"));
    expect(screen.getByRole("button", { name: "SMA20" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "RSI14" }));
    expect(screen.getByRole("button", { name: "RSI14" })).toHaveAttribute("aria-pressed", "true");
  });

  it("explains an empty chart", () => {
    render(<MainChart ticker="PYPL" quote={null} points={[]} mode="simulator" />);
    expect(screen.getByText("Loading candles for PYPL…")).toBeInTheDocument();
  });
});

describe("PnlChart", () => {
  beforeEach(() => vi.clearAllMocks());

  it("plots every snapshot and exposes the count", () => {
    const snapshots = [
      { total_value: 10000, recorded_at: "2026-10-19T14:00:00.000Z" },
      { total_value: 10012.5, recorded_at: "2026-10-19T14:00:30.000Z" },
    ];
    render(<PnlChart snapshots={snapshots} liveTotal={10020} />);
    expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "2");
    expect(series.setData).toHaveBeenCalledTimes(1);
    expect((series.setData.mock.calls[0][0] as { value: number }[]).map((d) => d.value)).toEqual([10000, 10012.5]);
    // The line is extended to the live total.
    expect(series.update).toHaveBeenCalledWith(expect.objectContaining({ value: 10020 }));
    expect(screen.getByText("+$20.00 total")).toBeInTheDocument();
  });

  it("merges snapshots that share a second and keeps time ascending", () => {
    expect(
      snapshotPoints([
        { total_value: 1, recorded_at: "2026-10-19T14:00:00.100Z" },
        { total_value: 2, recorded_at: "2026-10-19T14:00:00.900Z" },
        { total_value: 3, recorded_at: "2026-10-19T14:00:01.000Z" },
      ]).map((p) => p.value),
    ).toEqual([2, 3]);
  });
});
