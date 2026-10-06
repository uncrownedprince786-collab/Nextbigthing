
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


/// What an investigation found, as a status word rather than a flag.
/// What a recorded reason's status means, in a label and a sentence.
///
/// `ThesisBlock` held its own copy of this as a local `STATUS` map reading "reason intact" /
/// "reason weakening" / "reason broken", while this map said "Still holds" / "Weakening" /
/// "Broken" and added the sentence explaining each. Two vocabularies for one idea is the thing
/// rule 36 exists to stop, so the component now reads this and the local copy is gone. The
/// sentence is the part that was being lost: it used to appear only in the prose block above
/// the table, which the decision panel replaced.
export const THESIS_WORDS: Record<
  string,
  { label: string; plain: string; tone: "up" | "down" | "warn" | "default" }
> = {
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
    plain:
      "The price passed the stop price, which was named in advance as the point this read stops being right.",
    tone: "down",
  },
};

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
  if (ratio >= 3) return `about ${ratio.toFixed(1)} times as far to the target as to the stop price`;
  if (ratio >= 1) return `about ${ratio.toFixed(1)} times as far up as down`;
  return `closer to the stop price than to the target (${ratio.toFixed(1)} times)`;
}

/// ---------------------------------------------------------------------------------------
/// Simple read
///
/// Four short lines at the top of an asset or product page, built only from values the jobs
/// have already computed. It adds no source, no model and no claim: every sentence is a
/// restatement of a stored field, and the page below it still carries the same figure with
/// its source and as-of date attached.
///
/// The caution line is the one that earns its place. It is `null` unless something real is
/// there to say — a dated item inside the window, a condition pointing the other way, a news
/// reading that is thin or has not run. An always-present caution is wallpaper, and a reader
/// learns to skip it.
export type SimpleReadLines = {
  shows: string;
  grade: string;
  gradeWhy: string;
  caution: string | null;
  changes: string | null;
};


/// Product status in words, matching the group blurbs on /products.
export const PRODUCT_STATUS_WORDS: Record<
  string,
  { label: string; tone: "up" | "warn" | "default" }
> = {
  rising: { label: "Rising", tone: "up" },
  early: { label: "Early", tone: "warn" },
  flat: { label: "Flat", tone: "default" },
  unknown: { label: "No data", tone: "default" },
};

/// What a source's coverage status means to a reader, rather than to the audit job.
///
/// The four words matter separately: a source that answered but is late is a different fault
/// from one that answered thinly, and both are different from one that has stopped. Collapsing
/// them into "problem" would throw away the distinction the Coverage table exists to keep.
export const COVERAGE_WORDS: Record<
  string,
  { label: string; plain: string; tone: "up" | "down" | "warn" | "default" }
> = {
  healthy: {
    label: "Answering",
    plain: "This source is answering as often as expected.",
    tone: "up",
  },
  partial: {
    label: "Thin",
    plain: "It answered, but with far less than it usually sends, so treat its newest day as incomplete.",
    tone: "warn",
  },
  stale: {
    label: "Late",
    plain: "It has gone longer than expected without anything new. What is stored is still good; it is just older than it should be.",
    tone: "warn",
  },
  silent: {
    label: "Not answering",
    plain: "Nothing new has arrived for long enough that this should be read as a fault, not a quiet week.",
    tone: "down",
  },
};

/// How much information a cluster of headlines actually carries.
///
/// Items and publishers answer different questions: items is how many copies exist, and
/// publishers is whether the story travelled. One item from one publisher is a single report;
/// twenty items from two publishers is a syndicated release; four items from four publishers
/// is four newsrooms deciding the same thing was worth covering. Said in words rather than
/// left as two integers a reader has to interpret.
export function storyWords(items: number, publishers: number): string {
  if (items <= 1) return "a single report from one publisher";
  if (publishers <= 1) return `${items} items, all from one publisher, so one report repeated`;
  if (items >= publishers * 3) {
    return `${items} items but only ${publishers} publishers, which is the shape of a syndicated release rather than a developing story`;
  }
  if (items === publishers) return `${publishers} publishers, one item each, so ${publishers} separate pickups`;
  return `${items} items across ${publishers} publishers`;
}
