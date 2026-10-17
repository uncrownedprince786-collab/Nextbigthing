import type { Metadata } from "next";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { count } from "@/lib/format";
import { getHealthReadings, getIntradayCoverage, getSourceHealth } from "@/lib/queries";
import { Preferences } from "./Preferences";

/// Screen 8 — preferences and system status.
///
/// Two halves with one thing in common: both say plainly what is and is not known.
///
/// **Status** is read from `getSourceHealth`, `getHealthReadings` and `getIntradayCoverage`, all
/// existing and tested. The contract maps `getIntradayHealth` to this screen, but that reader takes
/// an asset id and answers for one instrument; `getIntradayCoverage` is the site-wide one, and
/// using the named reader here would have meant asking it 555 times for a single panel.
///
/// **A source's own status word is printed, never recomputed.** `jobs/audit.py` writes
/// healthy/partial/stale/silent into `Coverage` with the cadence it expects for that source in
/// hand, and a screen that re-derived "stale" from a timestamp would call a weekly source stale
/// six days out of seven. Classifying those cadences is Workstream B's B3, not this screen's.
export const revalidate = 900;
export const metadata: Metadata = { title: "Status and preferences" };

const STATUS_NOTE: Record<string, string> = {
  healthy: "answering, and current for its own cadence",
  partial: "answered, but with less than the run expected",
  stale: "answering, but its newest row is older than its cadence allows",
  silent: "did not answer",
};

function day(d: Date | string | null | undefined): string {
  return d ? new Date(d).toISOString().slice(0, 10) : "—";
}

export default async function StatusPage() {
  const [sources, health, intraday] = await Promise.all([
    getSourceHealth().catch(() => null),
    getHealthReadings().catch(() => null),
    getIntradayCoverage().catch(() => null),
  ]);

  return (
    <>
      <Section title="Preferences">
        <Preferences />
      </Section>

      <Section title="Where each market's data stands">
        {!health ? (
          <Empty>
            The health readings could not be read, so nothing is known here about how current the
            data is. That is a failed read, not a report that everything is current.
          </Empty>
        ) : (
          <>
            <Note>
              {count(health.pool)} instruments are in the active pool. Newest decision day{" "}
              {health.newestDecision ?? "not recorded"}.
            </Note>
            <Table
              head={
                <>
                  <th className="px-3 py-2 text-left">Market</th>
                  <th className="px-3 py-2 text-left">Newest stored close</th>
                  <th className="px-3 py-2 text-left">Newest live quote</th>
                </>
              }
            >
              {health.closes.map((c) => {
                const q = health.quotesByMarket.find((x) => x.market === c.market);
                return (
                  <tr key={c.market}>
                    <td className="px-3 py-2">{c.market}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {c.newest ?? (
                        <span className="text-muted-foreground">no close stored</span>
                      )}
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {q?.newest ? (
                        day(q.newest)
                      ) : (
                        <span className="text-muted-foreground">no quote stored</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </Table>
          </>
        )}
      </Section>

      <Section title="Collection lanes, last seven days">
        {!health || health.lanes.length === 0 ? (
          <Empty>
            No lane runs are recorded for the last seven days. A lane that has not run records
            nothing, so this is silence rather than a report of success.
          </Empty>
        ) : (
          <Table
            head={
              <>
                <th className="px-3 py-2 text-left">Lane</th>
                <th className="px-3 py-2 text-left">Last run</th>
                <th className="px-3 py-2 text-left">Last run that succeeded</th>
              </>
            }
          >
            {health.lanes.map((l) => (
              <tr key={l.job}>
                <td className="px-3 py-2">{l.job}</td>
                <td className="px-3 py-2 tabular-nums">{day(l.lastRun)}</td>
                <td className="px-3 py-2 tabular-nums">
                  {l.lastOk ? (
                    day(l.lastOk)
                  ) : (
                    <span className="text-muted-foreground">none in this window</span>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Sources">
        {!sources ? (
          <Empty>The source inventory could not be read.</Empty>
        ) : sources.length === 0 ? (
          <Empty>No source coverage rows are stored.</Empty>
        ) : (
          <>
            <Note>
              Worst first. Each status is the word the collection lane itself recorded, with that
              source&rsquo;s own expected cadence in hand — it is not recomputed here from a
              timestamp, because a source that publishes weekly is not stale on day two.
            </Note>
            <Table
              head={
                <>
                  <th className="px-3 py-2 text-left">Source</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-right">Rows</th>
                  <th className="px-3 py-2 text-left">Newest</th>
                </>
              }
            >
              {sources.map((s) => (
                <tr key={s.source}>
                  <td className="px-3 py-2">
                    {s.source}
                    {s.note ? (
                      <span className="text-muted-foreground block text-xs">{s.note}</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    {s.status}
                    <span className="text-muted-foreground block text-xs">
                      {STATUS_NOTE[s.status] ?? "status as the lane recorded it"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{count(s.rows)}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {s.newest ? day(s.newest) : <span className="text-muted-foreground">—</span>}
                  </td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </Section>

      <Section title="Intraday coverage">
        {!intraday || !intraday.sessionDate ? (
          <Empty>No intraday session is stored.</Empty>
        ) : (
          <>
            <Note>
              The newest stored session is {day(intraday.sessionDate)}. &ldquo;unsupported&rdquo; is
              an instrument the provider cannot serve, which is a stored fact rather than a gap in
              the lane — it is counted separately and never added to the failures.
            </Note>
            <Table
              head={
                <>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-right">Instruments</th>
                </>
              }
            >
              {intraday.counts.map((c) => (
                <tr key={c.status}>
                  <td className="px-3 py-2">{c.status}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{count(c.n)}</td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </Section>

      <Section title="Known limitations">
        <Card>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">
            <li>
              <strong>No directional model is validated.</strong> Four candidates have been trained
              and evaluated; all four are recorded NO-GO and none is approved for production.
            </li>
            <li>
              <strong>There are no user accounts.</strong> The watchlist and the preferences above
              are held in this browser and nowhere else.
            </li>
            <li>
              <strong>Everything here is stored data, not a live feed.</strong> Each panel states
              the day its figures were read from; a missing figure is shown as missing and never
              replaced with a zero.
            </li>
          </ul>
        </Card>
      </Section>
    </>
  );
}
