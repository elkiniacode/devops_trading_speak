import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearAdminKey,
  clearPending,
  clearToken,
  DEFAULT_MONITOR_BASE,
  getAdminKey,
  getMonitorBase,
  getPending,
  getToken,
  setAdminKey,
  setMonitorBase,
  setPending,
  setToken,
} from "./session";

const PENDING = { pending: "p-secret", email: "jose@empresa.com", username: "José P", sentAt: 1_792_700_000_000 };

describe("session", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stores, reads and clears the token", () => {
    expect(getToken()).toBeNull();
    setToken("tok");
    expect(window.localStorage.getItem("charla.token")).toBe("tok");
    expect(getToken()).toBe("tok");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("round-trips the pending registration", () => {
    expect(getPending()).toBeNull();
    setPending(PENDING);
    expect(getPending()).toEqual(PENDING);
    clearPending();
    expect(getPending()).toBeNull();
  });

  it.each(["not json", "null", "42", '{"pending":"p"}', '{"pending":"","email":"a","username":"b","sentAt":1}', '{"pending":"p","email":"a","username":"b","sentAt":"1"}'])(
    "treats a corrupt pending value %j as nothing pending",
    (raw) => {
      window.localStorage.setItem("charla.pending", raw);
      expect(getPending()).toBeNull();
    },
  );

  it("stores and clears the admin key; an empty key clears it", () => {
    setAdminKey("k");
    expect(getAdminKey()).toBe("k");
    setAdminKey("");
    expect(getAdminKey()).toBeNull();
    setAdminKey("k");
    clearAdminKey();
    expect(getAdminKey()).toBeNull();
  });

  it("defaults the monitor base and strips trailing slashes", () => {
    expect(getMonitorBase()).toBe(DEFAULT_MONITOR_BASE);
    setMonitorBase(" http://192.168.0.5:4800/ ");
    expect(getMonitorBase()).toBe("http://192.168.0.5:4800");
  });

  it("never throws when storage is unavailable", () => {
    const boom = () => {
      throw new DOMException("denied", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(boom);

    expect(() => setToken("t")).not.toThrow();
    expect(() => clearToken()).not.toThrow();
    expect(() => setPending(PENDING)).not.toThrow();
    expect(() => clearPending()).not.toThrow();
    expect(() => setAdminKey("k")).not.toThrow();
    expect(() => clearAdminKey()).not.toThrow();
    expect(() => setMonitorBase("http://x")).not.toThrow();
    expect(getToken()).toBeNull();
    expect(getPending()).toBeNull();
    expect(getAdminKey()).toBeNull();
    expect(getMonitorBase()).toBe(DEFAULT_MONITOR_BASE);
  });

  it("never throws when localStorage itself can't be reached", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(() => setToken("t")).not.toThrow();
    expect(getToken()).toBeNull();
    expect(getPending()).toBeNull();
  });
});
