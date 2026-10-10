import type { Metadata } from "next";
import { Card, Pill, Table } from "@/components/ui";
import { getAuditLog, getLogbookSummary } from "@/lib/queries";
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

export default async function LogbookPage() {
  const [summary, entries] = await loadOrDefer(() => Promise.all([getLogbookSummary(), getAuditLog()]));
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
