import { count, pct, price } from "@/lib/format";

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

/// How close a scheduled date has to be before it is worth a caution. Matches the window
/// jobs/setup.py already treats as context for a swing read, so the page and the job agree.
const DATE_SOON_DAYS = 14;
/// Below this many distinct stories the news reading is reported as thin rather than used.
/// Same floor jobs/human.py labels `thin`.
const THIN_STORIES = 8;

/// Whole days from today to `when`. Exported so a page never calls `Date.now()` inside
/// render, which the react-hooks purity rule rejects.
export function daysUntil(when: Date | string): number {
  const target = typeof when === "string" ? new Date(when) : when;
  const today = new Date();
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/// The plain-language read for one asset.
///
/// `horizons` is expected in the order the page shows them. The line describes the horizon a
/// reader is most likely to act on: the first with a directional state, or the first of all
/// when none is directional. Picking the "best" state instead would make the summary
/// disagree with the three cards beneath it.
export function assetSimpleRead(input: {
  name: string;
  dayPct: number | null;
  horizons: {
    horizon: string;
    state: string;
    headline: string;
    against: string;
    missing: string;
    confidence: string;
    confidenceNote: string | null;
    invalidateLevel: number | null;
    invalidateNote: string | null;
  }[];
  thesis: { status: string; reason: string } | null;
  investigation: { headline: string; pointsToward: string } | null;
  discussion: { items: number; recentStories: number; catalyst: boolean } | null;
  nextDated: { name: string; date: Date | string } | null;
  currency: string;
}): SimpleReadLines {
  const primary =
    input.horizons.find((h) => h.state === "buy" || h.state === "short") ?? input.horizons[0];

  // --- what the data shows
  let shows: string;
  if (input.investigation) {
    shows = `${input.investigation.headline} ${input.investigation.pointsToward}`;
  } else if (primary) {
    const words = SETUP_WORDS[primary.state] ?? SETUP_WORDS.none;
    const label = HORIZON_WORDS[primary.horizon]?.label ?? primary.horizon;
    const move =
      input.dayPct != null
        ? `${input.name} is ${direction(input.dayPct).word.toLowerCase()} ${pct(input.dayPct, 1)} on its latest stored day`
        : `${input.name} has no stored move for its latest day`;
    shows = `${move}, and on the ${label.toLowerCase()} view the reading is "${words.label.toLowerCase()}": ${words.plain.toLowerCase()}`;
  } else {
    shows = `No condition read is stored for ${input.name} yet, so nothing is claimed about it.`;
  }

  // --- confidence, and why in a few words
  const grade = primary?.confidence ?? "none";
  let gradeWhy: string;
  if (!primary) {
    gradeWhy = "nothing has been computed to grade";
  } else if (primary.confidenceNote) {
    // The note's first clause is the reason; the rest repeats the counts shown below.
    gradeWhy = primary.confidenceNote.split(";")[0].replace(/^./, (c) => c.toLowerCase());
  } else if (grade === "high") {
    gradeWhy = "every condition it tested was available and none disagreed";
  } else {
    gradeWhy = "graded on how many conditions were measurable, not on the direction";
  }

  // --- the one caution that is actually true right now, in order of how much it matters
  const against = primary && primary.against !== "none"
    ? primary.against.split(" | ").filter(Boolean)
    : [];
  const missing = primary && primary.missing !== "none"
    ? primary.missing.split(" | ").filter(Boolean)
    : [];

  let caution: string | null = null;
  if (input.thesis?.status === "broken") {
    caution = "the level this view named in advance has already been passed";
  } else if (input.thesis?.status === "weakening") {
    caution = "something this view was based on has changed since it was recorded";
  } else if (input.nextDated && daysUntil(input.nextDated.date) <= DATE_SOON_DAYS) {
    const d = daysUntil(input.nextDated.date);
    caution = `${input.nextDated.name} is ${d <= 0 ? "due now" : `${d} day${d === 1 ? "" : "s"} away`}, which can move the price for reasons unrelated to the conditions above`;
  } else if (!input.discussion) {
    caution = "news coverage has not been checked for this asset yet";
  } else if (input.discussion.recentStories < THIN_STORIES) {
    const n = input.discussion.recentStories;
    caution = `news coverage is thin — ${count(n)} distinct ${n === 1 ? "story" : "stories"} in the recent window, which is too few to read a direction from`;
  } else if (against.length) {
    caution = against[0];
  } else if (missing.length) {
    caution = `one input could not be checked: ${missing[0]}`;
  }

  // --- what would change the view
  let changes: string | null = null;
  if (primary?.invalidateLevel != null) {
    changes = `${primary.invalidateNote ?? "a close past the level recorded with this read"} (${price(primary.invalidateLevel, input.currency)})`;
  } else if (primary) {
    changes = "a clear direction appearing in the conditions below; there is none to invalidate yet";
  }

  return { shows, grade, gradeWhy, caution, changes };
}

/// The plain-language read for one product.
///
/// The thresholds are quoted from jobs/analysis.py rather than paraphrased, because "rising"
/// is reached two different ways and describing it as unanimous would claim more agreement
/// than the group holds.
export function productSimpleRead(input: {
  name: string;
  status: string;
  demandScore: number | null;
  confidence: string;
  confidenceNote: string | null;
  sourcesAnswered: number;
  sourcesAgree: number;
  discussion: { items: number; recentStories: number; catalyst: boolean } | null;
}): SimpleReadLines {
  const words = PRODUCT_STATUS_WORDS[input.status] ?? PRODUCT_STATUS_WORDS.unknown;

  const shows =
    input.demandScore != null && input.sourcesAnswered > 0
      ? `Attention on ${input.name} is ${words.label.toLowerCase()}: the ${input.sourcesAnswered} source${input.sourcesAnswered === 1 ? "" : "s"} that answered average ${pct(input.demandScore)} over their own short windows.`
      : `No source answered for ${input.name}, so nothing is claimed about attention on it.`;

  const grade = input.confidence;
  const gradeWhy =
    input.sourcesAnswered > 0
      ? `${input.sourcesAnswered} of 5 sources answered and ${input.sourcesAgree} point the same way`
      : "no source answered, so there is nothing to grade";

  let caution: string | null = null;
  if (input.sourcesAnswered === 0) {
    caution = "no source answered in this window";
  } else if (input.sourcesAnswered === 1) {
    caution = "this rests on a single source, which is one reading rather than agreement";
  } else if (input.sourcesAgree < input.sourcesAnswered) {
    caution = `the sources disagree — ${input.sourcesAgree} of ${input.sourcesAnswered} point the same way`;
  } else if (input.discussion && input.discussion.recentStories < THIN_STORIES) {
    const n = input.discussion.recentStories;
    caution = `news coverage is thin — ${count(n)} distinct ${n === 1 ? "story" : "stories"} in the recent window`;
  }

  const changes =
    input.status === "rising"
      ? "it leaves this group if the average falls below +5% with every source still up, or below +10% on its own"
      : input.status === "early"
        ? "it reaches rising if every answering source points up and the average passes +5%"
        : "a source changing direction in the next weekly run; this is a short-window average and one source moves it";

  return { shows, grade, gradeWhy, caution, changes };
}

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
