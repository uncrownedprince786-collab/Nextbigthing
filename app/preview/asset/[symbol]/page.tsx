import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { getAsset, getAssetFreshness, getAssetPrices, getLiveQuoteFor } from "@/lib/queries";
import { marketOf } from "@/lib/decisionInput";
import { MARKET_LABELS, canonicalMarket, capabilityFor, profileFor } from "@/lib/marketCapability";
import { SaveButton } from "@/app/preview/watchlist/SaveButton";

/// Screen 3 — asset detail.
///
/// The rule this screen exists to keep: a stored close and a live quote are different claims and
/// must never share a presentation. `getAssetFreshness` returns the newest stored close with its
/// own date and source; `getLiveQuoteFor` returns a quote with its own `quotedAt` or null. Both
/// are labelled with where they came from and when, and when the live quote is absent the screen
/// says the close is the latest available rather than silently showing it as current.
export const revalidate = 900;

export async function generateMetadata(
  { params }: { params: Promise<{ symbol: string }> },
): Promise<Metadata> {
  const { symbol } = await params;
  const a = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  return { title: a ? `${a.symbol} · ${a.name}` : "Asset" };
}

function day(d: Date | null | undefined) {
  return d ? new Date(d).toISOString().slice(0, 10) : "—";
}

export default async function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = await getAsset(decodeURIComponent(symbol)).catch(() => null);
  if (!asset) notFound();

  const [prices, fresh, quote] = await Promise.all([
    getAssetPrices(asset.id, new Date().getUTCFullYear() - 1).catch(() => []),
    getAssetFreshness(asset.id).catch(() => null),
    getLiveQuoteFor(asset.id).catch(() => null),
  ]);

  const recent = prices.slice(-30).reverse();
  const first = prices.length ? prices[0] : null;
  const last = prices.length ? prices[prices.length - 1] : null;
  const changePct =
    first && last && first.close ? ((last.close / first.close - 1) * 100) : null;
  const market = canonicalMarket(
    marketOf({ assetType: asset.assetType, industry: asset.industry ?? null }),
  );
  const profile = market ? profileFor(market) : null;
  const swing = market ? capabilityFor(market, "swing") : null;

  return (
    <>
      <Section title={`${asset.symbol} — ${asset.name}`}>
        <Card>
          <p className="text-sm">
            {asset.assetType}
            {market ? <> · {MARKET_LABELS[market]}</> : null}
            {asset.industry ? <> · {asset.industry.name}</> : null}
            {asset.currency ? <> · quoted in {asset.currency}</> : null}
          </p>
          <div className="mt-3">
            <SaveButton symbol={asset.symbol} name={asset.name} />
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <div className="text-xs text-muted-foreground">Latest stored close</div>
              <div className="text-xl font-semibold">
                {fresh?.close ?? "—"}
              </div>
              <div className="text-xs text-muted-foreground">
                {day(fresh?.newest)}{fresh?.priceSource ? <> · {fresh.priceSource}</> : null}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Live quote</div>
              <div className="text-xl font-semibold">{quote ? quote.price : "not available"}</div>
              <div className="text-xs text-muted-foreground">
                {quote
                  ? `quoted ${new Date(quote.quotedAt).toISOString().slice(0, 16).replace("T", " ")}Z`
                  : "the stored close above is the latest available, and is not a live price"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Change over the stored window</div>
              <div className="text-xl font-semibold">
                {changePct === null ? "—" : `${changePct > 0 ? "+" : ""}${changePct.toFixed(1)}%`}
              </div>
              <div className="text-xs text-muted-foreground">
                {first && last ? `${day(first.date)} → ${day(last.date)}` : "no stored closes"}
              </div>
            </div>
          </div>
        </Card>
        <Note>
          Only daily closes are stored for this instrument, so there is no candlestick chart here:
          a candle needs an open, a high and a low within a session, and this screen will not draw
          bars the database does not hold. The table below is the stored closes, with the session
          each belongs to.
        </Note>
        {profile && swing ? (
          <Note>
            <strong>{MARKET_LABELS[swing.market]} capability.</strong>{" "}
            {swing.input.available ? "Inputs are available" : `Inputs are not available — ${swing.input.note}`}
            {" "}({profile.sessionRule}; prices from {profile.priceSource}). A{" "}
            {swing.timeframe} call over {swing.horizonSessions} sessions is{" "}
            {swing.outcome.verifiable
              ? `judgeable on ${swing.outcome.judgedOn}`
              : `not judgeable here — ${swing.outcome.reason}`}
            .{" "}
            {swing.prediction.marketSpecific
              ? "A market-specific model exists for this market."
              : "No market-specific model exists: any call here comes from the single global model, not one built for this market."}
          </Note>
        ) : null}
        <Note>
          {/* The next step of the journey: market, asset, and now a trading style. Kept as a link
              rather than folded into this page because the style choice decides which horizon is
              graded, and a screen that showed every horizon at once would be showing four
              different questions as one answer. */}
          <Link href={`/preview/asset/${encodeURIComponent(asset.symbol)}/decision`}
                className="font-medium underline underline-offset-2">
            Choose a trading style and see the decision →
          </Link>
        </Note>
        <Note>
          <Link href={`/preview/asset/${encodeURIComponent(asset.symbol)}/research`}
                className="underline underline-offset-2">
            Research detail for this instrument →
          </Link>
        </Note>
      </Section>

      <Section title="Recent stored sessions">
        {recent.length === 0 ? (
          <Empty>No closes are stored for this instrument.</Empty>
        ) : (
          <Table
            head={
              <>
                <th className="px-3 py-2 text-left">Session</th>
                <th className="px-3 py-2 text-right">Close</th>
                <th className="px-3 py-2 text-right">Volume</th>
              </>
            }
          >
            {recent.map((p) => (
              <tr key={p.date.toISOString()}>
                <td className="px-3 py-2">{day(p.date)}</td>
                <td className="px-3 py-2 text-right">{p.close}</td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {p.volume === null || p.volume === undefined
                    ? "not published"
                    : Number(p.volume).toLocaleString()}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Recent headlines">
        {asset.news.length === 0 ? (
          <Empty>No headlines are stored for this instrument.</Empty>
        ) : (
          <ul className="space-y-2 text-sm">
            {asset.news.map((n) => (
              <li key={n.id}>
                <span className="text-muted-foreground">{day(n.publishedAt)}</span>{" "}
                {n.url ? (
                  <a href={n.url} className="underline underline-offset-2" rel="noreferrer noopener"
                     target="_blank">{n.title}</a>
                ) : n.title}
                {n.publisher ? <span className="text-muted-foreground"> · {n.publisher}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
