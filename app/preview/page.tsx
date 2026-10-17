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

export default async function PreviewHome() {
  const [stamp, upcoming, shadow] = await Promise.all([
    getDataStamp().catch(() => null),
    getUpcoming({ take: 8 }).catch(() => []),
    getShadowPredictions(1).catch(() => null),
  ]);

  return (
    <>
      <Section title="Where the data stands">
        {stamp ? (
          <Note>
            {stamp} Everything below is read from stored data at that point, not from a live feed.
          </Note>
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
            head={<tr><th className="px-3 py-2 text-left">Event</th>
              <th className="px-3 py-2 text-left">Date</th>
              <th className="px-3 py-2 text-right">In days</th></tr>}
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
