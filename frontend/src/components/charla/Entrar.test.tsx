import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { getPending, getToken, setPending } from "@/lib/charla/session";

const replace = vi.fn();
const router = { replace, push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const api = vi.hoisted(() => ({ verify: vi.fn() }));
vi.mock("@/lib/charla/api", () => ({ charlaApi: api }));

import { Entrar } from "./Entrar";

describe("Entrar", () => {
  beforeEach(() => {
    window.localStorage.clear();
    replace.mockReset();
    api.verify.mockReset();
    window.history.replaceState(null, "", "/charla/entrar/");
  });

  it("verifies the link, stores the session, strips the hash and opens the Sala", async () => {
    setPending({ pending: "p", email: "a@b.co", username: "Ana", sentAt: 1 });
    window.history.replaceState(null, "", "/charla/entrar/#v=link-123");
    api.verify.mockResolvedValue({ token: "tok", username: "Ana" });
    render(<Entrar />);
    expect(await screen.findByText("¡Listo, Ana! Ya estás dentro.")).toBeInTheDocument();
    expect(api.verify).toHaveBeenCalledWith("link-123");
    expect(window.location.hash).toBe("");
    expect(getToken()).toBe("tok");
    expect(getPending()).toBeNull();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/charla/sala/"), { timeout: 3000 });
  });

  it("shows the server message for an expired link", async () => {
    window.history.replaceState(null, "", "/charla/entrar/#v=old");
    api.verify.mockRejectedValue(new ApiError(400, "Este enlace expiró o no es válido. Pide uno nuevo."));
    render(<Entrar />);
    const page = screen.getByTestId("charla-entrar");
    await waitFor(() => expect(page).toHaveAttribute("data-state", "error"));
    expect(screen.getByRole("alert")).toHaveTextContent("Este enlace expiró o no es válido.");
    expect(screen.getByRole("link", { name: "Pedir un enlace nuevo" })).toHaveAttribute("href", "/charla/");
    expect(getToken()).toBeNull();
  });

  it("fails without calling the server when the hash has no token", async () => {
    render(<Entrar />);
    await waitFor(() => expect(screen.getByTestId("charla-entrar")).toHaveAttribute("data-state", "error"));
    expect(api.verify).not.toHaveBeenCalled();
  });
});
