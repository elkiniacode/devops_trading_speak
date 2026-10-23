import { describe, expect, it } from "vitest";

import { cleanUsername, emailError, openTextError, phoneDigits, phoneError, usernameError } from "./validate";

const LENGTH = "Usa entre 2 y 24 caracteres.";
const CHARS = "Usa solo letras, números, espacios, punto, guion o guion bajo.";

describe("usernameError", () => {
  it.each(["José P", "Ñoño", "ana.maria", "dev_42", "la-crack", "Jo", "a".repeat(24), "  Camilo   Andrés  ", "Zoë"])(
    "accepts %j",
    (name) => {
      expect(usernameError(name)).toBeNull();
    },
  );

  it("accepts accents typed as combining marks", () => {
    expect(usernameError("José")).toBeNull();
  });

  it("asks for a name when empty or blank", () => {
    expect(usernameError("")).toBe("Escribe tu nombre para el ranking.");
    expect(usernameError("   ")).toBe("Escribe tu nombre para el ranking.");
  });

  it("enforces 2 to 24 characters after trimming and collapsing spaces", () => {
    expect(usernameError("J")).toBe(LENGTH);
    expect(usernameError(" J ")).toBe(LENGTH);
    expect(usernameError("a".repeat(25))).toBe(LENGTH);
    // 24 after collapsing the inner run of spaces.
    expect(usernameError(`${"a".repeat(11)}      ${"b".repeat(12)}`)).toBeNull();
  });

  it.each(["José!", "ana@x", "emoji 🙂", "<b>", "tab\u0000x", "50%"])("rejects %j", (name) => {
    expect(usernameError(name)).toBe(CHARS);
  });

  it("cleans like the backend", () => {
    expect(cleanUsername("  José   P  ")).toBe("José P");
  });
});

describe("emailError", () => {
  it.each(["jose@empresa.com", " Jose@Empresa.com.co ", "a.b+tag@sub.dominio.co", "x@y.io"])("accepts %j", (email) => {
    expect(emailError(email)).toBeNull();
  });

  it.each(["", "   ", "jose", "jose@", "jose@empresa", "jose@empresa.", "jose@.com", "jo se@empresa.com", "a@b@c.com", "jose@empresa.c"])(
    "rejects %j",
    (email) => {
      expect(emailError(email)).toBe("Revisa el correo: necesitamos uno válido para el enlace.");
    },
  );
});

describe("phoneError", () => {
  it.each(["3001234567", "300 123 4567", "300-123-4567", "(300) 123 4567", " 3151234567 "])("accepts %j", (phone) => {
    expect(phoneError(phone)).toBeNull();
  });

  it.each(["", "300123456", "30012345678", "6011234567", "+57 300 123 4567", "abc"])("rejects %j", (phone) => {
    expect(phoneError(phone)).toBe("Escribe un celular colombiano de 10 dígitos.");
  });

  it("keeps only the digits", () => {
    expect(phoneDigits("300 123-4567")).toBe("3001234567");
  });
});

describe("openTextError", () => {
  it("needs 8 to 280 characters after trimming", () => {
    expect(openTextError("  corto  ")).toBe("Escribe al menos 8 caracteres.");
    expect(openTextError("Automatizar ventas")).toBeNull();
    expect(openTextError("x".repeat(280))).toBeNull();
    expect(openTextError("x".repeat(281))).toBe("Usa máximo 280 caracteres.");
  });
});
