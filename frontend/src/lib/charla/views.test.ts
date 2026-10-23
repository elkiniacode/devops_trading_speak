import { describe, expect, it } from "vitest";

import type { Me, Phase, PhoneStatus, RoomState, SalaView, StepKind } from "./types";
import { viewFor } from "./views";

function room(kind: StepKind, phase: Phase, overrides: Partial<RoomState> = {}): RoomState {
  const step = kind === "quiz" ? 2 : kind === "open" ? 7 : 8;
  return {
    version: 1,
    server_now_ms: 0,
    step,
    kind,
    phase,
    number: kind === "quiz" ? 3 : null,
    total_quiz: 7,
    remaining_ms: phase === "open" ? 10_000 : null,
    duration_ms: kind === "closing" ? null : 20_000,
    question: kind === "closing" ? null : { text: "¿?", options: kind === "quiz" ? ["a", "b", "c", "d"] : [], placeholder: null },
    reveal: null,
    phone_prompt: false,
    room_count: 30,
    ...overrides,
  };
}

function me(overrides: Partial<Me> = {}): Me {
  return {
    attendee_id: "a1",
    username: "José P",
    verified: true,
    score: 0,
    rank: 1,
    answer: null,
    result: null,
    phone_status: "none",
    ...overrides,
  };
}

const answered = (step: number) => ({ answer: { step, choice: 1, text: null } });

describe("viewFor", () => {
  it.each<[string, RoomState, Me | null, SalaView]>([
    // rule 3: idle
    ["quiz idle", room("quiz", "idle"), me(), "wait"],
    ["open question idle", room("open", "idle"), me(), "wait"],
    ["idle with no attendee", room("quiz", "idle"), null, "wait"],
    // rule 4: open
    ["quiz open, not answered", room("quiz", "open"), me(), "question"],
    ["quiz open, answered", room("quiz", "open"), me(answered(2)), "answered"],
    ["open question open, not answered", room("open", "open"), me(), "open"],
    ["open question open, answered", room("open", "open"), me({ answer: { step: 7, choice: null, text: "Mi idea" } }), "answered"],
    ["quiz open with no attendee", room("quiz", "open"), null, "question"],
    ["a stale answer for another step doesn't count", room("quiz", "open"), me(answered(1)), "question"],
    // rule 5: closed
    ["quiz closed, answered", room("quiz", "closed"), me(answered(2)), "answered"],
    ["quiz closed, time ran out", room("quiz", "closed"), me(), "answered"],
    ["open question closed", room("open", "closed"), me(), "answered"],
    // rule 6: revealed
    ["quiz revealed", room("quiz", "revealed"), me(answered(2)), "result"],
    ["quiz revealed without answer", room("quiz", "revealed"), me(), "result"],
    ["open question revealed", room("open", "revealed"), me(), "result"],
    // rule 2: closing
    ["closing idle, phone given", room("closing", "idle"), me({ phone_status: "given" }), "end"],
    ["closing idle, phone skipped", room("closing", "idle"), me({ phone_status: "skipped" }), "end"],
    ["closing without prompt", room("closing", "idle"), me(), "end"],
    ["closing with no attendee", room("closing", "idle", { phone_prompt: true }), null, "end"],
    // rule 1: phone prompt
    ["closing with prompt, phone pending", room("closing", "idle", { phone_prompt: true }), me(), "phone"],
    ["prompt while idle", room("quiz", "idle", { phone_prompt: true }), me(), "phone"],
    ["prompt while closed", room("quiz", "closed", { phone_prompt: true }), me(answered(2)), "phone"],
    ["prompt while revealed", room("quiz", "revealed", { phone_prompt: true }), me(), "phone"],
    ["prompt never interrupts an open quiz", room("quiz", "open", { phone_prompt: true }), me(), "question"],
    ["prompt never interrupts an open question", room("open", "open", { phone_prompt: true }), me(), "open"],
    ["prompt, phone already given", room("quiz", "idle", { phone_prompt: true }), me({ phone_status: "given" }), "wait"],
    ["prompt, phone skipped", room("quiz", "revealed", { phone_prompt: true }), me({ phone_status: "skipped" }), "result"],
  ])("%s", (_label, state, attendee, expected) => {
    expect(viewFor(state, attendee)).toBe(expected);
  });

  // Every combination of the inputs that matter, checked against the contract's invariants.
  const kinds: StepKind[] = ["quiz", "open", "closing"];
  const phases: Phase[] = ["idle", "open", "closed", "revealed"];
  const phones: (PhoneStatus | null)[] = ["none", "given", "skipped", null]; // null = no attendee
  const combos = kinds.flatMap((kind) =>
    phases.flatMap((phase) =>
      [false, true].flatMap((prompt) =>
        phones.flatMap((phone) => [false, true].map((hasAnswer) => ({ kind, phase, prompt, phone, hasAnswer }))),
      ),
    ),
  );

  it(`covers all ${combos.length} combinations consistently`, () => {
    for (const { kind, phase, prompt, phone, hasAnswer } of combos) {
      const state = room(kind, phase, { phone_prompt: prompt });
      const attendee = phone === null ? null : me({ phone_status: phone, ...(hasAnswer ? answered(state.step) : {}) });
      const view = viewFor(state, attendee);
      const label = JSON.stringify({ kind, phase, prompt, phone, hasAnswer, view });

      const wantsPhone = phone === "none" && prompt && phase !== "open";
      expect(view === "phone", label).toBe(wantsPhone);
      if (wantsPhone) continue;
      if (kind === "closing") {
        expect(view, label).toBe("end");
        continue;
      }
      const expected: Record<Phase, SalaView> = {
        idle: "wait",
        open: attendee?.answer ? "answered" : kind === "open" ? "open" : "question",
        closed: "answered",
        revealed: "result",
      };
      expect(view, label).toBe(expected[phase]);
    }
  });
});
