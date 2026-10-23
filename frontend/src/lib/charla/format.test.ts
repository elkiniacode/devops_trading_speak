import { describe, expect, it } from "vitest";

import { fmtPoints, remainingMs, remainingSeconds } from "./format";

describe("fmtPoints", () => {
  it("groups thousands the Colombian way", () => {
    expect(fmtPoints(0)).toBe("0");
    expect(fmtPoints(842)).toBe("842");
    expect(fmtPoints(1820)).toBe("1.820");
    expect(fmtPoints(18200.4)).toBe("18.200");
  });
});

describe("remainingSeconds", () => {
  const open = { phase: "open" as const, remaining_ms: 13_450 };

  it("counts down locally from when the state arrived", () => {
    expect(remainingSeconds(open, 1000, 1000)).toBe(14);
    expect(remainingSeconds(open, 1000, 1000 + 450)).toBe(13);
    expect(remainingSeconds(open, 1000, 1000 + 451)).toBe(13);
    expect(remainingSeconds(open, 1000, 1000 + 12_500)).toBe(1);
    expect(remainingMs(open, 1000, 1000 + 450)).toBe(13_000);
  });

  it("never goes below zero", () => {
    expect(remainingSeconds(open, 1000, 60_000)).toBe(0);
    expect(remainingMs(open, 1000, 60_000)).toBe(0);
  });

  it("ignores a clock that runs backwards", () => {
    expect(remainingMs(open, 5000, 4000)).toBe(13_450);
  });

  it("uses the full remaining time when the arrival time is unknown", () => {
    expect(remainingMs(open, null, 99_999)).toBe(13_450);
  });

  it("is null when no question is open", () => {
    expect(remainingSeconds({ phase: "closed", remaining_ms: null }, 0, 0)).toBeNull();
    expect(remainingSeconds({ phase: "idle", remaining_ms: 5000 }, 0, 0)).toBeNull();
    expect(remainingSeconds({ phase: "open", remaining_ms: null }, 0, 0)).toBeNull();
  });
});
