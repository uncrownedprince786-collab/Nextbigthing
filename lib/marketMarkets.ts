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
export type TimeframeName = "scalp" | "intraday" | "swing" | "position";

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
