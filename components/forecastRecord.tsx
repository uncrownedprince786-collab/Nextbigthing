import Link from "next/link";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { forecastTotals } from "@/lib/forecastStore";
import { HORIZONS, HORIZON_ORDER } from "@/lib/cryptoHorizons";
import { LANES, LANES_GENERATED_AT, LANES_STATUS } from "@/lib/cryptoLanes";
import { COINS_TOTAL, COINS_WITH_INTRADAY, VENUE_MAP_GENERATED_AT, VENUE_ROWS } from "@/lib/cryptoVenues";

/// The short-horizon crypto record: what has been claimed, what has matured, and what it is worth.
///
/// Separate from the `ShadowPrediction` table above it on this page, and deliberately not summed
/// with it. Those are 20-session calls from three-class models; these are minute-to-hour binary
/// calls from a different family with a different scoring rule, and a reader who added the two
/// counts would be counting two experiments as one. The two tables never merge — the migration
/// that created `BrainForecast` says why.
///
/// Three numbers, never one. A forecast inside its window is not a miss and not a result; a
/// matured one nobody has scored is work owed, shown as owed; only a graded one may enter a rate.
/// And no rate is printed under thirty graded results, because a percentage over nine is not a
/// percentage.
export async function ForecastRecord() {
  const totals = await forecastTotals().catch(() => null);
  const servable = LANES.filter((l) => l.servable);

  return (
    <Section
      title="Short-horizon crypto forecasts"
      lead="A second, separate record: binary UP/DOWN calls over windows from five minutes to a month, written down as they are shown and graded only once each window has closed."
    >
      {!totals ? (
        <Empty>
          The forecast store could not be read, so nothing is shown. An empty table here would be
          indistinguishable from &ldquo;no forecast has ever been made&rdquo;, and those are
          different facts.
        </Empty>
      ) : (
        <>
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Card>
              <div className="text-2xl font-semibold">{totals.forecasts.toLocaleString()}</div>
              <div className="text-muted-foreground text-sm">recorded, one per coin per window per bar</div>
            </Card>
            <Card>
              <div className="text-2xl font-semibold">{totals.pending.toLocaleString()}</div>
              <div className="text-muted-foreground text-sm">still inside their window — not a miss and not a result</div>
            </Card>
            <Card>
              <div className="text-2xl font-semibold">{totals.awaitingScore.toLocaleString()}</div>
              <div className="text-muted-foreground text-sm">matured, not yet graded — work owed, shown as owed</div>
            </Card>
            <Card>
              <div className="text-2xl font-semibold">
                {totals.graded >= 30
                  ? `${((totals.correct / totals.graded) * 100).toFixed(1)}%`
                  : totals.graded.toLocaleString()}
              </div>
              <div className="text-muted-foreground text-sm">
                {totals.graded >= 30
                  ? `right, over ${totals.graded.toLocaleString()} graded`
                  : "graded — under the 30 needed before a rate is reported"}
              </div>
            </Card>
          </div>

          {totals.byHorizon.length ? (
            <Table head={["Window", "Reach", "Recorded", "Graded", "Right", "Rate"]}>
              {HORIZON_ORDER.filter((k) => totals.byHorizon.some((b) => b.horizonKey === k)).map((k) => {
                const b = totals.byHorizon.find((x) => x.horizonKey === k)!;
                return (
                  <tr key={k}>
                    <td className="px-3 py-2">{HORIZONS[k].label}</td>
                    <td className="px-3 py-2 text-right">{HORIZONS[k].minutes} min</td>
                    <td className="px-3 py-2 text-right">{b.forecasts.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right">{b.graded.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right">{b.correct.toLocaleString()}</td>
                    <td className="text-muted-foreground px-3 py-2 text-right">
                      {b.graded >= 30 ? `${((b.correct / b.graded) * 100).toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </Table>
          ) : (
            <Empty>
              No short-horizon forecast has been recorded yet. One is written the first time a
              reader opens a coin&apos;s page and picks a window, keyed on the bar it was read
              from, so this fills as the pages are used rather than on a schedule.
            </Empty>
          )}
        </>
      )}

      <Note>
        <p>
          <strong>What is licensed to answer.</strong>{" "}
          {servable.length === 0
            ? "No window has passed its gates, so no direction is served anywhere on the site."
            : `${servable.length} of ${LANES.length} fitted windows passed their gates: ` +
              servable.map((l) => `${l.family} ${HORIZONS[l.horizon].label.toLowerCase()} (${l.confidence})`).join(", ") +
              "."}{" "}
          {LANES_STATUS} Lane table computed {LANES_GENERATED_AT.slice(0, 10)}.
        </p>
        <p className="mt-2">
          <strong>Coverage.</strong> {COINS_TOTAL} coins are in the registry and{" "}
          {COINS_WITH_INTRADAY} of them have a free venue that serves intraday bars, so{" "}
          {COINS_TOTAL - COINS_WITH_INTRADAY} can be read on their daily history only —{" "}
          {VENUE_ROWS.filter((r) => !r.intraday)
            .map((r) => r.name)
            .join(", ") || "none"}
          . Venue lists checked {VENUE_MAP_GENERATED_AT.slice(0, 10)}.
        </p>
        <p className="mt-2">
          Every number here is prospective: each forecast existed before its outcome did. That is
          the one thing a holdout cannot give, and it is why these counts are kept apart from the
          accuracy figures on the{" "}
          <Link href="/crypto" className="underline underline-offset-2">
            coin pages
          </Link>
          , which are measured on history.
        </p>
      </Note>
    </Section>
  );
}
