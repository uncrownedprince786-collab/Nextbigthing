import type { Metadata } from "next";
import Link from "next/link";
import { LivePrice } from "@/components/LivePrice";
import { notFound } from "next/navigation";
import * as React from "react";
import { Sparkline } from "@/components/chart";
import {
  AccuracyNote,
  AnalogBlock,
  AttributionBlock,
  Card,
  ConfidenceBadge,
  ConfidenceKey,
  DiscussionBlock,
  Empty,
  HorizonStrip,
  IntradayHealth,
  InvestigationBlock,
  NeighbourhoodBlock,
  Note,
  Pill,
  Section,
  SetupBlock,
  StoriesBlock,
  Table,
  ThesisBlock,
  UpcomingBlock,
  weakest,
} from "@/components/ui";
import { DecisionPanel } from "@/components/decision";
import { pickTarget, targetForCall } from "@/lib/target";
import { openSince, qualityGate, withOpenPosition } from "@/lib/quality";
import { rankHeadlines } from "@/lib/newsRank";
import {
  getAccuracy,
  getAsset,
  getAssetPrices,
  getAttribution,
  getDecisionBundle,
  getLiveQuoteFor,
  getCallRunFor,
  getDecisionHistory,
  getIntradayHealth,
  getRelevance,
  getSourceHealth,
  getStories,
  getTopNews,
  getSetup,
  getThesis,
  getUpcoming,
} from "@/lib/queries";
import { bundleFromQuery, marketOf, toDecisionInput, todayISO } from "@/lib/decisionInput";
import { decideCall } from "@/lib/resolve";
import { validityOf } from "@/lib/validity";
import { earlySignalOf } from "@/lib/earlySignal";
import { changeTimeline, latestChange } from "@/lib/stateChange";
import { quoteBesideClose } from "@/lib/liveQuote";
import { isoDate, longDate, money, pct, plainPrice, relativeTime, sizeAbsence, sizeBasisText, toneClass } from "@/lib/format";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>;
}): Promise<Metadata> {
  const { symbol } = await params;
  const a = await getAsset(decodeURIComponent(symbol));
  if (!a) return { title: "Asset not found" };
  return { title: a.name, description: `${a.name} (${a.symbol}) in ${a.industry.name}` };
}

const BASIS_LABEL: Record<string, string> = {
  size: "Size at a past date",
  sizeNow: "Size now",
  totalReturn: "Total return between two dates",
  rising: "24 month return against its industry",
};

/// One closed group inside the Details area.
///
/// A plain `<details>`, because that is how this site collapses things: the same pattern as
/// `HowToRead` and `ConfidenceKey` in components/ui.tsx, and it costs no client JavaScript — this
/// page has no `'use client'` and gains nothing by acquiring one to hide a table.
///
/// Why groups rather than one giant toggle: the decision at the top is the page now, and a reader
/// who scrolls past it is looking for *one* thing — the levels, the dates, the news. One toggle
/// would make them open all sixteen to find it. The summary is the whole title, so the list of
/// summaries reads as a table of contents whether anything is open or not.
///
/// `lead` is deliberately capped at one sentence by the call sites below. The old page carried
/// three-sentence leads explaining the method before the figure; the method has not moved, it is
/// still inside each block, and a reader who has not yet opened the group does not need it.
function Detail({
  title,
  lead,
  children,
}: {
  title: string;
  lead?: string;
  children: React.ReactNode;
}) {
  return (
    <details className="border-border bg-muted/30 rounded-lg border px-4 py-1 sm:py-3">
      {/* 44px tall on a phone through padding that collapses from `sm` up, so the desktop box
          keeps its measurements. Same trick as the other two disclosures on the site. */}
      <summary className="-my-1 cursor-pointer py-3 text-sm font-medium select-none sm:my-0 sm:py-0">
        {title}
      </summary>
      <div className="mt-3 mb-3 sm:mb-0">
        {lead ? <p className="text-muted-foreground mb-3 max-w-3xl text-sm">{lead}</p> : null}
        {children}
      </div>
    </details>
  );
}

export default async function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = await getAsset(decodeURIComponent(symbol));
  if (!asset) notFound();

  // The decision bundle is read with everything else rather than ahead of it. It is eight queries
  // of its own and the rest of the page is nine more, and the panel is the part a reader waits on,
  // so there is nothing to gain by making the two round trips sequential.
  const [
    bundle,
    sourceHealth,
    prices,
    accuracy,
    upcoming,
    setup,
    thesis,
    attribution,
    relevance,
    intradayHealth,
    stories,
    topNews,
    liveQuote,
    callRun,
    history,
  ] = await Promise.all([
    getDecisionBundle(asset.id),
    getSourceHealth(),
    getAssetPrices(asset.id, 2019),
    getAccuracy(30),
    getUpcoming({ assetId: asset.id, take: 8 }),
    getSetup(asset.id),
    getThesis(asset.id),
    getAttribution(asset.id),
    getRelevance(asset.id),
    getIntradayHealth(asset.id),
    getStories(asset.id),
    getTopNews(asset.id),
    getLiveQuoteFor(asset.id),
    getCallRunFor(asset.id),
    getDecisionHistory(asset.id),
  ]);

  // The horizons, analogs, news reading and investigation are taken off the bundle instead of
  // being queried a second time. They are the same rows — `getDecisionBundle` calls the same four
  // functions — and reading them twice would let the panel and the group below it describe
  // different states of the same asset within one render.
  const horizons = bundle.horizons;
  const investigation = bundle.investigation;
  const discussion = bundle.humanSignal;
  const analogs = { periodEnd: bundle.analogPeriodEnd, rows: bundle.analogs };

  // One decision, from the rule table, with today injected once. The freshness gate lives in that
  // table: this page does not test the close date itself, because a second staleness rule is how
  // the panel and the page come to disagree about whether the number on screen is today's.
  const today = todayISO();
  const decisionInput = toDecisionInput(bundleFromQuery(bundle, sourceHealth), today);
  const decision = decideCall(decisionInput);
  // The measured exit and the quality gate's verdict, by the same functions the lists use, so a name
  // withheld from the lists says so here, and why.
  const target = targetForCall(pickTarget(horizons), decision);
  // The same function the list rows use, fed the same three facts, so this page and the market page
  // show one horizon and one window for this name.
  const validity = validityOf({
    action: decision.action,
    setupHorizon: decisionInput.setup?.horizon ?? null,
    runAction: callRun?.action ?? null,
    runSince: callRun?.since ?? null,
    asOf: bundle.newestCloseDate ?? null,
    today,
  });
  // The quality gate, with the trading style and open-position protection, as scoreRows applies them.
  const style = validity ? validity.label.toUpperCase() : null;
  const gate = withOpenPosition(
    qualityGate(decision, target, decisionInput.atr ?? null, style),
    openSince({
      action: decision.action,
      publishedAction: bundle.published?.action ?? null,
      publishedOn: bundle.published?.on ?? null,
      lastRunAction: decisionInput.lastRun ? (decisionInput.lastRun.direction === "up" ? "LONG" : "SHORT") : null,
      lastRunSince: decisionInput.lastRun?.since ?? null,
      validityStatus: validity?.status ?? null,
    }),
  );
  // The verdict change in the newest cycle (same function as the rows) and the timeline for the banner.
  const change = latestChange({
    action: decision.action,
    runAction: callRun?.action ?? null,
    runSince: callRun?.since ?? null,
    runPrev: callRun?.prev ?? null,
    runGate: callRun?.gate ?? null,
    latestCycle: callRun?.latest ?? null,
  });
  const changes = changeTimeline(history);
  // The rising-star marker, from the same function the list rows use, fed the same validated pair.
  const early = earlySignalOf(decisionInput.entryTrigger?.rule, decisionInput.entryTrigger?.direction, decision.action);

  const note = asset.analysis[0];
  const market = marketOf(asset);

  const byBasis = new Map<string, typeof asset.rankings>();
  for (const r of asset.rankings) {
    if (!byBasis.has(r.basis)) byBasis.set(r.basis, []);
    byBasis.get(r.basis)!.push(r);
  }

  // Guarded, because an asset with no stored closes is a real state here — a name seeded before its
  // first price run has rankings and news and no series at all, and the old unguarded read of
  // `latestPrice.date` would have thrown the page away rather than said so.
  const latestPrice = prices.length ? prices[prices.length - 1] : null;
  const yearAgo = latestPrice
    ? prices.filter((p) => p.date <= new Date(latestPrice.date.getTime() - 365 * 86_400_000)).pop()
    : undefined;
  const oneYear = latestPrice && yearAgo ? (latestPrice.close / yearAgo.close - 1) * 100 : null;

  // Current size comes from the ranking row rather than the newest price snapshot, so the
  // figure shown here is the same one the industry table ranks and grades.
  const sizeNowRow = (byBasis.get("sizeNow") ?? [])[0];
  const sizePreRow = (byBasis.get("size") ?? [])[0];
  const sizeGrade = weakest(sizeNowRow?.confidence, sizePreRow?.confidence);

  return (
    <div>
      {/* Name, symbol, market. Nothing else above the decision — not the industry link, not the
          source, not the stored prose. Each of those was a line a reader had to pass before
          reaching the one word they came for, and all three are still in Details below. */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{asset.name}</h1>
        <Pill>{asset.symbol}</Pill>
        <Pill>{market}</Pill>
      </div>

      {/* The decision, first and alone. Action, the two levels, when, and how well evidenced —
          and the missing-data list, which the panel renders itself and which is why there is no
          branch here for an asset with nothing stored. `currency` is the asset's own: PSX names
          are quoted in rupees and the panel's `price()` prints the right mark. */}
      <div className="mt-6">
        <DecisionPanel
          decision={decision}
          symbol={asset.symbol}
          currency={asset.currency}
          market={bundle.market}
          asOf={bundle.newestCloseDate}
          /* The close the panel prints is the one the bundle decided on, not `latestPrice`.
             They are the same row today, and taking it from the bundle is what keeps them the
             same row on the day a price arrives between the two reads. */
          priceNow={bundle.newestClose ?? latestPrice?.close ?? null}
          /* The measured exit, from the same rule the overview and the coming-week block use, so
             one name cannot be quoted two different levels on two pages. */
          target={target}
          withheld={gate.published ? null : gate.reasons}
          held={gate.held ?? null}
          validity={validity}
          early={early}
          change={change}
          changes={changes}
          quote={quoteBesideClose(liveQuote, { price: bundle.newestClose ?? null, date: bundle.newestCloseDate ?? null })}
          /* Ranked here rather than in the panel: the panel renders what it is given, and a
             component that re-sorted its own input would be a second ordering rule for one
             idea. Three is the panel's own cap; passing a few more lets it stay the only place
             that number is written down. */
          news={rankHeadlines(topNews).slice(0, 3)}
        />
      </div>

      {/*
        Everything that is not the decision.

        `id="detail"` lives here because the old `SimpleRead` card linked to `#detail` and that
        anchor pointed at the plain-summary wrapper, which is gone. The link still resolves, and it
        now lands on the list of groups rather than on a restatement of the panel above it.
        `scroll-mt-4` keeps the heading off the very top edge when it does.
      */}
      <div id="detail" className="scroll-mt-4">
        <Section
          title="Details"
          lead="Every measurement the decision was read from. Open what you want."
        >
          <div className="space-y-2">
            {/* The grades are explained once, here, in words. Every confidence badge below
                carries a `title=` with its reason, and a title is a hover: on a phone it does
                not exist. This is the same explanation, reachable by tapping. */}
            <ConfidenceKey />
            <Detail
              title="The same asset over three time frames"
              lead="Today, the next few weeks, and the longer term; they will sometimes disagree."
            >
              <HorizonStrip horizons={horizons} currency={asset.currency} market={bundle.market} />
            </Detail>

            <Detail
              title="What the conditions say right now"
              lead="Every condition tested, including the ones that failed and the inputs that were unavailable."
            >
              <SetupBlock setup={setup} currency={asset.currency} market={bundle.market} />
            </Detail>

            {/* Kept next to the conditions above, because the two are one question asked twice:
                what the conditions are today, and whether the conditions the last read was taken
                on are still there. Split apart, a two week old reason reads as a fresh one. */}
            <Detail
              title="What we said before, and whether it still holds"
              lead="The last directional read, compared against the day it first appeared rather than against yesterday."
            >
              <ThesisBlock thesis={thesis} currency={asset.currency} market={bundle.market} />
            </Detail>

            <Detail
              title="What was looked at"
              lead="Everything checked when the last large move happened, including what was not found."
            >
              <InvestigationBlock investigation={investigation} />
            </Detail>

            <Detail
              title="Price and history"
              lead="Daily closes from 2019 onward, as stored, not adjusted for dividends."
            >
              {/* `sm:grid-cols-2 lg:grid-cols-3` and not `sm:grid-cols-3`: three columns at 640px
                  is about 190px each, which is not enough for a `text-2xl` money figure next to a
                  badge. Two until there is room for three. */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Card>
                  <p className="text-muted-foreground text-xs">Last stored close</p>
                  <p className="num mt-1 text-2xl font-semibold">
                    {latestPrice ? plainPrice(latestPrice.close, bundle.market) : "no close stored yet"}
                  </p>
                  <p className="text-muted-foreground text-xs">{isoDate(latestPrice?.date)}</p>
                  {/* The last trade, refreshed in the browser when it is more than five minutes old.
                      Beside the close and never instead of it: the decision is read from closes. */}
                  <LivePrice
                    symbol={asset.symbol}
                    currency={asset.currency}
                    initial={
                      liveQuote
                        ? { price: liveQuote.price, quotedAt: liveQuote.quotedAt.toISOString() }
                        : null
                    }
                  />
                </Card>
                <Card>
                  <p className="text-muted-foreground text-xs">Return over the last year</p>
                  <p className={`num mt-1 text-2xl font-semibold ${toneClass(oneYear)}`}>
                    {pct(oneYear)}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {latestPrice && yearAgo
                      ? `${isoDate(yearAgo.date)} to ${isoDate(latestPrice.date)}`
                      : "not enough history"}
                  </p>
                </Card>
                <Card>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-muted-foreground text-xs">Size now</p>
                    <ConfidenceBadge grade={sizeGrade} />
                  </div>
                  <p className="num mt-1 text-2xl font-semibold">
                    {sizeNowRow ? money(sizeNowRow.value, asset.currency) : sizeAbsence(asset.assetType)}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {sizeNowRow
                      ? `${sizeBasisText(asset.capBasis)}, newest stored close`
                      : asset.capBasis === "none"
                        ? sizeBasisText("none")
                        : "no size ranking is stored for this asset, so no figure is shown"}
                  </p>
                </Card>
              </div>

              {prices.length ? (
                <>
                  <Card className="mt-3">
                    <Sparkline points={prices} label={asset.name} />
                  </Card>
                  <p className="text-muted-foreground mt-2 text-xs">
                    {prices.length.toLocaleString("en-US")} stored closes from{" "}
                    {isoDate(prices[0]?.date)} to {isoDate(latestPrice?.date)}.
                  </p>
                </>
              ) : (
                <div className="mt-3">
                  <Empty>No closes are stored for this asset from 2019 onward.</Empty>
                </div>
              )}
            </Detail>

            <Detail title="Rankings" lead="Every ranking row for this asset, newest window first.">
              {asset.rankings.length ? (
                // 760px rather than the 640px default: seven columns, one of which is free text.
                // At 640px the note column took whatever width was left and the dates wrapped to
                // three lines each. The table scrolls instead, which the edge shadow announces.
                <Table
                  minWidth="760px"
                  stickyFirstColumn
                  head={
                    <>
                      <th className="px-3 py-2 font-medium">Basis</th>
                      <th className="px-3 py-2 text-right font-medium">Rank</th>
                      <th className="px-3 py-2 text-right font-medium">Value</th>
                      <th className="px-3 py-2 font-medium">Confidence</th>
                      <th className="px-3 py-2 text-right font-medium">From</th>
                      <th className="px-3 py-2 text-right font-medium">To</th>
                      <th className="px-3 py-2 font-medium">Note</th>
                    </>
                  }
                >
                  {asset.rankings.map((r) => (
                    <tr key={r.id}>
                      <td className="px-3 py-2 text-xs">{BASIS_LABEL[r.basis] ?? r.basis}</td>
                      <td className="num px-3 py-2 text-right">{r.rank}</td>
                      <td
                        className={`num px-3 py-2 text-right ${r.basis === "totalReturn" || r.basis === "rising" ? toneClass(r.value) : ""}`}
                      >
                        {r.basis === "size" || r.basis === "sizeNow"
                          ? money(r.value, asset.currency)
                          : pct(r.value)}
                      </td>
                      <td className="px-3 py-2" title={r.confidenceNote ?? undefined}>
                        <ConfidenceBadge grade={r.confidence} />
                      </td>
                      <td className="num text-muted-foreground px-3 py-2 text-right">
                        {isoDate(r.periodStart)}
                      </td>
                      <td className="num text-muted-foreground px-3 py-2 text-right">
                        {isoDate(r.periodEnd)}
                      </td>
                      {/* Capped, because this cell is the only free-text column in the table and
                          an uncapped one lets a long confidence note set the width of all seven. */}
                      <td className="text-muted-foreground wrap-hard max-w-[18rem] px-3 py-2 text-xs">
                        {r.confidenceNote ?? r.note ?? "-"}
                      </td>
                    </tr>
                  ))}
                </Table>
              ) : (
                <Empty>No ranking rows are stored for this asset.</Empty>
              )}
            </Detail>

            {/* "What the move was shared with", never "attribution". The reader is owed the
                finding, not the name of the method that produced it. */}
            <Detail
              title="What the move was shared with"
              lead="Its recent move split into the part the whole exchange group made, the part its industry made, and what is left."
            >
              <AttributionBlock attribution={attribution} />
            </Detail>

            <Detail
              title="Why this asset is near today's news"
              lead="How a sudden jump in news somewhere else reaches this asset, through recorded links, at most two steps away."
            >
              <NeighbourhoodBlock relevance={relevance} showAsset={false} />
            </Detail>

            <Detail
              title="What followed days like this one"
              lead="Past days whose move, volume and five day trend were close to the latest one's, and what happened next."
            >
              <AnalogBlock analogs={analogs} />
            </Detail>

            <Detail
              title="Dates ahead"
              lead="Dated items already published for this asset."
            >
              <UpcomingBlock events={upcoming} showTargets={false} />
            </Detail>

            <Detail
              title="What is being written about it"
              lead="How much is being published, how it is worded, and whether it reads as promotion."
            >
              <DiscussionBlock signal={discussion} targetLabel={asset.name} />
              <div className="mt-3">
                <AccuracyNote accuracy={accuracy} />
              </div>
            </Detail>

            <Detail
              title="Stories behind the coverage"
              lead="Headlines grouped into stories, so one report carried by twenty outlets counts once."
            >
              <StoriesBlock stories={stories} />
            </Detail>

            <Detail title="Recent news mentioning this asset">
              {asset.news.length ? (
                <ul className="space-y-2">
                  {asset.news.map((n) => (
                    <li key={n.id} className="border-border border-b pb-2 text-sm last:border-0">
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="underline underline-offset-2"
                      >
                        {n.title}
                      </a>
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        {n.publisher} &middot; {relativeTime(n.publishedAt)}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No news items matched this asset in the stored window.</Empty>
              )}
            </Detail>

            <Detail
              title="Products that touch this asset"
              lead="The stated relationship is why the product was linked, not a recommendation."
            >
              {asset.productLinks.length ? (
                <ul className="grid gap-2 sm:grid-cols-2">
                  {asset.productLinks.map((l) => (
                    <li key={l.id} className="border-border rounded-lg border px-3 py-2 text-sm">
                      <Link
                        href={`/product/${encodeURIComponent(l.product.slug)}`}
                        className="font-medium underline underline-offset-2"
                      >
                        {l.product.name}
                      </Link>
                      <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                        {l.relation}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No products are linked to this asset.</Empty>
              )}
            </Detail>

            <Detail
              title="Same-day data health"
              lead="Whether the five minute series behind the same-day read is complete."
            >
              <IntradayHealth health={intradayHealth} />
            </Detail>

            {/* Last group, and the only home left for the page's stored prose. Both paragraphs
                used to sit above the fold: `asset.note` as an unlabelled lead, and the analysis
                row as a card called "Where this sits". Neither carries a figure the decision does
                not already give in numbers, so they are kept for the reader who wants the
                background and are no longer in the way of the one who does not. The confidence
                badge and the data note travel with the analysis row, because a graded claim shown
                without its grade is worse than the claim being buried. */}
            <Detail title="What this asset is">
              <p className="text-sm">
                In{" "}
                <Link
                  href={`/industry/${asset.industry.slug}`}
                  className="underline underline-offset-2"
                >
                  {asset.industry.name}
                </Link>
                , trading in {market}. Price source {asset.source}.
              </p>
              {asset.note ? (
                <p className="mt-2 max-w-3xl text-sm leading-relaxed">{asset.note}</p>
              ) : null}
              {note ? (
                <Card className="mt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-medium">What was written about it</h3>
                    <ConfidenceBadge grade={note.confidence} />
                  </div>
                  <p className="mt-2 text-sm leading-relaxed">{note.body}</p>
                  {note.dataNote ? <Note>{note.dataNote}</Note> : null}
                </Card>
              ) : null}
              <p className="text-muted-foreground mt-3 text-xs">
                Source {asset.source} &middot; reference {asset.sourceRef} &middot; first stored{" "}
                {longDate(asset.createdAt)}.
              </p>
            </Detail>
          </div>
        </Section>
      </div>
    </div>
  );
}
