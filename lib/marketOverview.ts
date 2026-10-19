// The pure half of the market overview: stored rows in, five markets out.
//
// Kept out of lib/queries so it holds no database import and the test lane can run it directly
// under `node --test`. The query builds the row groups and hands them here; this decides which
// market each row belongs to and which market each industry is filed under. That decision is the
// defect the market explorer had — every crypto coin and every front-month future shown as a US
// listing — so it is the part worth testing on its own.

import { marketOf } from "./decisionInput.ts";
import { canonicalMarket, MARKET_LABELS, MARKET_ORDER, type MarketName } from "./marketMarkets.ts";

export interface AssetGroupRow {
  assetType: string;
  /// The industry's own `market` column, which is US/PK/FX only and never the whole story.
  market: string | null;
  n: number | bigint;
}
export interface DateGroupRow {
  assetType: string;
  market: string | null;
  newest: Date | string | null;
}
export interface IndustryCompositionRow {
  id: string;
  slug: string;
  name: string;
  /// The industry's own `market` column (US/PK/FX). Carried so a stock row is filed by its
  /// industry and not guessed; `marketOf` still reads crypto/commodity/forex off the instrument.
  market: string | null;
  assetType: string;
  n: number | bigint;
}

export interface MarketIndustryRow {
  id: string;
  slug: string;
  name: string;
  assets: number;
}
export interface MarketOverviewRow {
  market: MarketName;
  label: string;
  assets: number;
  industries: MarketIndustryRow[];
  newestClose: string | null;
  newestFactor: string | null;
  newestQuote: Date | null;
  predictions: number;
}

/// Which market an instrument trades in, per the one rule the model path uses.
export function marketKeyFor(assetType: string, industryMarket: string | null): MarketName | null {
  return canonicalMarket(
    marketOf({ assetType, industry: industryMarket ? { market: industryMarket } : null }),
  );
}

function dayOf(v: Date | string | null): string | null {
  if (!v) return null;
  const d = v instanceof Date ? v : new Date(v);
  return Number.isNaN(d.getTime()) ? String(v).slice(0, 10) : d.toISOString().slice(0, 10);
}

function maxDay(map: Map<MarketName, string>, key: MarketName, v: Date | string | null) {
  const day = dayOf(v);
  if (!day) return;
  const prev = map.get(key);
  if (!prev || day > prev) map.set(key, day);
}

export interface MarketOverviewInput {
  assetGroups: AssetGroupRow[];
  closeGroups: DateGroupRow[];
  factorGroups: DateGroupRow[];
  quoteGroups: DateGroupRow[];
  industryRows: IndustryCompositionRow[];
  predictionsByMarket: Map<string, number>;
}

/// Reduce stored groups to exactly the five markets, in the fixed order. A row whose market cannot
/// be classified is dropped rather than filed under a default, so an unclassifiable instrument
/// never inflates a market's count.
export function reduceMarketOverview(input: MarketOverviewInput): MarketOverviewRow[] {
  const assets = new Map<MarketName, number>();
  const newestClose = new Map<MarketName, string>();
  const newestFactor = new Map<MarketName, string>();
  const newestQuote = new Map<MarketName, Date>();
  const industries = new Map<MarketName, MarketIndustryRow[]>();
  const industryVotes = new Map<
    string,
    { row: Omit<MarketIndustryRow, "assets">; assets: number; votes: Map<MarketName, number> }
  >();

  for (const g of input.assetGroups) {
    const key = marketKeyFor(g.assetType, g.market);
    if (!key) continue;
    assets.set(key, (assets.get(key) ?? 0) + Number(g.n));
  }
  for (const g of input.closeGroups) {
    const key = marketKeyFor(g.assetType, g.market);
    if (key) maxDay(newestClose, key, g.newest);
  }
  for (const g of input.factorGroups) {
    const key = marketKeyFor(g.assetType, g.market);
    if (key) maxDay(newestFactor, key, g.newest);
  }
  for (const g of input.quoteGroups) {
    const key = marketKeyFor(g.assetType, g.market);
    if (!key || !g.newest) continue;
    const d = g.newest instanceof Date ? g.newest : new Date(g.newest);
    if (Number.isNaN(d.getTime())) continue;
    const prev = newestQuote.get(key);
    if (!prev || d > prev) newestQuote.set(key, d);
  }

  // An industry is filed under the market most of its instruments actually trade in. Standalone
  // instruments keep the industry's own market column; `crypto`/`commodity`/`forex` are read off
  // the instrument by `marketOf`, so an industry holding them votes for that market.
  for (const r of input.industryRows) {
    const market = marketKeyFor(r.assetType, r.market);
    if (!market) continue;
    const entry = industryVotes.get(r.id) ?? {
      row: { id: r.id, slug: r.slug, name: r.name },
      assets: 0,
      votes: new Map<MarketName, number>(),
    };
    entry.assets += Number(r.n);
    entry.votes.set(market, (entry.votes.get(market) ?? 0) + Number(r.n));
    industryVotes.set(r.id, entry);
  }
  for (const entry of industryVotes.values()) {
    const dominant = [...entry.votes.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    if (!dominant) continue;
    const list = industries.get(dominant) ?? [];
    list.push({ ...entry.row, assets: entry.assets });
    industries.set(dominant, list);
  }

  const predictions = new Map<MarketName, number>();
  for (const [market, n] of input.predictionsByMarket) {
    const key = canonicalMarket(market);
    if (key) predictions.set(key, (predictions.get(key) ?? 0) + n);
  }

  return MARKET_ORDER.map((market) => ({
    market,
    label: MARKET_LABELS[market],
    assets: assets.get(market) ?? 0,
    industries: (industries.get(market) ?? []).sort((a, b) => a.name.localeCompare(b.name)),
    newestClose: newestClose.get(market) ?? null,
    newestFactor: newestFactor.get(market) ?? null,
    newestQuote: newestQuote.get(market) ?? null,
    predictions: predictions.get(market) ?? 0,
  }));
}
