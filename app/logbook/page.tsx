import type { Metadata } from "next";
import { Card } from "@/components/ui";
import { getAuditLog } from "@/lib/queries";
import { toLines } from "@/lib/logbook";

export const metadata: Metadata = {
  title: "Logbook",
  description: "The daily evaluation audit: completed calls graded against what followed, the day's shifts and exits, and the early signals.",
};

// Written once a day by the decision workflow, so an hour of caching costs nothing.
export const revalidate = 3600;

export default async function LogbookPage() {
  const entries = await getAuditLog();
  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Logbook</h1>
        <p className="mt-2 max-w-2xl text-sm">
          The engine&apos;s own audit, written at the end of every daily decision run: calls whose
          five-session window has closed, graded against what the price did; the day&apos;s shifts and
          exits; and the early signals. A review of the week opens each Monday. Newest first.
        </p>
        <p className="text-muted-foreground mt-2 text-sm">
          Every grade is the scorecard&apos;s own: a stop crossed by a daily close counts first, then the
          move across the window. Entries are kept as they were written that day, never rewritten with
          what was learned later. Nothing here is advice.
        </p>
      </div>

      {entries.length === 0 ? (
        <Card>
          <p className="text-muted-foreground text-sm">
            The first entry is written at the end of the next daily decision run.
          </p>
        </Card>
      ) : (
        entries.map((e) => (
          <Card key={`${e.kind}-${e.day.toISOString().slice(0, 10)}`}>
            <div className="space-y-1 text-sm leading-relaxed">
              {toLines(e.lines).map((l, i) =>
                l.kind === "rule" ? (
                  <hr key={i} className="border-border my-2" />
                ) : l.kind === "title" ? (
                  <h2 key={i} className="text-lg font-semibold tracking-tight">
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
                  <p key={i} className="text-muted-foreground" style={{ paddingLeft: `${l.indent * 0.5}rem` }}>
                    {l.text}
                  </p>
                ),
              )}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
