import * as React from "react";
import { targetMethodLabel, type TargetLike } from "@/lib/target";
import { price, relativeTime } from "@/lib/format";
import type { Action, Confidence, Decision, Market, TimeSense } from "@/lib/decision";
import type { ProductDecision, WhereToCheck } from "@/lib/productDecision";
import {
  AsOf, Card, ConfidenceBadge, Empty, Note, Pill, Section, WaitBasisChip,
} from "@/components/ui";
import { gapLine } from "@/lib/reconcile";
import { headlineOf } from "@/lib/newsRank";

// The decision panel, and nothing else.
//
// Everything here is one shape: a word that tells the reader what to do, the short reason, the two
// numbers that bound being wrong, and then — always — what is missing. The deeper sections of the
// site still carry the evidence; this is the part a reader can act on, so it is the part that must
// never look blank. `decision.missing` is therefore rendered unconditionally whenever it has items,
// at full size, above the honesty line rather than tucked under it.
//
// Server components only. There is no `'use client'` anywhere in this app by design, and nothing in
// a panel like this needs it: every state the reader can reach is either already in the props or is
// a native `<details>`. Adding a client boundary here would ship a bundle to make a word bigger.

/// Direction is not sentiment, and the colour is never the message.
///
/// LONG reads as green and SHORT as red because that is what a price reader expects of a direction,
/// but a SHORT is not bad news and a LONG is not an endorsement — they are two sides of the same
/// measurement, and one of them being red is a convention, not a judgement. WAIT gets `warn` because
/// WAIT genuinely is a caution: it means the rule table refused to answer.
///
/// Which is why the colour is only ever decoration here. The word LONG, SHORT or WAIT is printed in
/// full at the largest size on the page, and every field beside it carries a text label. A reader
/// with deuteranopia, a reader on a washed-out phone screen in sunlight, and a reader of a printout
/// in greyscale all get the same answer from the text alone. If removing the colour from this panel
/// would lose any information, the panel is wrong.
const ACTION_TONE: Record<Action, "up" | "down" | "warn"> = {
  LONG: "up",
  SHORT: "down",
  WAIT: "warn",
};

const ACTION_TEXT: Record<Action, string> = {
  LONG: "text-up",
  SHORT: "text-down",
  WAIT: "text-warn",
};

/// What each time sense means, spelled out next to it.
///
/// The three words are not self-explanatory on their own — "NOW" especially, which a reader could
/// take as urgency when it only means the last close sits inside the entry band. CARE says a dated
/// event is near, because that is the one case where the instruction is about the calendar rather
/// than the price.
const TIME_SENSE_COPY: Record<TimeSense, string> = {
  NOW: "The last stored close is inside the entry zone.",
  "WAIT FOR LEVEL": "The price is not in the zone yet. Nothing to do until it is.",
  CARE: "A dated event is near, so a position opened today meets it.",
};

const TIME_SENSE_TONE: Record<TimeSense, "default" | "up" | "warn"> = {
  NOW: "up",
  "WAIT FOR LEVEL": "default",
  CARE: "warn",
};

/// One stored news row, reduced to what a link in the top block needs.
///
/// Deliberately not the Prisma row. The panel takes three or four fields and a count, and taking
/// the whole model would mean this component could only ever be fed by one query — the home page
/// lists are the reason `DecisionRow` exists and this is the same argument.
export interface TopNews {
  /// Stored row id, used as the list key. Urls are not unique: the same article can be stored
  /// once per asset and once per industry.
  id: string;
  title: string;
  url: string;
  publisher: string;
  publishedAt: Date | string;
  /// How many separate outlets carried the same story, taken from the stored clusters. Printed
  /// only above one, because "carried by 1 outlet" is a fact about nothing.
  outlets?: number | null;
}

export interface DecisionPanelProps {
  decision: Decision;
  symbol: string;
  /// Quoted currency for the two levels. PSX names are in rupees and `price()` knows the marks.
  currency: string;
  /// Newest stored close date, shown so the reader can see how old the answer is.
  asOf: Date | string | null;
  /// The newest stored close itself.
  ///
  /// Separate from `decision.entry` and `decision.invalidation` on purpose: those two are levels
  /// the rules computed, this is the number the market last printed, and a panel that shows the
  /// band and the stop but not where the price actually is asks the reader to go and find the one
  /// figure every other figure here is measured against. Null when nothing is stored, which is the
  /// same state that makes the action WAIT at gate 1.
  priceNow?: number | null;
  /// Up to three stored news rows. More than three are ignored rather than scrolled: this block is
  /// above the fold and a fourth link is the start of a feed.
  news?: TopNews[];
  /// The measured exit, chosen by `pickTarget`. Null when the job stored none.
  target?: TargetLike | null;
}

/// One labelled figure or sentence. Used for every field in the panel so that the label and the
/// value always travel together — a bare number under a big word is the thing this panel is
/// replacing.
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs font-medium">{label}</p>
      <div className="mt-0.5 text-sm leading-relaxed">{children}</div>
      {hint ? (
        <p className="text-muted-foreground mt-0.5 text-micro leading-relaxed">{hint}</p>
      ) : null}
    </div>
  );
}

/// What could not be checked, said out loud.
///
/// The spec behind this panel is one sentence: if data is missing, the action is WAIT and the page
/// says exactly what is missing, with no silent empty. The rule table already guarantees the first
/// half; this is the second half, and it is a block rather than a footnote because a reader who
/// scrolls past it has been told nothing. It renders for LONG and SHORT too — a direction with no
/// stored entry band is still a direction with a hole in it.
function Missing({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="border-warn/30 bg-warn-bg mt-4 rounded-lg border px-3 py-2">
      <p className="text-warn text-xs font-medium">What is missing</p>
      <ul className="mt-1.5 space-y-1">
        {items.map((m, i) => (
          <li key={i} className="text-muted-foreground text-xs leading-relaxed">
            {m}
          </li>
        ))}
      </ul>
    </div>
  );
}



/// What qualifies the direction without replacing it.
///
/// This block is where the two demoted gates surface. Until 2026-10-09 a name that moved
/// unusually with thin news, or one lagging its peers, was refused outright and the reader saw
/// WAIT and one sentence; 75 of 477 names were in that state. They now print their direction and
/// this block, which means the qualification has to be *more* visible than it was as a gate, not
/// less — a panel that quietly drops a caveat it used to shout is worse than one that never had
/// it. So: its own bordered block, above the honesty line, at the same size as the reasons.
///
/// Deliberately a different block from `Missing`. Missing is a measurement nobody took; a note is
/// a measurement that was taken and argues the other way, and merging them would tell a reader
/// that a peer reading is absent when it is present and unfavourable.
function Notes({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="border-border mt-4 rounded-lg border px-3 py-2">
      <p className="text-muted-foreground text-xs font-medium">What argues against it</p>
      <ul className="mt-1.5 space-y-1">
        {items.map((n, i) => (
          <li key={i} className="text-sm leading-relaxed">
            {n}
          </li>
        ))}
      </ul>
    </div>
  );
}

/// The three figures that say whether the trade is worth its own stop.
///
/// Rendered only on a direction, because `Decision.plan` is null on every WAIT. Each figure is a
/// stored number or arithmetic over two of them, and each one prints its own denominator:
///
///   * **Reward against risk** is `jobs/horizons.py`'s own `rewardRisk`, measured from the target
///     range against the setup's own stop. Not computed here, and not averaged across methods.
///   * **Similar days** is a frequency over a stored sample, and the sample size is printed beside
///     it every time. Principle 3 — a share without its denominator is the overclaim this site
///     exists not to make, and "62%" over six days and over six hundred are different sentences.
///   * **Per unit risked** is what those matched days would have returned at this reward, had each
///     been taken. It is a statement about the stored sample and the hint says so in those words.
///     It is not a forecast, and nothing here says what the next move does.
///
/// An absent figure prints the reason it is absent rather than a dash. A missing reward is a
/// target `jobs/horizons.py` did not write; a missing frequency is a set under the 8 matches that
/// job refuses to grade.
function Sizing({ plan }: { plan: NonNullable<Decision["plan"]> }) {
  const rate = plan.baseRate;
  return (
    <div className="border-border mt-4 grid gap-3 border-t pt-3 sm:grid-cols-3">
      <Field
        label="Reward against risk"
        hint={
          plan.rewardRisk !== null
            ? "The measured target against the stop above. Measured, not chosen."
            : undefined
        }
      >
        {plan.rewardRisk !== null ? (
          // Two decimals under 1, one at or above it. A measured 0.04x printed as "0.0x" reads
          // as a missing number, which is the one thing this figure must never look like: it is
          // the reader's whole answer to "is this trade worth its own stop", and a flat answer
          // is still an answer.
          <span className="num text-lg font-semibold">
            {plan.rewardRisk < 1 ? plan.rewardRisk.toFixed(2) : plan.rewardRisk.toFixed(1)}x
          </span>
        ) : (
          <span className="text-muted-foreground">
            No measured target is stored, so the reward cannot be sized.
          </span>
        )}
      </Field>

      <Field
        label="Similar days that went this way"
        hint={
          rate
            ? `Out of ${rate.count} matched past days. A frequency over stored history, never a probability of the next move.`
            : undefined
        }
      >
        {rate ? (
          <span className="num text-lg font-semibold">
            {Math.round(rate.share * 100)}%{" "}
            <span className="text-muted-foreground text-sm font-normal">of {rate.count}</span>
          </span>
        ) : (
          <span className="text-muted-foreground">
            Too few matched past days are stored to quote a frequency.
          </span>
        )}
      </Field>

      <Field
        label="Per unit risked"
        hint={
          plan.expectancyR !== null
            ? "What those matched days would have returned at this reward, had each been taken. A measurement of the sample above, not of what happens next."
            : undefined
        }
      >
        {plan.expectancyR !== null ? (
          <span className="num text-lg font-semibold">
            {plan.expectancyR >= 0 ? "+" : ""}
            {plan.expectancyR.toFixed(2)}R
          </span>
        ) : (
          <span className="text-muted-foreground">
            Needs both a measured reward and a graded set of past days.
          </span>
        )}
      </Field>
    </div>
  );
}

/// Up to three stored headlines, as links out.
///
/// Why links and not summaries: nothing on this site writes prose about a news item, and a panel
/// that paraphrased one would be inventing the only unsourced claim on the page. The reader gets
/// the stored title, who published it, how long ago, and a way out to read it themselves.
///
/// `nofollow` joins `noopener noreferrer` because these are outbound links to whoever a feed
/// happened to name, carried in bulk, and this site does not vouch for any of them.
function MarketNews({ items }: { items: TopNews[] }) {
  if (!items.length) return null;
  return (
    <div className="border-border mt-4 border-t pt-3">
      <p className="text-muted-foreground text-xs font-medium">Important news</p>
      <ul className="mt-1.5 space-y-1.5">
        {items.map((n) => (
          <li key={n.id}>
            {/* The anchor is the headline only, not the whole row: the publisher line underneath
                is attribution rather than part of the destination, and a link that swallows it
                reads out as one long run-on to a screen reader. */}
            <a
              href={n.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="text-sm leading-snug underline underline-offset-2"
            >
              {headlineOf(n.title, n.publisher)}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            <p className="text-muted-foreground text-micro leading-relaxed">
              {n.publisher}
              {n.outlets && n.outlets > 1 ? ` and ${n.outlets - 1} more` : ""} &middot;{" "}
              {relativeTime(n.publishedAt)}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/// The asset decision, at the top of every asset page.
///
/// Field order is the order the questions get asked, and it is the order the spec asks them in:
/// what to do, what the price is now, the two levels, when, why, and then what is being published.
/// Price now comes second because it is the first number a reader looks for and every other figure
/// in the panel is measured against it — a band and a stop with no spot price between them is a
/// quiz. The two levels sit in one block after it because they are read as a pair; an entry with no
/// exit is the shape of a tip.
///
/// At 375px every one of these is a full-width stacked line, which is the whole point: the block
/// has to answer on one screen, so nothing in it is allowed to need a second column to be legible.
export function DecisionPanel({
  decision,
  symbol,
  currency,
  asOf,
  priceNow = null,
  news = [],
  target = null,
}: DecisionPanelProps) {
  const grade = decision.confidence.toLowerCase();
  const gap = gapLine(decision);

  return (
    <Card className="border-primary/30">
      {/* The word, and then everything that qualifies it. `wrap-hard` is not needed — the three
          words are short — but the row wraps because the pills beside it will not fit at 375px. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className={`text-4xl leading-none font-bold tracking-tight sm:text-5xl ${ACTION_TEXT[decision.action]}`}>
          {decision.action}
        </p>
        <span className="flex flex-wrap items-center gap-2">
          <Pill tone="default">{symbol}</Pill>
          {/* Beside the grade, because the grade alone cannot carry it: "Low" reads as a weak
              judgement whether or not anything was judged. This says which. */}
          <WaitBasisChip basis={decision.basis} />
          <ConfidenceBadge grade={grade} />
          <AsOf date={asOf} />
        </span>
      </div>

      {/* The one line that reconciles a strong direction with a weak grade. It sits directly
          under the word and above every number, because it is the sentence that stops the two
          of them reading as a contradiction, and a reader who has already scrolled past the
          grade has already formed the impression it exists to correct. */}
      {gap ? (
        <p className="text-muted-foreground mt-3 text-sm leading-snug">{gap}</p>
      ) : null}

      {/* Price first, then the two levels, then the timing. This is the block that has to
          answer on one screen: a reader looking at a band and a stop with no spot price
          between them has been handed a quiz, since every figure here is measured against the
          one the market last printed. Three columns from `sm` up; at 375px all of them stack,
          which is the point — nothing in this block may need a second column to be legible. */}
      <div className="border-border mt-4 grid gap-3 border-t pt-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Price now" hint="The newest stored close, not a live quote.">
          {priceNow !== null ? (
            <span className="num text-lg font-semibold">{price(priceNow, currency)}</span>
          ) : (
            <span className="text-muted-foreground">
              Nothing is stored, which is why the action is WAIT.
            </span>
          )}
        </Field>

        <Field
          label="Entry"
          hint={
            decision.entry
              ? "Both ends inclusive. Outside the zone there is nothing to do."
              : undefined
          }
        >
          {decision.entry ? (
            <span className="num">
              {price(decision.entry.low, currency)} to {price(decision.entry.high, currency)}
            </span>
          ) : (
            <span className="text-muted-foreground">
              No measured zone is stored, so no entry is named.
            </span>
          )}
        </Field>

        {/* "Exit if wrong", never "invalidation". The reader is owed the instruction, not the
            vocabulary the field is stored under. */}
        <Field
          label="Exit if wrong"
          hint={
            decision.invalidation !== null
              ? "Past this level the reason above no longer holds."
              : undefined
          }
        >
          {decision.invalidation !== null ? (
            <span className="num">{price(decision.invalidation, currency)}</span>
          ) : (
            <span className="text-muted-foreground">
              No stop level is stored, which is why the action is WAIT.
            </span>
          )}
        </Field>

        {/* The other exit, and a panel that shows only the first one answers half the question a
            reader arrives with. One measured method, named: never an average of the three, and
            never a number computed here. `jobs/horizons.py` writes no target row at all when
            there is no stop to measure reward against, and that absence is printed rather than
            filled. */}
        <Field
          label="Exit if working"
          hint={
            target
              ? `Measured from ${targetMethodLabel(target.method)} — a measured level, not a promise.`
              : undefined
          }
        >
          {target ? (
            <span className="num">
              {target.low === target.high
                ? price(target.low, currency)
                : `${price(target.low, currency)} to ${price(target.high, currency)}`}
            </span>
          ) : (
            <span className="text-muted-foreground">No clear target stored.</span>
          )}
        </Field>

        <Field label="When" hint={TIME_SENSE_COPY[decision.timeSense]}>
          <Pill tone={TIME_SENSE_TONE[decision.timeSense]}>{decision.timeSense}</Pill>
        </Field>
      </div>

      {/* Directly under the levels, because it is the question the levels raise. A reader who has
          just been shown an entry, a stop and a target asks whether the three are worth each
          other, and the answer is three stored numbers rather than a judgement. Null on every
          WAIT, so a refusal never carries a sizing block it could be read as a trade through. */}
      {decision.plan ? <Sizing plan={decision.plan} /> : null}

      {/* Why, after the numbers rather than before them. Three at most: the rules routinely
          record five or six true sentences, and a reader who has to read six to find the
          decision has not been given a decision. The rest are under Details, unabridged. */}
      <div className="border-border mt-4 border-t pt-3">
        <Field label="Why">
          {decision.why.length ? (
            <ul className="space-y-1">
              {decision.why.slice(0, 3).map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          ) : (
            "No reason was recorded, which is itself a fault — read what is missing below."
          )}
        </Field>
      </div>

      {/* Above the news and above the missing block, because it is about the verdict rather than
          about the file. A caveat printed under three headlines has been filed, not read. */}
      <Notes items={decision.notes} />

      <MarketNews items={news.slice(0, 3)} />

      <Missing items={decision.missing} />

      {/* Verbatim, and never rewritten per page. It is the sentence that stops a measured range
          being read as a forecast, so it says the same thing everywhere it appears. */}
      <Note>{decision.measured}</Note>
    </Card>
  );
}

const ATTENTION_TONE: Record<string, "up" | "warn" | "default"> = {
  RISING: "up",
  EARLY: "warn",
  FLAT: "default",
};

/// Sell interest is an instruction about looking, not about buying, so none of the three gets a
/// green. "YES LOOK" earns `up` because it is the one that asks for an action; the other two are
/// plain, since "NOT YET" is not a failure and "NO CLEAR SIGNAL" is an admission about the data.
const SELL_TONE: Record<string, "up" | "default" | "warn"> = {
  "YES LOOK": "up",
  "NOT YET": "default",
  "NO CLEAR SIGNAL": "warn",
};

export interface ProductDecisionPanelProps {
  decision: ProductDecision;
  name: string;
}

/// One link, sized to be hit with a thumb.
///
/// `min-h-11` is 44px. The reason the whole block is the anchor rather than the label alone is that
/// the `why` line is the part that makes the click worth making, and a reader who aims at it should
/// not miss. The label carries the destination in words and the arrow is `aria-hidden`, because an
/// external link marked only by an icon is unreadable to a screen reader and invisible in a
/// greyscale print.
function WhereLink({ item }: { item: WhereToCheck }) {
  return (
    <li>
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="border-border hover:border-primary/50 flex min-h-11 flex-col justify-center gap-0.5 rounded-lg border px-3 py-2 transition-colors"
      >
        <span className="text-sm font-medium underline underline-offset-2">
          {item.label}
          <span aria-hidden="true"> &rarr;</span>
          <span className="sr-only"> (opens in a new tab)</span>
        </span>
        <span className="text-muted-foreground text-xs leading-relaxed">{item.why}</span>
      </a>
    </li>
  );
}

/// The product decision, at the top of every product page.
///
/// What this panel deliberately does not say is how much of anything sold. Nothing stored here
/// counts a sale: the attention reading is built from searches, pageviews and article counts, and a
/// marketplace row is a rank. So every word is about interest and about where to go and check, and
/// the risk line names which of the two is weak. There is no figure on this panel that a reader
/// could mistake for a unit count, and none should ever be added.
export function ProductDecisionPanel({ decision, name }: ProductDecisionPanelProps) {
  return (
    <Card className="border-primary/30">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="text-2xl leading-none font-bold tracking-tight sm:text-3xl">{name}</p>
        <span className="flex flex-wrap items-center gap-2">
          <ConfidenceBadge grade={decision.confidence} />
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Attention">
          {decision.attention ? (
            <Pill tone={ATTENTION_TONE[decision.attention] ?? "default"}>
              {decision.attention}
            </Pill>
          ) : (
            <span className="text-muted-foreground">
              {decision.attentionMissing ?? `No attention reading stored for ${name}.`}
            </span>
          )}
        </Field>

        <Field label="Sell interest">
          <Pill tone={SELL_TONE[decision.sellInterest] ?? "default"}>{decision.sellInterest}</Pill>
        </Field>
      </div>

      {decision.why.length ? (
        <div className="mt-4">
          <Field label="Why">
            <ul className="space-y-1">
              {decision.why.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Field>
        </div>
      ) : null}

      <div className="mt-4">
        <Field
          label="Geo"
          hint={
            decision.geo
              ? "Where stored interest concentrates, which is not where the buyers are."
              : undefined
          }
        >
          {decision.geo ? (
            decision.geo
          ) : (
            <span className="text-muted-foreground">Geo not stored yet.</span>
          )}
        </Field>
      </div>

      {/* The links are the point of the page, so they are a list of tap targets rather than a
          sentence with words underlined in it. One column on a phone, two from `sm`. */}
      <div className="border-border mt-4 border-t pt-3">
        <p className="text-muted-foreground text-xs font-medium">Where to check</p>
        {decision.where.length ? (
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {decision.where.map((w) => (
              <WhereLink key={w.url} item={w} />
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground mt-1 text-sm">
            No search term is stored, so no link could be built.
          </p>
        )}
      </div>

      <Missing items={decision.missing} />

      {/* Exactly one risk line, as the rules produce it. A second one would make the reader choose
          which risk to carry, which is how both get ignored. */}
      <Note>
        <span className="font-medium">Risk:</span> {decision.risk}
      </Note>
    </Card>
  );
}

/// One row of a home-page list.
///
/// Exported as a named interface rather than left inline: three pages build these arrays and a
/// shape nobody can import is a shape everybody retypes slightly differently.
export interface DecisionRow {
  /// Raw stored symbol. Contains `^`, `=`, `.` and `-`, so every link encodes it.
  symbol: string;
  name: string;
  market: Market;
  action: Action;
  entry: { low: number; high: number } | null;
  invalidation: number | null;
  /// The measured exit if the setup works, chosen by `pickTarget` and never averaged. Null when
  /// `jobs/horizons.py` stored no target row, which it does not when there is no stop to measure
  /// reward against. Optional so a caller that has not fetched targets renders exactly as before.
  target?: TargetLike | null;
  confidence: Confidence;
  /// Quoted currency for this row's levels. Defaults to USD, which is wrong for PSX names, so
  /// callers covering PSX must pass it.
  currency?: string;
  /// When the decision applies, from the rule table.
  ///
  /// Only "CARE" changes anything here, and it is the reason this field exists: a LONG with a
  /// dated event two days out is a different proposition from a LONG with an empty calendar, and
  /// the six columns had nowhere to say so. Omitted rows render exactly as before.
  timeSense?: TimeSense;
  /// What the dated event is, when "CARE" is set. "Event today: Q3 earnings." reads as a reason;
  /// a bare CARE badge reads as decoration.
  eventNote?: string | null;
}

export interface DecisionListProps {
  title: string;
  lead?: string;
  rows: DecisionRow[];
  /// What to say when there are none. A list with no rows still owes the reader a reason.
  empty: React.ReactNode;
  /// How many rows to print before the rest are counted rather than listed.
  ///
  /// Undefined prints all of them, which is right on a market page where the list *is* the page.
  /// On the overview it is not: the pool has grown from 160 names to 477, and an eighty-row table
  /// above the fold is a table nobody reads to the end of. Every other block on that page already
  /// cuts and says so -- WAIT at twelve, developing at eighteen, the coming week at six a side --
  /// and these two were the only ones that did not.
  ///
  /// The cut is safe because the order is not arbitrary: `byOpportunity` puts the best evidenced
  /// first, so nothing hidden is better evidenced than something shown. What is hidden is counted
  /// under the heading and reachable on its own market page.
  cap?: number;
}

const ROW_LABEL = "text-muted-foreground text-micro font-medium sm:hidden";

/// A home-page list of decisions.
///
/// Not a `Table`. Seven columns is where the site's table scroller stops being enough: the useful
/// columns here are two prices and three words, and at 375px the reader would have to scroll
/// sideways past the name to reach the stop level — which is the column they came for. So the row
/// is one grid that reflows instead of one table that scrolls. Below `sm` each field is a labelled
/// line stacked in a card; from `sm` up the same cells sit in a six-column row under a header, and
/// the per-field labels go away because the header is carrying them.
///
/// The whole row is the link, so the tap target is the card rather than the name inside it, and
/// there is nothing else interactive in a row to conflict with it.
export function DecisionList({ title, lead, rows, empty, cap }: DecisionListProps) {
  const shown = cap === undefined ? rows : rows.slice(0, cap);
  const hidden = rows.length - shown.length;
  const cols =
    // Seven columns since the measured exit joined the row. The two exit columns are given the
// same width as each other on purpose: they are a pair a reader compares, and sizing one
// smaller would read as one of them mattering less.
  "grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-[minmax(0,1.8fr)_minmax(0,0.7fr)_minmax(0,0.8fr)_minmax(0,1.3fr)_minmax(0,1.1fr)_minmax(0,1.1fr)_minmax(0,1fr)] sm:items-baseline sm:gap-y-0";

  return (
    <Section title={title} lead={lead}>
      {rows.length ? (
        <>
          {/* The header exists only where the row layout does. On a phone each cell labels
              itself, so a header row there would be six words of duplication. */}
          <div
            aria-hidden="true"
            className={`text-muted-foreground border-border bg-muted/60 hidden rounded-t-lg border px-3 py-2 text-xs sm:grid ${cols}`}
          >
            <span>Name</span>
            <span>Market</span>
            <span>Action</span>
            <span>Entry</span>
            <span>Exit if wrong</span>
            <span>Exit if working</span>
            <span>Confidence</span>
          </div>
          <ul className="space-y-2 sm:space-y-0">
            {shown.map((r) => {
              const currency = r.currency ?? "USD";
              return (
                <li
                  key={r.symbol}
                  className="sm:border-border sm:border-x sm:border-b sm:last:rounded-b-lg"
                >
                  <Card
                    href={`/asset/${encodeURIComponent(r.symbol)}`}
                    className={`${cols} sm:rounded-none sm:border-0 sm:px-3 sm:py-3`}
                  >
                    <span className="col-span-2 min-w-0 sm:col-span-1">
                      <span className={ROW_LABEL}>Name</span>
                      <span className="block text-sm font-medium">{r.name}</span>
                      <span className="text-muted-foreground num block text-micro">{r.symbol}</span>
                    </span>

                    <span className="min-w-0">
                      <span className={ROW_LABEL}>Market</span>
                      <span className="block text-sm">{r.market}</span>
                    </span>

                    <span className="min-w-0">
                      <span className={ROW_LABEL}>Action</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1 sm:mt-0">
                        <Pill tone={ACTION_TONE[r.action]}>{r.action}</Pill>
                        {/* A dated event is a hazard on a row that says LONG, and the rule table
                            already decided that by setting the time sense. Printed as its own word
                            rather than a colour, because colour is not a reason. */}
                        {r.timeSense === "CARE" ? <Pill tone="warn">CARE</Pill> : null}
                      </span>
                      {r.timeSense === "CARE" && r.eventNote ? (
                        <span className="text-warn text-micro mt-0.5 block">{r.eventNote}</span>
                      ) : null}
                    </span>

                    <span className="min-w-0">
                      <span className={ROW_LABEL}>Entry</span>
                      <span className="num block text-sm">
                        {r.entry
                          ? `${price(r.entry.low, currency)} to ${price(r.entry.high, currency)}`
                          : "none stored"}
                      </span>
                    </span>

                    <span className="min-w-0">
                      <span className={ROW_LABEL}>Exit if wrong</span>
                      <span className="num block text-sm">
                        {r.invalidation !== null ? price(r.invalidation, currency) : "none stored"}
                      </span>
                    </span>

                    {/* The other exit. A list that names only the level a reading is wrong at
                        answers half the question, and the half it leaves out is the one a reader
                        asks second. One measured method, never an average; a name whose job
                        stored no target says so rather than being given one. */}
                    <span className="min-w-0">
                      <span className={ROW_LABEL}>Exit if working</span>
                      <span
                        className={r.target ? "num block text-sm" : "text-muted-foreground block text-sm"}
                        title={
                          r.target
                            ? `Measured from ${targetMethodLabel(r.target.method)} — a measured level, not a promise.`
                            : undefined
                        }
                      >
                        {r.target
                          ? r.target.low === r.target.high
                            ? price(r.target.low, currency)
                            : `${price(r.target.low, currency)} to ${price(r.target.high, currency)}`
                          : "none stored"}
                      </span>
                    </span>

                    <span className="min-w-0">
                      <span className={ROW_LABEL}>Confidence</span>
                      <span className="mt-0.5 block sm:mt-0">
                        <ConfidenceBadge grade={r.confidence.toLowerCase()} />
                      </span>
                    </span>
                  </Card>
                </li>
              );
            })}
          </ul>
          {hidden > 0 ? (
            <p className="text-muted-foreground mt-3 text-sm">
              {hidden} further {hidden === 1 ? "name reads" : "names read"} the same way with less
              evidence behind {hidden === 1 ? "it" : "them"}. Every one of them carries this reading
              on its own page, and its market page lists them in this order.
            </p>
          ) : null}
        </>
      ) : (
        <Empty>{empty}</Empty>
      )}
    </Section>
  );
}
