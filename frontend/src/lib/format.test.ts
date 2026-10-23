import { describe, expect, it } from "vitest";

import { formatMoney, formatPercent, formatPrice, formatQuantity, formatSignedMoney, pnlSign } from "./format";

describe("format", () => {
  it("formats money with cents and separators", () => {
    expect(formatMoney(10000)).toBe("$10,000.00");
    expect(formatMoney(8098.8)).toBe("$8,098.80");
    expect(formatMoney(-12.5)).toBe("-$12.50");
    expect(formatMoney(-0)).toBe("$0.00");
  });

  it("signs money and percentages explicitly", () => {
    expect(formatSignedMoney(10.8)).toBe("+$10.80");
    expect(formatSignedMoney(-5)).toBe("-$5.00");
    expect(formatSignedMoney(0.001)).toBe("$0.00");
    expect(formatPercent(0.333)).toBe("+0.33%");
    expect(formatPercent(-1)).toBe("-1.00%");
    expect(formatPercent(-0.001)).toBe("0.00%");
  });

  it("keeps up to 4 quantity decimals without trailing zeros", () => {
    expect(formatQuantity(10)).toBe("10");
    expect(formatQuantity(0.5)).toBe("0.5");
    expect(formatQuantity(1.23456)).toBe("1.2346");
    expect(formatQuantity(1500)).toBe("1,500");
  });

  it("formats prices to cents", () => {
    expect(formatPrice(190.1)).toBe("190.10");
    expect(formatPrice(1234.5)).toBe("1,234.50");
  });

  it("judges the P&L sign at cent precision", () => {
    expect(pnlSign(0.01)).toBe("positive");
    expect(pnlSign(-0.01)).toBe("negative");
    expect(pnlSign(0.004)).toBe("zero");
    expect(pnlSign(-0.004)).toBe("zero");
  });
});
