import type { Metadata } from "next";
import Link from "next/link";
import { Card, Empty, Note, Section, Table } from "@/components/ui";
import { getMarketOverview } from "@/lib/queries";
import { CAPABILITY, MARKET_LABELS, capabilityForMarket } from "@/lib/marketCapability";

/// Screen 2 — market explorer, the top of the browse path.
///
/// Five markets, because the instruments trade in five groups: US, Pakistan, foreign exchange,
/// commodities and crypto. The list used to be drawn from each industry's `market` column, which
/// only ever held US/PK/FX — so every crypto coin and every front-month future was shown as a US
/// listing, filed under the industry it happened to sit in. The market is now read the same way the
/// model path reads it (`lib/decisionInput.marketOf`, via `getMarketOverview`), and an industry is
/// filed under the market most of its instruments actually trade in.
///
/// Three questions are answered apart, never merged into one "supported":
///
///   input      does the stored data exist for this market, and how fresh is it right now
///   model      is there a market-specific model — today, no, for every market
///   outcome    can a prediction in this market ever be judged, and the reason either way
///
/// The capability half is served from the research artifact (`lib/marketCapability`); the freshness
/// half is read live. A UI that answered the capability question itself would be a second opinion
/// that can disagree with the pipeline, which is how a market comes to be offered a timeframe the
/// scorer cannot grade.
export const revalidate = 900;
export const metadata: Metadata = { title: "Markets" };

function day(d: string | Date | null | undefined): string {
  return d ? new Date(d).toISOString().slice(0, 10) : "—";
}
function stamp(d: Date | null | undefined): string {
  return d ? new Date(d).toISOString().slice(0, 16).replace("T", " ") + "Z" : "not available";
}

export default async function MarketsPage() {
  const markets = await getMarketOverview().catch(() => null);

  if (!markets) {
    return (
      <Section title="Markets">
        <Empty>
          The market overview could not be read. This is a read failure, not an empty universe —
          the two would look identical if this said &ldquo;no markets&rdquo;.
        </Empty>
      </Section>
    );
  }

  return (
    <>
      <Note>
        Five markets, grouped the way each instrument actually trades. Counts are instruments in
        the stored universe, not instruments with a reading today. The capability figures are the
        research contract version <span className="font-mono text-xs">{CAPABILITY.version}</span>,
        generated {day(CAPABILITY.generatedAt)}; the freshness figures are read live.
      </Note>

      {markets.map((m) => {
        const swing = capabilityForMarket(m.market).find((r) => r.timeframe === "swing") ?? null;
        const modelSpecific = swing?.prediction.marketSpecific ?? false;
        return (
          <Section key={m.market} title={m.label}>
            <Card>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <div className="text-xs text-muted-foreground">Input — stored data</div>
                  <div className="text-sm">
                    {m.assets} instrument{m.assets === 1 ? "" : "s"} ·{" "}
                    {m.industries.length} industr{m.industries.length === 1 ? "y" : "ies"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    newest close {day(m.newestClose)} · newest factor session{" "}
                    {day(m.newestFactor)} · newest live quote {stamp(m.newestQuote)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {swing?.input.note ?? "capability not recorded for this market"}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Prediction model</div>
                  <div className="text-sm font-semibold">
                    {modelSpecific ? "market-specific model available" : "no market-specific model"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {swing?.prediction.note ??
                      "one global model is applied to every market; there is no per-market model"}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Recorded predictions</div>
                  <div className="text-sm font-semibold">{m.predictions}</div>
                  <div className="text-xs text-muted-foreground">
                    outcome is judged only after the declared horizon, and separately from the call
                  </div>
                </div>
              </div>
            </Card>

            <div className="mt-4">
              <Table
                head={
                  <>
                    <th className="px-3 py-2 text-left">Timeframe</th>
                    <th className="px-3 py-2 text-right">Sessions</th>
                    <th className="px-3 py-2 text-left">Input</th>
                    <th className="px-3 py-2 text-left">Model</th>
                    <th className="px-3 py-2 text-left">Outcome verifiable</th>
                  </>
                }
              >
                {capabilityForMarket(m.market).map((r) => (
                  <tr key={r.timeframe}>
                    <td className="px-3 py-2">{r.timeframe}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.horizonSessions}</td>
                    <td className="px-3 py-2">
                      {r.input.available ? "available" : "not available"}
                    </td>
                    <td className="px-3 py-2">
                      {r.prediction.marketSpecific ? "market-specific" : (
                        <span className="text-muted-foreground">shared global model</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {r.outcome.verifiable ? (
                        <span>yes</span>
                      ) : (
                        <span className="text-muted-foreground">no</span>
                      )}
                      <span className="text-muted-foreground block text-xs">{r.outcome.reason}</span>
                    </td>
                  </tr>
                ))}
              </Table>
            </div>

            {m.industries.length === 0 ? (
              <Note>
                No industry groups are stored for {MARKET_LABELS[m.market]}; its instruments are
                browsed from the asset pages rather than through an industry.
              </Note>
            ) : (
              <div className="mt-4">
                <Table
                  head={
                    <>
                      <th className="px-3 py-2 text-left">Industry</th>
                      <th className="px-3 py-2 text-right">Instruments</th>
                    </>
                  }
                >
                  {m.industries.map((ind) => (
                    <tr key={ind.id}>
                      <td className="px-3 py-2">
                        <Link
                          href={`/preview/markets/${ind.slug}`}
                          className="underline underline-offset-2"
                        >
                          {ind.name}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-right">{ind.assets}</td>
                    </tr>
                  ))}
                </Table>
              </div>
            )}
          </Section>
        );
      })}
    </>
  );
}
