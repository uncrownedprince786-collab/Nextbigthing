import type { Metadata } from "next";
import { Card, HowToRead, Note, Section, SourceHealthBlock, Table } from "@/components/ui";
import { getIntradayCoverage, getSourceHealth } from "@/lib/queries";
import { loadOrDefer } from "@/lib/buildSafe";
import { isoDate } from "@/lib/format";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "Every ranking and demand number on this site, the free source it comes from, the formula behind it, and what is deliberately left blank.",
};

// The gate table, copied from the header comment of lib/decision.ts rather than restated. It is
// first-match-wins there and reads as a list here for the same reason: a reader is owed the one
// gate that fired, not all nine. Any edit to that file's order has to move these rows too.
const GATES = [
  { n: 1, gate: "No price series", answer: "WAIT", told: "Nothing is stored for this name." },
  { n: 2, gate: "Close too old", answer: "WAIT", told: "The number on the page is not today's number, and how old it is." },
  { n: 3, gate: "A source is silent", answer: "WAIT", told: "Which source answered nothing." },
  { n: 4, gate: "No stop level", answer: "WAIT", told: "There is no level at which being wrong is known." },
  { n: 5, gate: "Setup and longer view disagree, and the reward is not asymmetric", answer: "WAIT", told: "Which way each one points, and how far the reward fell short." },
  { n: 6, gate: "Setup up, longer view not down", answer: "LONG", told: "Setup is up, and what the longer view adds." },
  { n: 7, gate: "Setup down, longer view not up", answer: "SHORT", told: "Setup is down, and what the longer view adds." },
  { n: 8, gate: "A measured direction whose conditions are incomplete — the withheld trend, or failing that the side the two moving averages sit on — resting on volume, on the peer gap, on an entry event or on an asymmetric reward, with news coverage readable and not worded against it", answer: "LONG / SHORT", told: "Which reading it acted on, which confirmation it rests on, and every condition still absent." },
  { n: 9, gate: "Anything left, including a check 8 direction nothing carries", answer: "WAIT", told: "Which part is absent — setup, longer view, or both." },
];

// The four refusals every direction from checks 5 to 8 must pass before it prints, in the order
// `direction()` in lib/decision.ts runs them. Each is a refusal and nothing else: none of them turns a
// direction into the opposite one (brain.md rule 93).
const REFUSALS = [
  { n: "a", gate: "The close is already through the stop", answer: "WAIT", told: "The call ended at its stop. The level it ended at; no entry, exit or opposite call." },
  { n: "b", gate: "A stored macro veto, a day old at most", answer: "WAIT", told: "That the gatekeeper refused it. Never the other side." },
  { n: "c", gate: "It turns against a call of the last week with nothing confirming the turn", answer: "WAIT", told: "Which call it turns against, and what would confirm the turn." },
  { n: "d", gate: "A short where shorts measured a loss (US, commodities) or after a fall of 10% or more, with no confirmation", answer: "WAIT", told: "Why a short needs backing here." },
];

// What runs after the table, on every list, every asset page, /api/signals and the nightly log (one
// function, `decideCall` in lib/resolve.ts). Each step can only take a direction away or lower a grade.
const AFTER = [
  { n: "A", gate: "None of the five confirmations backs the direction", answer: "WAIT", told: "Every confirmation that is absent." },
  { n: "B", gate: "The stop is nearer the entry zone than one average true range", answer: "the stop moves", told: "The stop, one average true range beyond the zone." },
  { n: "C", gate: "The data check, again, last: no close, an unreadable date, a close too old, a silent source", answer: "WAIT", told: "The data reason. Nothing earlier can carry a direction past it." },
  { n: "D", gate: "To be published: a trading style, an entry range, a stop at least 1 x ATR beyond it, a measured exit, reward:risk of at least 1.2, a confirmation", answer: "published, or withheld", told: "A withheld direction is on no list; its own page says “Not a published call” and gives no levels." },
];

// What stopped being a gate on 2026-10-09, and what happened to it instead.
//
// On the page because a reader who knew the old table is owed the change, and a reader who did
// not is owed the fact that these two things are still measured and still printed. A system that
// quietly drops a caveat it used to refuse on has told its readers less, not more.
const DEMOTED = [
  {
    gate: "Unusual move, thin news",
    was: "WAIT — 60 of 477 names on 2026-10-09",
    now: "Printed under “What argues against it”, with the story count or the fact that no feed answered. It does not change the action.",
    why: "Thin news under a move says the published explanation has not arrived. It is not evidence that the direction is wrong, and refusing every unexplained move refuses exactly the moves that happen before the reason is public.",
  },
  {
    gate: "Peers argue the other way",
    was: "WAIT — 15 of 477 names on 2026-10-09",
    now: "Printed under “What argues against it” with the measured gap in points, and the confidence grade is capped one step for it.",
    why: "A name lagging its group is a real and often decisive fact, but it is a fact about relative return. Vetoing an absolute direction with it discards the direction rather than qualifying it.",
  },
];

// Every number the decision rules use, with the file it is read from. A rule table without its
// numbers is decoration, and a number without its file cannot be checked against the code.
const THRESHOLDS = [
  {
    value: "2 / 5 / 6 days",
    rule: "How old a close may be before gate 2 fires: Crypto 2, US 5, PSX 6. Anything else 5.",
    file: "lib/decision.ts STALE_AFTER_DAYS",
  },
  {
    value: "8 stories",
    rule: "Below this, news counts as thin. Printed as a caveat under an unusual move; no longer a check.",
    file: "lib/decision.ts THIN_NEWS_BELOW",
  },
  {
    value: "2x the risk",
    rule: "A measured reward at least this far above the stop carries a direction past a disagreeing longer view (check 5) or past incomplete conditions (check 8). 111 of 717 stored setups reached it on 2026-10-09.",
    file: "lib/decision.ts ASYMMETRY_CLEARS",
  },
  {
    value: "2.5 to 11 points, by market",
    rule: "How far from its peer median a name must be over 20 sessions before that counts either way: confirming the direction, or arguing against it and capping the grade. FX 2.5, PSX 7, US 7.5, crypto 11 — twice each market's own measured median gap, because a point of relative return means a different thing to a currency pair than to a coin.",
    file: "lib/decision.ts REL_BAND",
  },
  {
    value: "positive or negative",
    rule: "A published coverage verdict pointing the opposite way stops the matched past days counting as confirmation, and stops check 8 carrying a trend at all. A neutral reading, or none, changes nothing. 378 of 454 stored readings were neutral on 2026-10-09.",
    file: "lib/decision.ts newsContradicts",
  },
  {
    value: "±2σ",
    rule: "A move counts as unusual at this size, or whenever the investigate job wrote a move or volume trigger at all.",
    file: "lib/decisionInput.ts isUnusualMove",
  },
  {
    value: "3 days",
    rule: "A dated event this close marks the timing CARE, whatever the decision is.",
    file: "lib/decision.ts EVENT_SOON_DAYS",
  },
  {
    value: "3 similar days",
    rule: "Below this many stored similar past days, no range is quoted under the decision.",
    file: "lib/decision.ts ANALOGS_MIN",
  },
  {
    value: "2 sources",
    rule: "Below this many demand sources answering, a product reads NO CLEAR SIGNAL instead of being graded.",
    file: "lib/productDecision.ts MIN_SOURCES_TO_JUDGE",
  },
  {
    value: "2 days",
    rule: "How stale a crypto venue's newest bar may be before the chain keeps looking. Matches the Crypto figure above on purpose.",
    file: "jobs/prices.py CRYPTO_FRESH_DAYS",
  },
];

const RANKINGS = [
  {
    basis: "Size at a past date",
    formula: "Price on the snapshot date multiplied by shares outstanding.",
    source: "Yahoo Finance for equities and funds, CoinPaprika for crypto market cap",
    gap: "Size is not one comparable quantity across the site. A stock's is market capitalisation, a fund's is assets under management, and a commodity future publishes neither, so it is shown without a size rather than given a proxy. Rankings only ever compare assets inside one industry, and every table says how many assets in that industry actually carry a size figure.",
  },
  {
    basis: "Size now",
    formula: "Same formula, using the newest stored close.",
    source: "Yahoo Finance, CoinPaprika",
    gap: "A stock split or new issue between the two dates is not adjusted for, so a rank change can reflect a share count change rather than a price change.",
  },
  {
    basis: "Total return",
    formula: "Close on the later date divided by close on the earlier date, minus one. Two windows: 2019-01-01 to the last close of 2021, and that date to the newest close. Price only, dividends are not added.",
    source: "Yahoo Finance, Binance klines",
    gap: "Because dividends are excluded, a high yielding asset looks weaker than a total return figure would suggest. The number is labelled as a price return everywhere it appears.",
  },
  {
    basis: "24 month relative strength",
    formula: "The asset's 24 month return minus the average 24 month return of the other assets in the same industry. A positive number means the asset beat its own peers.",
    source: "Yahoo Finance, Binance",
    gap: "It is a ranking, not a prediction. A strong number can follow a large fall, and an asset with less than 24 months of history is left out of the list rather than given a short window.",
  },
];

const SIGNALS = [
  {
    source: "Google Trends",
    measure: "Search interest for the product term, weekly, last 8 weeks against the 8 before.",
    caveat: "Relative interest on a 0 to 100 scale inside one request, so it is a direction and a rough size, not a search count. A term shared by several products will move for all of them.",
  },
  {
    source: "Wikipedia pageviews",
    measure: "Pageviews for the mapped article, last 8 weeks against the 8 before.",
    caveat: "Interest in the article is not interest in buying. The article title is chosen in the seed list, and for a few products the page does not exist, so the source is simply missing.",
  },
  {
    source: "Hacker News",
    measure: "Number of stories in the Algolia search index mentioning the product, last 90 days against the 90 before.",
    caveat: "A very small audience. Useful as one input, never on its own.",
  },
  {
    source: "Reddit",
    measure: "Posts in the product's subreddits through the public search RSS. The last 30 days against the rate over the 90 days immediately before, both cut from the year feed. The longer window is divided by three first, so the two figures cover the same length of time.",
    caveat: "Rate limited and often silent, so a missing value is common and shown as missing. Reddit caps the 30 day feed at 25 results, which is why both windows are read from the year feed instead. Post counts here are small: across all thirty products the largest 90 day window is fifteen posts, so a percentage built on a single post is a rounding artifact and is not published.",
  },
  {
    source: "Google News RSS",
    measure: "Article count for the product name, last 30 days against the 30 before.",
    caveat: "News volume follows a story, so a spike usually means something happened rather than that demand grew.",
  },
];

const NEW_SECTIONS = [
  {
    title: "Pakistan Stock Exchange",
    source:
      "The exchange's own end of day file, dps.psx.com.pk/download/mkt_summary/<date>.Z, a ZIP holding one pipe delimited line per listed symbol.",
    measure:
      "Close and volume per symbol per trading day. Eight sectors, using the exchange's own sector groupings, and every symbol was checked against the closing files for both 2021-12-31 and the latest trading day before being added.",
    gap: "Market capitalisation exists for the latest close only. The exchange publishes a current share count with no history behind it, and multiplying today's share count by a 2021 price would produce a figure that was never true, so these sectors show no pre-AI size at all. Prices and returns are in rupees: a return earned over a period of currency depreciation is not the same quantity as a dollar return, and no conversion is applied.",
  },
  {
    title: "Event windows",
    source:
      "The event date and description come from the public record, with a source URL shown on each event page. The price moves come from closes already stored by this site.",
    measure:
      "For each event, the change between the stored close nearest the event date and the stored close nearest 14 and 30 days later, for every asset that has both. Ranked by the size of the move, largest first, with rises and falls shown separately.",
    gap: "No causation is measured and none is claimed. Over any thirty day window some asset has the largest move whether or not anything happened, so a large number in an event table is evidence the asset moved and nothing else. Events are chosen by hand rather than detected, because detecting them from the price series would select the dates that sit next to large moves and every row would then confirm a relationship the selection had created.",
  },
  {
    title: "Marketplace rankings",
    source:
      "Amazon Best Sellers, the first page of nine categories, read as published. eBay's sold and completed search returns 403 to an ordinary request, so it is not used.",
    measure:
      "The top thirty positions of each category, with each listing's movement against the previous stored run of the same category.",
    gap: "A rank is an order, never a volume: Amazon publishes no units, so nothing here says how much of anything sold. Only the first page is read, because the rank counter restarts on page two and using it would mean guessing an offset. A listing absent from the previous run is reported as new rather than as a rise, because its earlier position was never published. None of this enters any product's demand score.",
  },
];

export default async function MethodologyPage() {
  const [health, intraday] = await loadOrDefer(async () => [await getSourceHealth(), await getIntradayCoverage()] as const);
  return (
    <div className="max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Methodology</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Every figure on this site is computed by a script from a free public source and
          stored in a database. Nothing is estimated, filled in or carried over from another
          period. Where a source cannot answer, the cell says so.
        </p>
      </div>

      {/* The written rule table. It sits first because the decision is what the site now leads
          with on every other page, and a reader who disagrees with a rule should be able to find
          it without reading an essay first. Every number here carries the file it was read from,
          so the next person can check it rather than trust this page. */}
      <Section
        title="The decision rule"
        lead="Nine checks in a fixed order, four refusals every direction must pass, and four steps after them that can only take a direction away. The first check that matches decides, and you are told that one reason rather than all of them."
      >
        <Table
          minWidth="760px"
          head={
            <>
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Check</th>
              <th className="px-3 py-2 font-medium">Answer</th>
              <th className="px-3 py-2 font-medium">What you are told</th>
            </>
          }
        >
          {[...GATES, ...REFUSALS, ...AFTER].map((g) => (
            <tr key={g.n}>
              <td className="num text-muted-foreground px-3 py-2">{g.n}</td>
              <td className="px-3 py-2">{g.gate}</td>
              <td className="px-3 py-2 font-medium">{g.answer}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">{g.told}</td>
            </tr>
          ))}
        </Table>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          Rows a to d are the refusals checks 5 to 8 run before a direction prints; rows A to D run after
          the table, everywhere a call appears. Until 2026-10-11 a layer after the table turned refusals
          into calls — a crossed stop into the opposite side, an unconfirmed short into SHORT anyway, a
          macro veto into the other side, a stale or silent name into whatever its momentum leaned, and
          a name with nothing measured into LONG. It is gone: a refusal stays a refusal, and a name the
          table refuses is held back with its reason.
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          Checks 1 to 4 are faults in the data and name the missing thing. Check 5 is real
          disagreement in the data and is not a fault. Check 9 is WAIT rather than a direction
          because a rule table that falls through to LONG is how a page recommends a trade it has
          no reason for.
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          Check 8 is the one that produces a direction over an incomplete set of conditions, and it
          is deliberately narrow. The direction is one already measured and stored, never one
          computed here: either the trend reading the condition job withheld, or — where even that
          came back mixed — which side of the 50 day average the 20 day average sits on. It is
          only carried when one of four stored figures backs it: volume at or above its own
          20-session average on a session that moved the trend&rsquo;s way, a gap against its peer group wide enough for the market it trades
          in, an entry event on this session, or a measured reward of at least twice the risk —
          and only when news coverage could be read and is not worded against it. With none of the
          four, the name falls through to check 9, and every missing confirmation is still listed
          on the page.
        </p>
        <h3 className="mt-6 font-medium">The grade, and whether calls have been right</h3>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed">
          Two different questions get two different labels. The <strong className="text-foreground">grade</strong>{" "}
          (High, Medium, Low) is the evidence for this one reading: two or more of the five
          confirmations is High, one is Medium. It says nothing about results. <strong className="text-foreground">Outcome
          status</strong> says whether calls have been right, measured on calls whose five-session window has
          closed, graded the way the logbook grades them: untested while none has matured, pending until
          30 have, then the share that were accurate with its 95% interval, called validated only if the
          whole interval is above 50%. Every call&rsquo;s page, the lists, the coming-week block, the logbook
          and /api/signals print the same outcome sentence from the same counts.
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          Volume is participation, not direction. It counts as a confirmation only on a session that
          moved the call&rsquo;s way: heavy trading on a day the price fell is not evidence for a LONG. When
          it does not count, the page says so. Execution is a third question again &mdash; checked,
          unverified or blocked &mdash; and a call whose execution is not checked is shown &ldquo;IN
          ZONE&rdquo;, never &ldquo;NOW&rdquo;, even with its close inside the entry zone.
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          The two readings are never given the same words. Three things lining up — the close, the
          20 day average and the 50 day average — is a trend. Two things, with the price sitting
          between them, is written as &ldquo;price is between its own averages, with the 20 day
          above the 50 day&rdquo;, because calling that a trend would claim a measurement that was
          not taken.
        </p>

        <h3 className="mt-6 font-medium">When the news and the history disagree</h3>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed">
          The “what followed similar past days” figure is matched on three things — the day&rsquo;s
          return, the volume multiple and the five-day return — and nothing else. None of those
          past days had today&rsquo;s headline in it. So when the stored coverage reading carries a
          direction and it is the opposite one, those matched days stop counting as confirmation:
          they describe a situation that is missing the thing most likely to move the price next.
          The set is still shown, with how many days were in it and why it is not being counted.
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          This only ever takes evidence away. Coverage pointing the <em>same</em> way is not
          counted as confirmation and cannot raise a grade — the reading is a word list over
          headlines, with no article bodies, no negation and no sarcasm, which is enough to
          withdraw a claim and not enough to make one. A reading that came back neutral, and an
          asset with no reading stored at all, both change nothing.
        </p>

        <h3 className="mt-6 font-medium">What a LONG or a SHORT here is, and what it is not</h3>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed">
          It is a <strong>trend reading</strong>. The condition behind nearly every direction is
          the close sitting above its own 20-day average, which sits above its 50-day average —
          or, where those three do not line up, the two averages on one side of each other. Both
          are backward-looking by construction: they describe a move that has already started.
          Nothing here attempts to detect a move before it begins.
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          Measured over the 467 directional readings on 2026-10-09, this is how far along each one
          already was when it was written:
        </p>
        <Table
          minWidth="640px"
          head={
            <>
              <th className="px-3 py-2 font-medium">Reading</th>
              <th className="px-3 py-2 font-medium">Move already made, 20 sessions</th>
              <th className="px-3 py-2 font-medium">Where it sits in its own range</th>
              <th className="px-3 py-2 font-medium">Sessions the trend had already held</th>
            </>
          }
        >
          <tr>
            <td className="px-3 py-2">LONG (166)</td>
            <td className="num px-3 py-2">median +3.1%, upper quarter above +11.3%</td>
            <td className="num px-3 py-2">72% of the way up</td>
            <td className="num px-3 py-2">median 40</td>
          </tr>
          <tr>
            <td className="px-3 py-2">SHORT (301)</td>
            <td className="num px-3 py-2">median −3.9%, lower quarter below −7.2%</td>
            <td className="num px-3 py-2">18% of the way up</td>
            <td className="num px-3 py-2">median 24</td>
          </tr>
        </Table>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          So a typical long is a name that has already risen, sitting near the top of its own
          range, roughly forty sessions into the trend being read. A typical short is the mirror.
          Only 16% of longs and 13% of shorts are written within five sessions of the trend
          starting. <strong>These are not early entries and the site does not claim they are.</strong>
        </p>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          Whether that is a weakness is a separate question, and the stored history answers part of
          it: over 680,800 asset-sessions, a day on which volume reached 1.2 times its own average
          was followed by a move about a percentage point wider than an ordinary day. Trends tend
          to continue in <em>size</em>. The thing the same measurement does not support is the
          common belief that a quiet, compressed market precedes a large move: over 133,463
          compressed sessions the next twenty sessions moved <em>less</em> than average, not more.
          A pre-breakout detector was considered, measured, and not built, because the data said
          it would fire hardest on the names least likely to move.
        </p>

        <h3 className="mt-6 font-medium">What stopped being a check, and where it went</h3>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed">
          Two checks used to answer WAIT and no longer do. Both are still measured and both are
          still printed next to the decision, under “What argues against it”. Neither was removed
          from the page; both were moved out of the way of the answer.
        </p>
        <Table
          minWidth="760px"
          head={
            <>
              <th className="px-3 py-2 font-medium">Was a check</th>
              <th className="px-3 py-2 font-medium">What it did</th>
              <th className="px-3 py-2 font-medium">What it does now</th>
              <th className="px-3 py-2 font-medium">Why</th>
            </>
          }
        >
          {DEMOTED.map((d) => (
            <tr key={d.gate}>
              <td className="px-3 py-2">{d.gate}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">{d.was}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">{d.now}</td>
              <td className="text-muted-foreground px-3 py-2 text-xs">{d.why}</td>
            </tr>
          ))}
        </Table>

        <h3 className="mt-6 font-medium">Every number these checks use</h3>
        <Table
          minWidth="720px"
          head={
            <>
              <th className="px-3 py-2 font-medium">Number</th>
              <th className="px-3 py-2 font-medium">What it decides</th>
              <th className="px-3 py-2 font-medium">Read from</th>
            </>
          }
        >
          {THRESHOLDS.map((t) => (
            <tr key={t.file}>
              <td className="num px-3 py-2 whitespace-nowrap">{t.value}</td>
              <td className="px-3 py-2 text-xs leading-relaxed">{t.rule}</td>
              <td className="text-muted-foreground px-3 py-2 text-micro whitespace-nowrap">
                {t.file}
              </td>
            </tr>
          ))}
        </Table>
        <Note>
          Staleness is counted in calendar days, not trading days, because the question is whether
          the number on this page is today&apos;s number and a reader asks that on a Sunday too.
          Crypto trades every day, so 2 days is already a fault. US equities allow a Friday close
          to be read on the Monday. PSX gets one more day because it keeps more holidays, and a
          holiday must not read as a dead feed.
        </Note>

        <HowToRead
          title="Entry, Stop level, Timing and Confidence"
          points={[
            <>
              <strong>Which reading is the setup.</strong> A reading with a direction wins, in the
              order swing, longer, intraday — the shorter the view the sooner you would have to
              act, and intraday is last because a front page that re-reads itself through the
              session is a different page on every visit. With nothing directional, the swing
              reading is used as the honest &ldquo;measured, and flat&rdquo;.
            </>,
            <>
              <strong>Why the longer view can be absent.</strong> It only counts as a second
              opinion when it is a second row. When the directional reading <em>is</em> the longer
              one, there is nothing left to confirm it, so the longer view is recorded as absent
              and the row loses a confidence step — correctly, because one view is less evidence
              than two.
            </>,
            <>
              <strong>Entry.</strong> The zone is the range the two stored levels already span:
              the level the job wrote and the stop level it wrote. That range means something —
              it is where the trade is live but not yet wrong. No page widens it, because pages
              here do not compute their own figures.
            </>,
            <>
              <strong>Timing.</strong> <span className="num">NOW</span> only when the last close
              is inside that zone. Outside it, the honest answer is that you are waiting for a
              level, which is a different instruction. A dated event within 3 days overrides both
              and reads CARE.
            </>,
            <>
              <strong>Confidence.</strong> Counts weaknesses rather than scoring strengths: the
              two views not agreeing, fewer than 3 similar past days, news under 8 stories or
              never checked, and no entry zone. None weak is High, one is Medium, two or more is
              Low. Every WAIT is Low.
            </>,
          ]}
        />
        {/* The honest gaps. Naming them here is cheaper than a reader discovering that a number
            they expected to exist was invented to fill the hole. */}
        <h3 className="mt-6 font-medium">Numbers this site does not have</h3>
        <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed">
          <li>
            No measured entry band is stored anywhere. The zone is the two stored levels, and
            widening it by a volatility figure would be new arithmetic in the page layer.
          </li>
          <li>
            Crypto closes have no source health row, so check 3 can never name a blocked exchange.
            A blocked exchange shows up as check 2 instead, through a close that stops advancing.
            That is weaker than naming the source and it is the limit of what is stored.
          </li>
          <li>
            No hit rate for any of this. Readings are logged with the close beside them and
            measured later, and no rate is published until enough rows have matured.
          </li>
        </ul>
      </Section>

      <Section
        title="Two kinds of WAIT, and why they are labelled apart"
        lead="A WAIT because a measurement is missing is not a WAIT because the measurement came back unconvincing. Every WAIT on this site now says which, because reading one as the other overstates what is known."
      >
        <Table
          minWidth="680px"
          head={
            <>
              <th className="px-3 py-2 font-medium">Label</th>
              <th className="px-3 py-2 font-medium">What it means</th>
              <th className="px-3 py-2 font-medium">Which gates</th>
            </>
          }
        >
          <tr>
            <td className="px-3 py-2 align-top whitespace-nowrap">NOT MEASURED</td>
            <td className="px-3 py-2 align-top">
              A measurement this reading needs is absent, so nothing has been judged. The honest
              reading is &ldquo;unknown&rdquo;, not &ldquo;weak&rdquo;.
            </td>
            <td className="text-muted-foreground px-3 py-2 align-top">
              no stored prices &middot; unreadable date &middot; the venue answered nothing &middot;
              no break level computed &middot; close too old to describe the present &middot; an
              unusual move with no news collected &middot; no setup row stored at all
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2 align-top whitespace-nowrap">NO CONFIRMATION</td>
            <td className="px-3 py-2 align-top">
              The measurements exist and do not support acting. Something was judged, and the
              answer was no.
            </td>
            <td className="text-muted-foreground px-3 py-2 align-top">
              the two timeframes disagree &middot; the peers argue the other way &middot; an unusual
              move with news collected and thin &middot; a direction withheld because its conditions
              are incomplete &middot; price between its own averages
            </td>
          </tr>
        </Table>
        <Note>
          The worst case this fixes was in the fall-through gate. With no setup row stored at all,
          the page printed &ldquo;There is no clear direction to measure. Price is between its own
          averages.&rdquo; &mdash; a statement about where the price sits relative to averages that
          had never been computed. It read as a finished reading and it was an empty file. A
          directional call carries no label here, because a direction was produced and nothing was
          withheld.
        </Note>
      </Section>

      <Section
        title="For the coming week — how a name reaches that block"
        lead="The block at the top of the overview exists to put the week's confirmed names and their three levels in one place before the week starts. It is a filter over the lists below it, never a second opinion: every name in it is already published as LONG or SHORT by the rule above. This says what is removed, how the rest is ordered, and where the exit level comes from."
      >
        <ul className="text-muted-foreground list-disc space-y-2 pl-5 text-sm leading-relaxed">
          <li>
            <strong className="text-foreground">It already carries a direction.</strong> WAIT never
            appears, and that includes a WAIT whose conditions are forming. A direction forming is
            not a direction, and a block headed &ldquo;this week&rdquo; is the easiest place on the
            site for that difference to be missed.
          </li>
          <li>
            <strong className="text-foreground">It is not Low confidence.</strong> Low means nothing
            confirmed the direction beyond the direction itself. Those readings stay in the full
            lists, where the confidence sits in a column beside a hundred others rather than in a
            block that implies selection.
          </li>
          <li>
            <strong className="text-foreground">It has an entry band and a level to be wrong at.</strong>{" "}
            A reading with no stored invalidation cannot be sized or exited, so it cannot be acted
            on, so it is not shown here.
          </li>
          <li>
            <strong className="text-foreground">Order:</strong> confidence first (High before
            Medium), then how close the price already is to its band &mdash; inside it, then a dated
            event near, then still waiting for the level &mdash; then the fresher close, then the
            symbol so two reads of the same data never disagree.
          </li>
          <li>
            <strong className="text-foreground">Capped at six a side,</strong> and the count says
            when more qualified. Fewer than six is the normal case and is never padded: reaching
            into the Low-confidence names to fill the block would be inventing confidence the data
            did not produce. A side with nothing in it says so.
          </li>
        </ul>
        <p className="text-muted-foreground mt-3 text-sm leading-relaxed">
          <strong className="text-foreground">The exit if it works.</strong> Each row carries a
          third level beside the entry and the stop, and it is a stored measurement rather than a
          forecast. <code>jobs/horizons.py</code> writes up to three target ranges per setup, one
          per method, and the block quotes <em>one</em> of them with the method named:
        </p>
        <ul className="text-muted-foreground mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed">
          <li>
            <strong className="text-foreground">structure</strong> &mdash; the nearest price where
            this series has already turned. Preferred, because it is the only one of the three that
            is a fact about where the market stopped before.
          </li>
          <li>
            <strong className="text-foreground">volatility</strong> &mdash; a multiple of the
            asset&rsquo;s own recent daily range. Not a place anything happened, but a distance this
            asset actually covers.
          </li>
          <li>
            <strong className="text-foreground">what followed similar past days</strong> &mdash; the
            distribution over matched history. Last, because it answers how far this usually got
            rather than where it would stop.
          </li>
        </ul>
        <Note>
          The three are never averaged. Three methods that disagree are three answers, and their
          mean is a fourth number nothing measured &mdash; so one is chosen, by the order above, and
          shown with the method beside it. A setup whose stop could not be computed has no target
          row written at all, and the block prints &ldquo;No measured exit stored&rdquo; rather than
          reaching for a number. A setup favours a direction while its stop holds. That is not a
          statement that a price will move, no measured exit is a promise, and no outcome is promised.
        </Note>
      </Section>

      <Section
        title="The product rule"
        lead="A product answers a different question: is anyone paying attention yet, and where do you go to check."
      >
        <Table
          minWidth="680px"
          head={
            <>
              <th className="px-3 py-2 font-medium">Reading</th>
              <th className="px-3 py-2 font-medium">Rule</th>
            </>
          }
        >
          <tr>
            <td className="px-3 py-2 whitespace-nowrap">Attention</td>
            <td className="px-3 py-2 text-xs leading-relaxed">
              RISING, EARLY or FLAT, taken straight from the status the demand job wrote. Any
              other value is reported as not measured rather than shown as FLAT.
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2 whitespace-nowrap">Sell interest</td>
            <td className="px-3 py-2 text-xs leading-relaxed">
              YES LOOK needs all three: attention RISING, at least{" "}
              <span className="num">2</span> of the answering sources pointing the same way, and a
              confidence grade above low. Fewer than <span className="num">2</span> sources
              answering is NO CLEAR SIGNAL. Everything else is NOT YET.
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2 whitespace-nowrap">Risk</td>
            <td className="px-3 py-2 text-xs leading-relaxed">
              One line, worst first: no source answered, then one source carrying the whole score,
              then the sources disagreeing, then that rising attention is not rising sales.
            </td>
          </tr>
        </Table>
        <Note>
          Nothing in this database counts a sale. The demand score is built from search interest,
          pageviews and article counts, and a marketplace position is a rank and never a volume,
          so the output is an attention reading plus somewhere to look.
        </Note>
      </Section>

      <Section
        title="Where a crypto close comes from"
        lead="Four venues instead of one, tried in order, and the row records which one answered."
      >
        <Table
          minWidth="640px"
          head={
            <>
              <th className="px-3 py-2 font-medium">Order</th>
              <th className="px-3 py-2 font-medium">Venue</th>
              <th className="px-3 py-2 font-medium">History it holds</th>
            </>
          }
        >
          {/* Order and depths from CLOSE_VENUES in jobs/prices.py. */}
          <tr>
            <td className="num text-muted-foreground px-3 py-2">1</td>
            <td className="px-3 py-2">Binance</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">Pages back to 2019.</td>
          </tr>
          <tr>
            <td className="num text-muted-foreground px-3 py-2">2</td>
            <td className="px-3 py-2">Coinbase</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">Pages back to 2019.</td>
          </tr>
          <tr>
            <td className="num text-muted-foreground px-3 py-2">3</td>
            <td className="px-3 py-2">Kraken</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              Roughly the last <span className="num">720</span> days.
            </td>
          </tr>
          <tr>
            <td className="num text-muted-foreground px-3 py-2">4</td>
            <td className="px-3 py-2">Bitstamp</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              Last, because it lists the fewest of these coins.
            </td>
          </tr>
        </Table>
        <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-relaxed">
          The winner is the first venue whose newest bar is within{" "}
          <span className="num">2</span> days, not the first that answers at all. A venue can
          answer with a series that stopped days ago, and taking it because it was first would
          store a stale close and leave every coin reading &ldquo;data stale&rdquo; with nothing
          explaining why. When no venue is current the deepest answer is stored anyway and check 2
          above catches it.
        </p>
        <Note>
          A shallow venue never replaces a deeper stored series. The stored rows are rewritten only
          when the new fetch is at least as deep; otherwise the new days are added on top.
          Rewriting six years of history from a 720 day venue would lose the rows every similar-day
          and horizon reading is measured over, and it would look like a successful run.
        </Note>
      </Section>

      <Section title="Snapshot dates" lead="The pre-AI window ends at the last trading day of 2021. The current window ends at the newest stored close.">
        <Table
          head={
            <>
              <th className="px-3 py-2 font-medium">Window</th>
              <th className="px-3 py-2 font-medium">Dates used</th>
              <th className="px-3 py-2 font-medium">Why</th>
            </>
          }
        >
          <tr>
            <td className="px-3 py-2">Before the AI wave</td>
            <td className="num px-3 py-2">2019-01-01 to 2021-12-31</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              The two years before the large language model release cycle began.
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2">Since then</td>
            <td className="num px-3 py-2">2021-12-31 to newest close</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              The same boundary, so the two windows are directly comparable.
            </td>
          </tr>
          <tr>
            <td className="px-3 py-2">Relative strength</td>
            <td className="num px-3 py-2">24 months to newest close</td>
            <td className="text-muted-foreground px-3 py-2 text-xs">
              Long enough to include a full cycle of winners and losers.
            </td>
          </tr>
        </Table>
      </Section>

      <Section title="Rankings" lead="Four bases, each stored as a row with its own source and as of date.">
        <ul className="space-y-3">
          {RANKINGS.map((r) => (
            <li key={r.basis}>
              <Card>
                <h3 className="font-medium">{r.basis}</h3>
                <p className="mt-1 text-sm leading-relaxed">{r.formula}</p>
                <p className="text-muted-foreground mt-2 text-xs">Source: {r.source}</p>
                <Note>{r.gap}</Note>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Product demand" lead="Five sources, read on the same short windows for all thirty products.">
        <ul className="space-y-3">
          {SIGNALS.map((s) => (
            <li key={s.source}>
              <Card>
                <h3 className="font-medium">{s.source}</h3>
                <p className="mt-1 text-sm leading-relaxed">{s.measure}</p>
                <Note>{s.caveat}</Note>
              </Card>
            </li>
          ))}
        </ul>
        <Card className="mt-3">
          <h3 className="font-medium">Demand score and status</h3>
          <p className="mt-1 text-sm leading-relaxed">
            The score is the plain average of the percentage change of every source that
            answered, with no weighting and no adjustment. A source that did not answer is
            left out of the average, and is never counted as a zero. Status is{" "}
            <strong>rising</strong> when every source that answered is up and the average is
            at least 5 points, or when the average is at least 10,{" "}
            <strong>early</strong> when the average is positive, something is up, and at
            least two sources answered, <strong>flat</strong> otherwise, and{" "}
            <strong>unknown</strong> when nothing answered. A single source answering is
            reported as <strong>flat</strong>, not as early interest, because one reading is
            not a trend. Status is a label for the measured window and nothing more.
          </p>
        </Card>
      </Section>

      <Section
        title="Current discussion"
        lead="Three readings taken from the news coverage already stored for each asset and product: how much was published, how it was worded, and whether it reads as promotion."
      >
        <Card>
          <h3 className="font-medium">What produces the wording direction</h3>
          <p className="mt-1 text-sm leading-relaxed">
            Every stored headline is matched against a fixed list of directional words. A
            headline matching only positive words is counted positive, only negative words
            negative, and a headline matching both is counted as neither, because
            &ldquo;revenue beats but guidance misses&rdquo; is genuinely both and picking a
            winner on match count would invent a judgement the wording does not support. The
            direction is the net share of the window, and it is published only when the
            window holds at least 8 headlines and the net sits more than 15 points from zero.
            Below either threshold the counts are shown and no direction is.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            This is a word list, not sentiment analysis, and the difference is stated on every
            page that shows it. It reads headlines and never article bodies. It cannot see
            negation, so &ldquo;not a record year&rdquo; counts the positive word. It cannot
            see sarcasm or context at all. Words whose direction flips with context are left
            out of both lists entirely: <em>cut</em> is bad news about guidance and good news
            about interest rates, so it counts as neither.
          </p>
        </Card>

        <Card className="mt-3">
          <h3 className="font-medium">Attention, and why it is not interest</h3>
          <p className="mt-1 text-sm leading-relaxed">
            Attention compares the number of items in the last 30 days with the 30 days
            immediately before, and is called rising or falling only past 25 points, because
            news counts are noisy week to week. When the earlier window holds fewer than 5
            items the comparison is left empty rather than divided: one extra article against
            a base of two is +50%, which is arithmetic and not a change in attention.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            It measures coverage collected, not public interest. A feed that was rate limited
            returns fewer items, which looks identical to a quieter month, so the raw counts
            are always printed beside the percentage.
          </p>
        </Card>

        <Card className="mt-3">
          <h3 className="font-medium">The hype flag</h3>
          <p className="mt-1 text-sm leading-relaxed">
            A separate list of promotional and clickbait wording is counted the same way. The
            flag is raised only when that wording covers at least a fifth of the window{" "}
            <em>and</em> attention is rising at the same time. Promotional wording on its own
            is a publisher&apos;s house style; promotional wording arriving with a jump in
            coverage is the thing worth naming.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            The flag describes how a story is being written, not the thing being written
            about. Heavily promoted and overvalued are different claims and only the first is
            measured here.
          </p>
        </Card>
      </Section>

      <Section
        title="Checking these readings against what happened"
        lead="Every reading is logged on the day it is generated, and the move that followed is measured later. Nothing is published from that log until there is enough of it to divide by."
      >
        <Card>
          <p className="text-sm leading-relaxed">
            When a discussion reading is written it is stored with the factors it rested on
            and the closing price on that day. Thirty and sixty days later the price move
            since that close is measured and stored beside it. Readings with no direction are
            logged too: whether quiet, split coverage is followed by anything is exactly the
            question the log exists to answer, and recording only the confident readings would
            make any eventual figure flattering.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            Nothing is filled in. A window that has not elapsed stays open. A product has no
            price series, so its readings are marked unmeasurable rather than given a number.
            A window falling in a gap in the stored prices keeps its blank instead of
            borrowing a close more than five days away.
          </p>
          <p className="mt-2 text-sm leading-relaxed">
            No rate is published until at least 20 readings have matured, and the pages say
            how many are still waiting instead. A hit rate over a handful of rows is the kind
            of impressive-looking number this site exists not to publish. When there is enough
            to report, it will be reported as what followed the readings, measured from the
            stored close — not as a claim that the readings caused the moves, and not as a
            forecast.
          </p>
        </Card>
      </Section>

      <Section
        title="Confidence"
        lead="Every ranking, product and written line carries a grade, and the reason for it is stored next to the grade rather than left to the reader."
      >
        <p className="text-muted-foreground max-w-3xl text-sm leading-relaxed">
          A grade of high, medium, low or no data describes how well evidenced a figure is.
          It is not a view on direction, and it is not a prediction. A number can be accurate
          and still be thinly measured, so the two are judged separately.
        </p>
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm leading-relaxed">
          <li>
            <strong className="text-foreground">Rankings.</strong> An industry average is
            compared with its own median. If the two are far apart, the average is not a fair
            description of a typical peer, so the row is graded down and the gap is stated. The
            published rank is left as it is, because changing the comparator would quietly
            rewrite history.
          </li>
          <li>
            <strong className="text-foreground">Products.</strong> Agreement is measured
            against the average, not against whichever side has more sources. Three sources
            down and one up is a minority position. Sources that split up and down, or where
            the average and the median fall on opposite sides of zero, cap the grade at
            medium. One source supplying most of the average is disclosed but does not cap the
            grade by itself, because several sources can agree on direction while one supplies
            the size.
          </li>
          <li>
            <strong className="text-foreground">Small denominators.</strong> A Reddit
            percentage is not published at all when the window it is measured against holds
            fewer than five posts, because one post against none is a rounding artifact. When
            the base is between five and nine the percentage is published, since the arithmetic
            is correct, but the grade is capped at medium: at that scale a single post moves the
            number by ten to twenty percent. No product currently grades high, and the reason
            is written on the product rather than left for you to infer.
          </li>
        </ul>
        <Note>
          A grade is never more confident than the sentence beside it. The site is more
          willing to show a small number honestly labelled than a large one that hides how
          little is behind it.
        </Note>
      </Section>

      <Section
        title="The three newer sections"
        lead="Pakistan, events and marketplace rankings arrived after the original build, and each carries a limit worth stating before the numbers are read."
      >
        <div className="space-y-4">
          {NEW_SECTIONS.map((n) => (
            <Card key={n.title}>
              <h3 className="font-medium">{n.title}</h3>
              <dl className="mt-2 space-y-2 text-sm">
                <div>
                  <dt className="text-muted-foreground text-xs">Source</dt>
                  <dd className="leading-relaxed">{n.source}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">What is measured</dt>
                  <dd className="leading-relaxed">{n.measure}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">What it cannot tell you</dt>
                  <dd className="text-muted-foreground leading-relaxed">{n.gap}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      </Section>

      {/* These three read only rows the site already stored, which is why they could be
          added without a new source. Each one is a measurement whose limit is sharper than
          its output, so the limit is stated beside it rather than in a footnote. */}
      <Section
        title="Reading a state over time, a move, and a neighbourhood"
        lead="Three readings added over the stored rows rather than over a new source. Each is arithmetic, and each has a limit worth knowing before the number is used."
      >
        <div className="space-y-4">
          <Card>
            <h3 className="font-medium">What has happened to the reason</h3>
            <p className="mt-2 text-sm leading-relaxed">
              A condition read says what the numbers show today. Once that read has been held
              for a few days the useful question is a different one: is the reason it exists
              still there? So the day a directional state first appeared is kept, along with
              the conditions recorded on that day, and every later day is compared against
              them. The conditions are a copy of that day&apos;s row and are never recomputed,
              because recomputing them would answer what we would have said then knowing what
              we know now.
            </p>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              A reason is <em>weakening</em> when a condition has flipped its verdict or
              stopped being available, and <em>broken</em> when a stored close has passed the
              level the opening day named, or the read now points the other way. Broken is
              final. A later recovery does not reopen it, because the only value of a level
              written down in advance is that passing it cannot be taken back.
            </p>
            <Note>
              A status says whether the recorded conditions are still measurable. It does not
              say the read was right, and the counts are never shown as a percentage, which
              would read as a hit rate for something that measures nothing of the kind.
            </Note>
          </Card>

          <Card>
            <h3 className="font-medium">What a move was shared with</h3>
            <p className="mt-2 text-sm leading-relaxed">
              A 20 session move is split three ways: the median move across every asset quoted
              in the same exchange group, the median across the asset&apos;s own industry peers
              beyond that, and whatever is left. Medians rather than averages, because one
              very large crypto return would otherwise describe a sector nobody is in. The
              three parts add up to the move exactly, so they compete rather than overlap.
            </p>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              Below three industry peers with enough history the last two parts are not
              separated at all, and the row says the remainder could not be split instead of
              crediting it to the asset. Where the largest two parts are close, neither is
              named.
            </p>
            <Note>
              This is co-movement. It says what an asset moved <em>with</em>, never what moved
              it, and no probability is attached to any of the three: that would need a
              measured outcome rate, and the outcome log has no matured rows yet.
            </Note>
          </Card>

          <Card>
            <h3 className="font-medium">Why something is near today&apos;s news</h3>
            <p className="mt-2 text-sm leading-relaxed">
              When a catalyst is flagged, the relationships already stored are walked outward
              from it: assets linked to the same product, assets concerned by the same dated
              item, and assets in a small enough industry. The walk stops at two steps, skips
              any group large enough that membership says more about the group than about a
              member, and divides every link by the size of the group it came from, so being
              one of two assets linked to a product counts for more than being one of twenty
              in a sector.
            </p>
            <Note>
              A link is a relationship somebody recorded. Something reaching this list is a
              reason to look at it, and never evidence that a move on one end reached the
              other. Every row shows the chain that reached it, so a chain you do not accept
              can be discarded on sight.
            </Note>
          </Card>
        </div>
      </Section>

      <Section
        title="How to research something here yourself"
        lead="The order below is the one the site itself follows, and it is arranged so that the cheap checks come before the expensive ones."
      >
        <ol className="space-y-4 text-sm leading-relaxed">
          <li>
            <strong>1. Ask what would count as an answer, before looking.</strong>{" "}
            &ldquo;Is this rising?&rdquo; has no answer until you say rising against what,
            over what period. Every table on this site names both, and that is the only
            reason any of it can be checked. A question that cannot be answered wrongly
            cannot be answered.
          </li>
          <li>
            <strong>2. Find the number, then find its denominator.</strong> A percentage
            with no base is unreadable. +200% on this site might be six posts against two.
            The product pages print the raw counts next to every Reddit percentage for
            exactly this reason, and a figure whose base was never recorded is deleted
            rather than shown.
          </li>
          <li>
            <strong>3. Count the sources that answered, not the ones that agreed.</strong>{" "}
            Four sources agreeing on a small move is stronger than one source reporting a
            huge one. A source that did not answer is not evidence either way, and a source
            reporting no change still answered.
          </li>
          <li>
            <strong>4. Check whether one input is carrying the result.</strong> An average
            of five numbers where one supplies most of the magnitude is that one
            reading with an average written over it. Every demand score on this site
            discloses its largest contributor&apos;s share.
          </li>
          <li>
            <strong>5. Compare like with like.</strong> A 30 day count against a 90 day
            count is not a change, it is a ratio of two window lengths. Two assets in
            different currencies have comparable returns and incomparable sizes. Most
            errors that survive a first look are this one wearing different clothes.
          </li>
          <li>
            <strong>6. Separate what moved from why it moved.</strong> The first is
            measurable from a price series and the second is not. When a number sits next
            to an event, the honest sentence is that both happened, in that order.
          </li>
          <li>
            <strong>7. Write down what would change your mind.</strong> If nothing would,
            the reading was a conclusion looking for support. The confidence grades here
            exist so that a figure can be reported and doubted in the same breath.
          </li>
        </ol>
        <Note>
          None of this is investment advice, and none of it is a method for making money.
          It is how to avoid being misled by a number, including by one on this site.
        </Note>
      </Section>

      <Section title="What this site will not do">
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm leading-relaxed">
          <li>
            No forecasts and no probability of anything happening. A published call&apos;s measured exit is
            a level its own stored setup measured from past prices (a structure level, a range, or how far
            similar past days went), never a projection, and it is not a promise that price gets there.
          </li>
          <li>No paid data, no broker feed, no scraping behind a login, no fingerprint tricks.</li>
          <li>No filling a missing number from a related one. Crypto has no historical size because no free source publishes it.</li>
          <li>No X or Twitter data, because there is no free public source that can be used without a paid account.</li>
          <li>No performance claims. This is a read only archive of measured direction.</li>
          <li>
            No claim that an event caused a price move. The event windows measure what
            moved in a period and stop there.
          </li>
          <li>
            No sales, revenue or margin figures for any product. No marketplace publishes
            them for free and none of them can be derived from a bestseller rank.
          </li>
          <li>
            No conversion between rupees and dollars. Returns compare across currencies
            already; sizes do not, and converting them at today&apos;s rate would misstate
            every historical figure.
          </li>
        </ul>
        <Note>
          Data can be late, revised or wrong. A price feed that misses a day, a Trends term
          that is shared by several products, or a Reddit request that gets rate limited all
          change what a number means. Every page shows the as of date so a stale figure is
          visible rather than hidden.
        </Note>
      </Section>

      <Section
        title="Source health"
        lead="Every source this site reads, and whether it is currently answering. Measured by the audit job on each run, not asserted here."
      >
        <SourceHealthBlock sources={health} />
        {intraday.sessionDate ? (
          <p className="text-muted-foreground mt-3 max-w-3xl text-xs leading-relaxed">
            Intraday sessions stored for {isoDate(intraday.sessionDate)}:{" "}
            {intraday.counts.map((c) => `${c.n} ${c.status}`).join(", ")}. A session is counted
            by what it is, not merged into a total — an empty session is a quiet market and a
            failed one is a fault, and those are different facts.
          </p>
        ) : null}
        <p className="text-muted-foreground mt-3 max-w-3xl text-xs leading-relaxed">
          A feed that quietly stops looks exactly like a quiet week in the data. These four
          states exist to keep those apart: a source can be answering, answering thinly, late,
          or not answering at all. Nothing here is a verdict on the site — it says what was
          collected, so a thin reading can be recognised as thin rather than read as a finding.
        </p>
      </Section>

      <Section title="How the data is refreshed">
        <p className="text-muted-foreground max-w-3xl text-sm leading-relaxed">
          A scheduled job runs the scripts in this repository: prices and news daily for
          both exchanges, rankings and event windows daily, and product signals and the
          marketplace charts weekly, because Reddit and Wikipedia rate limit and the
          bestseller charts move faster than anything here is meant to track.
          Each run writes rows with a period end date, and this site reads only what has been
          written. If a job fails, the old rows stay and the freshness table on the front
          page shows the date of the last successful run. Nothing on the site is computed in
          the browser.
        </p>
      </Section>
    </div>
  );
}
