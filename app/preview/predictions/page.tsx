import type { Metadata } from "next";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { getShadowPredictions } from "@/lib/queries";

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
    </>
  );
}
