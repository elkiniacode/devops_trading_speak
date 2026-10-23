import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { getPending, getToken, setPending, setToken } from "@/lib/charla/session";

const replace = vi.fn();
const router = { replace, push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const api = vi.hoisted(() => ({
  checkUsername: vi.fn(),
  register: vi.fn(),
  status: vi.fn(),
  me: vi.fn(),
}));
vi.mock("@/lib/charla/api", () => ({
  charlaApi: api,
  OFFLINE_MESSAGE: "Sin conexión. Revisa tu internet e intenta de nuevo.",
}));

import { Registro } from "./Registro";

function fill(username: string, email: string) {
  fireEvent.change(screen.getByTestId("charla-username"), { target: { value: username } });
  fireEvent.change(screen.getByTestId("charla-email"), { target: { value: email } });
}

describe("Registro", () => {
  beforeEach(() => {
    window.localStorage.clear();
    replace.mockReset();
    api.checkUsername.mockReset().mockResolvedValue({ valid: true, available: true, message: null, suggestion: null });
    api.register.mockReset();
    api.status.mockReset().mockResolvedValue({ status: "waiting" });
    api.me.mockReset();
  });

  it("sends the link, waits, and enters the Sala once the email is clicked", async () => {
    api.register.mockResolvedValue({
      status: "link_sent",
      pending: "p1",
      email: "jose@empresa.com",
      username: "José P",
      resend_in_s: 30,
    });
    render(<Registro />);
    await screen.findByTestId("charla-submit");
    fill("José P", "jose@empresa.com");
    fireEvent.click(screen.getByTestId("charla-submit"));

    expect(await screen.findByTestId("charla-waiting")).toHaveTextContent("jose@empresa.com");
    expect(api.register).toHaveBeenCalledWith("José P", "jose@empresa.com");
    expect(getPending()?.pending).toBe("p1");
    expect(screen.getByTestId("charla-resend")).toBeDisabled();

    api.status.mockResolvedValue({ status: "in", token: "tok", username: "José P" });
    expect(await screen.findByTestId("charla-done", {}, { timeout: 4000 })).toHaveTextContent("¡Listo, José P!");
    expect(getToken()).toBe("tok");
    expect(getPending()).toBeNull();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/sala/"), { timeout: 3000 });
  });

  it("enters right away when verification is off", async () => {
    api.register.mockResolvedValue({ status: "in", token: "tok2", username: "Ana" });
    render(<Registro />);
    await screen.findByTestId("charla-submit");
    fill("Ana", "ana@empresa.com");
    fireEvent.click(screen.getByTestId("charla-submit"));
    await screen.findByTestId("charla-done");
    expect(getToken()).toBe("tok2");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/sala/"));
  });

  it("validates on the client before calling the server", async () => {
    render(<Registro />);
    await screen.findByTestId("charla-submit");
    fill("J", "no-es-correo");
    fireEvent.click(screen.getByTestId("charla-submit"));
    expect(await screen.findByTestId("charla-email-error")).toBeInTheDocument();
    expect(screen.getByTestId("charla-username-hint")).toHaveAttribute("data-tone", "error");
    expect(api.register).not.toHaveBeenCalled();
  });

  it("offers the suggested name on a 409", async () => {
    api.register.mockRejectedValue(
      new ApiError(409, "Ese nombre ya está en uso. Prueba con otro, por ejemplo «José P2»."),
    );
    render(<Registro />);
    await screen.findByTestId("charla-submit");
    fill("José P", "jose@empresa.com");
    fireEvent.click(screen.getByTestId("charla-submit"));
    fireEvent.click(await screen.findByRole("button", { name: "Usar «José P2»" }));
    expect(screen.getByTestId("charla-username")).toHaveValue("José P2");
  });

  it("shows a server error that isn't about the fields", async () => {
    api.register.mockRejectedValue(new ApiError(429, "Espera 12 s para pedir otro enlace."));
    render(<Registro />);
    await screen.findByTestId("charla-submit");
    fill("José P", "jose@empresa.com");
    fireEvent.click(screen.getByTestId("charla-submit"));
    expect(await screen.findByTestId("charla-form-error")).toHaveTextContent("Espera 12 s");
  });

  it("goes straight to the Sala with a working session", async () => {
    setToken("old");
    api.me.mockResolvedValue({ state: {}, me: {} });
    render(<Registro />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/sala/"));
  });

  it("drops an expired session and resumes a pending registration", async () => {
    setToken("old");
    api.me.mockRejectedValue(new ApiError(401, "Tu sesión expiró. Vuelve a registrarte."));
    setPending({ pending: "p9", email: "a@b.co", username: "Ana", sentAt: Date.now() });
    render(<Registro />);
    expect(await screen.findByTestId("charla-waiting")).toHaveTextContent("a@b.co");
    expect(getToken()).toBeNull();
    await waitFor(() => expect(api.status).toHaveBeenCalledWith("p9"));
  });

  it("returns to the form when the pending registration expired", async () => {
    setPending({ pending: "p9", email: "a@b.co", username: "Ana", sentAt: Date.now() });
    api.status.mockRejectedValue(new ApiError(404, "Este registro expiró. Vuelve a escribir tu correo."));
    render(<Registro />);
    expect(await screen.findByTestId("charla-form-error")).toHaveTextContent("Este registro expiró");
    expect(getPending()).toBeNull();
    await act(async () => undefined);
  });
});
