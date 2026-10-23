import { describe, expect, it } from "vitest";

import type { RankingRow } from "@/lib/charla/types";

import {
  adminTop,
  barWidths,
  controlsFor,
  kindLabel,
  pct,
  phoneTimeLabel,
  projectedTop,
  shortcutFor,
  timeText,
} from "./logic";

const row = (rank: number, hidden = false): RankingRow => ({
  rank,
  attendee_id: `a${rank}`,
  username: `user${rank}`,
  score: 5000 - rank * 100,
  correct: 7 - Math.min(rank, 7),
  verified: true,
  hidden,
});

describe("controlsFor", () => {
  const base = { kind: "quiz" as const, step: 2, phone_prompt: false };

  it("only launches while idle", () => {
    const c = controlsFor({ ...base, phase: "idle" }, 0);
    expect(c.launch).toMatchObject({ label: "LANZAR PREGUNTA", enabled: true, action: "launch" });
    expect(c.close.enabled).toBe(false);
    expect(c.reveal.enabled).toBe(false);
    expect(c.resetStep.enabled).toBe(false);
  });

  it("closes only while open and reveals only once closed", () => {
    const open = controlsFor({ ...base, phase: "open" }, 3);
    expect(open.launch).toMatchObject({ label: "LANZADA", enabled: false });
    expect(open.close.enabled).toBe(true);
    expect(open.reveal.enabled).toBe(false);
    expect(open.resetStep.enabled).toBe(true);

    const closed = controlsFor({ ...base, phase: "closed" }, 3);
    expect(closed.close.enabled).toBe(false);
    expect(closed.reveal).toEqual({ label: "REVELAR RESPUESTA", enabled: true });

    const revealed = controlsFor({ ...base, phase: "revealed" }, 3);
    expect(revealed.reveal.enabled).toBe(false);
    expect(revealed.next.enabled).toBe(true);
  });

  it("says MOSTRAR EN PANTALLA for the open question", () => {
    expect(controlsFor({ ...base, kind: "open", step: 7, phase: "closed" }, 1).reveal.label).toBe(
      "MOSTRAR EN PANTALLA",
    );
  });

  it("turns launch into the phone request at the closing step", () => {
    const before = controlsFor({ kind: "closing", step: 8, phase: "idle", phone_prompt: false }, 0);
    expect(before.launch).toMatchObject({ label: "LANZAR SOLICITUD AHORA", enabled: true, action: "phoneNow" });
    expect(before.next.enabled).toBe(false);
    expect(before.close.enabled).toBe(false);
    expect(before.reveal.enabled).toBe(false);
    const after = controlsFor({ kind: "closing", step: 8, phase: "idle", phone_prompt: true }, 0);
    expect(after.launch).toMatchObject({ label: "SOLICITUD ENVIADA", enabled: false });
  });
});

describe("labels and numbers", () => {
  it("formats the kind kicker", () => {
    expect(kindLabel({ kind: "quiz", number: 3, total_quiz: 7 })).toBe("QUIZ · PREGUNTA 3 DE 7");
    expect(kindLabel({ kind: "open", number: 8, total_quiz: 13 })).toBe("PREGUNTA ABIERTA · 8 DE 13");
    expect(kindLabel({ kind: "poll", number: 1, total_quiz: 13 })).toBe("ENCUESTA · 1 DE 13");
    expect(kindLabel({ kind: "closing", number: null, total_quiz: 7 })).toBe("CIERRE");
  });

  it("computes safe percentages and bar widths", () => {
    expect(pct(17, 34)).toBe(50);
    expect(pct(3, 0)).toBe(0);
    expect(barWidths([3, 20, 5, 0])).toEqual([15, 100, 25, 0]);
    expect(barWidths([0, 0])).toEqual([0, 0]);
  });

  it("formats the automatic phone time", () => {
    expect(phoneTimeLabel("15:50")).toBe("3:50 p. m.");
    expect(phoneTimeLabel("09:05")).toBe("9:05 a. m.");
    expect(phoneTimeLabel("12:00")).toBe("12:00 p. m.");
    expect(phoneTimeLabel(null)).toBeNull();
  });

  it("formats the remaining time", () => {
    expect(timeText({ kind: "quiz", phase: "idle", duration_ms: 20000 }, null)).toBe("20 s");
    expect(timeText({ kind: "quiz", phase: "open", duration_ms: 20000 }, 13)).toBe("13 s");
    expect(timeText({ kind: "quiz", phase: "closed", duration_ms: 20000 }, null)).toBe("0 s");
    expect(timeText({ kind: "closing", phase: "idle", duration_ms: null }, null)).toBe("—");
  });
});

describe("ranking cuts", () => {
  const ranking = [row(1), row(2, true), row(3), row(4), row(5)];

  it("keeps hidden rows inline for the presenter until n are visible", () => {
    expect(adminTop(ranking, 2).map((r) => r.attendee_id)).toEqual(["a1", "a2", "a3"]);
  });

  it("drops hidden rows and renumbers for the projector", () => {
    const top = projectedTop(ranking, 3);
    expect(top.map((r) => [r.attendee_id, r.rank])).toEqual([
      ["a1", 1],
      ["a3", 2],
      ["a4", 3],
    ]);
  });
});

describe("shortcutFor", () => {
  it("maps the documented keys", () => {
    expect(shortcutFor("l")).toBe("launch");
    expect(shortcutFor("C")).toBe("close");
    expect(shortcutFor("r")).toBe("reveal");
    expect(shortcutFor("ArrowRight")).toBe("next");
    expect(shortcutFor("p")).toBe("projection");
    expect(shortcutFor("q")).toBe("qr");
    expect(shortcutFor("Escape")).toBe("escape");
    expect(shortcutFor("x")).toBeNull();
  });
});
