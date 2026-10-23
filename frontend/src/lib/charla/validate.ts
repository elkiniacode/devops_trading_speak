/**
 * Client-side checks that mirror the backend's rules (CONTRACT §5.1, §5.2, §5.8), so the
 * phone shows the error before a round trip. Each returns a Spanish message or null.
 */

export const USERNAME_MIN = 2;
export const USERNAME_MAX = 24;
export const OPEN_MIN_CHARS = 8;
export const OPEN_MAX_CHARS = 280;

// Letters (accents and ñ included, also as combining marks), digits, space, . _ -
const USERNAME_CHARS = /^[\p{L}\p{M}\p{N} ._-]+$/u;
const EMAIL = /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)*\.[^\s@.]{2,}$/;

/** Trim and collapse inner whitespace, as the backend's clean_username() does. */
export function cleanUsername(raw: string): string {
  return raw.trim().replace(/\s+/g, " ");
}

export function usernameError(raw: string): string | null {
  const name = cleanUsername(raw);
  if (!name) return "Escribe tu nombre para el ranking.";
  // Count code points, like Python's len().
  const length = Array.from(name).length;
  if (length < USERNAME_MIN || length > USERNAME_MAX) return "Usa entre 2 y 24 caracteres.";
  if (!USERNAME_CHARS.test(name)) return "Usa solo letras, números, espacios, punto, guion o guion bajo.";
  return null;
}

export function emailError(raw: string): string | null {
  const email = raw.trim();
  if (!email || email.length > 254 || !EMAIL.test(email)) {
    return "Revisa el correo: necesitamos uno válido para el enlace.";
  }
  return null;
}

/** Digits only: "300 123 4567" -> "3001234567". */
export function phoneDigits(raw: string): string {
  return raw.replace(/\D/g, "");
}

/** A Colombian mobile: 10 digits starting with 3 (the +57 prefix is shown apart). */
export function phoneError(raw: string): string | null {
  return /^3\d{9}$/.test(phoneDigits(raw)) ? null : "Escribe un celular colombiano de 10 dígitos.";
}

/** The open question's text after strip must be 8–280 characters. */
export function openTextError(raw: string): string | null {
  const length = Array.from(raw.trim()).length;
  if (length < OPEN_MIN_CHARS) return "Escribe al menos 8 caracteres.";
  if (length > OPEN_MAX_CHARS) return "Usa máximo 280 caracteres.";
  return null;
}
