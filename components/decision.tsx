import * as React from "react";
import { clockUtc } from "@/lib/liveQuote";
import { shortDay, type Validity } from "@/lib/validity";
import type { EarlySignal } from "@/lib/earlySignal";
import { changeSentence, type StateChange, type Transition } from "@/lib/stateChange";
import { targetSourceSentence, type TargetLike } from "@/lib/target";
import { compactPrice, plainPrice, price, relativeTime } from "@/lib/format";
import { CONFIDENCE_ORDER } from "@/lib/decision";
import type { Action, Confidence, Decision, Market, TimeSense } from "@/lib/decision";
import type { ProductDecision, WhereToCheck } from "@/lib/productDecision";
import {
  AsOf, Card, ConfidenceBadge, Empty, Note, Pill, Section, WaitBasisChip,
} from "@/components/ui";
import { gapLine } from "@/lib/reconcile";
import { MIN_CONFIRMATIONS, MIN_REWARD_RISK, MIN_STOP_ATR } from "@/lib/quality";
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

/// The trade horizon and the call's validity window. One component for the list row and the asset
/// panel, so the two print the same badge, the same dates and the same status for one name.
export function HorizonValidity({ v }: { v: Validity | null | undefined }) {
  if (!v) {
    return <span className="text-muted-foreground block text-sm">Not a call, so no window.</span>;
  }
  return (
    <span className="block">
      <Pill tone="default">{v.label}</Pill>
      <span className="text-muted-foreground text-micro ml-1">{v.span}</span>
      <span className="text-muted-foreground text-micro mt-0.5 block">
        Valid {shortDay(v.from)} – {shortDay(v.until)} UTC
      </span>
      <span className={`text-micro block ${v.status === "Expired" ? "text-warn" : "text-muted-foreground"}`}>
        {v.status === "Active" ? `Active, day ${v.day}` : "Expired: older than its horizon"}
      </span>
    </span>
  );
}

/// The change a row or a header shows: a flip between two directions, and nothing that passes through
/// WAIT. WAIT is the rule table's working state; on the lists it is not printed as a verdict, so a badge
/// naming it would bring back the one word the lists keep out. The full history, WAIT included, stays in
/// the asset page's timeline, where a holder looks for what happened to a call.
export function shownChange(c: StateChange | null | undefined): StateChange | null {
  return c && c.kind === "REVERSED" ? c : null;
}

/// The change timeline at the top of an asset page: every change the log holds for the last 60 days,
/// newest first, and an alert treatment when the newest cycle carried one a holder must not miss.
export function ChangeBanner({
  changes,
  latest,
  market = null,
}: {
  changes: Transition[];
  latest: StateChange | null;
  /// For the closes' precision: FX prints in pips (`plainPrice`).
  market?: string | null;
}) {
  if (!changes.length) return null;
  const recent = [...changes].reverse().slice(0, 4);
  const alert = latest?.warn ?? false;
  return (
    <div
      role={alert ? "alert" : undefined}
      className={`mb-3 rounded-lg border px-3 py-2 text-sm ${alert ? "border-down bg-down/10" : "border-border bg-muted/40"}`}
    >
      <p className={`font-semibold ${alert ? "text-down" : ""}`}>
        {latest ? changeSentence(latest) : "Verdict history"}
      </p>
      <ol className="text-muted-foreground mt-1 space-y-0.5 text-xs">
        {recent.map((t) => (
          <li key={t.on}>
            {shortDay(t.fromOn)}: {t.from}
            {t.fromClose != null ? ` (${plainPrice(t.fromClose, market)})` : ""} ➔ {shortDay(t.on)}: {t.to}
            {t.toClose != null ? ` (${plainPrice(t.toClose, market)})` : ""} — {t.kind.toLowerCase()}, because {t.reason}.
          </li>
        ))}
      </ol>
    </div>
  );
}

/// The rising-star marker. Gold on its own background so it stands out from the action and grade
/// pills in both themes; muted when the rule table still holds the name back, because then it marks an
/// event and not a call. The whole explanation is in the tooltip and the accessible name.
export function EarlySignalBadge({ s }: { s: EarlySignal }) {
  const held = s.stance === "held";
  return (
    <span
      title={s.explain}
      aria-label={s.explain}
      className={`inline-flex items-center gap-0.5 rounded-full border px-1.5 py-1 text-micro leading-4 font-semibold whitespace-nowrap sm:py-0.5 ${
        held ? "border-border text-muted-foreground" : "border-warn bg-warn-bg text-warn ring-warn/30 ring-2"
      }`}
    >
      <span aria-hidden="true">★</span>
      {s.label.toUpperCase()} {s.direction === "up" ? "↑" : "↓"}
    </span>
  );
}

export interface DecisionPanelProps {
  decision: Decision;
  symbol: string;
  /// Quoted currency for the two levels. PSX names are in rupees and `price()` knows the marks.
  currency: string;
  /// The asset's market, for precision only: FX prints in pips, where two decimals made a pair's
  /// entry, stop and target read as one number.
  market?: string | null;
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
  /// The trade horizon and validity window, from the same function the list rows use.
  validity?: Validity | null;
  /// The rising-star marker, from the same function the list rows use. Null when no entry event fired.
  early?: EarlySignal | null;
  /// The newest-cycle change (same function as the rows) and the full timeline for the banner.
  change?: StateChange | null;
  changes?: Transition[];
  /// The stored last trade, when it says something the close does not. Shown as the price.
  quote?: { price: number; quotedAt: string } | null;
  /// The quality gate's reasons when the lists withhold this call (lib/quality.ts); null when published.
  withheld?: string[] | null;
  /// Set when the call is listed only because it is open (lib/quality.ts `withOpenPosition`).
  held?: { since: string; todays: string[] } | null;
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
            ? "The measured exit against the stop above, from the entry level. Measured, not chosen."
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
            No measured exit is stored, so the reward cannot be sized.
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
  market = null,
  asOf,
  priceNow = null,
  news = [],
  target = null,
  validity = null,
  early = null,
  change = null,
  changes = [],
  quote = null,
  withheld = null,
  held = null,
}: DecisionPanelProps) {
  // A call that ended at its stop (brain.md rule 92): its entry, exit and reward fields say so.
  const ended = decision.action === "WAIT" && decision.gate === "stop-crossed";
  const grade = decision.confidence.toLowerCase();
  const gap = gapLine(decision);

  return (
    <Card className="border-primary/30">
      {/* The verdict's history first: a reader holding yesterday's call needs to know it changed
          before reading today's. Nothing renders when the log holds no change for this name. */}
      <ChangeBanner changes={changes} latest={change} market={market} />
      {withheld && withheld.length ? (
        <div role="note" className="border-warn bg-warn-bg text-warn mb-3 rounded-lg border px-3 py-2 text-sm">
          <p className="font-semibold">Not on the signal lists today: this call did not pass the quality gate.</p>
          <p className="mt-0.5 text-xs">{withheld.join("; ")}. What follows is the analysis, not a published call.</p>
        </div>
      ) : null}
      {held ? (
        <div role="note" className="border-border bg-muted/40 mb-3 rounded-lg border px-3 py-2 text-sm">
          <p className="font-semibold">Open call, published {shortDay(held.since)}: held to its stop.</p>
          <p className="text-muted-foreground mt-0.5 text-xs">
            Today&apos;s reading alone would not publish it ({held.todays.join("; ")}), so it is not a new entry; it
            stays listed until its stop is crossed or its window ends.
          </p>
        </div>
      ) : null}
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
          {/* A grade grades a direction. On a WAIT there is none, and a Low badge there reads as a weak
              judgement where nothing was judged; the basis chip beside it already says why. */}
          {decision.action === "WAIT" ? null : <ConfidenceBadge grade={grade} />}
          {early ? <EarlySignalBadge s={early} /> : null}
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
        <Field label="Price" hint="The newest trade when one is stored, else the close; hover it for its time. The decision reads the daily close, shown under Price and history.">
          {quote ? (
            <span
              className="num block text-lg font-semibold"
              title={`Last trade, ${shortDay(quote.quotedAt.slice(0, 10))} ${clockUtc(quote.quotedAt)}`}
            >
              {price(quote.price, currency, market)}
            </span>
          ) : priceNow !== null ? (
            <span
              className="num block text-lg font-semibold"
              title={asOf ? `Close of ${shortDay(new Date(asOf).toISOString().slice(0, 10))}` : undefined}
            >
              {price(priceNow, currency, market)}
            </span>
          ) : (
            <span className="text-muted-foreground">
              Nothing is stored, which is why the action is WAIT.
            </span>
          )}
        </Field>

        <Field
          label="Entry zone"
          hint={
            decision.entry
              ? "Both ends inclusive. Outside the zone there is nothing to do."
              : undefined
          }
        >
          {decision.entry ? (
            <span className="num">
              {decision.entry.low === decision.entry.high
                ? price(decision.entry.low, currency, market)
                : `${price(decision.entry.low, currency, market)} to ${price(decision.entry.high, currency, market)}`}
            </span>
          ) : (
            <span className="text-muted-foreground">
              {ended ? "None: the call ended at its stop." : "No measured zone is stored, so no entry is named."}
            </span>
          )}
        </Field>

        {/* "Stop loss", never "invalidation". The reader is owed the instruction in the words
            they already trade in, not the vocabulary the column is stored under. The hint below
            keeps the instruction: the label says what it is, the hint says what it means. */}
        <Field
          label="Stop loss"
          hint={
            decision.invalidation !== null
              ? ended
                ? "The close went through this level, so the call ended here."
                : "Past this level the reason above no longer holds."
              : undefined
          }
        >
          {decision.invalidation !== null ? (
            <span className="num">{price(decision.invalidation, currency, market)}</span>
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
          label="Measured exit"
          hint={
            target
              ? targetSourceSentence(target.method)
              : undefined
          }
        >
          {target ? (
            <span className="num">
              {target.low === target.high
                ? price(target.low, currency, market)
                : `${price(target.low, currency, market)} to ${price(target.high, currency, market)}`}
            </span>
          ) : (
            <span className="text-muted-foreground">{ended ? "None: the call ended at its stop." : "No measured exit stored."}</span>
          )}
        </Field>

        {/* The same three columns the list prints, under the same names, so a name read on a market
            page and on its own page is described by the same figures. */}
        <Field label="Reward:risk" hint="Measured from the entry level. From today's price it is at least this.">
          {target?.rewardRisk != null ? (
            <span className="num">{target.rewardRisk.toFixed(1)}:1</span>
          ) : (
            <span className="text-muted-foreground">{ended ? "None: the call ended." : "No measured exit to weigh."}</span>
          )}
        </Field>

        <Field label="Early signal">
          {early ? (
            <span className="block">
              <EarlySignalBadge s={early} />
              <span className="text-muted-foreground text-micro mt-1 block">{early.explain}</span>
            </span>
          ) : (
            <span className="text-muted-foreground">No early entry event fired this session.</span>
          )}
        </Field>

        <Field label="Horizon & validity">
          <HorizonValidity v={decision.action === "WAIT" ? null : validity} />
        </Field>

        <Field label="Confirmations">
          {decision.action === "WAIT" ? (
            <span className="text-muted-foreground">Held back, so nothing to confirm.</span>
          ) : (
            <span className="block">
              <span className="num">
                {decision.legs.length} of {LEG_TOTAL}
              </span>
              <span className="text-muted-foreground text-micro block">
                {decision.legs.length ? decision.legs.map((l) => LEG_WORDS[l] ?? l).join(", ") : "none"}
              </span>
            </span>
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
            <span className="text-muted-foreground">Geography not measured yet.</span>
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
  /// Set when the row is listed only because it is an open call (lib/quality.ts `withOpenPosition`).
  held?: { since: string; todays: string[] } | null;
  /// Raw stored symbol. Contains `^`, `=`, `.` and `-`, so every link encodes it.
  symbol: string;
  name: string;
  market: Market;
  action: Action;
  /// The newest stored close. Printed before the levels, because every level in the row is read
  /// against it: a stop and a target with no spot price between them is a quiz, which is the
  /// argument the asset panel has carried since it was written and which these tables did not.
  ///
  /// Optional, and null is printed as a reason rather than a dash -- a row with no stored close
  /// is the one the rules refuse at gate 1, and the table should say so in the same column a
  /// reader is already looking at.
  priceNow?: number | null;
  /// The sector this row belongs under, and where that sector sits in the site-wide order.
  ///
  /// Optional so a caller that does not group renders exactly as before. Both are stored
  /// `Industry` columns -- `sectorSort` rather than alphabetical, because alphabetical would put
  /// Aerospace above Mega Cap Tech on the stocks page and the seed's order is the one every
  /// other surface uses.
  sector?: string | null;
  sectorSort?: number | null;
  entry: { low: number; high: number } | null;
  invalidation: number | null;
  /// A call that ended at its stop: no entry, exit or reward is printed for it (brain.md rule 92).
  ended?: boolean;
  /// The measured exit if the setup works, chosen by `pickTarget` and never averaged. Null when
  /// `jobs/horizons.py` stored no target row, which it does not when there is no stop to measure
  /// reward against. Optional so a caller that has not fetched targets renders exactly as before.
  target?: TargetLike | null;
  confidence: Confidence;
  /// The confirmations that backed this direction, by the names the rule table uses. Optional so a
  /// caller that has not carried them renders as before, with an empty cell rather than a guess.
  legs?: string[];
  /// Why the rule table made no call, for a WAIT: one or two sentences from the decision itself.
  /// Null on a direction. A row that is held back prints this instead of a grade and a dash.
  reason?: string[] | null;
  /// The last trade and when it was struck, when it adds something beside the close. Never replaces it.
  quote?: { price: number; quotedAt: string } | null;
  /// The close's own day, ISO.
  closeDate?: string | null;
  /// Trade horizon and validity window; null on a WAIT.
  validity?: Validity | null;
  /// The rising-star marker; null when no entry event fired.
  early?: EarlySignal | null;
  /// A verdict change made in the newest decision cycle; null when there was none.
  change?: StateChange | null;
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
  /// Break the list into sector headings instead of one run of rows.
  ///
  /// Off by default, so the overview's short lists stay one ranked run -- there the question is
  /// "what are the best-evidenced names anywhere", and a sector heading over two rows would be
  /// filing rather than ordering. On a market page the list *is* the page and 249 names in one
  /// column is a wall; there the sector is the structure a reader navigates by.
  ///
  /// Grouping never reorders within a sector: rows arrive sorted by the caller and keep that
  /// order inside their heading, so the best-evidenced name in a sector is still its first row.
  grouped?: boolean;
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

// The per-cell label, shown wherever the row is a stacked card rather than a table line.
//
// It hides at `lg`, not `sm`. Eight columns -- four of them prices -- is a desktop table: at
// 640px each price track is about 70px, which "Rs.1,201.22" does not fit in, and the row either
// wraps into an unreadable stack or clips. A phone and a tablet both get the labelled card, and
// only a screen with the width for eight columns gets the eight columns.
const ROW_LABEL = "text-muted-foreground text-micro font-medium xl:sr-only";

/// How many confirmations exist, for the "n of 5" a row prints. Kept beside the labels so the two
/// numbers a reader compares -- how many backed it and how many could have -- are written together.
const LEG_TOTAL = 5;

/// Reader-facing words for the rule table's leg names. An unknown name falls back to itself, so a
/// sixth confirmation added to the rule table prints under its own name instead of vanishing.
const LEG_WORDS: Record<string, string> = {
  timeframe: "longer view",
  volume: "volume",
  history: "similar days",
  peers: "peers",
  trigger: "entry trigger",
};

/// Rows split into sector sections, in the site-wide sector order.
///
/// `sectorSort` decides the order of the sections and never the order inside one: the caller has
/// already sorted its rows by evidence, and re-sorting here would quietly put a Low-confidence
/// name above a High one inside a heading.
///
/// A row with no sector collects under "Other", at the end. That is a real state rather than a
/// defensive branch -- `sector` is optional on `DecisionRow` so a caller that does not fetch it
/// still renders -- and lumping those rows into whichever sector happened to come first would be
/// worse than naming them.
function bySector(rows: DecisionRow[]): { sector: string | null; rows: DecisionRow[] }[] {
  const groups = new Map<string, { sector: string; sort: number; rows: DecisionRow[] }>();
  for (const row of rows) {
    const sector = row.sector ?? "Other";
    const sort = row.sector ? (row.sectorSort ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
    const found = groups.get(sector);
    if (found) found.rows.push(row);
    else groups.set(sector, { sector, sort, rows: [row] });
  }
  return [...groups.values()]
    .sort((a, b) => (a.sort !== b.sort ? a.sort - b.sort : a.sector.localeCompare(b.sector)))
    .map((g) => ({ sector: g.sector, rows: g.rows }));
}

/// Rows past this many in one sector and the sector scrolls inside itself.
///
/// Below it a scrollbar would be noise: a four-row sector fits on any screen and capping it adds
/// a scroll trap for no gain. Above it the sector is taller than a phone and the reader is
/// scrolling a sector when they wanted to be scrolling the page. 10 is roughly a laptop screen's
/// worth of table rows and well over a phone's, so the containers that engage are the ones that
/// were actually making the page long.
const SECTOR_SCROLL_AFTER = 10;

/// The height a scrolling sector is held to, in viewport units.
///
/// Viewport-relative rather than a pixel count, because the thing it is trying to stay smaller
/// than is the screen. 70vh leaves the sector heading, the page heading and some of the next
/// sector visible on a phone, which is what stops a nested scroll feeling like a trap: a reader
/// can always see something outside the box they are scrolling.
const SECTOR_MAX_HEIGHT = "70vh";

/// One block per sector, holding every direction in it, both ways round.
///
/// **Why both directions in one block.** Separate LONG and SHORT sections answered "what should I
/// do" first and buried the sector; a reader watching Banking had to read two lists and join them
/// in their head to see what the sector was doing. One block per sector answers "what is this
/// group doing" in one place, and the action is still the first coloured thing in every row, so
/// the directional question is a glance rather than a scroll.
///
/// Within a sector the longs come first and then the shorts, each best-evidenced first. Merging
/// them into one confidence ranking was the other option and is worse: a reader scanning for one
/// side would have to filter visually down the whole block, which is the work the two lists at
/// least did for them.
///
/// Each sector past `SECTOR_SCROLL_AFTER` rows scrolls inside itself, so a 40-name sector is a
/// box on the page rather than a page of its own. `aria-label` and `tabIndex` are on the scroller
/// because a keyboard user has to be able to reach a scroll container that holds focusable links,
/// and a div that scrolls without either is unreachable without a mouse.
export function SectorBoard({
  rows,
  empty,
  maxSectors,
}: {
  rows: DecisionRow[];
  empty: React.ReactNode;
  /// Show only this many sectors, for the overview where the block is a summary rather than the
  /// index. Undefined shows every sector, which is right on a market page.
  maxSectors?: number;
}) {
  if (!rows.length) return <Empty>{empty}</Empty>;

  const order = { LONG: 0, SHORT: 1, WAIT: 2 } as const;
  const all = bySector(rows).map((section) => ({
    ...section,
    rows: [...section.rows].sort(
      (a, b) =>
        order[a.action] - order[b.action] ||
        CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence] ||
        a.symbol.localeCompare(b.symbol),
    ),
  }));
  const shown = maxSectors === undefined ? all : all.slice(0, maxSectors);
  const hiddenSectors = all.length - shown.length;

  return (
    <div className="space-y-4">
      {shown.map((section) => {
        const longs = section.rows.filter((r) => r.action === "LONG").length;
        const shorts = section.rows.filter((r) => r.action === "SHORT").length;
        const scrolls = section.rows.length > SECTOR_SCROLL_AFTER;
        const label = section.sector ?? "Other";
        return (
          <div key={label} className="border-border overflow-hidden rounded-lg border">
            <div className="border-border bg-muted/60 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b px-3 py-2">
              <h3 className="text-sm font-medium">{label}</h3>
              <p className="text-muted-foreground text-xs">
                <span className="num">{section.rows.length}</span>
                {" names · "}
                <span className="num">{longs}</span> long{" · "}
                <span className="num">{shorts}</span> short
                {scrolls ? " · scrolls" : ""}
              </p>
            </div>
            <div
              className={scrolls ? "overflow-y-auto overscroll-contain" : undefined}
              style={scrolls ? { maxHeight: SECTOR_MAX_HEIGHT } : undefined}
              tabIndex={scrolls ? 0 : undefined}
              role={scrolls ? "group" : undefined}
              aria-label={scrolls ? `${label}, scrollable list of ${section.rows.length} names` : undefined}
            >
              {/* Inside the scroller and pinned, so it is the first thing in the box and stays
                  there. `rounded={false}` because the block's own border already rounds it. */}
              <DecisionHeader rounded={false} sticky />
              <DecisionRows rows={section.rows} />
            </div>
          </div>
        );
      })}
      {hiddenSectors > 0 ? (
        <p className="text-muted-foreground text-sm">
          {hiddenSectors} further {hiddenSectors === 1 ? "sector reads" : "sectors read"} the same
          way with less evidence behind {hiddenSectors === 1 ? "it" : "them"}. Every one is on its
          own market page, in this order.
        </p>
      ) : null}
    </div>
  );
}

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
/// The shared column track, and the one breakpoint that decides whether this is a table or a
/// stack of labelled cards.
///
/// Eight columns since the current price joined the row: name, market, action, price, zone, stop,
/// target, confidence. The three level columns are given the same width as each other on purpose
/// -- they are what a reader compares, and sizing one smaller would read as one of them mattering
/// less.
///
/// Two breakpoints rather than one. Below `sm` each field is its own labelled line. From `sm` to
/// `lg` the fields pair up two to a line, which is the shape a tablet has room for. The
/// eight-column table starts at `lg`, where there is genuinely width for eight tracks -- at 640px
/// a price track is about 70px and "Rs.1,201.22" does not fit in it.
///
/// The Action track has a floor of 176px because its cell is one line by rule: the widest pair, SHORT
/// beside a compact "★ FALLING STAR ↓", measured 171px in a browser. At 0.95fr it was 75px at 1024
/// and 89px at 1280, so every star wrapped under its call and grew the row. The three price tracks
/// keep a 76px floor for "$1,728.06", which already spilled 3px into the next column at 1024. Measured
/// at 1024 and 1280 with these tracks and a 10px gap: no cell overflows and no star wraps. Below lg the
/// Action cell spans two tracks and the grid packs densely, so the one-line cell fits a phone too.
const DECISION_COLS =
  "grid grid-flow-row-dense grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,0.5fr)_minmax(176px,0.95fr)_minmax(92px,0.85fr)_minmax(124px,1.15fr)_minmax(92px,0.9fr)_minmax(124px,0.95fr)_minmax(0,0.7fr)_minmax(0,1.05fr)_minmax(0,1.2fr)] xl:items-baseline xl:gap-x-2.5 xl:gap-y-0";

/// One price in a list cell: never broken across lines, and compact under 0.0001 (the subscript-zero
/// form, `compactPrice`) so a sub-cent coin fits the column instead of wrapping mid-number or spilling
/// into the next one. The full figure is the tooltip.
function Px({ v, currency, market = null }: { v: number; currency: string; market?: string | null }) {
  return (
    <span className="whitespace-nowrap" title={price(v, currency, market)}>
      {compactPrice(v, currency, market)}
    </span>
  );
}

/// A band in a list cell: one price when both ends are the same, else two that may break only at "to".
function PxRange({ low, high, currency, market = null }: { low: number; high: number; currency: string; market?: string | null }) {
  return low === high ? (
    <Px v={low} currency={currency} market={market} />
  ) : (
    <>
      {/* "to" travels with the second price, so a range is at most two lines: "Rs.1,165.00" over
          "to Rs.1,210.00", never the word alone on a line between them (ATRL, 2026-10-11). */}
      <Px v={low} currency={currency} market={market} />{" "}
      <span className="whitespace-nowrap">
        to <Px v={high} currency={currency} market={market} />
      </span>
    </>
  );
}

/// The calls the quality gate kept off the lists (lib/quality.ts): named, linked, each with the rule it
/// failed, and with no direction or levels, because they are not signals. Folded, so it is found on
/// purpose; complete inside, so a reader looking a name up can see why it is not on the board.
export function WithheldList({ rows }: { rows: { symbol: string; name: string; reasons: string[] }[] }) {
  if (!rows.length) return null;
  return (
    <details className="border-border bg-muted/30 mt-6 rounded-lg border px-4 py-1 text-sm sm:py-3">
      <summary className="-my-1 cursor-pointer py-3 font-medium select-none sm:my-0 sm:py-0">
        Not published: {rows.length} {rows.length === 1 ? "call" : "calls"} did not pass the quality gate
      </summary>
      <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
        A call is published only with an entry range, a stop at least {MIN_STOP_ATR} x ATR beyond it, a measured
        target, reward:risk of at least {MIN_REWARD_RISK}:1 and at least {MIN_CONFIRMATIONS} independent
        confirmation. These were computed, and are logged and graded; they are not shown as signals.
      </p>
      <ul className="mt-2 space-y-1 pb-2">
        {rows.map((r) => (
          <li key={r.symbol} className="flex flex-wrap items-baseline gap-x-2">
            <a href={`/asset/${encodeURIComponent(r.symbol)}`} className="font-medium underline-offset-2 hover:underline">
              {r.name}
            </a>
            <span className="text-muted-foreground num text-micro">{r.symbol}</span>
            <span className="text-muted-foreground text-xs">{r.reasons.join("; ")}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/// The column header, shown only where the table layout is.
///
/// On a phone and a tablet each cell labels itself, so a header there would be eight words of
/// duplication over every row.
function DecisionHeader({
  rounded = true,
  sticky = false,
}: {
  rounded?: boolean;
  /// Pin to the top of the nearest scrolling ancestor. For a header inside a sector's scroll box:
  /// without it the column names scroll away with the first row and a reader eight rows down is
  /// looking at ten unlabelled numbers.
  sticky?: boolean;
}) {
  return (
    <div
      aria-hidden="true"
      className={`text-muted-foreground border-border hidden border px-3 py-2 text-xs xl:grid ${
        sticky ? "bg-muted sticky top-0 z-10" : "bg-muted/60"
      } ${rounded ? "rounded-t-lg" : "border-x-0 border-t-0"} ${DECISION_COLS}`}
    >
      <span>Name</span>
      <span>Market</span>
      <span>Action</span>
      <span title="The newest trade when one is stored, else the close. Hover a price for its time.">Price</span>
      <span>Entry zone</span>
      <span>Stop loss</span>
      <span>Measured exit</span>
      <span title="Reward against risk, measured from the entry level. From today's price it is at least this.">
        Reward:risk
      </span>
      <span>Horizon & validity</span>
      <span title="How many of the five independent confirmations back this direction, and which.">
        Confirmations
      </span>
    </div>
  );
}

/// The rows themselves, with no heading and no section chrome around them.
///
/// Extracted so `DecisionList` and `SectorBoard` render an identical row. Two copies of this
/// markup is how the overview and a market page come to show the same name with different
/// columns -- which is the fault rule 36 names, and this block is eight columns of chances to
/// commit it.
function DecisionRows({ rows }: { rows: DecisionRow[] }) {
  return (
    <ul className="space-y-2 xl:space-y-0">
{rows.map((r) => {
        const currency = r.currency ?? "USD";
        return (
          <li
            key={r.symbol}
            className="xl:border-border xl:border-x xl:border-b xl:last:rounded-b-lg"
          >
            <Card
              href={`/asset/${encodeURIComponent(r.symbol)}`}
              className={`${DECISION_COLS} xl:rounded-none xl:border-0 xl:px-3 xl:py-3`}
            >
              <span className="col-span-2 min-w-0 xl:col-span-1">
                <span className={ROW_LABEL}>Name</span>
                <span className="block text-sm font-medium">{r.name}</span>
                <span className="text-muted-foreground num block text-micro">{r.symbol}</span>
              </span>

              <span className="min-w-0">
                <span className={ROW_LABEL}>Market</span>
                <span className="block text-sm">{r.market}</span>
              </span>

              <span className="col-span-2 min-w-0 xl:col-span-1">
                <span className={ROW_LABEL}>Action</span>
                {/* One line, always: the verdict and the star side by side, never stacked, so a star
                    does not make its row taller than its neighbours. The track is sized for it. */}
                <span className="mt-0.5 flex flex-row flex-nowrap items-center gap-1.5 whitespace-nowrap xl:mt-0">
                  {/* A held-back row prints no verdict pill: WAIT is the rule table's working state,
                      not a call, and the list it sits in already says the names in it are held back.
                      Its reason is in the row, under "Why no call". */}
                  {r.action === "WAIT" ? (
                    <span className="text-muted-foreground text-sm">Held back</span>
                  ) : (
                    <Pill tone={ACTION_TONE[r.action]}>{r.action}</Pill>
                  )}
                  {/* Two things only: the verdict and the early-signal star. The grade is on the
                      asset page; a change and a dated event are said in a sentence below. */}
                  {r.early ? <EarlySignalBadge s={r.early} /> : null}
                </span>
                {r.held ? (
                  <span className="text-muted-foreground text-micro mt-0.5 block leading-snug">
                    Open since {shortDay(r.held.since)}: held to its stop, not a new entry ({r.held.todays.join("; ")}).
                  </span>
                ) : null}
                {shownChange(r.change) ? (
                  <span className="text-down text-micro mt-0.5 block leading-snug">{changeSentence(shownChange(r.change)!)}</span>
                ) : null}
                {/* A dated event is a hazard on a row that says LONG, and the rule table already decided
                    that by setting the time sense. Said in words, because colour is not a reason. */}
                {r.timeSense === "CARE" ? (
                  <span className="text-warn text-micro mt-0.5 block leading-snug">{r.eventNote ?? TIME_SENSE_COPY.CARE}</span>
                ) : null}
              </span>

              <span className="min-w-0">
                <span className={ROW_LABEL}>Price</span>
                {/* The price alone: the newest stored trade when there is one that says something the
                    close does not, otherwise the close. When it was struck is on hover, not in the cell.
                    The decision reads the close either way, and the asset page shows it beside the
                    price history. */}
                {r.quote ? (
                  <span
                    className="num block text-sm font-medium whitespace-nowrap"
                    title={`${price(r.quote.price, currency, r.market)}, last trade ${shortDay(r.quote.quotedAt.slice(0, 10))} ${clockUtc(r.quote.quotedAt)}`}
                  >
                    {compactPrice(r.quote.price, currency, r.market)}
                  </span>
                ) : r.priceNow !== null && r.priceNow !== undefined ? (
                  <span
                    className="num block text-sm font-medium whitespace-nowrap"
                    title={`${price(r.priceNow, currency, r.market)}${r.closeDate ? `, close of ${shortDay(r.closeDate)}` : ""}`}
                  >
                    {compactPrice(r.priceNow, currency, r.market)}
                  </span>
                ) : (
                  <span className="text-muted-foreground block text-sm">no close yet</span>
                )}
              </span>

              <span className="min-w-0">
                <span className={ROW_LABEL}>Entry zone</span>
                <span className="num block text-sm">
                  {r.entry ? <PxRange low={r.entry.low} high={r.entry.high} currency={currency} market={r.market} /> : r.ended ? "none: the call ended" : "no entry band measured"}
                </span>
              </span>

              <span className="min-w-0">
                <span className={ROW_LABEL}>Stop loss</span>
                <span className="num block text-sm">
                  {r.invalidation !== null ? <Px v={r.invalidation} currency={currency} market={r.market} /> : "no stop level set"}
                </span>
              </span>

              {/* The other exit. A list that names only the level a reading is wrong at
                  answers half the question, and the half it leaves out is the one a reader
                  asks second. One measured method, never an average; a name whose job
                  stored no target says so rather than being given one. */}
              <span className="min-w-0">
                <span className={ROW_LABEL}>Measured exit</span>
                <span
                  className={r.target ? "num block text-sm" : "text-muted-foreground block text-sm"}
                  title={
                    r.target
                      ? targetSourceSentence(r.target.method)
                      : undefined
                  }
                >
                  {r.target ? <PxRange low={r.target.low} high={r.target.high} currency={currency} market={r.market} /> : r.ended ? "none: the call ended" : "no exit measured"}
                </span>
              </span>

              {/* Reward against risk, from the same target the column to its left prints, so the
                  two cannot disagree. Measured from the entry level: with the stop below the
                  close and the close at or under the entry for a long -- which the rule table now
                  guarantees -- the figure from today's price is at least this one, so it
                  understates and never flatters. */}
              <span className="min-w-0">
                <span className={ROW_LABEL}>Reward:risk</span>
                <span
                  className={
                    r.target?.rewardRisk != null && Number.isFinite(r.target.rewardRisk) ? "num block text-sm whitespace-nowrap" : "text-muted-foreground block text-sm"
                  }
                  title="Measured from the entry level. From today's price it is at least this."
                >
                  {r.target?.rewardRisk != null && Number.isFinite(r.target.rewardRisk) ? `${r.target.rewardRisk.toFixed(1)}:1` : r.ended ? "none: the call ended" : "no exit to weigh"}
                </span>
              </span>

              {/* A held-back row has no direction, so there is nothing to grade and nothing to confirm:
                  a Low badge and a dash would be two placeholders standing where the one thing the
                  rule table did say belongs. This prints that instead, across the two columns. */}
              {r.action === "WAIT" ? (
                <span className="col-span-2 min-w-0 sm:col-span-2 xl:col-span-2">
                  <span className={ROW_LABEL}>Why no call</span>
                  {r.reason?.length ? (
                    r.reason.map((line, i) => (
                      <span
                        key={i}
                        className={`block text-micro leading-snug ${i === 0 ? "" : "text-muted-foreground"}`}
                      >
                        {line}
                      </span>
                    ))
                  ) : (
                    <span className="block text-micro leading-snug">
                      Held back: no call for this name, so there is nothing to grade or confirm.
                    </span>
                  )}
                </span>
              ) : (
                <>
              <span className="min-w-0">
                <span className={ROW_LABEL}>Horizon & validity</span>
                <span className="mt-0.5 block xl:mt-0">
                  <HorizonValidity v={r.validity} />
                </span>
              </span>

              {/* The score and what it is made of. A grade says one thing backed a call; this says
                  which. A WAIT has no direction to confirm, so it prints a dash and not "0 of 5",
                  which would read as a call that nothing supports. */}
              <span className="min-w-0">
                <span className={ROW_LABEL}>Confirmations</span>
                {r.legs === undefined ? (
                  <span className="text-muted-foreground block text-sm">confirmations not carried</span>
                ) : (
                  <>
                    <span className="num block text-sm">
                      {r.legs.length} of {LEG_TOTAL}
                    </span>
                    <span className="text-muted-foreground text-micro block">
                      {r.legs.length ? r.legs.map((l) => LEG_WORDS[l] ?? l).join(", ") : "none"}
                    </span>
                  </>
                )}
              </span>
                </>
              )}
            </Card>
          </li>
        );
      })}    </ul>
  );
}

export function DecisionList({ title, lead, rows, empty, cap, grouped = false }: DecisionListProps) {
  const shown = cap === undefined ? rows : rows.slice(0, cap);
  const hidden = rows.length - shown.length;
  const sections = grouped ? bySector(shown) : [{ sector: null, rows: shown }];

  return (
    <Section title={title} lead={lead}>
      {rows.length ? (
        <>
          <DecisionHeader />
          {sections.map((section) => (
            <div key={section.sector ?? "all"}>
              {/* The heading carries its own count so a reader scanning headings knows the size
                  of each without expanding anything. Sticky on the table layout because a 40-row
                  sector scrolls past its own title otherwise, and the title is the thing that
                  makes the rows mean something. */}
              {section.sector ? (
                <h3 className="bg-background/95 text-muted-foreground supports-[position:sticky]:xl:sticky supports-[position:sticky]:xl:top-0 z-10 mt-4 border-b px-1 pt-2 pb-1 text-xs font-medium first:mt-0">
                  {section.sector} <span className="num">({section.rows.length})</span>
                </h3>
              ) : null}
              <DecisionRows rows={section.rows} />
            </div>
          ))}
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
