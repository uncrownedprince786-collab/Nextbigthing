// Reading a trained artifact and scoring one row with it.
//
// This is the only place in the web layer that evaluates a model, and it does so from the stored
// artifact alone: the feature order, the bin edges, the trees and the bias all come out of
// `model.json`, and nothing here knows how the fit was performed. A model that is replaced is a
// file that is replaced; no code changes with it.
//
// **Why the web layer scores at all.** Every other brain on this site is read, not run: a recorder
// writes `ShadowPrediction` rows and the pages show them (brain.md rule 5). That is right for a
// 20-session call, whose answer is the same all day. It is wrong for a five-minute one -- a
// precomputed five-minute forecast is stale before the page renders, and serving one would mean
// printing a direction for a window that has already closed. So short-horizon forecasts are
// computed at request time from bars fetched at request time, and then **written down** exactly
// as a recorder would write them (`lib/forecastStore.ts`), so they are still graded later against
// what actually happened. What changes is when the row is written, not whether it is auditable.
//
// The arithmetic is deliberately plain. A gradient-boosted tree at inference is a bin lookup and a
// walk; there is no library here and nothing to go wrong in a dependency.

// Relative, not aliased: the test lane runs under `node --test` with no bundler to resolve `@/`,
// and this module has to be exercisable there. Same split as lib/signalValidation and signalLanes.
import { CONTEXT_VERSION, N_CONTEXT } from "./marketContext.ts";
import { FEATURE_VERSION, FEATURES } from "./intradayFeatures.ts";

export interface GbmLeaf {
  leaf: number;
}
export interface GbmSplit {
  f: number;
  b: number;
  l: GbmNode;
  r: GbmNode;
}
export type GbmNode = GbmLeaf | GbmSplit;

export interface GbmModel {
  kind: "gbm-logistic";
  bias: number;
  lr: number;
  bins: number;
  edges: number[][];
  trees: GbmNode[];
}

export interface LogisticModel {
  kind: "logistic";
  mean: number[];
  sd: number[];
  w: number[];
}

export interface Artifact {
  modelVersion: string;
  featureSchema: string;
  features: string[];
  warmupBars: number;
  interval: "5m" | "4h";
  barsAhead: number;
  minutesAhead: number;
  classes: ["DOWN", "UP"];
  model: GbmModel | LogisticModel;
}

/// How many bin edges are strictly below `x` -- the serving twin of numpy's
/// `searchsorted(edges, x, side="left")`, which is what the trainer binned with.
function binOf(edges: number[], x: number): number {
  let lo = 0;
  let hi = edges.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (edges[mid] < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function walk(node: GbmNode, codes: number[]): number {
  let n = node;
  // Depth is bounded by the fit (4 today), so this terminates; the guard is against a corrupt
  // artifact rather than against the algorithm.
  for (let depth = 0; depth < 64; depth++) {
    if ("leaf" in n) return n.leaf;
    n = codes[n.f] <= n.b ? n.l : n.r;
  }
  throw new Error("model artifact: tree deeper than 64 levels");
}

/// P(UP) for one feature vector.
///
/// Throws rather than guessing when the vector is the wrong length or holds a non-finite value: a
/// forecast computed from a NaN is not a low-confidence forecast, it is a broken one, and the
/// caller turns the throw into a refusal the page can print.
export function probabilityUp(artifact: Artifact, x: number[]): number {
  if (x.length !== artifact.features.length) {
    throw new Error(
      `model ${artifact.modelVersion} wants ${artifact.features.length} features, got ${x.length}`,
    );
  }
  for (let i = 0; i < x.length; i++) {
    if (!Number.isFinite(x[i])) {
      throw new Error(`feature ${artifact.features[i]} is not finite`);
    }
  }
  const m = artifact.model;
  if (m.kind === "logistic") {
    let z = m.w[m.w.length - 1];
    for (let i = 0; i < x.length; i++) z += ((x[i] - m.mean[i]) / m.sd[i]) * m.w[i];
    return 1 / (1 + Math.exp(-z));
  }
  const codes = new Array<number>(x.length);
  for (let i = 0; i < x.length; i++) codes[i] = binOf(m.edges[i], x[i]);
  let s = m.bias;
  for (const t of m.trees) s += m.lr * walk(t, codes);
  return 1 / (1 + Math.exp(-s));
}

/// Refuse an artifact whose feature schema is not the one this build computes.
///
/// The parity test keeps the two *implementations* of a schema equal; this keeps a model from
/// being fed a *different* schema. They are different failures: the first is a drifting
/// transliteration, the second is an artifact from before a feature was added, and only the second
/// survives a green test suite.
/// The schema with the market factor appended, as `train_crypto_short.py` writes it.
const WITH_CONTEXT = `${FEATURE_VERSION}+${CONTEXT_VERSION}`;

/// What this build can compute. An artifact naming anything else is refused rather than served a
/// feature vector of the wrong width -- which would score, and be wrong.
const KNOWN_SCHEMAS = new Set([FEATURE_VERSION, WITH_CONTEXT]);

export function assertSchema(artifact: Artifact): void {
  if (!KNOWN_SCHEMAS.has(artifact.featureSchema)) {
    throw new Error(
      `model ${artifact.modelVersion} was trained on feature schema ` +
        `${artifact.featureSchema}; this build computes ${[...KNOWN_SCHEMAS].join(" or ")}`,
    );
  }
  // The schema name and the width have to agree. They are written by the same line of the trainer,
  // so a disagreement means the artifact was edited or assembled by something else -- and a model
  // scored on a vector of the wrong length does not fail, it returns a number.
  const expected = FEATURES.length + (artifact.featureSchema === WITH_CONTEXT ? N_CONTEXT : 0);
  if (artifact.features.length !== expected) {
    throw new Error(
      `model ${artifact.modelVersion} names schema ${artifact.featureSchema}, which is ` +
        `${expected} features, and carries ${artifact.features.length}`,
    );
  }
}

/// Does this artifact read the market-factor block as well as the coin's own bars?
///
/// Decided from the schema string the trainer stamped on it rather than from the feature count,
/// because a count is a coincidence waiting to happen and a name is a statement.
export function wantsContext(artifact: Artifact): boolean {
  return artifact.featureSchema === WITH_CONTEXT;
}
