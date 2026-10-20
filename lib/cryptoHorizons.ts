// How long the reader is asking about -- the one vocabulary the picker, the model artifacts and
// the stored forecasts all use.
//
// **A horizon is not a direction, and it is not a trading style.** The page this replaced offered
// "Scalp / Short swing / Swing / Position", which names how somebody trades, and more than one
// reader took the short style to mean a SHORT call. These seven are durations and nothing else:
// picking "Next 5 minutes" asks which way the next five minutes go, and the answer to that
// question is UP or DOWN independently of how long anyone intends to hold.
//
// Mirrors `tools/research/crypto_horizons.py` and is pinned to it by `tests/cryptoHorizons.test.ts`,
// so a horizon cannot be offered here that no model was trained for, and a model cannot be trained
// for a window the site never offers.

export type HorizonKey = "m5" | "m15" | "h1" | "h4" | "d1" | "d5" | "d20";

export interface Horizon {
  key: HorizonKey;
  /// Which corpus answers it: the 5-minute series or the 4-hour one.
  interval: "5m" | "4h";
  /// How many bars of that interval the forecast reaches forward.
  bars: number;
  /// The same reach in minutes, which is what a stored forecast is graded against.
  minutes: number;
  /// The button's words. A duration, never a style.
  label: string;
  /// What that duration is, stated in the units the model actually steps in.
  lead: string;
}

export const HORIZONS: Record<HorizonKey, Horizon> = {
  m5: { key: "m5", interval: "5m", bars: 1, minutes: 5, label: "Next 5 minutes", lead: "one 5-minute bar from the last close" },
  m15: { key: "m15", interval: "5m", bars: 3, minutes: 15, label: "Next 15 minutes", lead: "three 5-minute bars from the last close" },
  h1: { key: "h1", interval: "5m", bars: 12, minutes: 60, label: "Next hour", lead: "twelve 5-minute bars from the last close" },
  h4: { key: "h4", interval: "5m", bars: 48, minutes: 240, label: "Rest of today", lead: "four hours from the last close" },
  d1: { key: "d1", interval: "4h", bars: 6, minutes: 1440, label: "Next session", lead: "one UTC day from the last close" },
  d5: { key: "d5", interval: "4h", bars: 30, minutes: 7200, label: "This week", lead: "five UTC days from the last close" },
  d20: { key: "d20", interval: "4h", bars: 120, minutes: 28800, label: "Coming month", lead: "twenty UTC days from the last close" },
};

export const HORIZON_ORDER: HorizonKey[] = ["m5", "m15", "h1", "h4", "d1", "d5", "d20"];

/// The two groups the picker shows, because "minutes from now" and "weeks from now" are answered
/// from different corpora and a reader should be able to see that they are different questions.
export const HORIZON_GROUPS: { title: string; note: string; keys: HorizonKey[] }[] = [
  {
    title: "Minutes and hours",
    note: "read from the 5-minute series, looking back 24 hours",
    keys: ["m5", "m15", "h1", "h4"],
  },
  {
    title: "Sessions and weeks",
    note: "read from the 4-hour series, looking back 48 days. Crypto has no exchange session, so a session here is a UTC day",
    keys: ["d1", "d5", "d20"],
  },
];

export function isHorizonKey(s: string | null | undefined): s is HorizonKey {
  return !!s && (HORIZON_ORDER as string[]).includes(s);
}

/// The horizon a `?h=` parameter names, or null. Null is "nothing chosen", which is a real state
/// the page renders -- it is not defaulted to a horizon the reader did not ask for.
export function horizonFrom(s: string | null | undefined): Horizon | null {
  return isHorizonKey(s) ? HORIZONS[s] : null;
}

/// When a forecast made at `asOf` can first be graded.
export function maturesAt(asOf: Date, h: Horizon): Date {
  return new Date(asOf.getTime() + h.minutes * 60_000);
}
