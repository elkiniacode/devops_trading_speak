import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

import { ChatPanel } from "./ChatPanel";

const reply: ChatMessage = {
  id: "a1",
  role: "assistant",
  content: "Adding PYPL to your watchlist. Placing a buy order for 5 AAPL. Placing a sell order for 50 TSLA.",
  actions: {
    watchlist_changes: [{ ticker: "PYPL", action: "add", status: "ok", error: null }],
    trades: [
      { ticker: "AAPL", side: "buy", quantity: 5, status: "ok", price: 190.12, error: null },
      {
        ticker: "TSLA",
        side: "sell",
        quantity: 50,
        status: "failed",
        price: null,
        error: "Insufficient shares: you have 0 TSLA, tried to sell 50",
      },
    ],
  },
  created_at: "2026-10-19T14:03:13.100Z",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderChat(overrides: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  const props = {
    open: true,
    onClose: vi.fn(),
    send: vi.fn().mockResolvedValue(reply),
    loadHistory: vi.fn().mockResolvedValue([]),
    onActions: vi.fn(),
    ...overrides,
  };
  render(<ChatPanel {...props} />);
  return props;
}

function type(text: string) {
  fireEvent.change(screen.getByTestId("chat-input"), { target: { value: text } });
}

describe("ChatPanel", () => {
  it("loads the conversation history on mount", async () => {
    renderChat({
      loadHistory: vi.fn().mockResolvedValue([
        { id: "u1", role: "user", content: "hello", actions: null, created_at: "2026-10-19T14:00:00.000Z" },
        { ...reply, id: "a0" },
      ]),
    });
    const messages = await screen.findAllByTestId("chat-message");
    expect(messages.map((m) => m.getAttribute("data-role"))).toEqual(["user", "assistant"]);
    expect(screen.getAllByTestId("chat-action")).toHaveLength(3);
  });

  it("shows a loading indicator, then the reply with inline action results", async () => {
    const pending = deferred<ChatMessage>();
    const props = renderChat({ send: vi.fn().mockReturnValue(pending.promise) });
    type("Buy 5 AAPL and add PYPL");
    fireEvent.click(screen.getByTestId("chat-send-button"));

    expect(props.send).toHaveBeenCalledWith("Buy 5 AAPL and add PYPL");
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    expect(screen.getByTestId("chat-message")).toHaveAttribute("data-role", "user");
    expect(screen.getByTestId("chat-input")).toHaveValue("");

    pending.resolve(reply);
    await waitFor(() => expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument());

    const assistant = screen.getAllByTestId("chat-message")[1];
    expect(assistant).toHaveAttribute("data-role", "assistant");
    const actions = within(assistant).getAllByTestId("chat-action");
    expect(actions.map((a) => [a.dataset.kind, a.dataset.status])).toEqual([
      ["watchlist", "ok"],
      ["trade", "ok"],
      ["trade", "failed"],
    ]);
    expect(actions[0]).toHaveTextContent("✓PYPL added to watchlist");
    expect(actions[1]).toHaveTextContent("Bought 5 AAPL at $190.12");
    expect(actions[2]).toHaveTextContent("✗Sell 50 TSLA failed: Insufficient shares: you have 0 TSLA, tried to sell 50");
    expect(props.onActions).toHaveBeenCalledTimes(1);
  });

  it("does not refetch after a reply without actions", async () => {
    const props = renderChat({
      send: vi.fn().mockResolvedValue({ ...reply, actions: { trades: [], watchlist_changes: [] } }),
    });
    type("hi");
    fireEvent.click(screen.getByTestId("chat-send-button"));
    await waitFor(() => expect(screen.getAllByTestId("chat-message")).toHaveLength(2));
    expect(screen.queryByTestId("chat-action")).not.toBeInTheDocument();
    expect(props.onActions).not.toHaveBeenCalled();
  });

  it("sends on Enter but not on Shift+Enter", () => {
    const props = renderChat();
    type("hello");
    fireEvent.keyDown(screen.getByTestId("chat-input"), { key: "Enter", shiftKey: true });
    expect(props.send).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByTestId("chat-input"), { key: "Enter" });
    expect(props.send).toHaveBeenCalledWith("hello");
  });

  it("shows the server's error inline when the LLM is unavailable", async () => {
    renderChat({
      send: vi
        .fn()
        .mockRejectedValue(new ApiError(502, "The AI assistant is unavailable right now. Please try again.")),
    });
    type("How am I doing?");
    fireEvent.click(screen.getByTestId("chat-send-button"));
    expect(await screen.findByTestId("chat-error")).toHaveTextContent("The AI assistant is unavailable right now.");
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
    // The user's message stays in the conversation.
    expect(screen.getByTestId("chat-message")).toHaveAttribute("data-role", "user");
  });

  it("ignores empty messages", () => {
    const props = renderChat();
    type("   ");
    expect(screen.getByTestId("chat-send-button")).toBeDisabled();
    fireEvent.keyDown(screen.getByTestId("chat-input"), { key: "Enter" });
    expect(props.send).not.toHaveBeenCalled();
  });

  it("is hidden when collapsed", () => {
    renderChat({ open: false });
    expect(screen.getByTestId("chat-panel")).not.toBeVisible();
  });
});
