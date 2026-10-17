import type { Metadata } from "next";
import Link from "next/link";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { getDataStamp, getShadowPredictions, getUpcoming } from "@/lib/queries";

/// Screen 1 — overview. What changed, what is coming, and when the data was last read.
///
/// Built from readers that already exist and are already tested, which is the point of the
/// contract: six of the eight screens need no new query, and inventing a parallel data layer for
/// them would be the duplication the brief warns against.
///
/// What this screen deliberately does **not** show is a direction. Four model artifacts exist and
/// all four are NO-GO, so there is nothing validated to headline. Saying that plainly is more
/// useful than an empty panel implying something is coming.
export const revalidate = 900;
export const metadata: Metadata = { title: "Overview" };

/// The six fields `getDataStamp` packs into its string, in the order it packs them.
///
/// The stamp is a cache key first -- `/api/revalidate` compares it with the stamp the cached rows
/// were read with -- and its wire form is `pool|decided|setups|quotes|closes|news`, joined with a
/// pipe and carrying "-" where a table is empty. That is a machine's shape, and printing it at a
/// reader was this screen's own bug: the panel headed "Where the data stands" said
/// `555|2026-10-17T01:26:38.126Z|...`, which stands for nothing a reader can act on.
///
/// Split here rather than asked for again. `getFreshness` returns the same ground in a friendlier
/// shape and the contract maps it to this screen, but it costs four more aggregates against a
/// pooler that admits fifteen clients in total, and the stamp is already in hand.
const STAMP_FIELDS = [
  ["Instruments in the pool", "active rows in the asset table"],
  ["Decisions computed", "the rule engine's last pass"],
  ["Setups computed", "the last read of entry and invalidation levels"],
  ["Live quotes", "newest quote, by the time the source quoted it"],
  ["Stored closes", "newest session close held for any instrument"],
  ["News read", "the last pass over collected stories"],
] as const;

/// `pool|decided|setups|quotes|closes|news` as rows a reader can use.
///
/// A field the stamp gives as "-" is returned null and rendered as absent, never as a date and
/// never as a zero: the table being empty is not the same claim as the table being empty today.
function readStamp(stamp: string): { label: string; note: string; value: string | null }[] | null {
  const parts = stamp.split("|");
  if (parts.length !== STAMP_FIELDS.length) return null;
  return STAMP_FIELDS.map(([label, note], i) => {
    const raw = parts[i];
    if (i === 0) return { label, note, value: raw === "-" ? null : raw };
    if (raw === "-") return { label, note, value: null };
    const d = new Date(raw);
    return {
      label,
      note,
      value: Number.isNaN(d.getTime()) ? null : `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)}Z`,
    };
  });
}

export default async function PreviewHome() {
  const [stamp, upcoming, shadow] = await Promise.all([
    getDataStamp().catch(() => null),
    getUpcoming({ take: 8 }).catch(() => []),
    getShadowPredictions(1).catch(() => null),
  ]);
  const stampRows = stamp ? readStamp(stamp) : null;

  return (
    <>
      <Section title="Where the data stands">
        {stampRows ? (
          <>
            <Note>
              Everything below is read from stored data at the times given here, not from a live
              feed. A row reading &ldquo;not recorded&rdquo; means that table holds nothing, which is
              not the same as it holding nothing today.
            </Note>
            <Table
              head={
                <>
                  <th className="px-3 py-2 text-left">Reading</th>
                  <th className="px-3 py-2 text-right">As of</th>
                </>
              }
            >
              {stampRows.map((r) => (
                <tr key={r.label}>
                  <td className="px-3 py-2">
                    {r.label}
                    <span className="text-muted-foreground block text-xs">{r.note}</span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.value ?? <span className="text-muted-foreground">not recorded</span>}
                  </td>
                </tr>
              ))}
            </Table>
          </>
        ) : (
          <Empty>The freshness stamp could not be read. Nothing here should be treated as current.</Empty>
        )}
      </Section>

      <Section title="Research status">
        <Card>
          <p className="text-sm leading-relaxed">
            <strong>No directional model is validated.</strong> Four candidates have been trained
            and evaluated; all four are recorded NO-GO and none is approved for production. This
            interface therefore shows what is measured — prices, ranges, volatility state, events
            and their context — and does not present a predicted direction.
          </p>
          {shadow ? (
            <p className="mt-2 text-sm text-muted-foreground">
              {shadow.total} experimental prediction{shadow.total === 1 ? "" : "s"} are recorded
              for later evaluation. <Link href="/preview/predictions" className="underline">
              See their status</Link> — none has matured yet.
            </p>
          ) : null}
        </Card>
      </Section>

      <Section title="Dated events ahead">
        {upcoming.length === 0 ? (
          <Empty>No dated events are stored for the window ahead.</Empty>
        ) : (
          <Table
            head={<><th className="px-3 py-2 text-left">Event</th>
              <th className="px-3 py-2 text-left">Date</th>
              <th className="px-3 py-2 text-right">In days</th></>}
          >
            {upcoming.map((u) => (
              <tr key={u.id}>
                <td className="px-3 py-2">{u.name}</td>
                <td className="px-3 py-2">{new Date(u.date).toISOString().slice(0, 10)}</td>
                <td className="px-3 py-2 text-right">
                  {Math.max(0, Math.round(
                    (new Date(u.date).getTime() - Date.now()) / 86_400_000))}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
    </>
  );
}
