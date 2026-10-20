import type { Metadata } from "next";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { getShadowPredictions } from "@/lib/queries";
import { ForecastRecord } from "@/components/forecastRecord";

/// Screen 7 — recorded predictions and their outcomes.
///
/// The screen the maturity rule exists for. A prediction made for a twenty-session horizon has no
/// outcome until that horizon has elapsed, and the single most misleading thing this page could
/// do is let an unelapsed horizon read as a result. So the three states are shown as three
/// numbers and never summed into one:
///
///   awaiting   the horizon has not passed. Not a miss, not a FLAT, not a result.
///   matured    the horizon passed and nothing has scored it yet. Work owed, shown as owed.
///   scored     an outcome exists. Only these may ever enter an accuracy figure.
///
/// There is no accuracy figure on this page today, because `scored` is zero. An accuracy over
/// zero scored records is not a small number, it is not a number, and printing `0%` would be a
/// claim about a model that has not been measured.
export const revalidate = 900;
export const metadata: Metadata = { title: "Predictions" };

function fmt(d: Date | null | undefined) {
  return d ? new Date(d).toISOString().slice(0, 10) : "—";
}

export default async function PredictionsPage() {
  const s = await getShadowPredictions(100).catch(() => null);

  if (!s) {
    return (
      <Section title="Recorded predictions">
        <Empty>
          The prediction store could not be read, so nothing is shown. An empty table here would
          be indistinguishable from &ldquo;no predictions exist&rdquo;, and those are different facts.
        </Empty>
      </Section>
    );
  }

  return (
    <>
      <Section title="Recorded predictions">
        <Card>
          <p className="text-sm leading-relaxed">
            These come from <strong>{s.modelVersions.join(", ") || "no model"}</strong>, which is
            <strong> not approved for production</strong>. They are recorded so that their outcomes
            can be measured once each horizon has elapsed — they are not advice and not a
            published call.
          </p>
          {s.anyApproved ? (
            <p className="mt-2 text-sm font-semibold text-red-600">
              A record is marked approved. That should not be possible; treat this page as faulty.
            </p>
          ) : null}
        </Card>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Card>
            <div className="text-2xl font-semibold">{s.awaitingMaturity}</div>
            <div className="text-sm text-muted-foreground">
              awaiting maturity{s.earliestMaturity ? <> — earliest {fmt(s.earliestMaturity)}</> : null}
            </div>
          </Card>
          <Card>
            <div className="text-2xl font-semibold">{s.maturedAwaitingOutcome}</div>
            <div className="text-sm text-muted-foreground">matured, outcome not yet recorded</div>
          </Card>
          <Card>
            <div className="text-2xl font-semibold">{s.scored}</div>
            <div className="text-sm text-muted-foreground">scored against a real outcome</div>
          </Card>
        </div>

        {/* Per horizon, because the totals above are the only honest thing to say about the whole
            table and the only useless thing to say about either lane. A 5-session call is judged
            on the week after it against a +/-1% band; a 20-session call is judged on the month
            after it against +/-2%. They mature weeks apart, so one number for "awaiting" hides
            which of them anyone is actually waiting for, and the earliest date above belongs to
            whichever lane is slowest. */}
        {s.byHorizon.length > 1 ? (
          <Section title="By forward horizon">
            <Table
              head={
                <>
                  <th className="px-3 py-2 text-right">Horizon</th>
                  <th className="px-3 py-2 text-left">Models</th>
                  <th className="px-3 py-2 text-right">Records</th>
                  <th className="px-3 py-2 text-right">Awaiting</th>
                  <th className="px-3 py-2 text-right">Matured, unscored</th>
                  <th className="px-3 py-2 text-right">Scored</th>
                  <th className="px-3 py-2 text-left">First result possible</th>
                </>
              }
            >
              {s.byHorizon.map((h) => (
                <tr key={h.horizonSessions}>
                  <td className="px-3 py-2 text-right">{h.horizonSessions}</td>
                  <td className="px-3 py-2 font-mono text-xs">{h.modelVersions.join(", ")}</td>
                  <td className="px-3 py-2 text-right">{h.total}</td>
                  <td className="px-3 py-2 text-right">{h.awaitingMaturity}</td>
                  <td className="px-3 py-2 text-right">{h.maturedAwaitingOutcome}</td>
                  <td className="px-3 py-2 text-right">{h.scored}</td>
                  <td className="px-3 py-2">{fmt(h.earliestMaturity)}</td>
                </tr>
              ))}
            </Table>
            <Note>
              Each row is a different question. A 5-session call asks where a name is a week from
              its decision session and is graded against a ±1% band; a 20-session call asks about
              the month after it, against ±2%. The bands are the same rule scaled by the square
              root of the horizon, fixed before any result was looked at, and an accuracy is only
              ever reported inside one of these rows — never across them.
            </Note>
          </Section>
        ) : null}

        {s.scored === 0 ? (
          <Note>
            No accuracy is shown because no prediction has been scored yet. A percentage over zero
            scored records would be a claim about a model nobody has measured.
          </Note>
        ) : (
          <Note>
            Accuracy over <strong>{s.scored}</strong> scored record{s.scored === 1 ? "" : "s"}:{" "}
            <strong>{s.accuracy === null ? "—" : `${(s.accuracy * 100).toFixed(1)}%`}</strong>.
            Descriptive only — no threshold is applied here and a figure over a handful of matured
            records is not a promotion case.
          </Note>
        )}
      </Section>

      <Section title="How they were made">
        <Note>
          Quality: {Object.entries(s.byQuality).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}.
          Predicted class: {Object.entries(s.byPredictedClass).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}.
          Market: {Object.entries(s.byMarket).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}.
          Strategy: {Object.entries(s.byStrategy).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}.
          A <strong>refused</strong> record is one where a critical input was missing and no
          prediction was produced — it is kept rather than dropped, because knowing the model
          declined is worth as much as knowing what it said.
        </Note>
      </Section>

      <Section title={`Latest ${s.rows.length} records`}>
        {s.rows.length === 0 ? (
          <Empty>No predictions are stored.</Empty>
        ) : (
          <Table
            head={
              <>
                <th className="px-3 py-2 text-left">Session</th>
                <th className="px-3 py-2 text-left">Symbol</th>
                <th className="px-3 py-2 text-left">Market</th>
                {/* Without this column two different models reading the same asset on the same
                    session render as one row printed twice. Measured on the deployed page:
                    `2026-10-16 AA US swing UP 41.45` appeared twice, and the two rows were
                    brain-v2-context and brain-v4-us -- distinct records with distinct identities,
                    shown as an apparent double-write. The model is part of what a prediction is,
                    so it is part of what the table says. */}
                <th className="px-3 py-2 text-left">Model</th>
                <th className="px-3 py-2 text-left">Strategy</th>
                <th className="px-3 py-2 text-right" title="forward sessions the call is measured over">
                  Horizon
                </th>
                <th className="px-3 py-2 text-left">Predicted</th>
                <th className="px-3 py-2 text-right">Ref</th>
                <th className="px-3 py-2 text-left">Quality</th>
                <th className="px-3 py-2 text-right">Imputed</th>
                <th className="px-3 py-2 text-left">Matures</th>
                <th className="px-3 py-2 text-left">Outcome</th>
              </>
            }
          >
            {s.rows.map((r) => {
              const o = r.outcomes[0];
              const outcome = o
                ? `${o.label ?? "recorded"} (${o.fwdPct === null
                    ? "—"
                    : `${o.fwdPct >= 0 ? "+" : ""}${o.fwdPct.toFixed(1)}%`})`
                : r.outcomeLabel ?? "not yet";
              return (
                <tr key={r.id}>
                  <td className="px-3 py-2">{fmt(r.asOf)}</td>
                  <td className="px-3 py-2">{r.symbol}</td>
                  <td className="px-3 py-2">{r.market}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.modelVersion}</td>
                  <td className="px-3 py-2">
                    {r.strategy}
                    {r.timeframe && r.timeframe !== r.strategy ? `/${r.timeframe}` : ""}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {r.horizonSessions === null ? "—" : r.horizonSessions}
                  </td>
                  <td className="px-3 py-2">{r.predicted ?? "—"}</td>
                  <td className="px-3 py-2 text-right">
                    {r.referencePrice === null ? "—" : r.referencePrice.toFixed(2)}
                  </td>
                  <td className="px-3 py-2">{r.quality}</td>
                  <td className="px-3 py-2 text-right" title="features imputed rather than observed">
                    {r.imputedCount}
                  </td>
                  <td className="px-3 py-2">{fmt(r.maturesAfter)}</td>
                  <td className="px-3 py-2 text-muted-foreground">{outcome}</td>
                </tr>
              );
            })}
          </Table>
        )}
      </Section>

      {/* The second record, and never added to the first. Those rows are 20-session calls from
          three-class models; these are minute-to-hour binary calls from a different family under
          a different scoring rule, and one total over both would be two experiments counted as
          one. */}
      <ForecastRecord />
    </>
  );
}
