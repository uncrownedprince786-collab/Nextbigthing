// Why an asset has no recorded reading — the rules, with no data in the file.
//
// The asset page used to say "Nothing recorded yet" and stop. That sentence covers four unrelated
// situations: an asset with too little stored history to build a feature vector at all, an asset
// whose newest bar is weeks old, an asset the recorder simply has not reached, and an asset whose
// market carries no validated lane. A reader cannot act on any of them without being told which.
//
// `tools/foundation/coverage_registry.py` precomputes the data half of that answer for every asset,
// so the page reads a lookup rather than asking the database. As of the first run: 618 of 620
// assets are data-ready, which means almost every blank tile on the site is a *recorder* gap and
// not a data gap — and saying so is the honest version of the sentence.

/// The data status of one asset, as the registry writes it. Exactly one status applies.
///   ready        — the data supports a reading now
///   thin-history — fewer stored sessions than a feature vector needs
///   stale        — history exists but the newest bar is too old to be about now
///   no-history   — nothing stored
///   feature-gap  — the bars are there and the recorder refuses the row anyway, because a feature
///                  the model needs is not observed for this asset. Twelve US assets have 1,960
///                  sessions each and are still refused: BA and COPX lack `peerMedianR20` and
///                  `relStrength`, the peer-relative features, because nothing comparable to them
///                  is stored. Counting bars alone called these ready and would have had the page
///                  promise a reading that never arrives.
export type CoverageStatus =
  | "ready"
  | "thin-history"
  | "stale"
  | "no-history"
  | "feature-gap";

export interface AssetCoverage {
  market: string;
  bars: number;
  oldest: string | null;
  newest: string | null;
  sessionsBehind: number | null;
  status: CoverageStatus;
  /// Present on every status except `ready`: the specific thing that is missing, in words the
  /// page can print. Absent on `ready` because there is nothing to explain.
  why?: string;
  /// How many of the model's features were imputed, on a `feature-gap`. Named because "some
  /// inputs were missing" is the shrug this file exists to replace.
  imputedCount?: number;
  horizons: Record<string, CoverageStatus>;
}

export interface CoverageRegistry {
  generatedAt: string;
  featureWindowSessions: number;
  staleAfterSessions: number;
  assetsByStatus: Partial<Record<CoverageStatus, number>>;
  assets: Record<string, AssetCoverage>;
}

/// Why there is no recorded reading for this asset at this horizon.
///
/// Two shapes, because they call for different things from the reader:
///   * `data`     — the data is not there yet, and `why` says what is missing. Nothing the
///                  recorder does will change this until the history is filled.
///   * `recorder` — the data is ready and no row has been written. The reading is pending, not
///                  impossible, and the page should say that rather than implying a defect.
///   * `unknown`  — the asset is not in the registry at all, which is itself worth admitting
///                  rather than papering over with either of the above.
export type MissingReason =
  | { kind: "data"; status: CoverageStatus; why: string; coverage: AssetCoverage }
  | { kind: "recorder"; coverage: AssetCoverage }
  | { kind: "unknown" };

export function whyNoReading(
  registry: Pick<CoverageRegistry, "assets">,
  symbol: string,
  horizonSessions: number,
): MissingReason {
  const c = registry.assets[symbol];
  if (!c) return { kind: "unknown" };
  // The per-horizon entry is the authority: the history floor does not vary with horizon today,
  // but the registry is where that could change and the page should not re-derive it.
  const status = c.horizons[String(horizonSessions)] ?? c.status;
  if (status === "ready") return { kind: "recorder", coverage: c };
  return {
    kind: "data",
    status,
    why: c.why ?? `the stored history is ${status}`,
    coverage: c,
  };
}

/// How much of the universe is data-ready, for a page that wants to say "this is the exception"
/// rather than leaving a reader to assume the whole site is empty.
export function readyShare(registry: Pick<CoverageRegistry, "assets">): {
  ready: number;
  total: number;
} {
  const all = Object.values(registry.assets);
  return { ready: all.filter((a) => a.status === "ready").length, total: all.length };
}
