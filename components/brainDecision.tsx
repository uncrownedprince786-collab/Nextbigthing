import Link from "next/link";
import { Card, Empty, Note, Section } from "@/components/ui";
import { getAssetPrediction } from "@/lib/queries";
import { canonicalMarket, capabilityFor } from "@/lib/marketCapability";
import {
  TIMEFRAME_LABELS, TIMEFRAME_ORDER, TIMEFRAME_SESSIONS, type TimeframeName,
} from "@/lib/marketMarkets";
import {
  laneFor, sideOfClass, verdictFor,
  VALIDATION_GENERATED_AT, VALIDATION_REQUIREMENTS, VALIDATION_STATUS,
} from "@/lib/signalValidation";

/// The brain's half of an asset page: pick a trading style, get a direction or a reason there
/// isn't one.
///
/// **It lives on the asset page, not on a page of its own.** A reader who has chosen an
/// instrument should not have to navigate away to find out what the model says about it, and the
/// style they pick is a property of the question they are asking about *this* asset — not a
/// separate destination. The style arrives as a `?style=` search parameter, so the whole thing
/// stays a server component with no client JavaScript and every state is a real, linkable URL.
///
/// **This is not the rule table.** The panel above it on the asset page is a fixed set of
/// deterministic rules over stored data, and it has its own confidence wording. This component
/// renders only what has survived testing, which is one lane. Keeping them visibly apart is the
/// point: a reader must be able to tell a rule firing from a model that has been measured, and
/// before 2026-10-20 the site gave them no way to.
///
/// Three things must all hold before a direction appears, and each fails on its own:
///   1. the horizon can be graded from stored closes at all (`marketCapability`);
///   2. a side has survived testing on this market and horizon (`signalValidation`);
///   3. a prediction has actually been recorded for this asset — the web layer reads rows, it
///      does not run a model (brain.md rule 5).
export async function BrainDecision({
  symbol,
  market,
  style,
}: {
  symbol: string;
  market: string;
  style?: string;
}) {
  const chosen = style && (TIMEFRAME_ORDER as readonly string[]).includes(style)
    ? (style as TimeframeName)
    : null;

  // The page hands a market word; `canonicalMarket` is the one place the site's vocabulary and
  // the research vocabulary are reconciled (PSX/PK), so it is used here rather than assumed.
  const canon = canonicalMarket(market);
  const options = TIMEFRAME_ORDER.map((tf) => {
    const cap = canon ? capabilityFor(canon, tf) : null;
    const sessions = TIMEFRAME_SESSIONS[tf];
    return {
      tf,
      sessions,
      judgeable: cap?.outcome.verifiable ?? false,
      verdict: verdictFor(market, sessions),
    };
  });

  const current = chosen ? options.find((o) => o.tf === chosen) ?? null : null;
  const prediction = current?.judgeable
    ? await getAssetPrediction(symbol, current.sessions).catch(() => null)
    : null;

  const href = (tf: string) => `/asset/${encodeURIComponent(symbol)}?style=${tf}#brain`;
  const day = (d: Date | string | null | undefined) =>
    d ? new Date(d).toISOString().slice(0, 10) : "—";

  return (
    <div id="brain" className="scroll-mt-4">
      <Section
        title="The brain"
        lead="A trained model, separate from the rule table above. Pick the horizon you are asking about."
      >
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {options.map((o) => {
            const label = TIMEFRAME_LABELS[o.tf] ?? o.tf;
            const length = o.sessions === 0
              ? "intra-session"
              : `${o.sessions} session${o.sessions === 1 ? "" : "s"}`;
            if (!o.judgeable) {
              // Not offered, and the reason is the scorer's rather than a preference. Shown
              // rather than hidden, so a reader can see scalping was considered and refused.
              return (
                <div
                  key={o.tf}
                  className="border-border text-muted-foreground rounded-lg border border-dashed px-3 py-3 text-sm"
                >
                  <div className="font-medium">{label}</div>
                  <div className="mt-1 text-xs">{length}</div>
                  <div className="mt-2 text-xs">Not gradeable from stored closes</div>
                </div>
              );
            }
            const on = o.tf === chosen;
            const has = o.verdict.kind === "directional";
            return (
              <Link
                key={o.tf}
                href={href(o.tf)}
                className={`rounded-lg border px-3 py-3 text-sm transition ${
                  on ? "border-primary bg-primary/5" : "border-border hover:bg-muted"
                }`}
              >
                <div className="font-medium">{label}</div>
                <div className="text-muted-foreground mt-1 text-xs">{length}</div>
                <div
                  className={`mt-2 text-xs ${
                    has ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"
                  }`}
                >
                  {has ? "Validated signal" : "No validated signal"}
                </div>
              </Link>
            );
          })}
        </div>

        {!current ? (
          <Empty>Choose a trading style above to see what has been recorded for it.</Empty>
        ) : current.verdict.kind === "untested" ? (
          <Card>
            <div className="text-2xl font-semibold">No direction</div>
            <p className="text-muted-foreground mt-2 text-sm">
              Nothing has been measured for this market over {current.sessions} sessions. That is
              not a finding that a direction would be wrong — no test has been run, so there is
              nothing to report.
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
            {current.verdict.lanes
              .filter((l) => !l.validated)
              .map((l) => (
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
              prediction has been recorded for {symbol} at {current.sessions} sessions. The site
              reads recorded predictions; it does not generate one on request, so what is shown is
              the same row the scorer will later grade.
            </p>
          </Card>
        ) : sideOfClass(prediction.predicted) !== current.verdict.side ? (
          <Card>
            <div className="text-2xl font-semibold">No direction</div>
            <p className="text-muted-foreground mt-2 text-sm">
              The recorded prediction for {symbol} is{" "}
              <strong>{prediction.predicted ?? "none"}</strong>
              {prediction.predicted === "FLAT"
                ? ", which is no move clearing the band rather than a direction."
                : `, and only ${current.verdict.side} has survived testing on this market and horizon.`}{" "}
              The prediction is kept and will be graded; it is not shown as a call.
            </p>
          </Card>
        ) : (
          <>
            <Card>
              <div className="flex flex-wrap items-center gap-3">
                <div className="text-4xl font-semibold tracking-tight">{current.verdict.side}</div>
                <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-semibold tracking-wide text-amber-700 dark:text-amber-400">
                  {current.verdict.confidence} CONFIDENCE
                </span>
              </div>
              <p className="text-muted-foreground mt-3 text-sm">
                Over {current.sessions} sessions from {day(prediction.asOf)}, maturing{" "}
                {day(prediction.maturesAfter)}.
                {prediction.referencePrice !== null ? (
                  <> Reference price {prediction.referencePrice.toFixed(2)}.</>
                ) : null}
                {prediction.outcome ? (
                  <>
                    {" "}
                    Graded {day(prediction.outcome.observedOn)}:{" "}
                    <strong>{prediction.outcome.label ?? "recorded"}</strong>
                    {prediction.outcome.fwdPct !== null ? (
                      <> ({prediction.outcome.fwdPct >= 0 ? "+" : ""}
                      {prediction.outcome.fwdPct.toFixed(1)}%)</>
                    ) : null}
                    .
                  </>
                ) : null}
              </p>
            </Card>

            {/* A lane can be validated on one side and refused on the other, and a reader who
                sees LONG is entitled to know the other side was looked at. Without this, the
                absence of SHORT reads as "not tried" when it is "tried and failed". */}
            {laneFor(market, current.sessions, current.verdict.side === "LONG" ? "SHORT" : "LONG")
              ?.validated === false ? (
              <Note>
                <strong>
                  {current.verdict.side === "LONG" ? "SHORT" : "LONG"} is suppressed here.
                </strong>{" "}
                {
                  laneFor(
                    market,
                    current.sessions,
                    current.verdict.side === "LONG" ? "SHORT" : "LONG",
                  )!.why
                }
              </Note>
            ) : null}

            <Note>
              Research, not advice, and not a profitability claim. Behind the badge: a holdout lift
              of {((current.verdict.lane.evidence.lift ?? 0) * 100).toFixed(1)} points over a
              baseline knowable at the cutoff, a date-blocked bootstrap z of{" "}
              {current.verdict.lane.evidence.blockedBootstrapZ} across{" "}
              {current.verdict.lane.evidence.holdoutSessions} sessions, positive in{" "}
              {current.verdict.lane.evidence.walkForwardPositive} of{" "}
              {current.verdict.lane.evidence.walkForwardFolds} walk-forward folds. No transaction
              cost, spread or borrow is in that number.
            </Note>
          </>
        )}

        {current?.judgeable ? (
          <details className="border-border mt-3 rounded-lg border px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium">
              How a direction earns its place here
            </summary>
            <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5 text-sm">
              {VALIDATION_REQUIREMENTS.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <p className="text-muted-foreground mt-2 text-xs">
              A badge never reads HIGH: everything validated so far is validated on a historical
              holdout, which is still a backtest. Validation table computed{" "}
              {VALIDATION_GENERATED_AT.slice(0, 10)} — {VALIDATION_STATUS}
            </p>
          </details>
        ) : null}
      </Section>
    </div>
  );
}
