import Link from "next/link";
import { unstable_cache } from "next/cache";
import {
  AsOf,
  Card,
  ConfidenceBadge,
  Empty,
  HowToRead,
  Note,
  Pill,
  Section,
  SourceHealthBlock,
  Table,
} from "@/components/ui";
import {
  getAllIndustriesByBasis,
  getDecisionRows,
  getFreshness,
  getIndustriesByMarket,
  getPricedAssetsByIndustry,
  getSourceHealth,
  rankingAsOf,
  type DecisionQueryRow,
} from "@/lib/queries";
import { bundleFromRow, toDecisionInput, todayISO } from "@/lib/decisionInput";
import { decide, EVENT_SOON_DAYS, type Confidence, type Decision, type Market } from "@/lib/decision";
import { DecisionList, type DecisionRow } from "@/components/decision";
import { FilterChips } from "@/components/filters";
import { describeFilters, readFilters, type FilterGroup } from "@/lib/filters";
import { isoDate, money, price, pct, sizeLabel, toneClass } from "@/lib/format";

// The home page is three lists and nothing else above the fold.
//
// What it used to be: a lede, an editorial callout, thirteen sections and several multi-sentence
// section leads, ending with a seven-column table. Every one of those was true and none of them
// answered the question a reader actually arrives with, which is "is there anything to do today,
// and if not, why not". Reading the old page to that answer took minutes of scrolling; the target
// is ten seconds. So the order is now LONG, SHORT, WAIT, and everything that survived is behind one
// collapsed `<details>` at the bottom, where a reader goes deliberately rather than by accident.
//
// The page computes nothing. `lib/decision.ts` owns the rule table, `lib/decisionInput.ts` owns the
// translation from stored columns, and this file's only jobs are to read, filter, sort and render.
// If a verdict here disagrees with the one on an asset page, the bug is in neither file: it is a
// `today` or a `sourceHealth` that was fetched twice, which is why both are fetched once below and
// passed down.

// Reading `searchParams` opts this route into dynamic rendering at request time, so this export no
// longer protects anything — it is kept because the route is still happy to be revalidated on that
// cadence, but the database protection is now the `unstable_cache` wrappers below. Nothing about the
// three lists is per-reader: the filters only choose which stored rows to print.
export const revalidate = 3600;

/// Why the reads are wrapped, and wrapped here.
///
/// `getDecisionRows()` is 12 queries against a Neon free tier and the rest of this page adds ten
/// more. Before the filters existed the route was static and `revalidate` capped that at one run an
/// hour; a dynamic route runs all 22 on every request, including a crawler walking every chip
/// combination. `unstable_cache` puts the hour back where it was.
///
/// `'use cache'` would be the Next 16 way to say this and does not work here: `cacheComponents` is
/// not enabled in next.config.ts, so the directive and `cacheLife` are unavailable and
/// `unstable_cache` is the correct API in this configuration.
const HOUR = { revalidate: 3600 } as const;

const cachedDecisionRows = unstable_cache(getDecisionRows, ["decision-rows"], HOUR);
const cachedSourceHealth = unstable_cache(getSourceHealth, ["source-health"], HOUR);
const cachedFreshness = unstable_cache(getFreshness, ["freshness"], HOUR);
const cachedIndustriesByMarket = unstable_cache(
  getIndustriesByMarket,
  ["industries-by-market"],
  HOUR,
);
const cachedRisers = unstable_cache(
  () => getAllIndustriesByBasis("rising"),
  ["industries-rising"],
  HOUR,
);
const cachedSizeNow = unstable_cache(
  () => getAllIndustriesByBasis("sizeNow"),
  ["industries-size-now"],
  HOUR,
);
/// A `Map` is handed over as entries rather than as a `Map`.
///
/// Everything that goes through this cache crosses a serialization boundary, and a `Map` does not
/// survive one — it would come back as an empty object, the industry cards would silently lose the
/// "how many of its assets have prices" count, and the empty-state sentence underneath them would
/// start lying about why an industry has no ranking. Entries are an array, which does survive.
const cachedPricedByIndustry = unstable_cache(
  async () => [...(await getPricedAssetsByIndustry()).entries()],
  ["priced-by-industry"],
  HOUR,
);

/// The two filters, and deliberately not a third.
///
/// There is no Action chip. The three lists already separate LONG from SHORT from WAIT, so an action
/// filter's only possible effect is to empty two of the three — a control whose every setting makes
/// the page look broken. Market and Confidence both cut across all three lists, which is the test a
/// filter has to pass to belong here.
const FILTERS: FilterGroup[] = [
  {
    key: "market",
    label: "Market",
    options: [
      { label: "All markets", value: null },
      { label: "US", value: "US" },
      { label: "PSX", value: "PSX" },
      { label: "Crypto", value: "Crypto" },
      // The value is the mapped `Market`, not the industry's column, which is why this reads
      // FX and not the four `fx-` industry slugs behind it. `marketOf` keys a currency pair off
      // its assetType rather than its industry for exactly that reason.
      { label: "Forex", value: "FX" },
    ],
  },
  {
    key: "confidence",
    label: "Confidence",
    options: [
      { label: "Any confidence", value: null },
      { label: "High", value: "High" },
      { label: "Medium", value: "Medium" },
      { label: "Low", value: "Low" },
    ],
  },
];

/// How many WAIT rows are printed before the rest are counted rather than listed.
///
/// WAIT is the fall-through of the rule table, so on an ordinary day most of the asset list is in
/// it, and a hundred cards is not a list a reader scans in ten seconds. The cut is honest rather
/// than silent: the count of what is not shown is printed under the heading, and nothing is hidden
/// that is more urgent than something shown, because the order below puts urgency first.
const WAIT_SHOWN = 12;

const MARKET_NAME: Record<string, string> = {
  US: "United States listings",
  PK: "Pakistan Stock Exchange",
};

const CONFIDENCE_ORDER: Record<Confidence, number> = { High: 0, Medium: 1, Low: 2 };

/// How urgent each WAIT reason is, lowest first.
///
/// Keyed on `Decision.gate`, which the rule table exposes for exactly this kind of use and which is
/// never shown to the reader — the reader gets `why` and `missing` in words. The ranking is the
/// user's own ordering of the WAIT list: a dated event today, then a move nobody has explained, then
/// the data faults, then the ordinary "there is no setup here" cases. A fault ranks above an absence
/// because a fault is something someone can go and fix.
const GATE_URGENCY: Record<string, number> = {
  "unexplained-move": 2,
  stale: 3,
  "source-silent": 3,
  "no-prices": 3,
  "bad-date": 3,
  "no-invalidation": 4,
  "mixed-horizons": 5,
  incomplete: 6,
};

/// One asset, read once: the stored row, the rule table's input, and the verdict.
///
/// The input is kept beside the decision because the mapped `market` lives on it. Taking the market
/// off the raw query row instead would print "PK" where the rest of the site says "PSX" and would
/// file every crypto name under whichever industry market it happens to sit in.
interface Scored {
  row: DecisionQueryRow;
  market: Market;
  decision: Decision;
}

function urgency(s: Scored): number {
  const days = s.row.nextEventInDays;
  if (days !== null && days <= 0) return 0;
  if (days !== null && days <= EVENT_SOON_DAYS) return 1;
  return GATE_URGENCY[s.decision.gate] ?? 7;
}

/// WAIT, most urgent first.
///
/// Inside one urgency band: the nearer event first, then the larger unusual move, then the symbol so
/// that two identical rows do not swap places between two reads of the same page.
function byUrgency(a: Scored, b: Scored): number {
  const u = urgency(a) - urgency(b);
  if (u !== 0) return u;
  const da = a.row.nextEventInDays ?? 9_999;
  const db = b.row.nextEventInDays ?? 9_999;
  if (da !== db) return da - db;
  const za = Math.abs(a.row.robustZ ?? 0);
  const zb = Math.abs(b.row.robustZ ?? 0);
  if (za !== zb) return zb - za;
  return a.row.symbol.localeCompare(b.row.symbol);
}

/// LONG and SHORT, best-evidenced first. A High-confidence row is the one worth reading, and within
/// a grade the symbol keeps the order stable.
function byConfidence(a: Scored, b: Scored): number {
  const c = CONFIDENCE_ORDER[a.decision.confidence] - CONFIDENCE_ORDER[b.decision.confidence];
  return c !== 0 ? c : a.row.symbol.localeCompare(b.row.symbol);
}

function toListRow(s: Scored): DecisionRow {
  return {
    symbol: s.row.symbol,
    name: s.row.name,
    market: s.market,
    action: s.decision.action,
    entry: s.decision.entry,
    invalidation: s.decision.invalidation,
    confidence: s.decision.confidence,
    // PSX names are in rupees. Without this every level on the page would be printed with a dollar
    // mark in front of a rupee number, which is worse than printing no level at all.
    currency: s.row.currency,
    // The calendar, on the lists that are not WAIT. A dated event never gates the rule table, so a
    // LONG row with earnings tomorrow carries no hint of it in `why` — it reaches the reader only
    // through the time sense, and until this was passed the front page dropped it silently. The
    // WAIT cards already print the same sentence; `eventLabel` is shared so the two cannot drift.
    timeSense: s.decision.timeSense,
    eventNote: eventLabel(s.row),
  };
}

/// The calendar line, when the calendar is the reason this row is urgent.
///
/// Separate from `decision.why` on purpose: a dated event does not gate the rule table — it only
/// sets the time sense — so a row that is in WAIT for a stale close and happens to report earnings
/// today would otherwise say nothing about today. The event is what makes it the first card.
function eventLabel(row: DecisionQueryRow): string | null {
  const days = row.nextEventInDays;
  if (days === null || days > EVENT_SOON_DAYS) return null;
  const name = row.nextEventName ?? "a dated event";
  if (days <= 0) return `Event today: ${name}.`;
  return `Event in ${days} ${days === 1 ? "day" : "days"}: ${name}.`;
}

/// One WAIT card.
///
/// Not a `DecisionList` row, and this is the one place the three lists differ in shape. A WAIT row's
/// two price columns are usually "none stored" — that absence is frequently the whole reason the row
/// is in WAIT — so the six-column layout would spend most of its width printing the same two words
/// over and over, with no room left for the thing the reader came for. What a WAIT row owes the
/// reader is the reason, in a sentence, and a sentence does not fit in a column. So the fields the
/// user's spec asks for are all here, stacked: name, market, action, entry, invalidation, confidence
/// and the link, with the reason given the width it needs.
function WaitCard({ item }: { item: Scored }) {
  const { row, decision, market } = item;
  const event = eventLabel(row);
  const currency = row.currency;

  return (
    <Card href={`/asset/${encodeURIComponent(row.symbol)}`} className="space-y-1.5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <span className="min-w-0">
          <span className="block text-sm font-medium">{row.name}</span>
          <span className="num text-muted-foreground block text-xs">{row.symbol}</span>
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <Pill tone="default">{market}</Pill>
          <Pill tone="warn">WAIT</Pill>
          <ConfidenceBadge grade={decision.confidence.toLowerCase()} />
        </span>
      </div>

      {event ? <p className="text-warn text-xs font-medium">{event}</p> : null}

      {/* The reason, always. A WAIT with no reason printed is the silent empty this page exists to
          end, so the fallback is a sentence that says the absence is itself a fault. */}
      <p className="text-sm leading-relaxed">
        {decision.why[0] ?? "No reason was recorded for this WAIT, which is itself a fault."}
      </p>

      {decision.missing.length ? (
        <ul className="space-y-0.5">
          {decision.missing.slice(0, 2).map((m, i) => (
            <li key={i} className="text-muted-foreground text-xs leading-relaxed">
              {m}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-muted-foreground text-xs">
        Entry{" "}
        <span className="num">
          {decision.entry
            ? `${price(decision.entry.low, currency)} to ${price(decision.entry.high, currency)}`
            : "none stored"}
        </span>
        {" · "}Exit if wrong{" "}
        <span className="num">
          {decision.invalidation !== null ? price(decision.invalidation, currency) : "none stored"}
        </span>
      </p>
    </Card>
  );
}

export default async function Home({
  searchParams,
}: {
  // A Promise, and awaited below. Synchronous access to `searchParams` was removed in Next 16, not
  // deprecated: the old shape does not warn, it fails.
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const current = readFilters(FILTERS, params);
  const showing = describeFilters(FILTERS, current);

  const [rows, health] = await Promise.all([cachedDecisionRows(), cachedSourceHealth()]);

  // Once, for the whole page. The rule table takes `today` as an input precisely so that one page
  // cannot straddle midnight and decide two assets against two different days.
  const today = todayISO();

  const scored: Scored[] = rows.map((row) => {
    const input = toDecisionInput(bundleFromRow(row, health), today);
    return { row, market: input.market, decision: decide(input) };
  });

  // Newest stored close across the page, as an ISO string the rule table already produced. Compared
  // as text rather than as a date because `yyyy-mm-dd` sorts correctly as text and because anything
  // that came back through the cache above is a string now whatever its type says.
  const asOf = scored.reduce<string | null>((newest, s) => {
    const d = s.row.closeDate ? isoDate(s.row.closeDate) : null;
    if (!d || d === "no date") return newest;
    return newest === null || d > newest ? d : newest;
  }, null);

  const matching = scored.filter(
    (s) =>
      (current.market === undefined || s.market === current.market) &&
      (current.confidence === undefined || s.decision.confidence === current.confidence),
  );

  const longs = matching.filter((s) => s.decision.action === "LONG").sort(byConfidence);
  const shorts = matching.filter((s) => s.decision.action === "SHORT").sort(byConfidence);
  const waits = matching.filter((s) => s.decision.action === "WAIT").sort(byUrgency);
  const waitHidden = Math.max(0, waits.length - WAIT_SHOWN);

  // Rows exist, and the filters removed all of them. Without this the reader gets three empty lists
  // and no way to tell a filtered page from a broken one.
  const emptiedByFilter =
    scored.length > 0 && matching.length === 0 && Object.keys(current).length > 0;

  const [byMarket, risers, sizeNow, pricedEntries, fresh] = await Promise.all([
    cachedIndustriesByMarket(),
    cachedRisers(),
    cachedSizeNow(),
    cachedPricedByIndustry(),
    cachedFreshness(),
  ]);
  const pricedByIndustry = new Map(pricedEntries);

  const byIndustry = new Map<string, typeof risers>();
  for (const r of risers) {
    if (!byIndustry.has(r.industryId)) byIndustry.set(r.industryId, []);
    byIndustry.get(r.industryId)!.push(r);
  }

  // Current size lives in its own table, keyed by asset. It cannot be read off a rising row, whose
  // value is a return rather than a size.
  const largestByIndustry = new Map<string, (typeof sizeNow)[number]>();
  for (const r of sizeNow) {
    const seen = largestByIndustry.get(r.industryId);
    if (!seen || r.rank < seen.rank) largestByIndustry.set(r.industryId, r);
  }
  // How many assets in each industry actually have a size figure. Precious metals is the hard case:
  // 3 of its 10 assets publish one, so "largest" there means largest of three and the card says so.
  const sizeCountByIndustry = new Map<string, number>();
  for (const r of sizeNow) {
    sizeCountByIndustry.set(r.industryId, (sizeCountByIndustry.get(r.industryId) ?? 0) + 1);
  }

  return (
    <div className="space-y-2">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">LONG, SHORT or WAIT</h1>
        {/* What the site is, before what it says. Someone arriving here for the first time has
            three words in 48px type in front of them and no way to tell whether this is a tip
            sheet; the old subtitle began "One verdict per asset, from the same rule table the
            asset pages use", which answers a question a new reader has not got to yet and uses
            two words they have no reason to know. This sentence is the one thing above the fold
            that has to be understood by somebody who has never seen the page. */}
        <p className="mt-2 max-w-2xl text-sm">
          Every name below is read from stored market data by a fixed set of rules. These are
          readings, not tips: nothing here is advice, a forecast, or a promise that anything will
          happen.
        </p>
        <p className="text-muted-foreground mt-2 text-sm">
          One reading per name, the same one its own page shows. Showing {showing}, priced to{" "}
          {asOf ?? "no stored close"}.
        </p>
      </div>

      <div className="mt-4">
        <FilterChips groups={FILTERS} current={current} basePath="/" />
      </div>

      {scored.length === 0 ? (
        <Empty>
          No asset rows are stored at all, so no verdict could be computed. This is a data state and
          not a filter: the price, setup and analog jobs write the rows these lists read, and the
          source health table in Details below says which of them last answered.
        </Empty>
      ) : emptiedByFilter ? (
        <Note>
          Nothing matches {showing}. {scored.length} assets are stored and all of them were removed
          by that filter, so the three lists below are empty for that reason and not because the
          verdicts are missing.{" "}
          <Link href="/" className="underline underline-offset-2">
            Clear the filters
          </Link>
          .
        </Note>
      ) : null}

      <DecisionList
        title="LONG candidates"
        lead="Price is trending up, the longer view is not against it, and there is a level that would prove the reading wrong."
        rows={longs.map(toListRow)}
        empty={
          Object.keys(current).length > 0
            ? `No stored asset reads LONG under ${showing}. Clear the filters to see the rest.`
            : "No asset reads LONG today. That is an ordinary state, not a missing list: the rule table refuses a direction without an invalidation level, and most days most names have none."
        }
      />

      <DecisionList
        title="SHORT candidates"
        lead="Price is trending down, the longer view is not against it, and there is a level that would prove the reading wrong."
        rows={shorts.map(toListRow)}
        empty={
          Object.keys(current).length > 0
            ? `No stored asset reads SHORT under ${showing}. Clear the filters to see the rest.`
            : "No asset reads SHORT today. Same rule as LONG, mirrored: a direction is only printed when a break level is stored."
        }
      />

      <Section
        title="WAIT / caution"
        lead={
          waitHidden > 0
            ? `Most urgent first: a date today, then an unexplained move, then a data fault. ${WAIT_SHOWN} of ${waits.length} shown.`
            : "Most urgent first: a date today, then an unexplained move, then a data fault."
        }
        aside={<AsOf date={asOf} />}
      >
        {waits.length ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {waits.slice(0, WAIT_SHOWN).map((s) => (
                <WaitCard key={s.row.symbol} item={s} />
              ))}
            </div>
            {waitHidden > 0 ? (
              <p className="text-muted-foreground mt-3 text-sm">
                <span className="num">{waitHidden}</span> further assets are in WAIT for reasons
                less urgent than every card above. Each one carries its reason on its own asset page.
              </p>
            ) : null}
          </>
        ) : (
          <Empty>
            Nothing is in WAIT{Object.keys(current).length > 0 ? ` under ${showing}` : ""}. For a
            rule table whose fall-through is WAIT that is unusual rather than reassuring, so check
            the source health in Details below before reading it as good news.
          </Empty>
        )}
      </Section>

      {/* The legend, under the three lists rather than above them. A reader who has just scrolled
          past forty rows of LONG and SHORT is the one who needs it; printing it first would be
          explaining an answer nobody has been given yet. Three sentences, no stored vocabulary. */}
      <p className="text-muted-foreground border-border mt-6 border-t pt-4 text-sm">
        <strong className="text-foreground">LONG</strong> or{" "}
        <strong className="text-foreground">SHORT</strong> means the rules found a setup and a
        level that would prove it wrong. <strong className="text-foreground">WAIT</strong> means
        no clear action today. None of it is a promise, and confidence says how much evidence sat
        behind the reading — not how likely it is to work.
      </p>

      {/* Everything that survived the rewrite, collapsed.
          It is one `<details>` rather than three because a reader who wants any of it wants to be
          somewhere other than the three lists, and three separate toggles would put that decision
          in front of them three times. Open by default would simply be the old page again. */}
      <details className="border-border bg-muted/30 mt-10 rounded-lg border px-4 py-1 text-sm sm:py-3">
        <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
          Details: industries, data freshness, and how to read this
        </summary>
        <div className="mt-2 pb-2">
          <HowToRead
            points={[
              <>
                <strong>Nothing here is a forecast.</strong> Every verdict is a reading of data that
                already exists, measured between two dates that are always shown.
              </>,
              <>
                <strong>The confidence badge grades the evidence, not the direction.</strong> High
                means the reading is well measured. A high-confidence SHORT is not a bad asset and a
                high-confidence LONG is not an endorsement.
              </>,
              <>
                <strong>WAIT is an answer.</strong> It means the rule table refused to name a
                direction, and the card says which input was missing or which two timeframes
                disagreed. It never means nothing was checked.
              </>,
              <>
                <strong>Compare percentages, not sizes, across markets.</strong> The Karachi figures
                are in rupees and are not comparable with the dollar figures beside them.
              </>,
              <>
                <strong>Check the freshness table below.</strong> If a job failed, the previous rows
                stay and this page keeps working. The dates there are how you find out.
              </>,
            ]}
          />

          {byMarket.map(([market, industries]) => (
            <Section key={market} title={MARKET_NAME[market] ?? market}>
              <div className="grid gap-3 sm:grid-cols-2">
                {industries.map((ind) => {
                  const top = byIndustry.get(ind.id)?.slice(0, 3) ?? [];
                  const largest = largestByIndustry.get(ind.id);
                  const l = largest?.asset;
                  const assetTotal = ind._count.assets;
                  const withSize = sizeCountByIndustry.get(ind.id) ?? 0;
                  const partial = withSize > 0 && withSize < assetTotal;
                  const priced = pricedByIndustry.get(ind.id) ?? 0;
                  const ranked = top.length > 0 || Boolean(largest);
                  // The as-of date comes off whichever ranking this card is actually printing.
                  // Reading it off the return rows alone produced "as of no date" on every industry
                  // that has a size ranking and no 24-month one — a card showing a real, dated
                  // figure while claiming to have no date, which reads as a broken page and does not
                  // match the industry page the card links to.
                  const asOfRanking = rankingAsOf(top) ?? largest?.periodEnd ?? null;
                  return (
                    <Card key={ind.id} href={`/industry/${ind.slug}`}>
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="font-medium">{ind.name}</h3>
                        {ranked ? <AsOf date={asOfRanking} /> : null}
                      </div>
                      <p className="text-muted-foreground mt-1 text-xs">{ind.summary}</p>
                      {!ranked ? (
                        <p className="text-muted-foreground mt-3 text-sm leading-relaxed">
                          {priced === 0
                            ? `No prices are stored for any of the ${assetTotal} assets here yet, so there is nothing to rank. Size and returns appear once the daily price job has fetched them.`
                            : `No ranking is stored for this industry yet, although ${priced} of its ${assetTotal} assets have prices. The ranking is computed nightly and will appear on the next run.`}
                        </p>
                      ) : l ? (
                        <p className="mt-3 text-sm">
                          Largest now:{" "}
                          <span className="underline underline-offset-2">{l.name}</span>{" "}
                          <span className="num">{money(largest.value, ind.currency)}</span>
                          <ConfidenceBadge
                            grade={largest.confidence}
                            className="ml-1.5 align-middle"
                          />
                          <span className="text-muted-foreground ml-1.5 text-xs">
                            {sizeLabel(l.capBasis)}
                          </span>
                          {partial ? (
                            <span className="text-muted-foreground block text-xs">
                              Largest of the {withSize} of {assetTotal} assets here that publish a
                              size figure.
                            </span>
                          ) : null}
                        </p>
                      ) : (
                        <p className="text-muted-foreground mt-3 text-sm">
                          No asset in this industry publishes a size figure. Returns are shown
                          instead.
                        </p>
                      )}
                      {!ranked ? null : top.length ? (
                        <ul className="mt-2 space-y-0.5 text-sm">
                          {top.map((r) => (
                            <li key={r.id} className="flex items-center justify-between gap-3">
                              <span>{r.asset.name}</span>
                              <span className="flex items-center gap-2">
                                <span className={`num ${toneClass(r.value)}`}>{pct(r.value)}</span>
                                <ConfidenceBadge grade={r.confidence} />
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-muted-foreground mt-2 text-sm">
                          No 24 month ranking stored yet.
                        </p>
                      )}
                    </Card>
                  );
                })}
              </div>
            </Section>
          ))}

          {/* Kept, and kept last. It is how a reader learns a feed died rather than guessing that a
              quiet week is a quiet week. */}
          <Section
            title="Data freshness"
            lead="What is stored right now, so a stale page is obvious rather than hidden."
          >
            <div className="mb-4">
              <SourceHealthBlock sources={health} brief />
            </div>
            <Table
              head={
                <>
                  <th className="px-3 py-2 font-medium">Table</th>
                  <th className="px-3 py-2 text-right font-medium">Rows</th>
                  <th className="px-3 py-2 text-right font-medium">Newest</th>
                </>
              }
            >
              <tr>
                <td className="px-3 py-2">Price snapshots</td>
                <td className="num px-3 py-2 text-right">
                  {fresh.snap._count.toLocaleString("en-US")}
                </td>
                <td className="num px-3 py-2 text-right">{isoDate(fresh.snap._max.date)}</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Rankings</td>
                <td className="num px-3 py-2 text-right">
                  {fresh.rank._count.toLocaleString("en-US")}
                </td>
                <td className="num px-3 py-2 text-right">{isoDate(fresh.rank._max.periodEnd)}</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Product signals</td>
                <td className="num px-3 py-2 text-right">
                  {fresh.signal._count.toLocaleString("en-US")}
                </td>
                <td className="num px-3 py-2 text-right">{isoDate(fresh.signal._max.periodEnd)}</td>
              </tr>
              <tr>
                <td className="px-3 py-2">News items</td>
                <td className="num px-3 py-2 text-right">
                  {fresh.news._count.toLocaleString("en-US")}
                </td>
                <td className="num px-3 py-2 text-right">{isoDate(fresh.news._max.publishedAt)}</td>
              </tr>
            </Table>
          </Section>
        </div>
      </details>
    </div>
  );
}
