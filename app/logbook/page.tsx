import type { Metadata } from "next";
import { Card, Pill, Table } from "@/components/ui";
import { getAuditLog, getDecisionRuns, getLogbookSummary, getTradeSummary } from "@/lib/queries";
import { expectancyText, rateText, type RunRow, type TradeBucket, type TradeSummary } from "@/lib/history";
import { outcomeCounts, outcomeStatusOf } from "@/lib/outcome";
import { loadOrDefer } from "@/lib/buildSafe";
import { toLines, type Summary } from "@/lib/logbook";

export const metadata: Metadata = {
  title: "Logbook",
  description:
    "The final verdicts in one screen: how many calls were graded and how many were right, every LONG/SHORT flip, and what was caught early.",
};

// Written once a day by the decision workflow, so an hour of caching costs nothing.
export const revalidate = 3600;

const dayLabel = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="border-border rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="text-muted-foreground mt-1 text-xs">{note}</p>}
    </div>
  );
}

function Scorecard({ s }: { s: Summary }) {
  const none = s.graded === 0;
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">Final verdicts</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Calls graded"
          value={String(s.graded)}
          note="graded 5 sessions after the call"
        />
        <Stat
          label="Accurate"
          value={none ? "—" : `${s.accuratePct}%`}
          note={none ? "no call graded yet" : `${s.accurate} of ${s.graded}`}
        />
        <Stat
          label="Failed"
          value={none ? "—" : `${s.failedPct}%`}
          note={
            none
              ? "no call graded yet"
              : `${s.failed} of ${s.graded}, stops included`
          }
        />
        <Stat
          label="Early catches right"
          value={s.starsAccuratePct === null ? "—" : `${s.starsAccuratePct}%`}
          note={
            s.starsGraded
              ? `${s.starsAccurate} of ${s.starsGraded} graded`
              : "none graded yet"
          }
        />
        <Stat
          label="Resolved calls right"
          value={s.forcedAccuratePct === null ? "—" : `${s.forcedAccuratePct}%`}
          note={
            s.forcedGraded
              ? `${s.forcedAccurate} of ${s.forcedGraded}: calls the evidence rules alone held back`
              : "calls the evidence rules alone held back; none graded yet"
          }
        />
      </div>
      {none && (
        <p className="text-muted-foreground text-sm">
          A call is graded five trading sessions after it is made, so the first
          grades land about a week after the first calls. Until then the rates
          stay blank rather than show a number from nothing.
        </p>
      )}
    </section>
  );
}

function Flips({ s }: { s: Summary }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">
        Changed direction (last 30 days)
      </h2>
      {s.flips.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No call switched between LONG and SHORT in the last 30 days.
        </p>
      ) : (
        <>
          <Shown
            shown={s.flips.length}
            total={s.flipsTotal}
            what={s.flipsTotal === 1 ? "flip" : "flips"}
          />
          <Table
            minWidth="0"
            head={
              <>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Asset</th>
                <th className="px-3 py-2">Change</th>
              </>
            }
          >
            {s.flips.map((f) => (
              <tr key={`${f.day}-${f.symbol}`}>
                <td className="px-3 py-2 whitespace-nowrap">
                  {dayLabel(f.day)}
                </td>
                <td className="px-3 py-2">
                  <span className="font-medium">{f.symbol}</span>{" "}
                  <span className="text-muted-foreground hidden sm:inline">{f.name}</span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <Pill tone={f.from === "LONG" ? "up" : "down"}>{f.from}</Pill>{" "}
                  → <Pill tone={f.to === "LONG" ? "up" : "down"}>{f.to}</Pill>
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </section>
  );
}

const RESULT: Record<
  Summary["stars"][number]["result"],
  { text: string; tone: "up" | "down" | "default" }
> = {
  accurate: { text: "Accurate", tone: "up" },
  failed: { text: "Failed", tone: "down" },
  flat: { text: "Flat", tone: "default" },
  pending: { text: "Pending", tone: "default" },
};

function Shown({
  shown,
  total,
  what,
}: {
  shown: number;
  total: number;
  what: string;
}) {
  return (
    <p className="text-muted-foreground text-sm">
      {total} {what} in the last 30 days
      {shown < total
        ? `; the newest ${shown} are shown.`
        : "."}
    </p>
  );
}

function Stars({ s }: { s: Summary }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">
        Caught early (last 30 days)
      </h2>
      {s.stars.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No Rising or Falling Star in the last 30 days.
        </p>
      ) : (
        <>
          <Shown
            shown={s.stars.length}
            total={s.starsTotal}
            what={s.starsTotal === 1 ? "early catch" : "early catches"}
          />
          <Table
            minWidth="0"
            head={
              <>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Asset</th>
                <th className="px-3 py-2">Signal</th>
                <th className="px-3 py-2">Result</th>
              </>
            }
          >
            {s.stars.map((x) => (
              <tr key={`${x.day}-${x.symbol}`}>
                <td className="px-3 py-2 whitespace-nowrap">
                  {dayLabel(x.day)}
                </td>
                <td className="px-3 py-2">
                  <span className="font-medium">{x.symbol}</span>{" "}
                  <span className="text-muted-foreground hidden sm:inline">{x.name}</span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {x.direction === "up" ? "Rising Star" : "Falling Star"}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <Pill tone={RESULT[x.result].tone}>
                    {RESULT[x.result].text}
                  </Pill>
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </section>
  );
}

/// Directional accuracy and the simulated trade, side by side and never merged (rule 95). Directional
/// accuracy says whether the price went the way a call pointed; the trade says whether the call's own plan
/// -- its entry, stop and measured exit -- would have filled and where it would have closed.
function Trades({ t }: { t: TradeSummary | null }) {
  const a = t?.all ?? null;
  const SPLITS: [string, keyof Pick<TradeSummary, "byMarket" | "bySide" | "byHorizon" | "byConfidence">][] = [
    ["Market", "byMarket"],
    ["Side", "bySide"],
    ["Horizon", "byHorizon"],
    ["Confidence", "byConfidence"],
  ];
  return (
    <section className="space-y-3" data-trade-summary>
      <h2 className="text-lg font-semibold tracking-tight">Direction and trade, apart</h2>
      <p className="text-muted-foreground max-w-2xl text-sm">
        A call can point the right way and never reach its entry, or fill and reach its stop before its exit. So
        each published call is graded twice: by direction, and as a trade simulated on the daily bars from its
        own recorded entry, stop and measured exit. One trade per position, however many runs re-issued it. No
        rate here is a win probability or an edge until {t?.minSample ?? 30} trades have closed.
      </p>
      {!a || a.calls === 0 ? (
        <Card>
          <p className="text-muted-foreground text-sm">
            No simulated trade yet. Trades are graded from the calls the decision runs record, which began with
            this change; a swing call&apos;s window closes seven days after it is made.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <Stat label="Positions graded" value={String(a.evaluable)} note={`${a.pending} still inside their window`} />
            <Stat label="Filled" value={rateText(a.fillRate)} note="reached the entry within the window" />
            <Stat label="Exit first" value={rateText(a.targetFirst)} note="of filled trades" />
            <Stat label="Stop first" value={rateText(a.stopFirst)} note={`of filled trades; ${a.gapThrough} gapped through`} />
            <Stat label="Expired open" value={rateText(a.expired)} note="closed at the window's last close" />
            <Stat label="Ambiguous" value={rateText(a.ambiguous)} note="one bar reached both; booked at the stop" />
            <Stat
              label="Not filled / withdrawn"
              value={`${a.trades.NOT_FILLED ?? 0} / ${a.trades.WITHDRAWN ?? 0}`}
              note={`${a.trades.INVALIDATED_BEFORE_FILL ?? 0} invalidated before entry, ${a.trades.UNAVAILABLE ?? 0} without usable bars`}
            />
            <Stat label="Gross R per closed trade" value={a.grossRExpectancy.mean === null ? "—" : `${a.grossRExpectancy.mean.toFixed(2)}R`} note={expectancyText(a.grossRExpectancy, t!.minSample)} />
          </div>
          <p className="text-muted-foreground text-sm">
            Direction, on the same positions: {rateText(a.direction.accurate)} accurate after five sessions (
            {a.direction.stopped} stopped, {a.direction.flat} flat, {a.direction.pending} not yet five sessions old).
          </p>
          <Table
            head={
              <tr>
                <th className="px-3 py-2">Split</th>
                <th className="px-3 py-2">Positions</th>
                <th className="px-3 py-2">Filled</th>
                <th className="px-3 py-2">Exit first</th>
                <th className="px-3 py-2">Stop first</th>
                <th className="px-3 py-2">Gross R</th>
                <th className="px-3 py-2">Direction right</th>
              </tr>
            }
          >
            {SPLITS.flatMap(([label, key]) =>
              Object.entries(t![key]).map(([name, b]: [string, TradeBucket]) => (
                <tr key={`${key}-${name}`} className="border-border border-t">
                  <td className="px-3 py-2">
                    {label}: {name}
                  </td>
                  <td className="px-3 py-2 tabular-nums">{b.evaluable}</td>
                  <td className="px-3 py-2 tabular-nums">{rateText(b.fillRate)}</td>
                  <td className="px-3 py-2 tabular-nums">{rateText(b.targetFirst)}</td>
                  <td className="px-3 py-2 tabular-nums">{rateText(b.stopFirst)}</td>
                  <td className="px-3 py-2 tabular-nums">{expectancyText(b.grossRExpectancy, t!.minSample)}</td>
                  <td className="px-3 py-2 tabular-nums">{rateText(b.direction.accurate)}</td>
                </tr>
              )),
            )}
          </Table>
        </>
      )}
      {t && t.assumptions.length > 0 && (
        <p className="text-muted-foreground text-xs">Assumptions: {t.assumptions.join("; ")}.</p>
      )}
    </section>
  );
}

/// Every decision run of the last week, kept as it was made, with each day's current run marked (rule 95).
/// A second run on a day used to overwrite the first; now both are here and the site shows the newer one.
function Runs({ runs }: { runs: (RunRow & { current: boolean })[] }) {
  if (runs.length === 0) return null;
  return (
    <section className="space-y-3" data-decision-runs>
      <h2 className="text-lg font-semibold tracking-tight">Decision runs</h2>
      <p className="text-muted-foreground max-w-2xl text-sm">
        Every pass of the decision job, recorded once and never rewritten: when it ran, the code it ran, a
        fingerprint of the data it read, and the calls it made. The site shows each day&apos;s current run, the
        newest that finished; earlier runs stay here, and each published call is graded on the run that first
        made it.
      </p>
      <Table
        head={
          <tr>
            <th className="px-3 py-2">Day</th>
            <th className="px-3 py-2">Started (UTC)</th>
            <th className="px-3 py-2">Pass</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Names</th>
            <th className="px-3 py-2">Published</th>
            <th className="px-3 py-2">Code</th>
            <th className="px-3 py-2">Data</th>
          </tr>
        }
      >
        {runs.map((r) => (
          <tr key={r.id} className="border-border border-t" data-run-id={r.id} data-current={r.current ? "true" : "false"}>
            <td className="px-3 py-2">
              {dayLabel(r.periodEnd)} {r.current ? <Pill tone="up">current</Pill> : null}
            </td>
            <td className="px-3 py-2 tabular-nums">{r.startedAt.slice(11, 16)}</td>
            <td className="px-3 py-2">{r.pass}</td>
            <td className="px-3 py-2">{r.status}</td>
            <td className="px-3 py-2 tabular-nums">{r.written}</td>
            <td className="px-3 py-2 tabular-nums">{r.published}</td>
            <td className="px-3 py-2 font-mono text-xs">{r.commit ? r.commit.slice(0, 7) : "—"}</td>
            <td className="px-3 py-2 font-mono text-xs" title={r.fingerprint ?? undefined}>
              {r.fingerprint ? r.fingerprint.slice(0, 8) : "—"}
              {r.servedFrom && r.servedFrom !== "primary" ? ` (${r.servedFrom})` : ""}
            </td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export default async function LogbookPage() {
  const [summary, entries, trades, runs] = await loadOrDefer(() =>
    Promise.all([getLogbookSummary(), getAuditLog(), getTradeSummary(), getDecisionRuns()]),
  );
  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Logbook
        </h1>
        <p className="mt-2 max-w-2xl text-sm">
          The engine&apos;s own record, updated after every daily decision run.
          {summary && <> As of {dayLabel(summary.asOf)}.</>} Nothing here is
          advice.
        </p>
        {/* The sentence every call's page prints beside its grade, from these same counts (rule 94). */}
        <p className="text-muted-foreground mt-2 max-w-2xl text-sm" data-outcome-status>
          {outcomeStatusOf(outcomeCounts(summary)).sentence}
        </p>
      </div>

      {summary ? (
        <>
          <Scorecard s={summary} />
          <Flips s={summary} />
          <Stars s={summary} />
        </>
      ) : (
        <Card>
          <p className="text-muted-foreground text-sm">
            The summary is written at the end of the next daily decision run.
          </p>
        </Card>
      )}

      {/* Apart from the summary, so direction and trade are always shown as two questions (rule 95). */}
      <Trades t={trades} />
      <Runs runs={runs} />

      {entries.length > 0 && (
        <details className="border-border rounded-lg border">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
            Full daily audits ({entries.length}) — the full write-up of each day
          </summary>
          <div className="space-y-4 p-4 pt-0">
            <p className="text-muted-foreground text-sm">
              Every grade is the scorecard&apos;s own: a stop crossed by a daily
              close counts first, then the move across the five-session window.
              Entries are kept as written that day. Newest first.
            </p>
            {entries.map((e) => (
              <Card key={`${e.kind}-${e.day.toISOString().slice(0, 10)}`}>
                <div className="space-y-1 text-sm leading-relaxed">
                  {toLines(e.lines).map((l, i) =>
                    l.kind === "rule" ? (
                      <hr key={i} className="border-border my-2" />
                    ) : l.kind === "title" ? (
                      <h2
                        key={i}
                        className="text-lg font-semibold tracking-tight"
                      >
                        {l.text}
                      </h2>
                    ) : l.kind === "heading" ? (
                      <h2 key={i} className="text-base font-semibold">
                        {l.text}
                      </h2>
                    ) : l.kind === "bold" ? (
                      <p key={i} className="pt-2 font-semibold">
                        {l.text}
                      </p>
                    ) : (
                      <p
                        key={i}
                        className="text-muted-foreground"
                        style={{ paddingLeft: `${l.indent * 0.5}rem` }}
                      >
                        {l.text}
                      </p>
                    ),
                  )}
                </div>
              </Card>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
