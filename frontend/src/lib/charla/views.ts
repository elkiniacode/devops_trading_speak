import type { Me, RoomState, SalaView } from "./types";

/**
 * Which screen an attendee's phone shows (CONTRACT §9.2). The rules apply in order:
 * 1. the phone prompt is up, not yet answered, and no question is open -> phone
 * 2. the closing step -> end
 * 3. idle -> wait
 * 4. open -> answered if I already answered, else question (quiz) or open (open question)
 * 5. closed -> answered (with no answer, the view says "Se acabó el tiempo")
 * 6. revealed -> result
 */
export function viewFor(state: RoomState, me: Me | null): SalaView {
  if (me?.phone_status === "none" && state.phone_prompt && state.phase !== "open") return "phone";
  if (state.kind === "closing") return "end";
  switch (state.phase) {
    case "idle":
      return "wait";
    case "open":
      if (me?.answer && me.answer.step === state.step) return "answered";
      return state.kind === "open" ? "open" : "question";
    case "closed":
      return "answered";
    case "revealed":
      return "result";
  }
}
