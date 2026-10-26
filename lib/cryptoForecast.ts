// One forecast, end to end: the horizon a reader picked, the bars behind it, the model that was
// licensed to answer, and the direction -- or the specific reason there is not one.
//
// Everything the page needs to render is in the returned value, including every refusal, because
// the refusals are the part that was previously wrong. "No direction" covered an untested horizon,
// a tested-and-failed one, a coin no venue serves, a venue outage and a gap in the last twenty
// minutes of bars, and a reader could not tell which of those they were looking at. Each is now a
// distinct `kind` with its own sentence.
//
// This module runs the model. That is a deliberate exception to brain.md rule 5 -- the web layer
// reads rows, it does not run models -- and the exception is argued in `lib/cryptoModel.ts`: a
// precomputed five-minute forecast is stale before the page renders. The auditability the rule
// protects is preserved by `lib/forecastStore.ts`, which writes down exactly the forecast that was
// shown, keyed on the bar it was read from, for the scorer to grade later.

import models from "@/data/foundation/dataset/crypto_models.json";
import { windowFor, type BarWindow } from "@/lib/cryptoBars";
import { HORIZONS, maturesAt, type Horizon, type HorizonKey } from "@/lib/cryptoHorizons";
import { accuracyAtMargin, laneFor, servingLane, speaks, type Lane } from "@/lib/cryptoLanes";
import { assertSchema, probabilityUp, wantsContext, type Artifact } from "@/lib/cryptoModel";
import { contextAt, CONTEXT_FEATURES } from "@/lib/marketContext";
import { featuresAt, FEATURES, contiguous, WARMUP } from "@/lib/intradayFeatures";
import { levelsFor, type Levels } from "@/lib/cryptoLevels";
import {
  certificationOf,
  floorFor,
  laneMeasured,
  refusalReason,
  type CoinVerdict,
} from "@/lib/cryptoCertified";
import { hasIntradaySource, instrumentsFor, venueRowFor } from "@/lib/cryptoVenues";

const MODELS = models as unknown as Record<string, Artifact>;

/// The coin whose bars are the market factor. Mirrors `crypto_matrix.MARKET_SYMBOL`.
const MARKET_SLUG = "btc-bitcoin";

export type Forecast =
  | {
      kind: "direction";
      horizon: Horizon;
      lane: Lane;
      direction: "UP" | "DOWN";
      /// P(UP) from the artifact. Printed as a margin, never as a precision claim.
      probUp: number;
      confidence: "LOW" | "MEDIUM";
      /// How far from even the probability is, and whether that clears the lane's own floor.
      ///
      /// **Every window now gets a direction.** The model is binary and its output is a sign;
      /// withholding that sign on the bars it is least sure about was the honest *presentation*
      /// of a thin edge, and it is not what this is for -- a direction you cannot get when the
      /// model is unsure is a direction you cannot plan around. So the sign is always printed and
      /// the uncertainty is attached to it instead of replacing it: `strong` is a call that
      /// cleared the floor the holdout measured, `weak` is one that did not, and each carries the
      /// accuracy measured on its own band so the two are never read as the same claim.
      /// Null on a lane with no measured floor. There is no strong/weak banding to report
      /// there, and defaulting to "strong" labelled every `crypto d20` call as the model's best
      /// -- a claim nothing measured. An absence is printed as an absence.
      strength: "strong" | "weak" | null;
      margin: number;
      floor: number;
      /// How often a call in this confidence band was right on the test fold, if the band held
      /// enough rows to say. Null is an absence, not a zero.
      measured: { accuracy: number; coverage: number; rows: number } | null;
      /// Where to act, where to be wrong, and where to take it off -- sized from the coin's own
      /// recent range. Null when the window has no measured level table.
      levels: Levels | null;
      referencePrice: number;
      asOf: Date;
      maturesAt: Date;
      window: BarWindow;
      features: number[];
      /// What the per-coin sweep found about **this coin** on this lane, as opposed to the pool.
      /// Always `certified` on a served direction -- the other two states do not get here -- but
      /// carried so the page can print the coin's own measured rate instead of the pool's.
      certification: CoinVerdict;
    }
  | { kind: "no-model"; horizon: Horizon; why: string }
  | { kind: "refused"; horizon: Horizon; lane: Lane; why: string }
  /// The lane passed its gates over the pool, but **this coin** did not pass them on its own.
  ///
  /// A separate kind from `refused` because the two are different facts and a reader deserves to
  /// know which: `refused` means the brain cannot read this horizon for anybody, `uncertified`
  /// means it can, but not here. Nothing is shown either way -- a direction nobody checked on
  /// this coin is a guess with a confident font, and that is the one thing this repository is for
  /// not printing.
  | {
      kind: "uncertified";
      horizon: Horizon;
      lane: Lane;
      why: string;
      verdict: CoinVerdict | null;
      /// True when the sweep has simply not covered this coin yet, which is not a failure. An
      /// unmeasured coin and a measured-and-rejected one must never read as the same thing.
      unmeasured: boolean;
    }
  | { kind: "no-source"; horizon: Horizon; why: string }
  | { kind: "data"; horizon: Horizon; lane: Lane; why: string; tried: { venue: string; outcome: string }[] }
  | { kind: "error"; horizon: Horizon; why: string };

/// Which model answers, if any. Separate from `servingLane` because a lane can be licensed while
/// its weights are absent from the bundle -- that is a build fault, and it must read as one rather
/// than as a market with no signal.
function artifactFor(lane: Lane): Artifact | null {
  return MODELS[`${lane.family}:${lane.horizon}`] ?? null;
}

/// Everything a page needs about one coin and one horizon.
///
/// Never throws: every failure is a `kind` the caller renders. A thrown error on a page that is
/// mostly about something else would take the whole asset page down over a venue timeout.
export async function forecastFor(
  slug: string,
  key: HorizonKey,
  nowMs: number = Date.now(),
): Promise<Forecast> {
  const horizon = HORIZONS[key];
  const laneAt = servingLane(slug, key);
  if (!laneAt) {
    return {
      kind: "no-model",
      horizon,
      why: `no model has been fitted for crypto over ${horizon.label.toLowerCase()}`,
    };
  }
  if (!laneAt.servable) {
    return { kind: "refused", horizon, lane: laneAt, why: laneAt.why ?? "it did not pass its gates" };
  }
  // The lane passing over 140 coins does not mean it passes on this one. Checked before any bars
  // are fetched, because a coin we will not speak about is not worth a venue round trip.
  // Where the coin's own lane refuses it, try the pooled lane before giving up.
  //
  // **A coin can be refused on one model and certified on another, and the first routing only
  // ever asked one.** DOT is refused on dot:m15 and certified on crypto:m15 at 59.82%; SUI is
  // refused on sui:m15 and certified on crypto:m15 at 54.53%. Both were being told no by a
  // model while a model that reads them sat unused one lane over.
  //
  // The pooled lane is the only alternative tried, and only when it is itself servable and
  // gated. A coin is never handed a third coin's model to find a yes -- that would be shopping
  // for a verdict rather than using the one that fits.
  let lane = laneAt;
  let cert = certificationOf(lane.family, slug, key);
  if (laneMeasured(lane.family, key) && cert.state !== "certified" && lane.family !== "crypto") {
    const pooled = laneFor("crypto", key);
    if (pooled?.servable && pooled.conviction) {
      const pooledCert = certificationOf("crypto", slug, key);
      if (pooledCert.state === "certified") {
        lane = pooled;
        cert = pooledCert;
      }
    }
  }
  if (laneMeasured(lane.family, key) && cert.state !== "certified") {
    return {
      kind: "uncertified",
      horizon,
      lane,
      verdict: cert.verdict,
      unmeasured: cert.state === "unmeasured",
      why: cert.verdict
        ? refusalReason(cert.verdict)
        : "this coin was not measured on its own in the last sweep",
    };
  }
  if (!hasIntradaySource(slug)) {
    const row = venueRowFor(slug);
    return {
      kind: "no-source",
      horizon,
      why: row?.why ?? "no venue in the chain lists this coin, so there are no bars to read",
    };
  }
  const artifact = artifactFor(lane);
  if (!artifact) {
    return {
      kind: "error",
      horizon,
      why: `${lane.modelVersion} is licensed but its weights are not in this build`,
    };
  }

  try {
    assertSchema(artifact);
  } catch (e) {
    return { kind: "error", horizon, why: e instanceof Error ? e.message : "schema mismatch" };
  }

  const got = await windowFor(instrumentsFor(slug), horizon.interval, nowMs);
  if (!got.ok) {
    return { kind: "data", horizon, lane, why: got.why, tried: got.tried };
  }
  const w = got.window;
  // Read the bar the horizon lands on, not merely the newest one.
  //
  // **A fifteen-minute call was changing every five minutes, and that was wrong rather than
  // merely confusing.** The model is fitted on five-minute bars with a fifteen-minute forward
  // label, so it is valid at every bar -- but serving it at every bar produces a rolling
  // forecast that moves under a reader who is holding the trade it suggested. You enter on UP
  // at 14:05 for the next fifteen minutes and at 14:10 the page says DOWN, about a *different*
  // fifteen minutes, with the first call neither resolved nor withdrawn.
  //
  // So a call is read from the most recent bar whose close sits on the horizon's own grid: the
  // fifteen-minute lane reads at :00, :15, :30, :45 and holds between them. The call now lives
  // exactly as long as the window it describes, and the next one begins where the last ended.
  //
  // Nothing about the model changes -- an aligned bar is one of the bars it was fitted on, and
  // the features are the same features. What changes is which of its opinions is published.
  const periodMs = horizon.minutes * 60_000;
  if (periodMs > w.stepMs) {
    const alignedAsOf = Math.floor(w.asOfMs / periodMs) * periodMs;
    // Walk back to that bar, keeping the warm-up intact behind it. If the aligned bar is not in
    // the window -- a venue gap, or a very fresh listing -- the newest bar is served instead,
    // because a direction from a slightly early bar beats no direction at all.
    const drop = Math.round((w.asOfMs - alignedAsOf) / w.stepMs);
    if (drop > 0 && drop < w.bars.length - WARMUP) {
      w.bars = w.bars.slice(0, w.bars.length - drop);
      w.asOfMs = alignedAsOf;
      w.referencePrice = w.bars[w.bars.length - 1].c;
    }
  }
  const last = w.bars.length - 1;
  if (!contiguous(w.bars, last, w.stepMs)) {
    return {
      kind: "data",
      horizon,
      lane,
      why: `the ${WARMUP + 1} bars before ${new Date(w.asOfMs).toISOString()} are not consecutive`,
      tried: [{ venue: w.venue, outcome: "window spans a gap" }],
    };
  }
  const base = featuresAt(w.bars, last);
  if (!base) {
    return {
      kind: "data",
      horizon,
      lane,
      why: `only ${w.bars.length} bars are available where ${WARMUP + 1} are needed`,
      tried: [{ venue: w.venue, outcome: "short window" }],
    };
  }

  // A model fitted with the market factor has to be served it. Bitcoin's window is fetched
  // alongside the coin's -- one extra venue call, and for Bitcoin itself no call at all, since
  // the factor series *is* the window already in hand.
  //
  // A missing or misaligned factor window is a refusal, never an imputation. Every other
  // imputation on this page is a feature a venue does not publish and whose neutral value the
  // training fold's mean stands for; a context vector built from a factor window that does not
  // reach the decision instant is a set of numbers about a different moment, which no neutral
  // value represents.
  let x = base;
  if (wantsContext(artifact)) {
    let mkt = w.bars;
    if (slug !== MARKET_SLUG) {
      const got2 = await windowFor(instrumentsFor(MARKET_SLUG), horizon.interval, nowMs);
      if (!got2.ok) {
        return {
          kind: "data",
          horizon,
          lane,
          why: `this model reads what the rest of the market is doing, and Bitcoin's bars could ` +
            `not be fetched: ${got2.why}`,
          tried: got2.tried,
        };
      }
      mkt = got2.window.bars;
    }
    const ctx = contextAt(w.bars, last, mkt);
    if (!ctx) {
      return {
        kind: "data",
        horizon,
        lane,
        why: `Bitcoin's bars do not line up with this coin's over the window the model reads, ` +
          `so the market-context inputs could not be computed`,
        tried: [{ venue: w.venue, outcome: "factor window does not cover the decision instant" }],
      };
    }
    x = [...base, ...ctx];
  }

  let probUp: number;
  try {
    probUp = probabilityUp(artifact, x);
  } catch (e) {
    return { kind: "error", horizon, why: e instanceof Error ? e.message : "scoring failed" };
  }

  const margin = Math.abs(probUp - 0.5);
  const ownFloor = floorFor(lane.family, slug, key);
  const asOf = new Date(w.asOfMs);
  const direction: "UP" | "DOWN" = probUp >= 0.5 ? "UP" : "DOWN";
  return {
    kind: "direction",
    horizon,
    lane,
    // Binary and nothing else. A probability on the line goes DOWN rather than being refused:
    // the model was fitted with that boundary and the test fold was scored with it, so serving a
    // different rule would be serving a model nothing measured.
    direction,
    probUp,
    confidence: lane.confidence === "MEDIUM" ? "MEDIUM" : "LOW",
    // This coin's own floor where one was measured, the lane's otherwise.
    //
    // The lane floor is chosen over 140 coins at once and the liquid majors all sit below it --
    // Bitcoin's own floor is 0.050 against a pooled 0.075, so under the pooled rule Bitcoin
    // almost never speaks, and the board filled with small caps instead. Serving each coin at
    // its own measured floor is what lets a reader ask about the coin they care about and get
    // the answer that was actually measured for it.
    strength: ownFloor
      ? margin >= ownFloor.floor
        ? "strong"
        : "weak"
      : lane.conviction
        ? speaks(lane, probUp)
          ? "strong"
          : "weak"
        : null,
    margin,
    floor: ownFloor ? ownFloor.floor : (lane.conviction?.floor ?? 0),
    // The rate measured for THIS coin at THIS floor, not the pool's at a floor it never meets.
    measured:
      ownFloor && ownFloor.accuracy !== null
        ? { accuracy: ownFloor.accuracy, coverage: ownFloor.coverage, rows: cert.verdict?.called ?? 0 }
        : accuracyAtMargin(lane, margin),
    levels: levelsFor(lane, horizon.key, direction, w.referencePrice, x),
    // Non-null by construction: an uncertified coin returned above and never reaches here. The
    // fallback exists only so a lane the sweep has not covered yet still type-checks.
    certification: cert.verdict ?? {
      testRows: 0, called: 0, coverage: 0, convictionFloor: lane.conviction?.floor ?? 0,
      accuracy: null, certified: true, why: "lane not yet swept per coin",
    },
    referencePrice: w.referencePrice,
    asOf,
    maturesAt: maturesAt(asOf, horizon),
    window: w,
    features: x,
  };
}

/// The feature vector as `{name: value}`, for the stored row.
///
/// Stored with the forecast because a graded call that cannot be reproduced is a score without an
/// explanation: this is what lets a later reader tell a wrong direction from one made on a window
/// that was already degraded.
export function featureMap(x: number[]): Record<string, number> {
  const out: Record<string, number> = {};
  // The context block rides on the end of the vector when the model reads it, so the names have
  // to as well -- a stored row whose last eleven values had no names would be a feature vector
  // nobody could reproduce a forecast from, which is the whole reason it is stored.
  const names = x.length > FEATURES.length ? [...FEATURES, ...CONTEXT_FEATURES] : FEATURES;
  names.forEach((name, i) => {
    if (i < x.length) out[name] = Number(x[i].toFixed(8));
  });
  return out;
}
