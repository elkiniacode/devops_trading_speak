import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

import { adminApi, charlaApi, OFFLINE_MESSAGE } from "./api";

function respond(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function stubFetch(status = 200, body: unknown = { ok: true }) {
  const fetchMock = vi.fn().mockResolvedValue(respond(status, body));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("charlaApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("checks a username, encoding the query", async () => {
    const fetchMock = stubFetch(200, { valid: true, available: true, message: null, suggestion: null });
    await charlaApi.checkUsername("José P", "jose@empresa.com");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/charla/username?u=Jos%C3%A9%20P&email=jose%40empresa.com");
    await charlaApi.checkUsername("Ana");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/charla/username?u=Ana");
  });

  it("registers with a JSON body", async () => {
    const fetchMock = stubFetch(200, { status: "in", token: "t", username: "José P" });
    await expect(charlaApi.register("José P", "jose@empresa.com")).resolves.toEqual({ status: "in", token: "t", username: "José P" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/charla/register");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ username: "José P", email: "jose@empresa.com" });
  });

  it("polls the pending status and verifies a link", async () => {
    const fetchMock = stubFetch(200, { status: "waiting" });
    await charlaApi.status("p/1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/charla/register/status?p=p%2F1");
    await charlaApi.verify("v-token");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/charla/verify");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ v: "v-token" });
  });

  it("sends the bearer token on attendee calls", async () => {
    const fetchMock = stubFetch(200, { accepted: true });
    await charlaApi.me("tok");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/charla/me");
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Authorization: "Bearer tok" });

    await charlaApi.answer("tok", { step: 2, choice: 1 });
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/charla/answer");
    expect(init.headers).toEqual({ "Content-Type": "application/json", Authorization: "Bearer tok" });
    expect(JSON.parse(init.body)).toEqual({ step: 2, choice: 1 });

    await charlaApi.phone("tok", { skip: true });
    expect(fetchMock.mock.calls[2][0]).toBe("/api/charla/phone");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ skip: true });
  });

  it("builds the stream URL with the token in the query", () => {
    expect(charlaApi.streamUrl("a b")).toBe("/api/charla/stream?t=a%20b");
  });

  it("passes the backend's Spanish detail through", async () => {
    stubFetch(409, { detail: "La pregunta ya está cerrada." });
    await expect(charlaApi.answer("tok", { step: 1, choice: 0 })).rejects.toMatchObject({
      status: 409,
      detail: "La pregunta ya está cerrada.",
    });
  });

  it("maps a network failure to the Spanish offline message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await charlaApi.me("tok").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 0, detail: OFFLINE_MESSAGE });
  });

  it("never shows English for a 422 or a bodiless server error", async () => {
    stubFetch(422, { detail: [{ loc: ["body", "step"], msg: "Field required" }] });
    await expect(charlaApi.answer("tok", { step: 1, choice: 0 })).rejects.toMatchObject({
      status: 422,
      detail: "Revisa los datos e intenta de nuevo.",
    });
    stubFetch(502, "<html>Bad gateway</html>");
    await expect(charlaApi.me("tok")).rejects.toMatchObject({
      status: 502,
      detail: "Algo falló en el servidor (502). Intenta de nuevo.",
    });
  });
});

describe("adminApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts each control with the X-Admin-Key header", async () => {
    const fetchMock = stubFetch();
    const admin = adminApi("secret");
    const calls: [() => Promise<unknown>, string, unknown][] = [
      [admin.launch, "launch", undefined],
      [admin.close, "close", undefined],
      [admin.reveal, "reveal", undefined],
      [admin.next, "next", undefined],
      [() => admin.goto(3), "goto", { step: 3 }],
      [admin.resetStep, "reset-step", undefined],
      [admin.phoneNow, "phone-now", undefined],
      [admin.reclassify, "reclassify", undefined],
      [() => admin.verification(false), "verification", { on: false }],
      [() => admin.hide({ answer_id: "x", hidden: true }), "hide", { answer_id: "x", hidden: true }],
      [admin.reset, "reset", { confirm: "RESET" }],
    ];
    for (const [i, [run, path, body]] of calls.entries()) {
      await expect(run()).resolves.toEqual({ ok: true });
      const [url, init] = fetchMock.mock.calls[i];
      expect(url).toBe(`/api/charla/admin/${path}`);
      expect(init.method).toBe("POST");
      expect(init.headers["X-Admin-Key"]).toBe("secret");
      if (body === undefined) expect(init.body).toBeUndefined();
      else expect(JSON.parse(init.body)).toEqual(body);
    }
  });

  it("builds the export and stream URLs with the key in the query", () => {
    const admin = adminApi("k&1");
    expect(admin.exportUrl).toBe("/api/charla/admin/export.csv?key=k%261");
    expect(admin.streamUrl).toBe("/api/charla/admin/stream?key=k%261");
  });

  it("surfaces a wrong key", async () => {
    stubFetch(401, { detail: "Clave de presentador incorrecta." });
    await expect(adminApi("bad").launch()).rejects.toMatchObject({ status: 401, detail: "Clave de presentador incorrecta." });
  });

  it("checks a key without side effects", async () => {
    const fetchMock = stubFetch(200, "csv");
    await expect(adminApi("good").check()).resolves.toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/charla/admin/export.csv");
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ "X-Admin-Key": "good" });
    expect(fetchMock.mock.calls[0][1].method).toBeUndefined();

    stubFetch(401, { detail: "Clave de presentador incorrecta." });
    await expect(adminApi("bad").check()).resolves.toBe(false);

    stubFetch(503, { detail: "El presentador no está configurado." });
    await expect(adminApi("x").check()).rejects.toMatchObject({ status: 503, detail: "El presentador no está configurado." });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(adminApi("x").check()).rejects.toMatchObject({ status: 0, detail: OFFLINE_MESSAGE });
  });
});
