import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, Empty, Note, Section } from "@/components/ui";
import { getAsset, getAssetFreshness, getAssetPrediction } from "@/lib/queries";
import { marketOf } from "@/lib/decisionInput";
import { MARKET_LABELS, canonicalMarket, capabilityFor } from "@/lib/marketCapability";
import {
  TIMEFRAME_SESSIONS, TIMEFRAME_ORDER, TIMEFRAME_LABELS, type TimeframeName,
} from "@/lib/marketMarkets";
import {
  verdictFor, sideOfClass, laneFor,
  VALIDATION_REQUIREMENTS, VALIDATION_GENERATED_AT, VALIDATION_STATUS,
} from "@/lib/signalValidation";

/// Screen 4 — the end of the journey: market, asset, trading style, and what the brain says.
///
/// The screen is mostly a set of refusals, and that is the design rather than a shortfall.
/// Three separate things all have to be true before a direction appears, and each fails on its own:
///
///   1. **The horizon can be judged at all.** `marketCapability` says whether a stored close can
///      ever score this market at this timeframe. A scalp cannot be judged from daily closes in
///      any market, so it is offered nowhere.
///   2. **A direction has survived testing** on this market, horizon and side.
///      `signalValidation` carries that, and today exactly one lane qualifies: US, five sessions,
///      LONG. The US short side was tested and failed — the price rose after the model said fall
///      in four years of five — so SHORT is suppressed here and the reason is printed.
///   3. **A prediction has actually been recorded** for this asset at this horizon. The web layer
///      reads rows; it does not run a model (brain.md rule 5). No row, no card.
///
/// The temptation this screen is built against is filling the space. A decision card with nothing
/// behind it is worse than an empty one, because a reader cannot tell them apart.
export const revalidate = 900;

export async function generateMetadata(
  { params }: { params: Promise<{ symbol: string }> },
): Promise<Metadata> {
  const { symbol } = await params;
  const a = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  return { title: a ? `${a.symbol} · decision` : "Decision" };
}

function day(d: Date | string | null | undefined) {
  return d ? new Date(d).toISOString().slice(0, 10) : "—";
}

/// The badge, which only ever reads MEDIUM or LOW. HIGH is reserved for a lane with matured
/// prospective outcomes; everything validated so far is validated on a holdout, and a holdout is
/// still a backtest.
function Badge({ level }: { level: "MEDIUM" | "LOW" }) {
  const tone = level === "MEDIUM"
    ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
    : "border-border bg-muted text-muted-foreground";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold tracking-wide ${tone}`}>
      {level} CONFIDENCE
    </span>
  );
}

export default async function DecisionPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ style?: string }>;
}) {
  const { symbol } = await params;
  const { style } = await searchParams;
  const asset = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  if (!asset) notFound();

  const market = canonicalMarket(marketOf({ assetType: asset.assetType, industry: asset.industry ?? null }));
  const chosen = style && (TIMEFRAME_ORDER as string[]).includes(style)
    ? (style as TimeframeName) : null;
  const fresh = await getAssetFreshness(asset.id).catch(() => null);

  // An asset whose market cannot be classified gets no styles and no direction. Guessing a group
  // here would hand it the capability table of a market it may not trade in.
  if (!market) {
    return (
      <Section title={`${asset.symbol} — ${asset.name}`}>
        <Empty>
          This asset is not classified into one of the five markets, so no trading style can be
          offered for it. Its stored data is on its{" "}
          <Link href={`/preview/asset/${encodeURIComponent(asset.symbol)}`}
                className="text-primary underline underline-offset-2">research page</Link>.
        </Empty>
      </Section>
    );
  }

  // Every timeframe this market could ever be graded on, with the two reasons it might not be
  // offered kept apart: the scorer cannot judge it, or nobody has validated a direction for it.
  const options = TIMEFRAME_ORDER.map((tf) => {
    const cap = capabilityFor(market, tf);
    const sessions = TIMEFRAME_SESSIONS[tf];
    const verdict = verdictFor(market, sessions);
    return { tf, sessions, judgeable: cap?.outcome.verifiable ?? false, verdict, cap };
  });

  const current = chosen ? options.find((o) => o.tf === chosen) ?? null : null;
  const prediction = current?.judgeable
    ? await getAssetPrediction(asset.symbol, current.sessions).catch(() => null)
    : null;

  return (
    <>
      <Section title={`${asset.symbol} — ${asset.name}`}>
        <p className="text-muted-foreground text-sm">
          {MARKET_LABELS[market] ?? market} · stored close {day(fresh?.newest)}
          {fresh?.priceSource ? <> · {fresh.priceSource}</> : null} ·{" "}
          <Link href={`/preview/asset/${encodeURIComponent(asset.symbol)}`}
                className="text-primary underline underline-offset-2">
            full research
          </Link>
        </p>
      </Section>

      <Section title="Trading style and forecast duration">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {options.map((o) => {
            const label = TIMEFRAME_LABELS[o.tf] ?? o.tf;
            const length = o.sessions === 0 ? "intra-session" : `${o.sessions} session${o.sessions === 1 ? "" : "s"}`;
            if (!o.judgeable) {
              // Not offered, and the reason is the scorer's, not a preference.
              return (
                <div key={o.tf}
                     className="border-border text-muted-foreground rounded-lg border border-dashed px-3 py-3 text-sm">
                  <div className="font-medium">{label}</div>
                  <div className="mt-1 text-xs">{length}</div>
                  <div className="mt-2 text-xs">Cannot be graded from stored closes</div>
                </div>
              );
            }
            const on = o.tf === chosen;
            const has = o.verdict.kind === "directional";
            return (
              <Link
                key={o.tf}
                href={`/preview/asset/${encodeURIComponent(asset.symbol)}/decision?style=${o.tf}`}
                className={`rounded-lg border px-3 py-3 text-sm transition ${
                  on ? "border-primary bg-primary/5" : "border-border hover:bg-muted"}`}
              >
                <div className="font-medium">{label}</div>
                <div className="text-muted-foreground mt-1 text-xs">{length}</div>
                <div className={`mt-2 text-xs ${has ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}`}>
                  {has ? "Validated signal" : "No validated signal"}
                </div>
              </Link>
            );
          })}
        </div>
      </Section>

      {!current ? (
        <Section title="The brain's decision">
          <Empty>Choose a trading style above to see what has been recorded for it.</Empty>
        </Section>
      ) : (
        <Section title="The brain's decision">
          {current.verdict.kind === "untested" ? (
            <Card>
              <div className="text-2xl font-semibold">No direction</div>
              <p className="text-muted-foreground mt-2 text-sm">
                Nothing has been measured for {MARKET_LABELS[market] ?? market} over{" "}
                {current.sessions} sessions. That is not a finding that a direction would be wrong —
                it is that no test has been run, so there is nothing to report.
              </p>
            </Card>
          ) : current.verdict.kind === "refused" ? (
            <>
              <Card>
                <div className="text-2xl font-semibold">No direction</div>
                <p className="text-muted-foreground mt-2 text-sm">
                  A direction was tested here and did not hold.
                </p>
              </Card>
              {current.verdict.lanes.filter((l) => !l.validated).map((l) => (
                <Note key={l.side}>
                  <strong>{l.side} suppressed.</strong> {l.why}
                </Note>
              ))}
            </>
          ) : !prediction ? (
            <Card>
              <div className="text-2xl font-semibold">Nothing recorded yet</div>
              <p className="text-muted-foreground mt-2 text-sm">
                This market and horizon carry a validated {current.verdict.side} signal, but no
                prediction has been recorded for {asset.symbol} at {current.sessions} sessions. The
                site reads recorded predictions; it does not generate one on request, so that what
                is shown is the same row the scorer will later grade.
              </p>
            </Card>
          ) : sideOfClass(prediction.predicted) !== current.verdict.side ? (
            <>
              <Card>
                <div className="text-2xl font-semibold">No direction</div>
                <p className="text-muted-foreground mt-2 text-sm">
                  The recorded prediction for {asset.symbol} is{" "}
                  <strong>{prediction.predicted ?? "none"}</strong>
                  {prediction.predicted === "FLAT"
                    ? ", which is no move clearing the band rather than a direction."
                    : <>, and only {current.verdict.side} has survived testing on this market and
                       horizon.</>}{" "}
                  The prediction is kept and will be graded; it is not shown as a call.
                </p>
              </Card>
              {current.verdict.kind === "directional" ? null : null}
            </>
          ) : (
            <>
              <Card>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="text-4xl font-semibold tracking-tight">
                    {current.verdict.side}
                  </div>
                  <Badge level={current.verdict.confidence} />
                </div>
                <p className="text-muted-foreground mt-3 text-sm">
                  Over {current.sessions} sessions from {day(prediction.asOf)}, maturing{" "}
                  {day(prediction.maturesAfter)}.
                  {prediction.referencePrice !== null ? (
                    <> Reference price {prediction.referencePrice.toFixed(2)}.</>
                  ) : null}
                </p>
              </Card>
              {/* A lane can be validated on one side and refused on the other, and a reader who
                  sees LONG is entitled to know the other side was looked at. Without this the
                  absence of SHORT reads as "not tried" when it is in fact "tried and failed". */}
              {laneFor(market, current.sessions, current.verdict.side === "LONG" ? "SHORT" : "LONG")
                ?.validated === false ? (
                <Note>
                  <strong>
                    {current.verdict.side === "LONG" ? "SHORT" : "LONG"} is suppressed here.
                  </strong>{" "}
                  {laneFor(market, current.sessions,
                           current.verdict.side === "LONG" ? "SHORT" : "LONG")!.why}
                </Note>
              ) : null}
              <Note>
                This is research, not advice, and not a profitability claim. The evidence behind the
                badge is a holdout lift of{" "}
                {((current.verdict.lane.evidence.lift ?? 0) * 100).toFixed(1)} points over a
                baseline knowable at the cutoff, with a date-blocked bootstrap z of{" "}
                {current.verdict.lane.evidence.blockedBootstrapZ} across{" "}
                {current.verdict.lane.evidence.holdoutSessions} sessions, positive in{" "}
                {current.verdict.lane.evidence.walkForwardPositive} of{" "}
                {current.verdict.lane.evidence.walkForwardFolds} walk-forward folds. No transaction
                cost, spread or borrow is in that number.
              </Note>
            </>
          )}
        </Section>
      )}

      {current?.judgeable ? (
        <Section title="How a direction earns its place here">
          <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm">
            {VALIDATION_REQUIREMENTS.map((r) => <li key={r}>{r}</li>)}
          </ul>
          <Note>
            A badge never reads HIGH. Everything validated so far is validated on a historical
            holdout, which is still a backtest; HIGH is reserved for a lane whose prospective
            predictions have matured and been graded.
          </Note>
          {/* When the table was computed, and what it does and does not claim. A validation that
              does not say how old it is invites a reader to assume it is current. */}
          <p className="text-muted-foreground mt-2 text-xs">
            Validation table computed {VALIDATION_GENERATED_AT.slice(0, 10)} — {VALIDATION_STATUS}
          </p>
        </Section>
      ) : null}
    </>
  );
}
