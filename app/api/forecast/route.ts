import { NextResponse } from "next/server";
import { forecastFor, featureMap } from "@/lib/cryptoForecast";
import { HORIZON_ORDER, isHorizonKey } from "@/lib/cryptoHorizons";
import { recordForecast } from "@/lib/forecastStore";
import { getAsset } from "@/lib/queries";
import { marketOf } from "@/lib/decisionInput";

/// One coin, one window, one direction — the forecast on its own.
///
///     /api/forecast?symbol=btc-bitcoin&h=m5
///
/// **Why this exists beside the page.** The asset page renders the same forecast, and it also
/// renders seventeen other reads of the database; measured on the deployed site it answers in
/// seven to ten seconds, almost none of it the forecast. That makes "a direction within seconds"
/// impossible to verify from the page and impossible for anything else to consume. This route
/// does the forecast and nothing else, so the claim is measurable and the number is honest.
///
/// It is the same code path, not a parallel one: `forecastFor` and `recordForecast` are the two
/// the page calls, in the same order, so a forecast fetched here is the row the page would have
/// written and the scorer will later grade. A second implementation would be a second answer.
///
/// Read-mostly by design: the only write is the forecast row, keyed on the bar it was read from,
/// so repeated calls inside one bar write nothing.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: Request) {
  const started = Date.now();
  const url = new URL(request.url);
  const symbol = (url.searchParams.get("symbol") || "").trim();
  const h = (url.searchParams.get("h") || "").trim();

  if (!symbol) {
    return NextResponse.json(
      { error: "symbol is required", example: "/api/forecast?symbol=btc-bitcoin&h=m5" },
      { status: 400 },
    );
  }
  if (!isHorizonKey(h)) {
    return NextResponse.json(
      { error: `h must be one of ${HORIZON_ORDER.join(", ")}`, got: h || null },
      { status: 400 },
    );
  }

  const asset = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  if (!asset) {
    return NextResponse.json({ error: "no such asset", symbol }, { status: 404 });
  }
  const market = marketOf(asset);
  if (market !== "Crypto") {
    return NextResponse.json(
      {
        error: "short-horizon forecasts cover crypto only",
        symbol,
        market,
        why: "the other four markets have exchange sessions and no intraday corpus here; their " +
          "asset pages carry the session-horizon panel instead",
      },
      { status: 400 },
    );
  }

  const f = await forecastFor(asset.symbol, h);
  if (f.kind === "quiet") {
    // Everything worked and the answer is that there is no answer. Recorded like a call, and
    // returned with the number that produced the silence, so a caller can tell this apart from a
    // venue outage without parsing a sentence.
    const storedQuiet = await recordForecast(asset.id, market, asset.symbol, f);
    return NextResponse.json({
      symbol: asset.symbol,
      name: asset.name,
      horizon: { key: f.horizon.key, label: f.horizon.label, minutes: f.horizon.minutes },
      state: "quiet",
      direction: null,
      lean: f.lean,
      probUp: Number(f.probUp.toFixed(6)),
      margin: Number(f.margin.toFixed(6)),
      convictionFloor: f.floor,
      why: `the model put this window ${(f.margin * 200).toFixed(1)} points from an even call, ` +
        `inside the ${(f.floor * 200).toFixed(0)}-point floor this lane clears before it prints a ` +
        `direction`,
      referencePrice: f.referencePrice,
      asOf: f.asOf.toISOString(),
      maturesAt: f.maturesAt.toISOString(),
      model: {
        version: f.lane.modelVersion,
        sha256: f.lane.modelSha256,
        featureSchema: f.lane.featureSchema,
        family: f.lane.family,
        trainedOn: f.lane.trainedOn,
      },
      conviction: f.lane.conviction
        ? {
            floor: f.lane.conviction.floor,
            calledAccuracy: f.lane.conviction.called.accuracy,
            calledCoverage: f.lane.conviction.called.coverage,
            calledMajority: f.lane.conviction.called.majorityHere,
            ungatedAccuracy: f.lane.conviction.ungatedAccuracy,
          }
        : null,
      data: {
        venue: f.window.venue,
        patchedFrom: f.window.patchedFrom,
        bars: f.window.bars.length,
        interval: f.horizon.interval,
        newestBarAgeMs: Math.round(f.window.ageMs),
        quality: f.window.quality,
        imputed: f.window.imputed,
        fetchedAt: f.window.fetchedAt,
        checks: f.window.checks,
      },
      features: featureMap(f.features),
      recorded: storedQuiet.stored,
      recordedNote: storedQuiet.why ?? null,
      servedInMs: Date.now() - started,
      disclaimer:
        "Research, not advice. Direction only, with no transaction cost, spread or funding in " +
        "any number here, and every accuracy figure is measured on a historical holdout.",
    });
  }
  if (f.kind !== "direction") {
    // A refusal is an answer and carries its reason, so a caller can tell an untested window from
    // a venue outage without reading the page.
    return NextResponse.json(
      {
        symbol: asset.symbol,
        name: asset.name,
        horizon: { key: f.horizon.key, label: f.horizon.label, minutes: f.horizon.minutes },
        direction: null,
        state: f.kind,
        why: "why" in f ? f.why : null,
        tried: "tried" in f ? f.tried : undefined,
        servedInMs: Date.now() - started,
      },
      { status: 200 },
    );
  }

  const stored = await recordForecast(asset.id, market, asset.symbol, f);
  return NextResponse.json({
    symbol: asset.symbol,
    name: asset.name,
    horizon: { key: f.horizon.key, label: f.horizon.label, minutes: f.horizon.minutes },
    state: "direction",
    direction: f.direction,
    probUp: Number(f.probUp.toFixed(6)),
    confidence: f.confidence,
    referencePrice: f.referencePrice,
    asOf: f.asOf.toISOString(),
    maturesAt: f.maturesAt.toISOString(),
    model: {
      version: f.lane.modelVersion,
      sha256: f.lane.modelSha256,
      featureSchema: f.lane.featureSchema,
      family: f.lane.family,
      trainedOn: f.lane.trainedOn,
    },
    // The evidence the badge rests on, beside the badge. A confidence word with no numbers under
    // it is the thing this whole lane table exists to stop.
    evidence: {
      testAccuracy: f.lane.evidence.accuracy,
      testMajority: f.lane.evidence.testMajority,
      marginOverMajority: f.lane.evidence.marginOverMajority,
      bootstrapCi95: f.lane.evidence.bootstrapCi95,
      testRows: f.lane.evidence.testRows,
      testFrom: f.lane.evidence.testFrom,
      testTo: f.lane.evidence.testTo,
      acceptanceTarget: f.lane.acceptanceTarget,
      acceptanceTargetMet: f.lane.acceptanceTargetMet,
    },
    // What the lane scores on the rows it actually speaks on, which is the population this
    // direction belongs to. Null for a lane that answers every bar.
    conviction: f.lane.conviction
      ? {
          floor: f.lane.conviction.floor,
          margin: Number(Math.abs(f.probUp - 0.5).toFixed(6)),
          calledAccuracy: f.lane.conviction.called.accuracy,
          calledCoverage: f.lane.conviction.called.coverage,
          calledMajority: f.lane.conviction.called.majorityHere,
          calledBootstrapCi95: f.lane.conviction.called.bootstrapCi95,
          ungatedAccuracy: f.lane.conviction.ungatedAccuracy,
        }
      : null,
    data: {
      venue: f.window.venue,
      patchedFrom: f.window.patchedFrom,
      bars: f.window.bars.length,
      interval: f.horizon.interval,
      newestBarAgeMs: Math.round(f.window.ageMs),
      quality: f.window.quality,
      imputed: f.window.imputed,
      fetchedAt: f.window.fetchedAt,
      checks: f.window.checks,
    },
    features: featureMap(f.features),
    recorded: stored.stored,
    recordedNote: stored.why ?? null,
    servedInMs: Date.now() - started,
    disclaimer:
      "Research, not advice. Direction only, with no transaction cost, spread or funding in any " +
      "number here, and every accuracy figure is measured on a historical holdout.",
  });
}
