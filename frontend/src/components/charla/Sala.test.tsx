import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { getToken, setToken } from "@/lib/charla/session";
import type { AttendeeView, Me, RoomState } from "@/lib/charla/types";

const replace = vi.fn();
const router = { replace, push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const api = vi.hoisted(() => ({
  me: vi.fn(),
  answer: vi.fn(),
  phone: vi.fn(),
  streamUrl: (t: string) => `/api/charla/stream?t=${t}`,
}));
vi.mock("@/lib/charla/api", () => ({ charlaApi: api }));

const stream = vi.hoisted(() => ({
  current: { data: null as unknown, status: "live", receivedAt: 0 as number | null, error: null },
  urls: [] as (string | null)[],
}));
vi.mock("@/lib/charla/stream", () => ({
  useCharlaStream: (url: string | null) => {
    stream.urls.push(url);
    return stream.current;
  },
}));

import { Sala } from "./Sala";

const QUESTION = { text: "¿Qué hace un agente?", options: ["A1", "B1", "C1", "D1"], placeholder: null };

function state(over: Partial<RoomState> = {}): RoomState {
  return {
    version: 1,
    server_now_ms: 0,
    step: 2,
    kind: "quiz",
    phase: "idle",
    number: 3,
    total_quiz: 7,
    remaining_ms: null,
    duration_ms: 20000,
    question: QUESTION,
    reveal: null,
    phone_prompt: false,
    room_count: 34,
    ...over,
  };
}

function me(over: Partial<Me> = {}): Me {
  return {
    attendee_id: "a1",
    username: "José P",
    verified: true,
    score: 1820,
    rank: 5,
    answer: null,
    result: null,
    phone_status: "none",
    ...over,
  };
}

function feed(view: AttendeeView) {
  stream.current = { data: view, status: "live", receivedAt: performance.now(), error: null };
}

const viewOf = () => screen.getByTestId("sala").getAttribute("data-view");

describe("Sala", () => {
  beforeEach(() => {
    window.localStorage.clear();
    replace.mockReset();
    api.me.mockReset();
    api.answer.mockReset().mockResolvedValue({ accepted: true });
    api.phone.mockReset().mockResolvedValue({ ok: true });
    stream.current = { data: null, status: "connecting", receivedAt: null, error: null };
    stream.urls = [];
    setToken("tok");
  });

  it("sends attendees without a session back to registration", async () => {
    window.localStorage.clear();
    render(<Sala />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/"));
  });

  it("connects with the stored token and shows the username", async () => {
    feed({ state: state(), me: me() });
    render(<Sala />);
    await waitFor(() => expect(stream.urls).toContain("/api/charla/stream?t=tok"));
    expect(viewOf()).toBe("wait");
    expect(screen.getByTestId("sala-username")).toHaveTextContent("José P");
  });

  it("answers a quiz question and shows it as registered right away", async () => {
    feed({ state: state({ phase: "open", remaining_ms: 15000 }), me: me() });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("question"));
    fireEvent.click(screen.getByTestId("sala-option-1"));
    expect(api.answer).toHaveBeenCalledWith("tok", { step: 2, choice: 1 });
    await waitFor(() => expect(viewOf()).toBe("answered"));
    expect(screen.getByTestId("sala-chosen")).toHaveTextContent("B1");
  });

  it("rolls back and shows the 409 message when the answer is rejected", async () => {
    api.answer.mockRejectedValue(new ApiError(409, "La pregunta ya está cerrada."));
    feed({ state: state({ phase: "open", remaining_ms: 15000 }), me: me() });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("question"));
    fireEvent.click(screen.getByTestId("sala-option-0"));
    expect(await screen.findByTestId("sala-toast")).toHaveTextContent("La pregunta ya está cerrada.");
    expect(viewOf()).toBe("question");
  });

  it("says time ran out when the question closed without an answer", async () => {
    feed({ state: state({ phase: "closed" }), me: me() });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("answered"));
    expect(screen.getByText("Se acabó el tiempo")).toBeInTheDocument();
  });

  it("shows the result after the reveal", async () => {
    feed({
      state: state({ phase: "revealed", reveal: { answer: 1, why: "Porque sí.", distribution: [1, 9, 2, 0] } }),
      me: me({ answer: { step: 2, choice: 1, text: null }, result: { correct: true, points: 842 } }),
    });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("result"));
    const result = screen.getByTestId("sala-result");
    expect(result).toHaveAttribute("data-correct", "true");
    expect(result).toHaveTextContent("CORRECTO");
    expect(result).toHaveTextContent("+842");
    expect(screen.getByText("Porque sí.")).toBeInTheDocument();
  });

  it("sends the open answer", async () => {
    feed({
      state: state({
        step: 7,
        kind: "open",
        number: null,
        phase: "open",
        remaining_ms: 50000,
        question: { text: "¿Qué proceso?", options: [], placeholder: "Escribe aquí" },
      }),
      me: me(),
    });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("open"));
    expect(screen.getByTestId("sala-open-send")).toBeDisabled();
    fireEvent.change(screen.getByTestId("sala-open-text"), { target: { value: "Conciliar facturas cada mes" } });
    fireEvent.click(screen.getByTestId("sala-open-send"));
    expect(api.answer).toHaveBeenCalledWith("tok", { step: 7, text: "Conciliar facturas cada mes" });
    await waitFor(() => expect(viewOf()).toBe("answered"));
  });

  it("validates the phone, then sends it", async () => {
    feed({ state: state({ phone_prompt: true }), me: me() });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("phone"));
    fireEvent.change(screen.getByTestId("sala-phone-input"), { target: { value: "123" } });
    fireEvent.click(screen.getByTestId("sala-phone-send"));
    expect(api.phone).not.toHaveBeenCalled();
    expect(screen.getByText("Necesitamos tu autorización para escribirte por WhatsApp.")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("sala-phone-input"), { target: { value: "300 123 4567" } });
    fireEvent.click(screen.getByTestId("sala-phone-consent"));
    fireEvent.click(screen.getByTestId("sala-phone-send"));
    await waitFor(() => expect(api.phone).toHaveBeenCalledWith("tok", { phone: "300 123 4567", consent: true }));
    await waitFor(() => expect(viewOf()).toBe("wait"));
  });

  it("lets the attendee skip the phone", async () => {
    feed({ state: state({ phone_prompt: true }), me: me() });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("phone"));
    fireEvent.click(screen.getByTestId("sala-phone-skip"));
    await waitFor(() => expect(api.phone).toHaveBeenCalledWith("tok", { skip: true }));
    await waitFor(() => expect(viewOf()).toBe("wait"));
  });

  it("shows the final score at the closing step", async () => {
    feed({ state: state({ step: 8, kind: "closing", number: null, question: null }), me: me({ score: 4410 }) });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("end"));
    expect(screen.getByTestId("sala-final-score")).toHaveTextContent("4.410");
  });

  it("leaves the room on a 401 from an answer", async () => {
    api.answer.mockRejectedValue(new ApiError(401, "Tu sesión expiró. Vuelve a registrarte."));
    feed({ state: state({ phase: "open", remaining_ms: 15000 }), me: me() });
    render(<Sala />);
    await waitFor(() => expect(viewOf()).toBe("question"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("sala-option-2"));
    });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/"));
    expect(getToken()).toBeNull();
  });

  it("leaves the room when the server no longer knows the session", async () => {
    feed({ state: state(), me: null });
    render(<Sala />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/"));
    expect(getToken()).toBeNull();
  });

  it("shows the reconnecting pill when the stream drops", async () => {
    feed({ state: state(), me: me() });
    stream.current = { ...stream.current, status: "reconnecting" };
    render(<Sala />);
    expect(await screen.findByTestId("sala-reconnecting")).toBeInTheDocument();
  });
});
