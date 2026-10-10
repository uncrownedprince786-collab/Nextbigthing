// The product decision, and the links that make the next click obvious.
//
// Same shape as lib/decision.ts and for the same reason: pure, no database, no clock, so the rules
// are testable as rules. A product decision answers a different question from an asset decision —
// not "long or short" but "is anyone paying attention yet, and where do I go to check".
//
// What this will not do is imply a sales figure. Nothing in this database counts a sale: the demand
// score is built from Google Trends, Wikipedia pageviews, Reddit, Hacker News and Google News
// article counts, and `MarketplaceItem` is a bestseller *rank*, never a volume. So the output is an
// attention reading plus somewhere to look, and the risk line says which of those it is.
//
//   attention     from Product.status, the job's own reading
//   sell interest RISING + sources that agree -> YES LOOK; too few sources -> NO CLEAR SIGNAL
//   where         deterministic search URLs built from the stored term
//   geo           ProductRegion lists, or an explicit "geo not stored yet"

export type Attention = "RISING" | "EARLY" | "FLAT";
export type SellInterest = "YES LOOK" | "NOT YET" | "NO CLEAR SIGNAL";

/// Below this many of the five demand sources answering, the score is one source wearing a number,
/// and the panel says so rather than grading it. `jobs/nbt.py` scores five sources; `sourcesAgree`
/// counts how many pointed the same way.
export const MIN_SOURCES_TO_JUDGE = 2;

export interface ProductDecisionInput {
  name: string;
  /// `Product.trendsTerm` when set, else the name. Empty `trendsTerm` means no Trends data exists,
  /// but the search links still work off the name.
  term: string;
  /// `Product.status`: "rising" | "early" | "flat" | "unknown".
  status: string;
  demandScore: number | null;
  /// How many of the five possible demand sources returned a usable value.
  sourcesAnswered: number;
  sourcesAgree: number;
  /// `Product.confidence`: "high" | "medium" | "low" | "none".
  confidence: string;
  /// Whether any `ProductRegion` rows are stored, and the places if so.
  regions: { name: string; scope: string; geo: string }[];
  /// Whether any marketplace listing matched this product's title.
  marketplaceItems: number;
}

export interface WhereToCheck {
  label: string;
  url: string;
  /// Why this link is worth opening, in plain words.
  why: string;
}

export interface ProductDecision {
  attention: Attention | null;
  /// Set when `attention` is null, naming what is absent instead of showing a blank.
  attentionMissing: string | null;
  sellInterest: SellInterest;
  why: string[];
  where: WhereToCheck[];
  /// The stored places, or null when nothing is stored.
  geo: string | null;
  confidence: string;
  /// Exactly one risk line. The single most likely way this read is wrong.
  risk: string;
  missing: string[];
}

function q(term: string): string {
  return encodeURIComponent(term.trim());
}

/// The links. Built from the term alone, so they work for every product whether or not a single
/// demand source answered — which is the point: when the data is thin, the next click matters more.
///
/// Daraz is included because this site covers PSX names and a Pakistani reader is a real reader
/// here; Facebook Marketplace is a search URL rather than an API because there is no free one.
export function whereToCheck(term: string): WhereToCheck[] {
  const t = q(term);
  return [
    {
      label: "Google Trends",
      url: `https://trends.google.com/trends/explore?q=${t}`,
      why: "Whether search interest is rising or you are late.",
    },
    {
      label: "Amazon search",
      url: `https://www.amazon.com/s?k=${t}`,
      why: "How many sellers are already on it, and at what price.",
    },
    {
      label: "eBay search",
      url: `https://www.ebay.com/sch/i.html?_nkw=${t}`,
      why: "What used units actually sell for, which is the honest floor.",
    },
    {
      label: "Daraz search",
      url: `https://www.daraz.pk/catalog/?q=${t}`,
      why: "Whether it has reached Pakistan yet, and at what markup.",
    },
    {
      label: "Facebook Marketplace",
      url: `https://www.facebook.com/marketplace/search/?query=${t}`,
      why: "Local demand near you, which no stored source covers.",
    },
  ];
}

function attentionOf(status: string): Attention | null {
  switch (status) {
    case "rising":
      return "RISING";
    case "early":
      return "EARLY";
    case "flat":
      return "FLAT";
    default:
      return null;
  }
}

/// The one risk line. Ordered worst first, because the reader gets one.
function riskLine(input: ProductDecisionInput, attention: Attention | null): string {
  if (input.sourcesAnswered === 0) {
    return "No demand source answered, so there is nothing behind this reading yet.";
  }
  if (input.sourcesAnswered === 1) {
    return "A single source carries the whole score, so one quiet week would change it.";
  }
  if (input.sourcesAgree < input.sourcesAnswered) {
    return `The sources disagree: ${input.sourcesAgree} of ${input.sourcesAnswered} point the same way.`;
  }
  if (attention === "RISING") {
    return "Rising attention is not rising sales; nothing here counts a single sale.";
  }
  return "Attention can move before price does, and it can move back.";
}

export function decideProduct(input: ProductDecisionInput): ProductDecision {
  const attention = attentionOf(input.status);
  const where = whereToCheck(input.term || input.name);
  const missing: string[] = [];

  if (attention === null) {
    missing.push(`Attention has not been measured for ${input.name} yet.`);
  }
  if (input.regions.length === 0) {
    missing.push("Geography not measured yet, so no country or region is known.");
  }
  if (input.marketplaceItems === 0) {
    missing.push("No marketplace listing matched this product, so rank is unknown.");
  }

  // Too few sources is its own answer. Grading a score that one source produced is how a panel
  // tells somebody to spend money on a single quiet API.
  if (input.sourcesAnswered < MIN_SOURCES_TO_JUDGE) {
    return {
      attention,
      attentionMissing: attention === null ? `No attention reading stored for ${input.name}.` : null,
      sellInterest: "NO CLEAR SIGNAL",
      why: [
        input.sourcesAnswered === 0
          ? "No demand source answered for this product."
          : "Only one demand source answered.",
        "Not enough to say whether anyone is looking.",
      ],
      where,
      geo: null,
      confidence: input.confidence,
      risk: riskLine(input, attention),
      missing,
    };
  }

  const geo =
    input.regions.length > 0
      ? input.regions
          .slice(0, 3)
          .map((r) => r.name)
          .join(", ")
      : null;

  const agreeing = input.sourcesAgree >= MIN_SOURCES_TO_JUDGE;
  const graded = input.confidence !== "low" && input.confidence !== "none";

  if (attention === "RISING" && agreeing && graded) {
    return {
      attention,
      attentionMissing: null,
      sellInterest: "YES LOOK",
      why: [
        `Attention is rising and ${input.sourcesAgree} of ${input.sourcesAnswered} sources agree.`,
        "Worth opening the links below before the price moves.",
      ],
      where,
      geo,
      confidence: input.confidence,
      risk: riskLine(input, attention),
      missing,
    };
  }

  return {
    attention,
    attentionMissing: attention === null ? `No attention reading stored for ${input.name}.` : null,
    sellInterest: "NOT YET",
    why: [
      attention === "RISING"
        ? "Attention is rising but the evidence behind it is weak."
        : `Attention reads ${attention === null ? "unmeasured" : attention.toLowerCase()}.`,
      "Check again rather than acting on it.",
    ],
    where,
    geo,
    confidence: input.confidence,
    risk: riskLine(input, attention),
    missing,
  };
}
