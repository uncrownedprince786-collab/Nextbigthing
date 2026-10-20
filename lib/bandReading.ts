// What to say about an asset the brain calls FLAT — the rules, with no data in the file.
//
// A three-class model at a 2.0% band answers a magnitude question: UP is "up at least 2% in five
// sessions", DOWN is the mirror, and FLAT is **the move did not clear the band**. FLAT is therefore
// not a direction and not an absence of information. The site treated it as an absence and showed
// "No direction" on 89 of 271 US instruments, which reads as "we have nothing" when the model had
// in fact said something testable.
//
// So direction and magnitude are separated here, and each is allowed to speak only as far as it
// was measured (`tools/research/within_band_direction.py`, holdout, 2026-10-20):
//
//   * Direction inside the band is **noise**. sign(P(UP) - P(DOWN)) scored 0.5164 against 0.5168
//     for the honest constant -- a lift of -0.0004, a 95% blocked-bootstrap interval of
//     [-0.0033, +0.0025], and a paired test that fails. No side is offered on a FLAT row, and
//     that is a measured refusal rather than a missing feature.
//   * The magnitude claim is **real but weak**. Of the rows called FLAT, 0.4076 really stayed
//     inside the band, against 0.3360 across all holdout rows: a +0.0716 lift that clears its
//     test. Right about two times in five -- worth saying, and worth saying with the rate
//     attached rather than as a fact.
//
// The split from `lib/bandReadings.ts` is the one `lib/signalLanes` makes against
// `lib/signalValidation`: rules here where `node --test` can reach them, the artifact bound next
// door where a bundler resolves the `@/` alias.

/// One measured reading, as `within_band_direction.py` writes it. Field names match the artifact.
export interface BandReading {
  market: string;
  horizonSessions: number;
  /// The artifact these numbers were measured on. A reading is evidence about one model, and
  /// attaching it to another is the 2026-10-20 defect in a new place -- so this is required, and
  /// `readingFor` will not return a reading whose model does not match the prediction's.
  modelVersion: string;
  bandScale: number;
  magnitude: {
    thresholdPct: number;
    precisionOnRowsCalledFlat: number;
    rateAcrossAllHoldoutRows: number;
    lift: number;
    holds: boolean;
  };
  /// The direction test on the same rows. `GO` would mean a side may be shown at LOW confidence;
  /// it is `NO-GO` today and the card says so rather than staying silent.
  verdict: "GO" | "NO-GO" | "INSUFFICIENT";
  lift: number;
  // JSON gives a plain array, so the pair is not asserted at the type level. The card checks
  // for two elements before reading them, which is cheaper than asserting a shape the artifact
  // does not actually guarantee.
  tests: { blockedBootstrap?: { ci95?: number[]; z?: number } };
  n: number;
}

/// What the card should render for a row the brain called FLAT.
///
/// Three cases, and they are different claims:
///   * `measured`  — the magnitude call has been tested on this very model. Show it with its rate.
///   * `unmeasured`— the model is one nothing has measured. Say that; do not borrow another
///                   model's numbers to fill the space.
export type BandVerdict =
  | { kind: "measured"; reading: BandReading }
  | { kind: "unmeasured" };

/// The reading for this prediction, or `unmeasured`.
///
/// Matching on model version as well as market and horizon is the point of the function. A
/// reading measured on `brain-v5-h5b20-us` says nothing about `brain-v5-h5-us`: those two models
/// disagreed about direction on 271 of 271 instruments.
export function readingFor(
  readings: readonly BandReading[],
  market: string,
  horizonSessions: number,
  modelVersion: string | null | undefined,
): BandVerdict {
  if (!modelVersion) return { kind: "unmeasured" };
  const r = readings.find(
    (x) =>
      x.market === market &&
      x.horizonSessions === horizonSessions &&
      x.modelVersion === modelVersion,
  );
  // An INSUFFICIENT reading was not actually measured -- too few rows to answer -- so it is not
  // allowed to present itself as a measurement.
  if (!r || r.verdict === "INSUFFICIENT") return { kind: "unmeasured" };
  return { kind: "measured", reading: r };
}

/// "about 2 times in 5" — a rate a reader can hold in their head, from one they cannot.
///
/// Deliberately coarse. 0.4076 invites a precision the number does not have, and rounding it to
/// "2 in 5" is honest about that while staying faithful to the measurement: the denominator is
/// chosen so the rounded fraction is within half a step of the rate.
export function asTimesIn(rate: number, denominator = 5): { times: number; of: number } {
  return { times: Math.round(rate * denominator), of: denominator };
}

/// Whether a side may be shown for a row inside the band. False today, and measured — not a
/// placeholder waiting for a feature.
export function bandDirectionIsServable(reading: BandReading): boolean {
  return reading.verdict === "GO";
}
