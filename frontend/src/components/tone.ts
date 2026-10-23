import type { PnlSign } from "@/lib/format";

/** Text color for a signed figure: green up, red down, muted when flat. */
export const SIGN_TEXT: Record<PnlSign, string> = {
  positive: "text-gain",
  negative: "text-loss",
  zero: "text-muted",
};
