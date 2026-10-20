import Link from "next/link";
import { Card, Empty, Note, Section } from "@/components/ui";
import { getAssetPrediction } from "@/lib/queries";
import { canonicalMarket, capabilityFor } from "@/lib/marketCapability";
import {
  TIMEFRAME_LABELS, TIMEFRAME_ORDER, TIMEFRAME_SESSIONS, type TimeframeName,
} from "@/lib/marketMarkets";
import {
  laneFor, predictionIsCovered, sideOfClass, verdictFor,
  VALIDATION_GENERATED_AT, VALIDATION_REQUIREMENTS, VALIDATION_STATUS,
} from "@/lib/signalValidation";
import { bandReadingFor, type BandVerdict } from "@/lib/bandReadings";
import { asTimesIn, bandDirectionIsServable } from "@/lib/bandReading";
import {
  coverageReadyShare, whyNoReading, COVERAGE_GENERATED_AT,
} from "@/lib/coverageRegistry";

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
          <PendingCard symbol={symbol} sessions={current.sessions} side={current.verdict.side} />
        ) : !predictionIsCovered(current.verdict.lane, prediction.modelVersion) ? (
          // The recorded prediction came from a different artifact than the one the evidence was
          // gathered on. It is kept and will be graded; it is not shown as a validated call, and
          // the badge is not printed beside somebody else's numbers.
          <Card>
            <div className="text-2xl font-semibold">No direction</div>
            <p className="text-muted-foreground mt-2 text-sm">
              The recorded prediction for {symbol} comes from{" "}
              <strong className="font-mono text-xs">{prediction.modelVersion}</strong>, and the
              evidence for this market and horizon was measured on{" "}
              <strong className="font-mono text-xs">
                {current.verdict.lane.modelVersion ?? "an unrecorded model"}
              </strong>
              . A confidence badge belongs to the model it was measured on, so none is shown. The
              prediction is kept and will be graded.
            </p>
          </Card>
        ) : prediction.predicted === "FLAT" ? (
          <BandCard
            symbol={symbol}
            sessions={current.sessions}
            asOf={prediction.asOf}
            reading={bandReadingFor(
              canon ?? market,
              current.sessions,
              prediction.modelVersion,
            )}
          />
        ) : sideOfClass(prediction.predicted) !== current.verdict.side ? (
          <Card>
            <div className="text-2xl font-semibold">No direction</div>
            <p className="text-muted-foreground mt-2 text-sm">
              The recorded prediction for {symbol} is{" "}
              <strong>{prediction.predicted ?? "none"}</strong>, and only{" "}
              {current.verdict.side} has survived testing on this market and horizon. The
              prediction is kept and will be graded; it is not shown as a call.
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


/// What an asset inside the band gets: the magnitude the brain actually claimed, with the rate at
/// which that claim has held, and an explicit statement that no side is offered.
///
/// Three failure modes were available here and this avoids all three. Printing SHORT because the
/// model did not say UP would be inventing a direction the model never gave. Printing "No
/// direction" -- what the site did until now -- throws away a tested claim and reads as an outage.
/// Printing "we expect it to stay inside the band" as a bare fact would overstate a call that is
/// right about two times in five.
///
/// So the claim is shown *with its hit rate*, and the missing side is shown as the measured
/// refusal it is. Numbers come from the reading for this very model version; a prediction from a
/// model nothing has measured gets the honest `unmeasured` wording instead of another model's
/// numbers.
function BandCard({
  symbol,
  sessions,
  asOf,
  reading,
}: {
  symbol: string;
  sessions: number;
  asOf: Date | string | null;
  reading: BandVerdict;
}) {
  if (reading.kind === "unmeasured") {
    return (
      <Card>
        <div className="text-2xl font-semibold">No big move expected</div>
        <p className="text-muted-foreground mt-2 text-sm">
          The brain expects {symbol} to stay inside its band over the next {sessions} sessions,
          so it offers no side. How often that call has held has not been measured for this
          model, so no hit rate is shown — and none is borrowed from another model. The
          prediction is kept and will be graded.
        </p>
      </Card>
    );
  }

  const r = reading.reading;
  const m = r.magnitude;
  const hit = asTimesIn(m.precisionOnRowsCalledFlat);
  const bounds = r.tests.blockedBootstrap?.ci95;
  const ci = bounds && bounds.length === 2 ? bounds : null;
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-3xl font-semibold tracking-tight">No big move expected</div>
          <span className="border-border text-muted-foreground rounded-full border px-3 py-1 text-xs font-semibold tracking-wide">
            NO SIDE
          </span>
        </div>
        <p className="text-muted-foreground mt-3 text-sm">
          Over {sessions} sessions the brain expects {symbol} to stay inside{" "}
          <strong>±{m.thresholdPct}%</strong>
          {asOf ? <> from {new Date(asOf).toISOString().slice(0, 10)}</> : null}. That is a claim
          about <strong>size</strong>, not about direction.
        </p>
      </Card>

      <Note>
        <p>
          <strong>How often that has held:</strong> about {hit.times} times in {hit.of}. On{" "}
          {r.n.toLocaleString()} past readings this model called the same way,{" "}
          {pct(m.precisionOnRowsCalledFlat)} really stayed inside the band, against{" "}
          {pct(m.rateAcrossAllHoldoutRows)} for an average reading — a real edge of{" "}
          {pct(m.lift)}, but one that is wrong more often than it is right. Treat it as a reason
          to expect a quiet stretch, not as a promise of one.
        </p>
        {/* Read from the reading rather than written into the sentence. If a regenerated
            artifact ever says GO, the paragraph below would otherwise go on asserting that the
            direction came out as noise -- a false statement the card would have no way to notice.
            The measurement drives the wording; the wording does not outlive the measurement. */}
        {bandDirectionIsServable(r) ? (
          <p className="mt-2">
            <strong>Direction inside the band has now survived testing</strong> — a lift of{" "}
            {(r.lift * 100).toFixed(2)} percentage points
            {ci ? (
              <>
                , 95% interval [{(ci[0] * 100).toFixed(2)}, {(ci[1] * 100).toFixed(2)}]
              </>
            ) : null}
            . A LOW-confidence side is not shown here yet: that needs each prediction to record
            its own P(UP) − P(DOWN) margin, which the recorder does not yet store. Until it
            does, this page states the magnitude only rather than guessing which of the two
            sides this particular asset falls on.
          </p>
        ) : (
          <p className="mt-2">
            <strong>Why no LONG or SHORT:</strong> the direction inside the band was tested on
            the same readings and came out as noise — {(r.lift * 100).toFixed(2)} percentage
            points
            {ci ? (
              <>
                , with a 95% interval of [{(ci[0] * 100).toFixed(2)},{" "}
                {(ci[1] * 100).toFixed(2)}] points that spans zero
              </>
            ) : null}
            . A side is withheld because it was measured and failed, not because nothing was
            looked at.
          </p>
        )}
      </Note>
    </>
  );
}


/// Why there is no recorded reading, specifically — in place of "Nothing recorded yet".
///
/// That sentence was true and useless: it covered an asset with 25 sessions of history, an asset
/// whose newest bar is three weeks old, and an asset the recorder has simply not reached, without
/// distinguishing them. Only the third is a wait; the first two are gaps, and a reader who is not
/// told which is left to guess whether the site is broken.
///
/// The data half of the answer is precomputed per asset by
/// `tools/foundation/coverage_registry.py`, so this is a lookup rather than four queries.
function PendingCard({
  symbol,
  sessions,
  side,
}: {
  symbol: string;
  sessions: number;
  side: string;
}) {
  const reason = whyNoReading(symbol, sessions);
  const { ready, total } = coverageReadyShare();
  const asOf = COVERAGE_GENERATED_AT.slice(0, 10);

  if (reason.kind === "data") {
    // A real gap, named with its number, because "insufficient data" on its own is the same shrug
    // in different words. The heading splits by kind: a feature gap is not a short history, and
    // telling a reader their 1,960 sessions are "not enough history" would simply be false.
    const c = reason.coverage;
    const isFeatureGap = reason.status === "feature-gap";
    const smallIndustry = c.gapKind === "small-industry";
    return (
      <Card>
        <div className="text-2xl font-semibold">
          {smallIndustry
            ? "Too few comparable assets"
            : isFeatureGap
              ? "Missing an input the model needs"
              : "Not enough history yet"}
        </div>
        <p className="text-muted-foreground mt-2 text-sm">
          {smallIndustry ? (
            <>
              {symbol} has {c.bars.toLocaleString()} stored sessions, which is plenty — the gap is
              not its history. The model reads every asset partly against its industry, and{" "}
              {c.industry} holds only {c.industryMembers} tracked assets, which leaves{" "}
              {(c.industryMembers ?? 1) - 1} to compare against where {c.peersNeeded} are needed.
              Below that the &ldquo;industry move&rdquo; is one or two names, so rather than
              publish a comparison that was never really made, the recorder declines to read this
              asset at all.
            </>
          ) : isFeatureGap ? (
            <>
              {symbol} has {c.bars.toLocaleString()} stored sessions, which is enough history —
              but a reading also needs every input the model relied on while training, and{" "}
              {c.imputedCount ?? "some"} of its {" "}
              inputs are not observed here. Rather than filling them with a training average and
              calling the result a reading, the recorder refuses the row.
            </>
          ) : (
            <>
              No reading can be computed for {symbol}: {reason.why}.
              {c.newest ? <> The newest stored session is {c.newest}.</> : null}
            </>
          )}{" "}
          {smallIndustry
            ? " This is a limit of the tracked universe, not a judgement about the asset."
            : " This is a gap in the stored data, not a judgement about the asset — once it is filled the reading follows automatically."}
        </p>
        <details className="border-border mt-3 rounded-lg border px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium">What exactly is missing</summary>
          <p className="text-muted-foreground mt-2 text-xs">{reason.why}</p>
        </details>
        <p className="text-muted-foreground mt-2 text-xs">
          {ready} of {total} assets can be read today; this is one of the {total - ready} that
          cannot. Coverage measured {asOf}.
        </p>
      </Card>
    );
  }

  if (reason.kind === "unknown") {
    return (
      <Card>
        <div className="text-2xl font-semibold">Coverage not measured</div>
        <p className="text-muted-foreground mt-2 text-sm">
          {symbol} is not in the coverage table computed on {asOf}, so whether its history supports
          a reading has not been established. That is a gap in the measurement rather than a
          statement about the asset, and it is shown rather than guessed at.
        </p>
      </Card>
    );
  }

  // Data-ready and unrecorded: the common case, and the one the old wording obscured most. With
  // 618 of 620 assets data-ready, nearly every empty page on the site is this.
  const c = reason.coverage;
  return (
    <Card>
      <div className="text-2xl font-semibold">Reading pending</div>
      <p className="text-muted-foreground mt-2 text-sm">
        {symbol} has the history a reading needs — {c.bars.toLocaleString()} stored sessions
        through {c.newest} — and this market and horizon carry a validated {side} signal. No
        prediction row has been written for it yet. The site reads recorded predictions and does
        not generate one on request, so what appears here will be the same row the scorer later
        grades.
      </p>
      <p className="text-muted-foreground mt-2 text-xs">
        {ready} of {total} assets are data-ready as of {asOf}, so an empty page here is a recording
        gap rather than a data gap.
      </p>
    </Card>
  );
}
