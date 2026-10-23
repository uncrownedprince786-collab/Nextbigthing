import Link from "next/link";
import { Card, Empty, Note, Section } from "@/components/ui";
import { ForecastChart } from "@/components/forecastChart";
import { forecastFor, type Forecast } from "@/lib/cryptoForecast";
import { HORIZON_GROUPS, HORIZONS, horizonFrom, type HorizonKey } from "@/lib/cryptoHorizons";
import {
  CONVICTION_RULE,
  HIGH_IS_UNREACHABLE,
  LANES_GENERATED_AT,
  LANE_REQUIREMENTS,
  lanesFor,
  type Lane,
} from "@/lib/cryptoLanes";
import { recordForecast, trackRecord } from "@/lib/forecastStore";
import { venueRowFor } from "@/lib/cryptoVenues";
import { plainPrice } from "@/lib/format";

/// The crypto brain: pick how long you are asking about, get UP or DOWN for exactly that window.
///
/// **What this replaced, and why.** The panel here used to offer "Scalp / Intraday / Short swing /
/// Swing / Position" -- five *trading styles* -- and every one of them answered "No validated
/// signal" for crypto. Two things were wrong with that and they are different problems. The first
/// is vocabulary: a style is a statement about how somebody trades, and more than one reader took
/// the short style to be a short call. The second is that nothing was behind it: the only crypto
/// models that existed were three-class fits that had collapsed onto DOWN, correctly refused by
/// the validation table, so the picker was a row of buttons leading to the same sentence.
///
/// Both are fixed in the same place. The buttons are now durations -- five minutes to a month --
/// and each one is answered by a binary model fitted for that exact window, or carries the
/// measured reason it is not. The chart above the verdict is drawn from the very bars the model
/// read, so the picture and the direction cannot describe different moments.
///
/// It runs the model rather than reading a stored row, which is the one deliberate exception to
/// brain.md rule 5; the argument is in `lib/cryptoModel.ts` and the auditability the rule protects
/// is kept by writing the shown forecast down (`lib/forecastStore.ts`) for the scorer to grade.
export async function CryptoBrain({
  symbol,
  assetId,
  market,
  name,
  horizon,
}: {
  symbol: string;
  assetId: string;
  market: string;
  name: string;
  horizon?: string;
}) {
  const chosen = horizonFrom(horizon);
  const href = (h: string) => `/asset/${encodeURIComponent(symbol)}?h=${h}#forecast`;

  const forecast: Forecast | null = chosen ? await forecastFor(symbol, chosen.key) : null;
  // One lookup for the whole picker rather than one per button: the lane that answers each
  // window for *this* coin, following the same family fallback the forecast itself follows, so a
  // button cannot promise something the forecast then refuses.
  const byHorizon = new Map(lanesFor(symbol).map((l) => [l.horizon, l.lane]));

  // Written down before it is rendered, so the stored row is the row the reader sees. A failure
  // here never costs the reader the forecast; it costs the forecast its place in the record, and
  // the card says so.
  // A silence is recorded exactly like a call. It is the only way the floor that produced it can
  // be checked later against what the market actually did, and a threshold nobody can check is a
  // guess that has been promoted to a rule.
  let stored: { stored: boolean; why?: string } | null = null;
  if (forecast && forecast.kind === "direction") {
    stored = await recordForecast(assetId, market, symbol, forecast);
  }
  const record = chosen ? await trackRecord(assetId, chosen.key).catch(() => null) : null;

  return (
    <div id="forecast" className="scroll-mt-4">
      <Section
        title="The brain"
        lead={
          `A trained model, separate from the rule table above. It answers one question: which way ` +
          `${name} goes over a window you choose.`
        }
      >
        {/* The distinction the old picker lost, stated before the buttons rather than after
            them. It is first because it is the thing a reader can get wrong in the two seconds
            before they click, and no amount of explaining underneath undoes that. */}
        <Note>
          <strong>How long you are asking about is not which way it goes.</strong> Picking{" "}
          <em>Next 5 minutes</em> asks what the next five minutes do. The answer to that is{" "}
          <strong>UP</strong> or <strong>DOWN</strong>, and a short window is just as likely to
          come back UP as a long one. Nothing here is advice, a position size or a trade.
        </Note>

        {/* Every window gets a direction. What changes between them is how much the model is
            saying, and that is attached to the call rather than replacing it. */}
        <Note>
          <strong>Every window gets a direction, and they are not equally strong.</strong> A{" "}
          <strong>strong</strong> call is one whose probability cleared the floor the holdout
          measured — about one bar in ten, and the band where the model was most often right. A{" "}
          <strong>weak</strong> one is the same model on a bar it is closer to even about. Both
          print the accuracy measured on their own band.
        </Note>

        <p className="mt-4 text-sm font-medium">How long are you asking about?</p>
        <div className="mt-2 space-y-3">
          {HORIZON_GROUPS.map((g) => (
            <div key={g.title}>
              <p className="text-muted-foreground text-xs">
                <span className="font-medium">{g.title}</span> — {g.note}.
              </p>
              <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {g.keys.map((k) => (
                  <HorizonButton
                    key={k}
                    k={k}
                    lane={byHorizon.get(k) ?? null}
                    on={chosen?.key === k}
                    href={href(k)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        {!chosen ? (
          <Empty>
            Choose a window above. Nothing is chosen for you: a direction over five minutes and a
            direction over a month are two different claims, and the site will not pick which one
            you meant.
          </Empty>
        ) : (
          <div
            className="mt-4"
            /* The panel's state, named. `tools/ui_audit.py` reads this rather than matching
               sentences: the first version matched the words "which way it goes", which also
               appear in the note above the picker explaining that a window is not a direction, so
               every page looked like a direction panel. A state a checker can read is not
               decoration -- it is the difference between a check that works and one that lies. */
            data-forecast={forecast!.kind}
            data-horizon={chosen.key}
            data-direction={forecast!.kind === "direction" ? forecast!.direction : undefined}
            /* A quiet panel is a working panel, and the audit has to be able to tell it from a
               venue failure that also prints no direction. */
            data-margin={
              forecast!.kind === "direction" ? forecast!.margin.toFixed(4) : undefined
            }
            data-strength={forecast!.kind === "direction" ? forecast!.strength : undefined}
          >
            <ForecastBody
              forecast={forecast!}
              symbol={symbol}
              name={name}
              stored={stored}
              record={record}
            />
          </div>
        )}

        <details className="border-border mt-4 rounded-lg border px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium">
            How a direction earns its place here
          </summary>
          <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5 text-sm">
            {LANE_REQUIREMENTS.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {CONVICTION_RULE ? (
            <p className="text-muted-foreground mt-2 text-sm">
              <strong>And when it may speak at all.</strong> {CONVICTION_RULE}
            </p>
          ) : null}
          <p className="text-muted-foreground mt-2 text-xs">
            {HIGH_IS_UNREACHABLE} Lane table computed {LANES_GENERATED_AT.slice(0, 10)}.
          </p>
        </details>
      </Section>
    </div>
  );
}

/// One duration. Carries what is known about it before it is clicked -- offered, tested and
/// refused, or never fitted -- so the picker is informative rather than a row of identical boxes.
function HorizonButton({
  k,
  lane,
  on,
  href,
}: {
  k: HorizonKey;
  lane: Lane | null;
  on: boolean;
  href: string;
}) {
  const h = HORIZONS[k];
  const state = !lane
    ? { text: "Not fitted yet", tone: "text-muted-foreground" }
    : !lane.servable
      ? { text: "Tested, refused", tone: "text-muted-foreground" }
      : {
          text: `Direction · ${lane.confidence}`,
          tone: "text-amber-700 dark:text-amber-400",
        };
  return (
    <Link
      href={href}
      className={`rounded-lg border px-3 py-3 text-sm transition ${
        on ? "border-primary bg-primary/5" : "border-border hover:bg-muted"
      }`}
    >
      <div className="font-medium">{h.label}</div>
      <div className={`mt-2 text-xs ${state.tone}`}>{state.text}</div>
    </Link>
  );
}

function ForecastBody({
  forecast,
  symbol,
  name,
  stored,
  record,
}: {
  forecast: Forecast;
  symbol: string;
  name: string;
  stored: { stored: boolean; why?: string } | null;
  record: Awaited<ReturnType<typeof trackRecord>> | null;
}) {
  const h = forecast.horizon;

  if (forecast.kind === "no-model") {
    return (
      <Card>
        <div className="text-2xl font-semibold">Not fitted yet</div>
        <p className="text-muted-foreground mt-2 text-sm">
          No model has been trained for {h.label.toLowerCase()} on crypto, so there is nothing to
          report. That is an absence of work, not a finding that a direction would be wrong — and
          it is shown rather than filled with a model fitted for a different window.
        </p>
      </Card>
    );
  }

  if (forecast.kind === "refused") {
    const e = forecast.lane.evidence;
    return (
      <>
        <Card>
          <div className="text-2xl font-semibold">Tested, and refused</div>
          <p className="text-muted-foreground mt-2 text-sm">
            A model was fitted for {h.label.toLowerCase()} and did not earn a direction:{" "}
            {forecast.why}. It is kept and its numbers are below; no direction is served from it.
          </p>
        </Card>
        <Note>
          On {e.testRows.toLocaleString()} unseen rows from {e.testFrom?.slice(0, 10)} to{" "}
          {e.testTo?.slice(0, 10)} it scored {(e.accuracy * 100).toFixed(2)}% against a{" "}
          {(e.testMajority * 100).toFixed(2)}% largest class. A model that cannot beat naming one
          direction has not read direction, and the site would rather say that than round it up.
        </Note>
      </>
    );
  }

  if (forecast.kind === "no-source") {
    const row = venueRowFor(symbol);
    return (
      <Card>
        <div className="text-2xl font-semibold">No intraday series for {name}</div>
        <p className="text-muted-foreground mt-2 text-sm">
          {forecast.why}. {name} keeps its daily closes
          {row?.dailySnapshots ? ` — ${row.dailySnapshots.toLocaleString()} of them` : ""}
          {row?.newestClose ? `, newest ${row.newestClose}` : ""} — and everything above on this
          page is read from them. A short-horizon direction needs bars this coin has no free venue
          for, so none is offered rather than one being computed from daily data and labelled as
          minutes.
        </p>
      </Card>
    );
  }

  if (forecast.kind === "data") {
    return (
      <>
        <Card>
          <div className="text-2xl font-semibold">The bars are not there yet</div>
          <p className="text-muted-foreground mt-2 text-sm">
            A model is ready for {h.label.toLowerCase()}, and the bars behind it are not: {forecast.why}.
            Nothing was filled in to cover it — a forward-filled bar is a claim that the market did
            not move, which is different from not knowing.
          </p>
        </Card>
        {forecast.tried.length ? (
          <Note>
            <strong>What was asked.</strong>{" "}
            {forecast.tried.map((t) => `${t.venue}: ${t.outcome}`).join("; ")}.
          </Note>
        ) : null}
      </>
    );
  }

  if (forecast.kind === "error") {
    return (
      <Card>
        <div className="text-2xl font-semibold">Not served</div>
        <p className="text-muted-foreground mt-2 text-sm">
          This horizon could not be answered in this build: {forecast.why}. That is a fault here,
          not a statement about {name}, and it is printed rather than hidden behind &ldquo;no
          signal&rdquo;.
        </p>
      </Card>
    );
  }

  const f = forecast;
  const e = f.lane.evidence;
  const w = f.window;
  const marginPts = (Math.abs(f.probUp - 0.5) * 200).toFixed(1);
  const ageSec = Math.round(w.ageMs / 1000);
  const when = (d: Date) => d.toISOString().slice(0, 16).replace("T", " ") + " UTC";

  return (
    <>
      {/* The question and the answer, side by side and labelled, because the confusion this
          component exists to end is exactly between the two. */}
      <div className="border-border grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2">
        <div className="bg-background p-4">
          <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            You asked about
          </div>
          <div className="mt-1 text-xl font-semibold">{h.label}</div>
          <p className="text-muted-foreground mt-1 text-xs">
            {h.lead}, maturing {when(f.maturesAt)}.
          </p>
        </div>
        <div className="bg-background p-4">
          <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Which way it goes
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <span
              className={`text-4xl font-semibold tracking-tight ${
                f.direction === "UP" ? "text-[var(--up)]" : "text-[var(--down)]"
              }`}
            >
              {f.direction}
            </span>
            <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-semibold tracking-wide text-amber-700 dark:text-amber-400">
              {f.confidence} CONFIDENCE
            </span>
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            from {plainPrice(f.referencePrice)} at {when(f.asOf)}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <ForecastChart
          bars={w.bars}
          stepMs={w.stepMs}
          reference={f.referencePrice}
          horizonMinutes={h.minutes}
          horizonLabel={h.label}
          direction={f.direction}
          symbol={symbol}
        />
      </div>

      <Note>
        <p>
          <strong>What is behind it.</strong> {f.lane.modelVersion}, a binary model with no FLAT
          class, fitted on {f.lane.trainingRows.toLocaleString()} rows and tested on{" "}
          {e.testRows.toLocaleString()} later ones it never saw ({e.testFrom?.slice(0, 10)} to{" "}
          {e.testTo?.slice(0, 10)}). It was right on {(e.accuracy * 100).toFixed(2)}% of them,
          against {(e.testMajority * 100).toFixed(2)}% for naming the larger direction — an edge of{" "}
          {(e.marginOverMajority * 100).toFixed(2)} points, with a day-blocked bootstrap interval of
          [{(e.bootstrapCi95[0] * 100).toFixed(2)}, {(e.bootstrapCi95[1] * 100).toFixed(2)}] points
          over {e.bootstrapBlocks.toLocaleString()} days, above its own block majority in{" "}
          {e.walkForwardAbove} of {e.walkForwardBlocks} chronological blocks. It called UP on{" "}
          {(e.predictedUpShare * 100).toFixed(0)}% of the test fold, so it is reading direction
          rather than naming one.
        </p>
        <p className="mt-2">
          <strong>Read that number as it is.</strong> An edge of a point or two is real and small.
          It is a tilt in the odds, not a forecast that will usually be right in the way a weather
          forecast is, and no transaction cost, spread or funding is in it. This model is{" "}
          {(e.accuracy * 100).toFixed(1)}% accurate on its holdout, which is far below the 90% this
          project set as its historical acceptance target — that target has not been met and
          nothing here is presented as though it had.
        </p>
        {f.lane.conviction ? (
          <p className="mt-2">
            <strong>It cleared its floor to say this.</strong> This lane prints nothing until its
            probability is at least{" "}
            {(f.lane.conviction.floor * 200).toFixed(0)} points from even; today&apos;s is{" "}
            {marginPts}. On the test fold the{" "}
            {(f.lane.conviction.called.coverage * 100).toFixed(1)}% of rows that cleared the same
            floor were right {(f.lane.conviction.called.accuracy * 100).toFixed(2)}% of the time
            against a {(f.lane.conviction.called.majorityHere * 100).toFixed(2)}% largest class
            among them, with a day-blocked interval of [
            {(f.lane.conviction.called.bootstrapCi95[0] * 100).toFixed(2)},{" "}
            {(f.lane.conviction.called.bootstrapCi95[1] * 100).toFixed(2)}] points and{" "}
            {f.lane.conviction.called.walkForwardAbove} of{" "}
            {f.lane.conviction.called.walkForwardBlocks} chronological blocks above their own
            majority. The headline figure above is the same model answering every row, and both
            are shown because the second is what the first was traded for.
          </p>
        ) : null}
        {f.measured ? (
          <p className="mt-2">
            <strong>On calls as confident as this one.</strong> Today&apos;s margin is {marginPts}{" "}
            points away from an even call. On the test fold, the{" "}
            {(f.measured.coverage * 100).toFixed(0)}% of rows at least that confident were right{" "}
            {(f.measured.accuracy * 100).toFixed(2)}% of the time ({f.measured.rows.toLocaleString()}{" "}
            rows). That is reported because a reader is entitled to see whether the model is better
            where it is surer; it is not how the headline accuracy above was computed, which is
            every row.
          </p>
        ) : null}
      </Note>

      <Note>
        <p>
          <strong>The data this was read from.</strong> {w.bars.length} consecutive {h.interval}{" "}
          bars from {w.venue}
          {w.patchedFrom ? `, with ${w.checks.barsPatched} filled from ${w.patchedFrom}` : ""}, the
          newest closing {ageSec < 90 ? `${ageSec} seconds` : `${Math.round(ageSec / 60)} minutes`}{" "}
          ago.{" "}
          {w.quality === "ok"
            ? "Every input the model was trained on was observed."
            : `Inputs ${w.imputed.join(", ")} are not published by that venue and were set to their neutral value, so this is marked degraded.`}{" "}
          {w.checks.openBarsDropped > 0
            ? `The bar still running was dropped: a window that has not closed is a partial observation. `
            : ""}
          {w.checks.conflictingDuplicates > 0
            ? `${w.checks.conflictingDuplicates} conflicting duplicate bars were refused. `
            : ""}
          Fetched {w.fetchedAt.slice(11, 19)} UTC.
        </p>
        <p className="mt-2">
          <strong>Recorded.</strong>{" "}
          {stored?.stored
            ? `This exact forecast is in the record, keyed on the bar it was read from, and will be graded once ${when(f.maturesAt)} has passed. Reloading this page inside the same bar writes nothing new.`
            : `This forecast could not be written to the record (${stored?.why ?? "unknown"}), so it will not appear in the score later. The direction above is unaffected.`}
        </p>
      </Note>

      {record ? <RecordCard record={record} label={h.label} /> : null}
    </>
  );
}

/// What this coin and window have actually done since forecasts started being recorded.
///
/// Kept strictly apart from the holdout numbers above. The holdout is a backtest, however
/// carefully split; this is the only prospective evidence that exists, and until it has enough
/// matured results to divide by, it says so rather than printing a rate over a handful.
function RecordCard({
  record,
  label,
}: {
  record: Awaited<ReturnType<typeof trackRecord>>;
  label: string;
}) {
  const { graded, correct, pending, awaitingScore, accuracy, firstAt, quietGraded, quietCorrect } =
    record;
  if (graded + pending + awaitingScore + quietGraded === 0) {
    return (
      <Note>
        <strong>Prospective record: none yet.</strong> This is the first forecast recorded for{" "}
        {label.toLowerCase()} on this coin. Every one from here is stored before it can be judged
        and graded only after its window closes, so a rate will appear here once there are results
        to divide by.
      </Note>
    );
  }
  return (
    <Note>
      <strong>Prospective record for {label.toLowerCase()}.</strong>{" "}
      {graded >= 30 && accuracy !== null ? (
        <>
          {correct} of {graded} matured forecasts were right, {(accuracy * 100).toFixed(1)}%.
        </>
      ) : (
        <>
          {graded} matured forecast{graded === 1 ? "" : "s"} graded so far
          {graded > 0 ? `, ${correct} right` : ""} — under the 30 this site requires before it
          reports a rate, so none is shown.
        </>
      )}{" "}
      {pending} still inside their window and {awaitingScore} matured but not yet graded.
      {quietGraded > 0 ? (
        <>
          {" "}
          Separately, {quietGraded} bar{quietGraded === 1 ? " was" : "s were"} read and left
          uncalled, and the lean {quietGraded === 1 ? "it" : "they"} did not print would have been
          right {quietCorrect} time{quietCorrect === 1 ? "" : "s"}. That is never added to the rate
          above — it is the check on the floor, not a claim the site made.
        </>
      ) : null}
      {firstAt ? ` Recording started ${firstAt.toISOString().slice(0, 16).replace("T", " ")} UTC.` : ""}{" "}
      This is forward evidence and the only kind that is not a backtest.
    </Note>
  );
}
