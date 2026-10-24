// Writing down the forecast the reader was shown, and reading back how the earlier ones did.
//
// The rule this keeps is the one that makes the whole thing honest: **the row that is stored is
// the row that was shown**. `asOf` is the close time of the bar the features were read from, so
// every request inside one bar produces an identical forecast and the unique key turns the repeat
// into a no-op. Nothing is re-derived at write time and nothing is rounded into a different claim.
//
// A write failure never fails a page. A forecast that could not be recorded is still a correct
// forecast to show; what it is not is an *auditable* one, so the failure is surfaced on the page
// as a line rather than swallowed -- a reader is entitled to know that this particular call will
// not appear in the record later.

import { prisma } from "@/lib/db";
import { featureMap, type Forecast } from "@/lib/cryptoForecast";

/// A forecast that reached the model. Every one of them is a direction now; `called` records
/// whether it cleared its lane's conviction floor.
export type Recordable = Extract<Forecast, { kind: "direction" }>;

/// Store a forecast, returning whether it is now in the record.
///
/// Idempotent: the same bar writes once. `skipDuplicates` rather than an update, because a
/// forecast is a claim made at an instant and a second write of the same claim must not be able
/// to change the first.
///
/// `called` means the probability cleared the lane's conviction floor, not that a direction was
/// shown -- every window shows one. It is kept because the floor is a threshold, and a threshold
/// that is never checked against what happened after it is a guess promoted to a rule: grading
/// the two bands apart is the only way to find out whether the floor is still worth anything.
export async function recordForecast(
  assetId: string,
  market: string,
  slug: string,
  f: Recordable,
): Promise<{ stored: boolean; why?: string }> {
  const called = f.strength === "strong";
  try {
    const res = await prisma.brainForecast.createMany({
      data: [
        {
          assetId,
          symbol: slug,
          market,
          horizonKey: f.horizon.key,
          horizonMinutes: f.horizon.minutes,
          interval: f.horizon.interval,
          asOf: f.asOf,
          maturesAt: f.maturesAt,
          direction: f.direction,
          probUp: f.probUp,
          called,
          convictionFloor: f.lane.conviction?.floor ?? null,
          // The lane's band for a call that cleared the floor; WEAK for one that did not, so a
          // graded row says which population it belonged to without recomputing the threshold.
          confidence: called ? f.confidence : "WEAK",
          referencePrice: f.referencePrice,
          modelVersion: f.lane.modelVersion,
          modelSha256: f.lane.modelSha256,
          featureSchema: f.lane.featureSchema,
          features: featureMap(f.features),
          quality: f.window.quality,
          imputed: f.window.imputed,
          venue: f.window.venue,
          patchedFrom: f.window.patchedFrom,
          barCount: f.window.bars.length,
          inputAgeMs: Math.max(0, Math.round(f.window.ageMs)),
        },
      ],
      skipDuplicates: true,
    });
    // `count: 0` means this bar's forecast was already recorded, which is the normal case on the
    // second and later views of the same page inside one bar -- not a failure.
    return { stored: true, why: res.count === 0 ? "already recorded for this bar" : undefined };
  } catch (e) {
    // Prisma's connection errors lead with a blank line, and the first line of one of those is
    // the empty string -- which rendered as "could not be written to the record ()" on the page,
    // a sentence that tells a reader the write failed and then withholds the only useful part.
    const first = e instanceof Error
      ? e.message.split("\n").map((l) => l.trim()).find((l) => l.length > 0)
      : undefined;
    return { stored: false, why: first ?? "write failed" };
  }
}

export interface TrackRecord {
  /// Forecasts whose horizon has matured and that have been graded. **Called rows only**: the
  /// rate below is how often the brain was right when it spoke, which is the only rate a reader
  /// can act on.
  graded: number;
  correct: number;
  /// Forecasts made but not yet mature. Counted separately so a rate is never computed over them.
  pending: number;
  /// Matured but not yet graded by the scorer -- a gap in the scoring, not in the forecasting.
  awaitingScore: number;
  accuracy: number | null;
  /// The same counts over the calls that did NOT clear the lane's floor. Never mixed into
  /// `accuracy` above: both are shown on the page, but they are two different bands and a rate
  /// over the pair would describe neither. A weak rate near a half is the floor doing its job; one
  /// level with the strong rate would mean the floor is no longer separating anything.
  quietGraded: number;
  quietCorrect: number;
  /// How many of the graded windows actually went UP.
  ///
  /// **Accuracy without this is unreadable.** Forecasts are written when somebody opens a page,
  /// so the prospective sample is clustered into whatever hours the site was being used -- not
  /// spread evenly across market conditions the way a holdout is. A stretch of hours in which
  /// 85% of five-minute windows fell is a stretch in which a balanced model scores near 50% while
  /// a model that says DOWN to everything scores 85%, and neither number means what it looks
  /// like. So the base rate of the graded sample travels with the rate, exactly as coverage
  /// travels with every accuracy figure on this site.
  gradedUp: number;
  firstAt: Date | null;
  newestAt: Date | null;
}

/// The prospective record for one coin and horizon: what has actually been called and what
/// happened, with nothing counted before its window closed.
///
/// `accuracy` stays null until there is something to divide by. A rate over three results is not
/// a rate, and printing one would be the same mistake as printing a confidence a backtest cannot
/// support, so the caller is given the counts and decides what is worth saying.
export async function trackRecord(
  assetId: string,
  horizonKey: string,
  now: Date = new Date(),
): Promise<TrackRecord> {
  // Counted in the database, never scanned here. A five-minute window produces a row per bar, so
  // one coin and one horizon reaches six figures inside a year -- pulling those into Node to add
  // them up is the shape `getAssetFreshness` exists to stop, on the page least able to afford it.
  const where = { assetId, horizonKey, called: true };
  const quiet = { assetId, horizonKey, called: false };
  const [total, graded, correct, pending, span, quietGraded, quietCorrect, gradedUp] =
    await Promise.all([
    prisma.brainForecast.count({ where }),
    prisma.brainForecast.count({ where: { ...where, outcome: { isNot: null } } }),
    prisma.brainForecast.count({ where: { ...where, outcome: { is: { correct: true } } } }),
    prisma.brainForecast.count({ where: { ...where, outcome: { is: null }, maturesAt: { gt: now } } }),
    prisma.brainForecast.aggregate({ where: { assetId, horizonKey }, _min: { asOf: true }, _max: { asOf: true } }),
    prisma.brainForecast.count({ where: { ...quiet, outcome: { isNot: null } } }),
    prisma.brainForecast.count({ where: { ...quiet, outcome: { is: { correct: true } } } }),
    prisma.brainForecast.count({
      where: { assetId, horizonKey, outcome: { is: { actual: "UP" } } },
    }),
  ]);
  return {
    graded,
    correct,
    pending,
    quietGraded,
    quietCorrect,
    gradedUp,
    // Matured and unscored is what is left over, which is the only one of the four that cannot be
    // asked for directly without a second index: it is total minus the two that are accounted for.
    awaitingScore: total - graded - pending,
    accuracy: graded > 0 ? correct / graded : null,
    firstAt: span._min.asOf ?? null,
    newestAt: span._max.asOf ?? null,
  };
}

/// The whole prospective record across every coin and horizon, for the record page.
///
/// Every count here is over **called** forecasts, except `quiet*`, which are the bars the brain
/// read and said nothing about. The two are never added together: a rate over both would be a
/// rate over a population no reader was ever shown, and the point of the split is that the
/// headline number is the one that was actually claimed.
export async function forecastTotals(now: Date = new Date()): Promise<{
  forecasts: number;
  graded: number;
  correct: number;
  pending: number;
  awaitingScore: number;
  quiet: number;
  quietGraded: number;
  quietCorrect: number;
  byHorizon: { horizonKey: string; forecasts: number; graded: number; correct: number }[];
}> {
  // Grouped in the database for the same reason as above: this page is prerendered every fifteen
  // minutes and must cost the same when the table holds a thousand rows and when it holds a
  // million.
  const called = { called: true };
  const [
    total, graded, correct, pending,
    quiet, quietGraded, quietCorrect,
    perHorizon, perHorizonGraded, perHorizonCorrect,
  ] = await Promise.all([
      prisma.brainForecast.count({ where: called }),
      prisma.brainForecast.count({ where: { ...called, outcome: { isNot: null } } }),
      prisma.brainForecast.count({ where: { ...called, outcome: { is: { correct: true } } } }),
      prisma.brainForecast.count({ where: { ...called, outcome: { is: null }, maturesAt: { gt: now } } }),
      prisma.brainForecast.count({ where: { called: false } }),
      prisma.brainForecast.count({ where: { called: false, outcome: { isNot: null } } }),
      prisma.brainForecast.count({ where: { called: false, outcome: { is: { correct: true } } } }),
      prisma.brainForecast.groupBy({ by: ["horizonKey"], where: called, _count: { _all: true } }),
      prisma.brainForecast.groupBy({
        by: ["horizonKey"],
        where: { ...called, outcome: { isNot: null } },
        _count: { _all: true },
      }),
      prisma.brainForecast.groupBy({
        by: ["horizonKey"],
        where: { ...called, outcome: { is: { correct: true } } },
        _count: { _all: true },
      }),
    ]);
  const countOf = (rows: { horizonKey: string; _count: { _all: number } }[], k: string) =>
    rows.find((r) => r.horizonKey === k)?._count._all ?? 0;
  return {
    forecasts: total,
    graded,
    correct,
    pending,
    awaitingScore: total - graded - pending,
    quiet,
    quietGraded,
    quietCorrect,
    byHorizon: perHorizon.map((r) => ({
      horizonKey: r.horizonKey,
      forecasts: r._count._all,
      graded: countOf(perHorizonGraded, r.horizonKey),
      correct: countOf(perHorizonCorrect, r.horizonKey),
    })),
  };
}
