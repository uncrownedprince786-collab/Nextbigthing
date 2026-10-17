import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { getAsset, getAssetFreshness, getFactor, getSetup } from "@/lib/queries";

/// Screen 4 — research detail, and the screen with a correctness rule rather than a design brief.
///
/// **No directional model is validated.** Four candidates exist, all four are recorded NO-GO, and
/// none is production-approved. So this screen shows what is measured — the stored factor
/// readings and the rule engine's own setup — and presents no model direction at all.
///
/// Every value is rendered with its own absence. A factor that was not computed shows as "not
/// measured", never as zero: null and 0 are different facts here, and the brain's own families
/// refuse to vote on the first while reading the second.
export const revalidate = 900;

export async function generateMetadata(
  { params }: { params: Promise<{ symbol: string }> },
): Promise<Metadata> {
  const { symbol } = await params;
  const a = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  return { title: a ? `${a.symbol} research` : "Research" };
}

/// Scalar fields only, with nulls kept. Relations and dates are left out, because a generic
/// renderer that stringifies a relation produces noise and buries the row worth reading.
function scalars(o: unknown): [string, string | number | boolean | null][] {
  if (!o || typeof o !== "object") return [];
  return Object.entries(o as Record<string, unknown>)
    .filter(([k]) => !["id", "assetId", "asset"].includes(k))
    .filter(([, v]) => v === null || ["string", "number", "boolean"].includes(typeof v))
    .map(([k, v]) => [k, v as string | number | boolean | null]);
}

function ValueRows({ rows }: { rows: [string, string | number | boolean | null][] }) {
  return (
    <>
      {rows.map(([k, v]) => (
        <tr key={k}>
          <td className="px-3 py-2">{k}</td>
          <td className="px-3 py-2 text-right">
            {v === null ? (
              <span className="text-muted-foreground">not measured</span>
            ) : (
              String(v)
            )}
          </td>
        </tr>
      ))}
    </>
  );
}

export default async function ResearchPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  if (!asset) notFound();

  const [factor, setup, fresh] = await Promise.all([
    getFactor(asset.id).catch(() => null),
    getSetup(asset.id).catch(() => null),
    getAssetFreshness(asset.id).catch(() => null),
  ]);

  const head = (
    <tr>
      <th className="px-3 py-2 text-left">Reading</th>
      <th className="px-3 py-2 text-right">Value</th>
    </tr>
  );

  return (
    <>
      <Section title={`${asset.symbol} — what is measured`}>
        <Card>
          <p className="text-sm leading-relaxed">
            <strong>No directional model is validated for this instrument or any other.</strong>{" "}
            Four candidates have been trained and evaluated; all four are recorded NO-GO and none
            is approved for production. What follows is measured from stored prices — it is not a
            forecast, and no direction is claimed from a model.
          </p>
          {fresh?.newest ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Read from stored data to {new Date(fresh.newest).toISOString().slice(0, 10)}
              {fresh.priceSource ? ` · ${fresh.priceSource}` : null}.
            </p>
          ) : null}
        </Card>
      </Section>

      <Section title="Stored factor readings">
        {!factor ? (
          <Empty>No factor row is stored for this instrument.</Empty>
        ) : (
          <Table head={head}>
            <ValueRows rows={scalars(factor)} />
          </Table>
        )}
      </Section>

      <Section title="Rule-engine setup">
        {!setup ? (
          <Empty>
            The rule engine has no stored setup for this instrument. That is a state, not an
            error: a setup exists only when its conditions were met on a stored session.
          </Empty>
        ) : (
          <Table head={head}>
            <ValueRows rows={scalars(setup)} />
          </Table>
        )}
      </Section>

      <Note>
        <Link
          href={`/preview/asset/${encodeURIComponent(asset.symbol)}`}
          className="underline underline-offset-2"
        >
          ← Back to {asset.symbol}
        </Link>
      </Note>
    </>
  );
}
