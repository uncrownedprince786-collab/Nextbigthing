// Has this coin, specifically, earned a direction on this horizon?
//
// Every other accuracy in this repository is a **pool** number: one figure measured over 140
// coins at once. That is the right way to score a pooled model and the wrong way to decide what
// to put in front of a reader, because it says nothing about the coin they are looking at. A lane
// at 53.7% could be 60% on the liquid majors and a coin flip on the small caps, and without this
// file the page would print the same sentence over both.
//
// So `tools/research/crypto_certify.py` measures each coin alone on the holdout and applies the
// five lane gates to it individually -- beats its **own** majority, calls both directions,
// day-blocked bootstrap clear of zero, four of five walk-forward blocks, and at least 500 called
// rows. This reads that verdict.
//
// **A coin that is not certified is served no direction on that lane at all.** Not a weaker one,
// not a hedged one, not one with a warning under it. The whole argument for showing a direction
// is that somebody checked it, and for an uncertified coin nobody has -- so there is nothing
// honest to show, and a blank is the honest thing.
//
// Absent file, or a lane the sweep has not covered yet, reads as `unknown` rather than as a pass
// or a fail. Those are three different states and collapsing them is how a missing measurement
// starts looking like a good one.

import raw from "@/data/foundation/dataset/crypto_certified.json";
import type { HorizonKey } from "@/lib/cryptoHorizons";
import { universeCoin } from "@/lib/cryptoUniverse";

export interface CoinVerdict {
  /// Rows of the holdout this coin contributed, and how many cleared the lane's floor.
  testRows: number;
  called: number;
  coverage: number;
  /// The margin a call had to clear. Zero means the lane speaks on every bar.
  convictionFloor: number;
  /// Measured on this coin's called rows alone. Null when there were too few to report.
  accuracy: number | null;
  /// The larger class among this coin's called rows -- what `accuracy` had to beat. A coin that
  /// rose 58% of the time in the test window needed to beat 58%, not 50%.
  ownMajority?: number;
  edgeOverMajority?: number;
  upShareCalled?: number;
  bootstrapCi95?: [number, number];
  walkForward?: string;
  gates?: Record<string, boolean>;
  certified: boolean;
  why: string | null;
}

interface Doc {
  generatedAt: string;
  minCalledRows: number;
  scoreStride: number;
  gates: Record<string, string>;
  certifiedByLane: Record<string, string[]>;
  coins: Record<string, Record<string, CoinVerdict>>;
}

const DOC = raw as unknown as Doc;

export const CERTIFIED_AT = DOC.generatedAt;
export const CERTIFY_GATES = DOC.gates;
export const CERTIFY_MIN_CALLED = DOC.minCalledRows;

/// `null` when this coin and lane have not been measured, which is not the same as failing.
/// The verdict file keys on the venue instrument -- LINKUSDT -- and the site routes on the slug,
/// link-chainlink. The two are not related by string surgery and an earlier version of this
/// function pretended they were: it uppercased the slug and appended USDT, producing
/// LINK-CHAINLINKUSDT, which matches nothing.
///
/// **That silently disabled the entire gate.** Every coin resolved to no verdict, every verdict
/// read as "not measured", and once the lane had been swept the serving path refused every coin
/// on the site -- each page printing "this coin was not measured on its own in the last sweep"
/// about coins that had in fact been measured and passed. The lookup failed, not the model.
///
/// The universe is the one place that knows both, so it does the translation. A slug it does not
/// hold has no instrument and therefore no verdict, which is a genuine absence rather than a
/// mistyped key.
function symbolFor(slug: string): string | null {
  const coin = universeCoin(slug);
  if (!coin) return null;
  // Prefer the venue instrument the corpus is keyed by; fall back to the bare ticker, which is
  // how the research tools name a coin when they build the pool from the bar cache.
  const inst = coin.on?.binance ?? coin.on?.mexc ?? null;
  if (inst) return inst.toUpperCase();
  return coin.ticker ? `${coin.ticker.toUpperCase()}USDT` : null;
}

export function verdictFor(
  family: string,
  slug: string,
  horizon: HorizonKey,
): CoinVerdict | null {
  const symbol = symbolFor(slug);
  if (!symbol) return null;
  return DOC.coins?.[symbol]?.[`${family}:${horizon}`] ?? null;
}

/// The floor this coin's own calls must clear, or null when it has no measured one.
///
/// **A pooled floor silences the coins a reader most wants.** The five-minute lane's floor is
/// 0.100 and the fifteen-minute lane's is 0.075, both chosen over 140 coins at once -- and every
/// one of the liquid majors sits below them: Bitcoin's own floor is 0.050, Ethereum's 0.050,
/// Solana's 0.050. That is not the model being worse on them, it is what a more efficient market
/// looks like. A major's probabilities cluster nearer a half because its price already reflects
/// more, while a volatile small cap throws wide margins readily, and a single threshold tuned on
/// the mixture admits the small caps and mutes the majors.
///
/// So each coin is served at the floor chosen on **its own validation rows** and measured once on
/// its own test rows -- the same discipline the lane floor follows, at the resolution the
/// decision is actually made at. The accuracy printed beside a call is then the accuracy measured
/// for that coin at that floor, rather than the pool's at a floor this coin never meets.
export function floorFor(
  family: string,
  slug: string,
  horizon: HorizonKey,
): { floor: number; accuracy: number | null; coverage: number } | null {
  const v = verdictFor(family, slug, horizon);
  if (!v || !v.certified || typeof v.convictionFloor !== "number") return null;
  return { floor: v.convictionFloor, accuracy: v.accuracy, coverage: v.coverage };
}

export type CertificationState = "certified" | "refused" | "unmeasured";

/// Has the sweep covered this lane at all?
///
/// This is what decides whether an unmeasured coin is withheld or served. Before the sweep has
/// run for a lane there is no verdict for *any* coin on it, and refusing them all would blank
/// the board over a measurement that has not happened yet -- a worse failure than the one it
/// prevents, and one caused by us rather than by the coin. Once the sweep has covered the lane,
/// a coin with no verdict is a real absence and is withheld.
///
/// So the gate arms itself when the evidence to enforce it exists, with no flag to set and
/// nothing to remember to turn on.
export function laneMeasured(family: string, horizon: HorizonKey): boolean {
  const key = `${family}:${horizon}`;
  if (DOC.certifiedByLane?.[key]?.length) return true;
  // A lane where every coin failed still counts as measured: the absence of certified coins is
  // the finding, not a reason to fall back to serving all of them.
  return Object.values(DOC.coins ?? {}).some((byLane) => key in byLane);
}

export function certificationOf(
  family: string,
  slug: string,
  horizon: HorizonKey,
): { state: CertificationState; verdict: CoinVerdict | null } {
  const verdict = verdictFor(family, slug, horizon);
  if (!verdict) return { state: "unmeasured", verdict: null };
  return { state: verdict.certified ? "certified" : "refused", verdict };
}

/// Every coin certified on a lane, for the list the reader is owed: these are the coins the brain
/// has actually been checked on, as opposed to the ones it merely has a model for.
export function certifiedCoins(family: string, horizon: HorizonKey): string[] {
    return DOC.certifiedByLane?.[`${family}:${horizon}`] ?? [];
}

/// Why a refused coin was refused, in words a reader can act on rather than gate names.
export function refusalReason(v: CoinVerdict): string {
  if (v.accuracy === null) {
    return v.why ?? `too few measured calls to judge this coin (${v.called})`;
  }
  const g = v.gates ?? {};
  const parts: string[] = [];
  if (g.aboveOwnMajority === false && v.ownMajority !== undefined) {
    parts.push(
      `it was right ${(v.accuracy * 100).toFixed(1)}% of the time while simply naming the ` +
      `commoner direction would have been right ${(v.ownMajority * 100).toFixed(1)}%`,
    );
  }
  if (g.bothDirectionsCalled === false && v.upShareCalled !== undefined) {
    const share = Math.max(v.upShareCalled, 1 - v.upShareCalled);
    parts.push(`it said the same thing on ${(share * 100).toFixed(0)}% of its calls`);
  }
  if (g.bootstrapExcludesZero === false) {
    parts.push("its edge is inside the range that resampling the days could produce by chance");
  }
  if (g.walkForwardMajority === false && v.walkForward) {
    parts.push(`it beat its own base rate in only ${v.walkForward} stretches of the holdout`);
  }
  if (g.enoughCalledRows === false) {
    parts.push(`it produced only ${v.called} measurable calls`);
  }
  return parts.length ? parts.join("; ") : (v.why ?? "it did not pass its gates");
}
