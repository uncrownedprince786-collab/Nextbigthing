import { latestChange } from "@/lib/stateChange";
import Link from "next/link";
import { unstable_cache } from "next/cache";
import {
  AsOf,
  Card,
  ConfidenceBadge,
  WaitBasisChip,
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
  getFreshness,
  getProducts,
  getIndustriesByMarket,
  getPricedAssetsByIndustry,
  rankingAsOf,
} from "@/lib/queries";
import { todayISO } from "@/lib/decisionInput";
// The overview and the four class indexes read the same rows through the same verdict, so the
// scoring, the ordering and the list-row shape live in one module rather than once per route.
// A second copy of any of them is how two pages come to disagree about what a name is.
import {
  ASSET_CLASSES,
  byCloseness,
  byConfidence,
  eventLabel,
  scoreRows,
  toListRow,
  type Scored,
} from "@/lib/assetClass";
import { cachedDecisionRows, cachedSourceHealth } from "@/lib/cached";
import { TopByClass } from "@/components/topByClass";
import { WeeklyFocusBlock } from "@/components/weeklyFocusBlock";
import { ProductsCard } from "@/components/productsCard";
import { EVENT_SOON_DAYS } from "@/lib/decision";
import { DecisionList, SectorBoard } from "@/components/decision";
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

const cachedFreshness = unstable_cache(getFreshness, ["freshness"], HOUR);
// Products, for the band under the asset classes. Cached on the same hour as everything
// else on this page so the overview is one snapshot rather than several.
const cachedProducts = unstable_cache(() => getProducts(), ["products-all"], HOUR);
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
      // Same rule as Forex: the value is the mapped `Market`, keyed off `assetType` rather than
      // the industry column, so the one chip covers the precious, industrial and energy groups
      // the contracts are filed under without naming any of them.
      { label: "Commodities", value: "Commodity" },
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

/// How many developing rows are printed before the rest are counted rather than listed.
///
/// Larger than `WAIT_SHOWN` because this list is ordered by a measured distance from a threshold
/// rather than by a reason, so the twelfth row is genuinely nearer to confirming than the
/// thirteenth, and the cut is the only thing keeping a 162-row list off the front page.
const DEVELOPING_SHOWN = 18;

/// How many LONG and SHORT rows are printed before the rest are counted rather than listed.
///
/// These two were the only blocks on this page that printed everything they had, which was fine
/// at 160 names and is not at 477: the two tables alone ran to eighty rows. Twelve matches
/// `WAIT_SHOWN` deliberately -- four blocks that each cut at a different number read as four
/// different rules rather than one -- and the order is `byOpportunity`, so what is hidden is
/// always less well evidenced than what is shown, never more urgent.
const LIST_SHOWN = 12;

/// Sectors printed in the overview's sector block before the rest are counted.
///
/// The market pages print every sector because there the block *is* the index. Here it is a
/// summary, and 41 sector cards would make the overview longer than the page it is summarising.
/// Six is the same judgement `LIST_SHOWN` makes one block up: enough to see the shape of the
/// day, ordered so what is cut is always less well evidenced than what is shown.
const SECTORS_SHOWN = 6;

const MARKET_NAME: Record<string, string> = {
  US: "United States listings",
  PK: "Pakistan Stock Exchange",
};

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
          {/* Why it is a WAIT, which the grade alone cannot say: "Low" reads as a weak judgement
              even when nothing was judged at all. */}
          <WaitBasisChip basis={decision.basis} />
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

      {/* The same three words the tables use. This card is the one place on the site that still
          said "Entry" and "Exit if wrong" after the relabelling, because it is not a
          `DecisionList` row and the sweep that renamed the columns did not reach it. A reader
          moving between the overview and a market page must not meet two vocabularies for one
          level. The current price leads, for the reason it leads everywhere else: every figure
          after it is read against it. */}
      <p className="text-muted-foreground text-xs">
        Price{" "}
        <span className="num">
          {row.close !== null ? price(row.close, currency) : "no close yet"}
        </span>
        {" · "}Entry zone{" "}
        <span className="num">
          {decision.entry
            ? `${price(decision.entry.low, currency)} to ${price(decision.entry.high, currency)}`
            : "no entry band measured"}
        </span>
        {" · "}Stop loss{" "}
        <span className="num">
          {decision.invalidation !== null ? price(decision.invalidation, currency) : "no stop level set"}
        </span>
      </p>
    </Card>
  );
}

/// One developing card: the direction forming, and what would confirm it.
///
/// Deliberately shaped unlike a `DecisionList` row. A list row's columns say entry, exit and
/// confidence -- the furniture of a decision -- and printing them here would make a forming read
/// look like an actionable one. What this row owes the reader is the direction, the distance, and
/// the named condition that is missing.
function DevelopingCard({ item }: { item: Scored }) {
  const { row, decision, market } = item;
  const forming = decision.developing;
  if (!forming) return null;
  const short = forming.would === "SHORT";

  return (
    <Card href={`/asset/${encodeURIComponent(row.symbol)}`} className="space-y-1.5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <span className="min-w-0">
          <span className="block text-sm font-medium">{row.name}</span>
          <span className="num text-muted-foreground block text-xs">{row.symbol}</span>
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <Pill tone="default">{market}</Pill>
          {/* "potential", in the chip itself. The word is what keeps a glance from reading this
              as the LONG list, and a reader who only ever sees chips must still see it. */}
          <Pill tone="default">potential {forming.would}</Pill>
        </span>
      </div>

      <p className="text-sm leading-relaxed">
        {short ? "Falling" : "Rising"} trend in place, not yet confirmed.
        {forming.closeness !== null ? (
          <>
            {" "}
            Nearest confirmation is{" "}
            <span className="num">{Math.round(forming.closeness * 100)}%</span> of the way to its
            threshold.
          </>
        ) : null}
      </p>

      <ul className="space-y-0.5">
        {forming.waitingOn.slice(0, 2).map((w, i) => (
          <li key={i} className="text-muted-foreground text-xs leading-relaxed">
            {w}
          </li>
        ))}
      </ul>
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

  const scored: Scored[] = scoreRows(rows, health, today);

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
  // Both directions, in one list, for the sector block. Built from the same `matching` rows the
  // two lists above use, so a filter narrows all three together and the overview cannot show a
  // name in one block that it has filtered out of another.
  const sectorRows = [...longs, ...shorts].map(toListRow);
  // A developing row is still a WAIT and is counted in neither of the two directional lists. It
  // is lifted out of the WAIT list rather than added beside it, because leaving it in both would
  // print the same asset twice with two different framings on one page.
  const allWaits = matching.filter((s) => s.decision.action === "WAIT");
  const developing = allWaits.filter((s) => s.decision.developing !== null).sort(byCloseness);
  const waits = allWaits.filter((s) => s.decision.developing === null).sort(byUrgency);
  const waitHidden = Math.max(0, waits.length - WAIT_SHOWN);
  // Calls that ended in the newest decision cycle -- invalidated, overridden or reversed into a WAIT --
  // counted for the closed line above the folded list, from the same function the row badges use.
  const endedNow = allWaits.filter((w) => {
    const c = latestChange({
      action: w.decision.action,
      runAction: w.row.callAction,
      runSince: w.row.callSince,
      runPrev: w.row.callPrev,
      runGate: w.row.callGate,
      latestCycle: w.row.callLatest,
    });
    return c !== null && c.warn;
  }).length;
  const developingHidden = Math.max(0, developing.length - DEVELOPING_SHOWN);

  // Rows exist, and the filters removed all of them. Without this the reader gets three empty lists
  // and no way to tell a filtered page from a broken one.
  const emptiedByFilter =
    scored.length > 0 && matching.length === 0 && Object.keys(current).length > 0;

  const [byMarket, risers, sizeNow, pricedEntries, fresh, products] = await Promise.all([
    cachedIndustriesByMarket(),
    cachedRisers(),
    cachedSizeNow(),
    cachedPricedByIndustry(),
    cachedFreshness(),
    cachedProducts(),
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

      {/* The browse block sits above the chips, and above the three lists, because it answers a
          different question: not "what should I look at today" but "what is in here". It reads the
          unfiltered `scored` on purpose -- see TopByClass -- so filtering the lists below never
          empties it. */}
      {/* Above the browse block, because it answers the question a reader arrives with -- "is
          there anything to do today" -- where the browse block answers "what is in here". It reads
          the unfiltered `scored` for the same reason TopByClass does: a chip narrowing the lists
          below must not empty the one block that says what the site acted on. */}
      <WeeklyFocusBlock rows={scored} />

      <TopByClass classes={ASSET_CLASSES} rows={scored} />

      {/* Products are not assets and carry no entry, stop or market, so they get their own band
          under the asset classes rather than a sixth cell in that grid. */}
      <ProductsCard rows={products} />

      <div className="mt-8">
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
        lead={
          longs.length > LIST_SHOWN
            ? `Price is trending up, the longer view is not against it, and there is a level that would prove the reading wrong. Best evidenced first; ${LIST_SHOWN} of ${longs.length} shown.`
            : "Price is trending up, the longer view is not against it, and there is a level that would prove the reading wrong."
        }
        cap={LIST_SHOWN}
        rows={longs.map(toListRow)}
        empty={
          Object.keys(current).length > 0
            ? `No stored asset reads LONG under ${showing}. Clear the filters to see the rest.`
            : "No asset reads LONG today. That is an ordinary state, not a missing list: the rule table refuses a direction without an invalidation level, and most days most names have none."
        }
      />

      <DecisionList
        title="SHORT candidates"
        lead={
          shorts.length > LIST_SHOWN
            ? `Price is trending down, the longer view is not against it, and there is a level that would prove the reading wrong. Best evidenced first; ${LIST_SHOWN} of ${shorts.length} shown.`
            : "Price is trending down, the longer view is not against it, and there is a level that would prove the reading wrong."
        }
        cap={LIST_SHOWN}
        rows={shorts.map(toListRow)}
        empty={
          Object.keys(current).length > 0
            ? `No stored asset reads SHORT under ${showing}. Clear the filters to see the rest.`
            : "No asset reads SHORT today. Same rule as LONG, mirrored: a direction is only printed when a break level is stored."
        }
      />

      {/* The same blocks the market pages are built from, in the same order, so a reader who
          learned the overview has not got to learn a second layout when they click through.
          
          It is not a third copy of the two lists above: those answer "the best evidenced names
          anywhere", ranked across every sector, and this answers "what is each group doing",
          which is the question the two lists cannot be read for. Six sectors here against every
          sector on a market page, for the reason `SECTORS_SHOWN` gives. */}
      <Section
        title="By sector"
        lead={
          `Both directions together, grouped the way the market pages group them. ` +
          (sectorRows.length > 0
            ? `Longs lead each block, then shorts, best evidenced first.`
            : ``)
        }
      >
        <SectorBoard
          rows={sectorRows}
          maxSectors={SECTORS_SHOWN}
          empty={
            Object.keys(current).length > 0
              ? `No stored asset carries a direction under ${showing}. Clear the filters to see the rest.`
              : "No asset carries a direction today, so there is no sector to group."
          }
        />
      </Section>

      <Section
        title="Developing"
        lead={
          developingHidden > 0
            ? `A direction is in place and the conditions behind it are not all present yet. Nearest to confirming first; ${DEVELOPING_SHOWN} of ${developing.length} shown.`
            : "A direction is in place and the conditions behind it are not all present yet. Nearest to confirming first."
        }
        aside={<AsOf date={asOf} />}
      >
        {developing.length ? (
          <>
            {/* Said once, above the cards, and not left to the chips. A reader who takes this
                list as a buy list has been misled by the page, not by the rules. */}
            <Note>
              These are not actions. Each one is a trend the stored conditions do not yet confirm,
              shown with the measurement that is missing, because the alternative is reading about
              it after it has happened.
            </Note>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {developing.slice(0, DEVELOPING_SHOWN).map((s) => (
                <DevelopingCard key={s.row.symbol} item={s} />
              ))}
            </div>
            {developingHidden > 0 ? (
              <p className="text-muted-foreground mt-3 text-sm">
                <span className="num">{developingHidden}</span> further assets have a direction
                forming further from confirming than every card above. Each one carries its own
                reading on its asset page.
              </p>
            ) : null}
          </>
        ) : (
          <Empty>
            No asset has a direction forming{Object.keys(current).length > 0 ? ` under ${showing}` : ""}.
            That means every stored trend is either confirmed and in the two lists above, or there
            is no trend to confirm.
          </Empty>
        )}
      </Section>

      {/* Held back, folded away. WAIT is the rule table's working state -- most names are in it on any
          day -- and twelve cards of it sat between the reader and the calls. It stays one click away,
          with every row's reason, because a held-back name must still be findable; and the one thing a
          holder cannot miss is said on the closed line itself: how many calls ended in this cycle. */}
      <details className="border-border bg-muted/30 mt-10 rounded-lg border px-4 py-1 text-sm sm:py-3">
        <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
          Held back: {waits.length} {waits.length === 1 ? "name" : "names"} with no call today
          {endedNow > 0 ? (
            <span className="text-down">
              {" "}
              · {endedNow} {endedNow === 1 ? "call" : "calls"} ended in the latest cycle
            </span>
          ) : null}
        </summary>
        <div className="mt-3 pb-2">
          <p className="text-muted-foreground mb-3 text-sm">
            Most urgent first: a date today, then an unexplained move, then a data fault.
            {waitHidden > 0 ? ` ${WAIT_SHOWN} of ${waits.length} shown.` : ""}
          </p>
          {waits.length ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {waits.slice(0, WAIT_SHOWN).map((s) => (
                  <WaitCard key={s.row.symbol} item={s} />
                ))}
              </div>
              {waitHidden > 0 ? (
                <p className="text-muted-foreground mt-3 text-sm">
                  <span className="num">{waitHidden}</span> further assets are held back for reasons
                  less urgent than every card above. Each one carries its reason on its own asset page.
                </p>
              ) : null}
            </>
          ) : (
            <Empty>
              Nothing is held back{Object.keys(current).length > 0 ? ` under ${showing}` : ""}. For a
              rule table whose fall-through is WAIT that is unusual rather than reassuring, so check the
              source health in Details below before reading it as good news.
            </Empty>
          )}
        </div>
      </details>

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
