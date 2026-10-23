import { describe, expect, it } from "vitest";

import { layoutTreemap, pnlColor } from "./heatmap";

function rgb(color: string): [number, number, number] {
  const m = color.match(/rgb\((\d+), (\d+), (\d+)\)/);
  if (!m) throw new Error(`not rgb: ${color}`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

describe("pnlColor", () => {
  it("is neutral gray at zero", () => {
    expect(pnlColor(0)).toBe("rgb(58, 65, 84)");
  });

  it("goes green for gains and red for losses", () => {
    const [gr, gg] = rgb(pnlColor(2));
    expect(gg).toBeGreaterThan(gr);
    const [lr, lg] = rgb(pnlColor(-2));
    expect(lr).toBeGreaterThan(lg);
  });

  it("clamps at ±5%", () => {
    expect(pnlColor(5)).toBe(pnlColor(25));
    expect(pnlColor(-5)).toBe(pnlColor(-80));
    expect(pnlColor(5)).toBe("rgb(31, 158, 107)");
    expect(pnlColor(-5)).toBe("rgb(214, 64, 69)");
  });

  it("gets stronger with the size of the move", () => {
    const g1 = rgb(pnlColor(1))[1];
    const g3 = rgb(pnlColor(3))[1];
    expect(g3).toBeGreaterThan(g1);
  });

  it("tints even tiny moves so the color always shows the sign", () => {
    const [r, g] = rgb(pnlColor(0.01, "positive"));
    expect(g - r).toBeGreaterThan(10);
  });

  it("takes its hue from an explicit sign", () => {
    expect(pnlColor(0.001, "zero")).toBe(pnlColor(0));
    const [r, g] = rgb(pnlColor(0.001, "negative"));
    expect(r).toBeGreaterThan(g);
  });
});

describe("layoutTreemap", () => {
  it("sizes tiles by value and fills the box", () => {
    const tiles = layoutTreemap(
      [
        { ticker: "AAPL", value: 300 },
        { ticker: "MSFT", value: 100 },
      ],
      400,
      200,
      0,
    );
    expect(tiles).toHaveLength(2);
    const area = (t: (typeof tiles)[number]) => t.width * t.height;
    const aapl = tiles.find((t) => t.ticker === "AAPL")!;
    const msft = tiles.find((t) => t.ticker === "MSFT")!;
    expect(area(aapl) / area(msft)).toBeCloseTo(3, 5);
    expect(area(aapl) + area(msft)).toBeCloseTo(100 * 100, 5);
  });

  it("drops zero-value items and handles an empty or unmeasured box", () => {
    expect(layoutTreemap([{ ticker: "A", value: 0 }], 100, 100)).toEqual([]);
    expect(layoutTreemap([], 100, 100)).toEqual([]);
    expect(layoutTreemap([{ ticker: "A", value: 1 }], 0, 100)).toEqual([]);
  });
});
