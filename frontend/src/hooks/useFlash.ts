import { useEffect, useRef, useState } from "react";

export const FLASH_MS = 500;

interface FlashState {
  direction: "flash-up" | "flash-down" | null;
  count: number;
}

/**
 * Class names for a price cell: "flash-up" / "flash-down" for FLASH_MS after `price` rises /
 * falls, then "". The CSS fades the tint out over the same 500 ms. "flash-a" / "flash-b"
 * alternate on every change so the fade restarts even when two ticks in a row go the same way.
 */
export function useFlash(price: number | null | undefined): string {
  const previous = useRef(price);
  const [flash, setFlash] = useState<FlashState>({ direction: null, count: 0 });

  useEffect(() => {
    const before = previous.current;
    previous.current = price;
    if (price == null || before == null || price === before) {
      setFlash((f) => (f.direction ? { ...f, direction: null } : f)); // e.g. the price went away mid-flash
      return;
    }
    const direction = price > before ? "flash-up" : "flash-down";
    setFlash((f) => ({ direction, count: f.count + 1 }));
    const timer = setTimeout(() => setFlash((f) => ({ ...f, direction: null })), FLASH_MS);
    return () => clearTimeout(timer);
  }, [price]);

  return flash.direction ? `${flash.direction} ${flash.count % 2 ? "flash-a" : "flash-b"}` : "";
}
