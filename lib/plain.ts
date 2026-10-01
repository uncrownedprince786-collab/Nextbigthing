/// Turning measurements into the sentence a person would actually say.
///
/// The rule this file exists to enforce: the first thing a reader sees is never a number they
/// have to interpret. "Volume 4.1×" is a fact about the data; "much more trading than usual"
/// is the same fact in a form someone can act on, and the figure stays available underneath.
///
/// Every function here is a pure translation of a stored value. None of them invents, rounds
/// away a distinction, or softens an absence — `null` in gives "not available" out, never a
/// reassuring default. That is the whole discipline: the plain-language layer is allowed to be
/// simpler than the data, and never allowed to be more confident than it.

/// Direction in the three words a reader actually wants, and never a fourth.
///
/// Mixed is a real answer, not a hedge. An asset above one average and below another has no
/// direction to report, and saying so is more useful than picking the one that reads better.
export function direction(pct: number | null | undefined): {
  word: "Up" | "Down" | "Flat" | "Not available";
  tone: "up" | "down" | "default";
} {
  if (pct == null || Number.isNaN(pct)) return { word: "Not available", tone: "default" };
  if (pct >= 0.25) return { word: "Up", tone: "up" };
  if (pct <= -0.25) return { word: "Down", tone: "down" };
  return { word: "Flat", tone: "default" };
}

/// A volume multiple as a sentence. The figure follows in brackets, it does not lead.
export function tradingWords(ratio: number | null | undefined): string | null {
  if (ratio == null || Number.isNaN(ratio)) return null;
  if (ratio >= 4) return `far more trading than usual (${ratio.toFixed(1)} times its own average)`;
  if (ratio >= 2) return `much more trading than usual (${ratio.toFixed(1)} times its own average)`;
  if (ratio >= 1.2) return `more trading than usual (${ratio.toFixed(1)} times its own average)`;
  if (ratio <= 0.6) return `less trading than usual (${ratio.toFixed(1)} times its own average)`;
  return `about as much trading as usual (${ratio.toFixed(1)} times its own average)`;
}

/// Where a price sits in a range, in words. The share follows in brackets.
export function positionWords(share: number | null | undefined): string | null {
  if (share == null || Number.isNaN(share)) return null;
  const pct = `${Math.round(share * 100)}%`;
  if (share >= 0.95) return `at the very top of the range it has traded in (${pct} of the way up)`;
  if (share >= 0.7) return `near the top of the range it has traded in (${pct} of the way up)`;
  if (share >= 0.3) return `in the middle of the range it has traded in (${pct} of the way up)`;
  if (share > 0.05) return `near the bottom of the range it has traded in (${pct} of the way up)`;
  return `at the very bottom of the range it has traded in (${pct} of the way up)`;
}

/// A historical share as a count, because "about 7 times out of 10" is a frequency and "70%" is
/// read as a promise. The denominator is kept so a reader can see how thin the sample is.
export function frequencyWords(
  positive: number | null | undefined,
  total: number | null | undefined,
): string | null {
  if (positive == null || total == null || total <= 0) return null;
  const outOfTen = Math.round((positive / total) * 10);
  return `in similar past cases this happened about ${outOfTen} times out of 10 (${positive} of ${total})`;
}

/// A robust score as a sentence. The score itself is a statistician's unit and never leads.
export function unusualWords(z: number | null | undefined): string | null {
  if (z == null || Number.isNaN(z)) return null;
  const size = Math.abs(z);
  if (size >= 5) return "a far bigger move than this asset normally makes";
  if (size >= 3) return "a much bigger move than this asset normally makes";
  if (size >= 2) return "a bigger move than this asset normally makes";
  return "a move within what this asset normally does";
}

/// What a setup state means, in the words the spec asks for, with the colour that goes with it.
export const SETUP_WORDS: Record<
  string,
  { label: string; plain: string; tone: "up" | "down" | "warn" | "default" }
> = {
  buy: {
    label: "Buy setup",
    plain: "The conditions this system looks for on the upside are all present.",
    tone: "up",
  },
  short: {
    label: "Short setup",
    plain: "The conditions this system looks for on the downside are all present.",
    tone: "down",
  },
  wait: {
    label: "Wait",
    plain: "The direction is clear but something it looks for is still missing.",
    tone: "warn",
  },
  none: {
    label: "No clear setup",
    plain: "There is no clear direction to read conditions against.",
    tone: "default",
  },
};

export const HORIZON_WORDS: Record<string, { label: string; window: string }> = {
  intraday: { label: "Today", window: "from five minute bars in the current and previous session" },
  swing: { label: "Next few weeks", window: "from daily closes over 20 and 50 sessions" },
  longer: { label: "Longer term", window: "from daily closes over 100 and 200 sessions" },
};

/// What a thesis status means for the reader, rather than for the state machine.
export const THESIS_WORDS: Record<string, { label: string; plain: string; tone: "up" | "down" | "warn" | "default" }> = {
  active: {
    label: "Still holds",
    plain: "Everything this view was based on is still true.",
    tone: "up",
  },
  weakening: {
    label: "Weakening",
    plain: "Something this view was based on has changed.",
    tone: "warn",
  },
  broken: {
    label: "Broken",
    plain: "The price passed the level that was named in advance as the point this stops being valid.",
    tone: "down",
  },
};

/// What an investigation found, as a status word rather than a flag.
export const FINDING_WORDS: Record<string, { label: string; tone: "up" | "warn" | "default" }> = {
  found: { label: "Found", tone: "up" },
  absent: { label: "Nothing there", tone: "default" },
  unavailable: { label: "Could not check", tone: "warn" },
};

/// The name of each thing an investigation checks, in plain words.
export const CHECK_WORDS: Record<string, string> = {
  news: "Company news",
  attribution: "How the move splits",
  peers: "Its industry",
  volume: "How much trading",
  calendar: "Dates ahead",
  graph: "Related names",
  analog: "Similar past days",
  intraday: "When in the day",
  product: "Linked products",
};

/// A target method in plain words, so the three rows read as three different questions.
export const METHOD_WORDS: Record<string, string> = {
  structure: "Where it stopped before",
  volatility: "How far it usually moves",
  analog: "What followed similar days",
};

/// Whether a set of target ranges disagree enough to be worth saying so out loud.
export function targetsDisagree(agreement: number | null | undefined): boolean {
  return agreement != null && agreement >= 0.5;
}

/// A reward-to-risk ratio as a sentence, with the figure kept.
export function rewardWords(ratio: number | null | undefined): string | null {
  if (ratio == null || Number.isNaN(ratio) || ratio <= 0) return null;
  if (ratio >= 3) return `about ${ratio.toFixed(1)} times as far to the target as to the invalidation`;
  if (ratio >= 1) return `about ${ratio.toFixed(1)} times as far up as down`;
  return `closer to the invalidation than to the target (${ratio.toFixed(1)} times)`;
}
