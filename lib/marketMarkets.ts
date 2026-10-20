// The five markets, named once, so every screen and every reader labels them the same way.
//
// This is a separate file from lib/marketCapability on purpose. The capability contract is read
// from a JSON artifact the research tools write; this file is the vocabulary, holds no data and no
// alias-imported JSON, so a pure module (and the test lane, which runs under `node --test` with no
// bundler) can import it without pulling in the artifact or the database.
//
// Two vocabularies name the same markets and must not be shown as five-plus-two. The site's own
// `marketOf` (lib/decisionInput) says `PSX` for the Karachi market and `US` for the American one;
// the research tools say `PK`. `canonicalMarket` is the single place they are reconciled.

export type MarketName = "US" | "PK" | "FX" | "Commodity" | "Crypto";
export type TimeframeName = "scalp" | "intraday" | "short" | "swing" | "position";

/// Fixed reading order for the five markets, so every screen lists them the same way.
export const MARKET_ORDER: MarketName[] = ["US", "PK", "FX", "Commodity", "Crypto"];

/// How a market is named to a reader.
export const MARKET_LABELS: Record<MarketName, string> = {
  US: "United States",
  PK: "Pakistan (PSX)",
  FX: "Foreign exchange",
  Commodity: "Commodities",
  Crypto: "Crypto",
};

/// Map the site's market words and the research words onto the one vocabulary. `PSX` and `PK` are
/// the same exchange and must not read as two markets. Anything unknown is null, which the caller
/// renders as "not classified" rather than guessing a group.
export function canonicalMarket(siteMarket: string | null | undefined): MarketName | null {
  switch (siteMarket) {
    case "US":
      return "US";
    case "PK":
    case "PSX":
      return "PK";
    case "FX":
      return "FX";
    case "Commodity":
      return "Commodity";
    case "Crypto":
      return "Crypto";
    default:
      return null;
  }
}

/// The trading styles, shortest first, and how many sessions each is judged over.
///
/// These numbers are not a presentation choice: they are `shadow_markets.STRATEGY_SESSIONS`, the
/// same map the predictor stamps on a row and the scorer grades against. Restating them here would
/// let a screen offer "weekly" while the pipeline recorded something else, so the two are kept
/// equal by `tests/marketMarkets.test.ts`, which reads the research artifact and fails if they
/// drift.
///
/// `scalp` is 0 because it is a claim about minutes, which daily closes cannot order. It appears
/// in the list so a reader can see it was considered and refused, rather than wondering why
/// scalping is missing.
export const TIMEFRAME_ORDER: TimeframeName[] = [
  "scalp", "intraday", "short", "swing", "position",
];

export const TIMEFRAME_SESSIONS: Record<TimeframeName, number> = {
  scalp: 0,
  intraday: 1,
  short: 5,
  swing: 20,
  position: 60,
};

/// How a style is named to a reader, with the horizon it implies rather than a trading slogan.
export const TIMEFRAME_LABELS: Record<TimeframeName, string> = {
  scalp: "Scalp",
  intraday: "Intraday",
  short: "Short swing",
  swing: "Swing",
  position: "Position",
};
