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
import { accuracyAtMargin, servingLane, type Lane } from "@/lib/cryptoLanes";
import { assertSchema, probabilityUp, type Artifact } from "@/lib/cryptoModel";
import { featuresAt, FEATURES, contiguous, WARMUP } from "@/lib/intradayFeatures";
import { hasIntradaySource, instrumentsFor, venueRowFor } from "@/lib/cryptoVenues";

const MODELS = models as unknown as Record<string, Artifact>;

export type Forecast =
  | {
      kind: "direction";
      horizon: Horizon;
      lane: Lane;
      direction: "UP" | "DOWN";
      /// P(UP) from the artifact. Printed as a margin, never as a precision claim.
      probUp: number;
      confidence: "LOW" | "MEDIUM";
      /// How often a call in this confidence band was right on the test fold, if the band held
      /// enough rows to say. Null is an absence, not a zero.
      measured: { accuracy: number; coverage: number; rows: number } | null;
      referencePrice: number;
      asOf: Date;
      maturesAt: Date;
      window: BarWindow;
      features: number[];
    }
  | { kind: "no-model"; horizon: Horizon; why: string }
  | { kind: "refused"; horizon: Horizon; lane: Lane; why: string }
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
  const lane = servingLane(slug, key);
  if (!lane) {
    return {
      kind: "no-model",
      horizon,
      why: `no model has been fitted for crypto over ${horizon.label.toLowerCase()}`,
    };
  }
  if (!lane.servable) {
    return { kind: "refused", horizon, lane, why: lane.why ?? "it did not pass its gates" };
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
  const x = featuresAt(w.bars, last);
  if (!x) {
    return {
      kind: "data",
      horizon,
      lane,
      why: `only ${w.bars.length} bars are available where ${WARMUP + 1} are needed`,
      tried: [{ venue: w.venue, outcome: "short window" }],
    };
  }

  let probUp: number;
  try {
    probUp = probabilityUp(artifact, x);
  } catch (e) {
    return { kind: "error", horizon, why: e instanceof Error ? e.message : "scoring failed" };
  }

  const margin = Math.abs(probUp - 0.5);
  const asOf = new Date(w.asOfMs);
  return {
    kind: "direction",
    horizon,
    lane,
    // Binary and nothing else. A probability on the line goes DOWN rather than being refused:
    // the model was fitted with that boundary and the test fold was scored with it, so serving a
    // different rule would be serving a model nothing measured.
    direction: probUp >= 0.5 ? "UP" : "DOWN",
    probUp,
    confidence: lane.confidence === "MEDIUM" ? "MEDIUM" : "LOW",
    measured: accuracyAtMargin(lane, margin),
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
  FEATURES.forEach((name, i) => {
    out[name] = Number(x[i].toFixed(8));
  });
  return out;
}
