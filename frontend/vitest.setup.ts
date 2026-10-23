import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/**
 * Node 25 ships its own global `localStorage` (without --localstorage-file it is a broken
 * stub) and it shadows jsdom's. When that happens, back Storage.prototype with an in-memory
 * map, so tests can still spy on Storage.prototype methods.
 */
function storageWorks(name: "localStorage" | "sessionStorage"): boolean {
  try {
    const s = window[name];
    return typeof s?.clear === "function" && typeof s?.setItem === "function";
  } catch {
    return false;
  }
}

if (!storageWorks("localStorage") || !storageWorks("sessionStorage")) {
  const stores = new WeakMap<object, Map<string, string>>();
  const mapOf = (self: object) => {
    let m = stores.get(self);
    if (!m) stores.set(self, (m = new Map()));
    return m;
  };
  const proto = Storage.prototype as unknown as Record<string, unknown>;
  Object.defineProperties(proto, {
    length: {
      configurable: true,
      get(this: object) {
        return mapOf(this).size;
      },
    },
    clear: {
      configurable: true,
      writable: true,
      value(this: object) {
        mapOf(this).clear();
      },
    },
    getItem: {
      configurable: true,
      writable: true,
      value(this: object, k: string) {
        return mapOf(this).get(String(k)) ?? null;
      },
    },
    key: {
      configurable: true,
      writable: true,
      value(this: object, i: number) {
        return Array.from(mapOf(this).keys())[i] ?? null;
      },
    },
    removeItem: {
      configurable: true,
      writable: true,
      value(this: object, k: string) {
        mapOf(this).delete(String(k));
      },
    },
    setItem: {
      configurable: true,
      writable: true,
      value(this: object, k: string, v: string) {
        mapOf(this).set(String(k), String(v));
      },
    },
  });
  for (const name of ["localStorage", "sessionStorage"] as const) {
    if (storageWorks(name)) continue;
    const storage = Object.create(Storage.prototype) as Storage;
    Object.defineProperty(window, name, {
      configurable: true,
      get: () => storage,
    });
    Object.defineProperty(globalThis, name, {
      configurable: true,
      get: () => storage,
    });
  }
}

afterEach(() => {
  cleanup();
});
