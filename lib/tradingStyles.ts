// Trading styles, and the exact window each one means.
//
// **The vocabulary problem this has to solve twice over.** The panel used to offer styles --
// "Scalp / Intraday / Swing / Position" -- and readers took the short style to be a SHORT call. It
// was rebuilt around durations for that reason, and the durations are right: the model predicts a
// window, and the window is what a direction is about.
//
// But a reader does not think "I would like to know about the next fifteen minutes". They think "I
// want to be in and out quickly". So the style is how the question is *asked*, and the window is
// how it is *answered*, and the only way both are safe is that every button prints the window
// beside the style and the answer restates it. A style here is a label on a duration and never a
// direction, a position size or a trade.
//
// The windows are `lib/cryptoHorizons.ts` and are not redefined here. This file is the mapping and
// nothing else, so a horizon cannot come to mean two things.

import { type HorizonKey } from "@/lib/cryptoHorizons";

export interface Style {
  key: string;
  label: string;
  /// What a reader is actually doing, in their words, not the model's.
  intent: string;
  horizons: HorizonKey[];
}

export const STYLES: Style[] = [
  {
    key: "scalp",
    label: "Scalping",
    intent: "in and out within minutes",
    horizons: ["m5", "m15"],
  },
  {
    key: "intraday",
    label: "Intraday",
    intent: "opened and closed inside the day",
    horizons: ["h1", "h4"],
  },
  {
    key: "swing",
    label: "Swing",
    intent: "held for days",
    horizons: ["d1", "d5"],
  },
  {
    key: "position",
    label: "Position",
    intent: "held for weeks",
    horizons: ["d20"],
  },
];

export function styleFrom(value: string | undefined | null): Style | null {
  if (!value) return null;
  return STYLES.find((s) => s.key === value) ?? null;
}
