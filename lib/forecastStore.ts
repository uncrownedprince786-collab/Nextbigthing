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

/// Store a forecast, returning whether it is now in the record.
///
/// Idempotent: the same bar writes once. `skipDuplicates` rather than an update, because a
/// forecast is a claim made at an instant and a second write of the same claim must not be able
/// to change the first.
export async function recordForecast(
  assetId: string,
  market: string,
  slug: string,
  f: Extract<Forecast, { kind: "direction" }>,
): Promise<{ stored: boolean; why?: string }> {
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
          confidence: f.confidence,
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
    return { stored: false, why: e instanceof Error ? e.message.split("\n")[0] : "write failed" };
  }
}

export interface TrackRecord {
  /// Forecasts whose horizon has matured and that have been graded.
  graded: number;
  correct: number;
  /// Forecasts made but not yet mature. Counted separately so a rate is never computed over them.
  pending: number;
  /// Matured but not yet graded by the scorer -- a gap in the scoring, not in the forecasting.
  awaitingScore: number;
  accuracy: number | null;
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
  const where = { assetId, horizonKey };
  const [total, graded, correct, pending, span] = await Promise.all([
    prisma.brainForecast.count({ where }),
    prisma.brainForecast.count({ where: { ...where, outcome: { isNot: null } } }),
    prisma.brainForecast.count({ where: { ...where, outcome: { is: { correct: true } } } }),
    prisma.brainForecast.count({ where: { ...where, outcome: { is: null }, maturesAt: { gt: now } } }),
    prisma.brainForecast.aggregate({ where, _min: { asOf: true }, _max: { asOf: true } }),
  ]);
  return {
    graded,
    correct,
    pending,
    // Matured and unscored is what is left over, which is the only one of the four that cannot be
    // asked for directly without a second index: it is total minus the two that are accounted for.
    awaitingScore: total - graded - pending,
    accuracy: graded > 0 ? correct / graded : null,
    firstAt: span._min.asOf ?? null,
    newestAt: span._max.asOf ?? null,
  };
}

/// The whole prospective record across every coin and horizon, for the record page.
export async function forecastTotals(now: Date = new Date()): Promise<{
  forecasts: number;
  graded: number;
  correct: number;
  pending: number;
  awaitingScore: number;
  byHorizon: { horizonKey: string; forecasts: number; graded: number; correct: number }[];
}> {
  // Grouped in the database for the same reason as above: this page is prerendered every fifteen
  // minutes and must cost the same when the table holds a thousand rows and when it holds a
  // million.
  const [total, graded, correct, pending, perHorizon, perHorizonGraded, perHorizonCorrect] =
    await Promise.all([
      prisma.brainForecast.count(),
      prisma.brainForecast.count({ where: { outcome: { isNot: null } } }),
      prisma.brainForecast.count({ where: { outcome: { is: { correct: true } } } }),
      prisma.brainForecast.count({ where: { outcome: { is: null }, maturesAt: { gt: now } } }),
      prisma.brainForecast.groupBy({ by: ["horizonKey"], _count: { _all: true } }),
      prisma.brainForecast.groupBy({
        by: ["horizonKey"],
        where: { outcome: { isNot: null } },
        _count: { _all: true },
      }),
      prisma.brainForecast.groupBy({
        by: ["horizonKey"],
        where: { outcome: { is: { correct: true } } },
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
    byHorizon: perHorizon.map((r) => ({
      horizonKey: r.horizonKey,
      forecasts: r._count._all,
      graded: countOf(perHorizonGraded, r.horizonKey),
      correct: countOf(perHorizonCorrect, r.horizonKey),
    })),
  };
}
