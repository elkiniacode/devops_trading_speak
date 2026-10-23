import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { getAdminKey, setAdminKey } from "@/lib/charla/session";
import type { AdminState, AdminView, RankingRow } from "@/lib/charla/types";

const calls = vi.hoisted(() => ({
  launch: vi.fn(),
  close: vi.fn(),
  reveal: vi.fn(),
  next: vi.fn(),
  goto: vi.fn(),
  resetStep: vi.fn(),
  phoneNow: vi.fn(),
  reclassify: vi.fn(),
  verification: vi.fn(),
  hide: vi.fn(),
  reset: vi.fn(),
  check: vi.fn(),
  keys: [] as string[],
}));
vi.mock("@/lib/charla/api", () => ({
  adminApi: (key: string) => {
    calls.keys.push(key);
    return {
      launch: calls.launch,
      close: calls.close,
      reveal: calls.reveal,
      next: calls.next,
      goto: calls.goto,
      resetStep: calls.resetStep,
      phoneNow: calls.phoneNow,
      reclassify: calls.reclassify,
      verification: calls.verification,
      hide: calls.hide,
      reset: calls.reset,
      check: calls.check,
      exportUrl: `/api/charla/admin/export.csv?key=${key}`,
      streamUrl: `/api/charla/admin/stream?key=${key}`,
    };
  },
}));

const stream = vi.hoisted(() => ({
  current: { data: null as unknown, status: "live", receivedAt: 0 as number | null, error: null },
}));
vi.mock("@/lib/charla/stream", () => ({ useCharlaStream: () => stream.current }));

import { Presentador } from "./Presentador";

const SCRIPT = [
  ...Array.from({ length: 7 }, (_, i) => ({
    step: i,
    kind: "quiz" as const,
    title: `Pregunta ${i + 1}`,
    options: ["Uno", "Dos", "Tres", "Cuatro"],
    answer: 1,
    why: "Porque sí.",
  })),
  { step: 7, kind: "open" as const, title: "¿Qué proceso?", options: [], answer: null, why: null },
  { step: 8, kind: "closing" as const, title: "Cierre", options: [], answer: null, why: null },
];

function adminState(over: Partial<AdminState> = {}): AdminState {
  const step = over.step ?? 2;
  const kind = SCRIPT[step].kind;
  return {
    version: 1,
    server_now_ms: 0,
    step,
    kind,
    phase: "idle",
    number: kind === "quiz" ? step + 1 : null,
    total_quiz: 7,
    remaining_ms: null,
    duration_ms: 20000,
    question: kind === "closing" ? null : { text: SCRIPT[step].title, options: SCRIPT[step].options, placeholder: null },
    reveal: null,
    phone_prompt: false,
    room_count: 34,
    verification_on: true,
    phone_prompt_at: "15:50",
    deadline_ms: null,
    opened_at_ms: null,
    ...over,
  };
}

const row = (rank: number, name: string, hidden = false): RankingRow => ({
  rank,
  attendee_id: `a${rank}`,
  username: name,
  score: 5000 - rank * 100,
  correct: 6,
  verified: true,
  hidden,
});

function adminView(over: Partial<AdminView> = {}, state: Partial<AdminState> = {}): AdminView {
  return {
    version: 1,
    server_now_ms: 0,
    state: adminState(state),
    script: SCRIPT,
    counts: { registered: 36, active: 34, verified: 31, pending: 3, with_phone: 12, answered: 20, correct: 15 },
    distribution: [3, 20, 5, 2],
    themes: [
      { name: "Ventas y atención", count: 2 },
      { name: "Finanzas", count: 1 },
      { name: "Operaciones", count: 0 },
      { name: "Marketing", count: 0 },
      { name: "Recursos humanos", count: 0 },
      { name: "Otro", count: 0 },
    ],
    quotes: [
      { answer_id: "q1", attendee_id: "a1", username: "Ana", text: "Atender WhatsApp", theme: "Ventas y atención", hidden: false, created_at: "" },
      { answer_id: "q2", attendee_id: "a2", username: "Beto", text: "Texto oculto", theme: null, hidden: true, created_at: "" },
    ],
    ranking: [row(1, "Ana"), row(2, "Beto", true), row(3, "Caro"), row(4, "Dani"), row(5, "Eva")],
    email: { queued: 0, sent: 31, failed: 1, last_error: "Resend 429" },
    ...over,
  };
}

function feed(view: AdminView) {
  stream.current = { data: view, status: "live", receivedAt: performance.now(), error: null };
}

async function openPanel(view: AdminView) {
  setAdminKey("k");
  feed(view);
  const utils = render(<Presentador />);
  await screen.findByTestId("pres-screen");
  return utils;
}

describe("Presentador key gate", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/charla/presentador/");
    for (const fn of Object.values(calls)) if (typeof fn === "function") fn.mockReset();
    calls.check.mockResolvedValue(true);
    calls.keys = [];
    stream.current = { data: null, status: "connecting", receivedAt: null, error: null };
  });

  it("asks for the key when there is none, and checks it before entering", async () => {
    calls.check.mockResolvedValueOnce(false);
    render(<Presentador />);
    const input = await screen.findByTestId("pres-key-input");
    fireEvent.change(input, { target: { value: "mala" } });
    fireEvent.click(screen.getByRole("button", { name: "ENTRAR" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Clave de presentador incorrecta.");
    expect(getAdminKey()).toBeNull();

    fireEvent.change(input, { target: { value: "buena" } });
    fireEvent.click(screen.getByRole("button", { name: "ENTRAR" }));
    await screen.findByTestId("pres-screen");
    expect(getAdminKey()).toBe("buena");
  });

  it("takes the key from #key= and strips it from the URL", async () => {
    window.history.replaceState(null, "", "/charla/presentador/#key=e2e");
    render(<Presentador />);
    await screen.findByTestId("pres-screen");
    expect(getAdminKey()).toBe("e2e");
    expect(window.location.hash).toBe("");
    expect(calls.keys).toContain("e2e");
  });

  it("drops a stored key the server rejects", async () => {
    setAdminKey("vieja");
    calls.check.mockResolvedValue(false);
    render(<Presentador />);
    expect(await screen.findByTestId("pres-gate")).toHaveTextContent("Clave de presentador incorrecta.");
    expect(getAdminKey()).toBeNull();
  });

  it("goes back to the gate when an admin call returns 401", async () => {
    calls.launch.mockRejectedValue(new ApiError(401, "Clave de presentador incorrecta."));
    await openPanel(adminView());
    fireEvent.click(screen.getByTestId("pres-launch"));
    expect(await screen.findByTestId("pres-gate")).toBeInTheDocument();
    expect(getAdminKey()).toBeNull();
  });
});

describe("Presentador controls", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/charla/presentador/");
    for (const fn of Object.values(calls)) if (typeof fn === "function") fn.mockReset().mockResolvedValue({ ok: true });
    calls.check.mockResolvedValue(true);
  });

  it("enables only LANZAR while idle and calls launch", async () => {
    await openPanel(adminView());
    expect(screen.getByTestId("pres-phase")).toHaveTextContent("EN ESPERA");
    expect(screen.getByTestId("pres-close")).toBeDisabled();
    expect(screen.getByTestId("pres-reveal")).toBeDisabled();
    fireEvent.click(screen.getByTestId("pres-launch"));
    await waitFor(() => expect(calls.launch).toHaveBeenCalledTimes(1));
  });

  it("closes while open and reveals once closed", async () => {
    const { rerender } = await openPanel(adminView({}, { phase: "open", remaining_ms: 12000 }));
    expect(screen.getByTestId("pres-launch")).toBeDisabled();
    expect(screen.getByTestId("pres-time")).toHaveTextContent("12 s");
    fireEvent.click(screen.getByTestId("pres-close"));
    await waitFor(() => expect(calls.close).toHaveBeenCalled());

    feed(adminView({}, { phase: "closed" }));
    rerender(<Presentador />);
    expect(screen.getByTestId("pres-close")).toBeDisabled();
    fireEvent.click(screen.getByTestId("pres-reveal"));
    await waitFor(() => expect(calls.reveal).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("pres-next"));
    await waitFor(() => expect(calls.next).toHaveBeenCalled());
  });

  it("highlights the correct option after the reveal", async () => {
    await openPanel(adminView({}, { phase: "revealed", reveal: { answer: 1, why: "Porque sí.", distribution: [3, 20, 5, 2] } }));
    expect(screen.getByTestId("pres-option-1")).toHaveAttribute("data-mark", "correct");
    expect(screen.getByTestId("pres-option-0")).toHaveAttribute("data-mark", "dim");
  });

  it("calls phoneNow at the closing step", async () => {
    await openPanel(adminView({}, { step: 8 }));
    const launch = screen.getByTestId("pres-launch");
    expect(launch).toHaveTextContent("LANZAR SOLICITUD AHORA");
    expect(screen.getByTestId("pres-next")).toBeDisabled();
    fireEvent.click(launch);
    await waitFor(() => expect(calls.phoneNow).toHaveBeenCalled());
    expect(calls.launch).not.toHaveBeenCalled();
  });

  it("shows a 409 as a toast", async () => {
    calls.launch.mockRejectedValue(new ApiError(409, "Esta pregunta ya se lanzó. Usa reiniciar pregunta."));
    await openPanel(adminView());
    fireEvent.click(screen.getByTestId("pres-launch"));
    expect(await screen.findByTestId("pres-toast")).toHaveTextContent("Esta pregunta ya se lanzó.");
  });

  it("jumps to a script step, closing an open question after confirming", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await openPanel(adminView({}, { phase: "open", remaining_ms: 9000 }));
    fireEvent.click(screen.getByTestId("pres-step-5"));
    await waitFor(() => expect(calls.goto).toHaveBeenCalledWith(5));
    expect(confirm).toHaveBeenCalled();
    expect(calls.close).toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("runs the keyboard shortcuts, but not while typing", async () => {
    await openPanel(adminView());
    fireEvent.keyDown(window, { key: "l" });
    await waitFor(() => expect(calls.launch).toHaveBeenCalledTimes(1));
    await act(async () => undefined); // let the call settle (busy clears)
    fireEvent.keyDown(window, { key: "c" }); // not open: ignored
    expect(calls.close).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() => expect(calls.next).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("pres-reset-all"));
    const input = screen.getByTestId("pres-reset-input");
    fireEvent.keyDown(input, { key: "l" });
    expect(calls.launch).toHaveBeenCalledTimes(1);
  });

  it("hides an open answer and resets everything only after typing RESET", async () => {
    await openPanel(adminView());
    expect(screen.getByText("clasificando…")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("pres-quote-hide-q1"));
    await waitFor(() => expect(calls.hide).toHaveBeenCalledWith({ answer_id: "q1", hidden: true }));
    expect(screen.getByTestId("pres-email")).toHaveTextContent("1 fallidos");
    expect(screen.getByText("Resend 429")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("pres-verification"));
    await waitFor(() => expect(calls.verification).toHaveBeenCalledWith(false));

    fireEvent.click(screen.getByTestId("pres-reset-all"));
    const confirm = screen.getByTestId("pres-reset-confirm");
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId("pres-reset-input"), { target: { value: "RESET" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(calls.reset).toHaveBeenCalled());
  });
});

describe("Presentador ranking, projection and QR", () => {
  beforeEach(() => {
    window.localStorage.clear();
    for (const fn of Object.values(calls)) if (typeof fn === "function") fn.mockReset().mockResolvedValue({ ok: true });
    calls.check.mockResolvedValue(true);
  });

  it("shows the ranking with hidden attendees inline for the presenter", async () => {
    await openPanel(adminView());
    fireEvent.click(screen.getByTestId("pres-tab-ranking"));
    const list = screen.getByTestId("pres-ranking");
    expect(within(list).getAllByRole("listitem").map((li) => li.getAttribute("data-username"))).toEqual([
      "Ana",
      "Beto",
      "Caro",
      "Dani",
      "Eva",
    ]);
    fireEvent.click(screen.getByTestId("pres-rank-hide-a2"));
    await waitFor(() => expect(calls.hide).toHaveBeenCalledWith({ attendee_id: "a2", hidden: false }));
  });

  it("projects the ranking without hidden attendees or controls", async () => {
    await openPanel(adminView());
    fireEvent.click(screen.getByTestId("pres-tab-ranking"));
    fireEvent.keyDown(window, { key: "p" });
    expect(screen.getByTestId("pres-screen")).toHaveAttribute("data-projection", "true");
    expect(screen.queryByText("Beto")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pres-rank-hide-a1")).not.toBeInTheDocument();
    // Podium shows the top 3 visible; the list continues with #4.
    expect(screen.getByText("Caro")).toBeInTheDocument();
    const list = screen.getByTestId("pres-ranking");
    expect(within(list).getAllByRole("listitem").map((li) => li.getAttribute("data-username"))).toEqual(["Eva"]);
  });

  it("shows only the answer count while a quiz is open in projection", async () => {
    const { rerender } = await openPanel(adminView({}, { phase: "open", remaining_ms: 10000 }));
    fireEvent.click(screen.getByTestId("pres-projection-toggle"));
    expect(screen.getByTestId("pres-proj-count")).toHaveTextContent("20");
    expect(screen.queryByTestId("pres-distribution")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pres-launch")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pres-quotes")).not.toBeInTheDocument();

    feed(adminView({}, { phase: "revealed", reveal: { answer: 1, why: "Porque sí.", distribution: [3, 20, 5, 2] } }));
    rerender(<Presentador />);
    expect(screen.getByTestId("pres-distribution")).toBeInTheDocument();
    expect(screen.getByTestId("pres-option-1")).toHaveAttribute("data-mark", "correct");
  });

  it("projects only visible quotes after MOSTRAR EN PANTALLA", async () => {
    await openPanel(adminView({}, { step: 7, phase: "revealed", reveal: { answer: null, why: null, distribution: null } }));
    fireEvent.keyDown(window, { key: "P" });
    expect(screen.getByTestId("pres-themes")).toBeInTheDocument();
    expect(screen.getByText("“Atender WhatsApp”")).toBeInTheDocument();
    expect(screen.queryByText("“Texto oculto”")).not.toBeInTheDocument();
  });

  it("toggles the QR overlay with Q and closes it with Esc", async () => {
    await openPanel(adminView());
    fireEvent.keyDown(window, { key: "q" });
    const qr = screen.getByTestId("pres-qr");
    expect(within(qr).getByTestId("pres-qr-url")).toHaveTextContent(`${window.location.origin}/charla/`);
    fireEvent.error(within(qr).getByTestId("pres-qr-image"));
    expect(within(qr).queryByTestId("pres-qr-image")).not.toBeInTheDocument();
    expect(within(qr).getByTestId("pres-qr-url")).toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    expect(screen.queryByTestId("pres-qr")).not.toBeInTheDocument();
  });
});
