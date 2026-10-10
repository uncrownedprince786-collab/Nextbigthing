/// The macro gatekeeper without a model: the same veto, decided by a fixed word table and the stored
/// source statistics, at no cost and with no network.
///
/// **Why this exists.** `lib/macroGate.ts` asks a language model, which is paid, not deterministic and
/// cannot be scored offline. This file answers the same question -- "do recent headlines describe a shock
/// big enough to refuse this LONG or SHORT?" -- as a pure function: same input, same answer, forever.
/// That is the property the rule table already holds, so this is the engine the nightly job uses unless
/// it is told otherwise, and the only one that can be put through an exam in CI.
///
/// **What it may do.** Turn a LONG or SHORT into a refusal. Nothing else: it returns a verdict, one of
/// two reasons, and a sentence. It has no way to touch a price, a stop or a ratio, and the sentence is
/// built from the headline and the stored statistics, never from anything it computed about the trade.
///
/// **What it cannot do, and the page must never claim.** It reads words, not meaning. A shock phrased
/// in a way this table does not list passes (a miss, and the safe direction: the rule table's own
/// verdict stands), and a headline that uses the listed words for something else could refuse a name
/// wrongly (a false veto, which costs one trade and is stored so it can be scored). It is a tripwire
/// for the unambiguous cases, not a reader. Hedged, denied and reversed news is deliberately never a
/// trigger, because a refusal on a rumour is the pump-and-dump this layer exists to resist.
///
/// **Trust comes first, from the stored Beta statistics, and decides before any word is read.** A
/// source is believed only at a mean of 0.70 or more *and* at least `MIN_EVIDENCE` observations' worth
/// of mass, so a brand-new source with one success cannot score 1.0. Below 0.30 it is ignored outright;
/// between the two it is uncertain, and an uncertain source never vetoes alone.

import { MACRO_WINDOW_HOURS, MAX_RATIONALE, sanitizeText, selectNews } from "./macroGate.ts";
import type { GateInput, GateNews, GateResult, RefusalReason } from "./macroGate.ts";

/// A sanity bound on one asset's headlines, not a budget.
const SCAN_LIMIT = 500;
export const LOCAL_ENGINE = "local-rules-v1";
/// A source must reach this mean to be believed on a shock.
export const TRUSTED_MEAN = 0.7;
/// ...and below this it is ignored outright, whatever it says.
export const IGNORED_BELOW = 0.3;
/// alpha + beta at least this, so a source with a handful of observations cannot reach the bar. The
/// stored prior is Beta(2, 2), which is a mass of 4: a source has to have earned its place.
export const MIN_EVIDENCE = 10;

type Reach = "market" | "crypto" | "asset";

interface Rule {
  id: string;
  reason: RefusalReason;
  /// Who the headline bears on: every class, crypto only, or the one asset the news is attached to.
  reach: Reach;
  /// The sentence fragment that says what was reported.
  says: string;
  /// Only a LONG is in conflict with this (corporate bad news supports a short, it does not contradict one).
  longOnly: boolean;
  /// Every one of these must match the normalised headline.
  all: RegExp[];
}

const ban = "(ban|bans|banned|banning|prohibit|prohibits|prohibited|prohibiting|outlaw|outlaws|outlawed)";
const authority = "(sec|cftc|fed|federal reserve|regulators?|government|treasury|congress|central bank|ministry|commission|nationwide|immediate|immediately)";

const RULES: Rule[] = [
  {
    id: "ban-crypto", reason: "macro-warning", reach: "crypto", longOnly: false,
    says: "a regulatory ban on crypto trading",
    all: [new RegExp(`\\b${ban}\\b`), /\b(crypto\w*|bitcoin|stablecoins?|digital assets?|derivatives)\b/, new RegExp(`\\b${authority}\\b`)],
  },
  {
    id: "ban-market", reason: "macro-warning", reach: "market", longOnly: false,
    says: "a regulatory ban on trading",
    all: [new RegExp(`\\b${ban}\\b`), /\b(short selling|stock trading|equities|securities|stock markets?|futures)\b/, new RegExp(`\\b${authority}\\b`)],
  },
  {
    id: "central-bank-emergency", reason: "macro-warning", reach: "market", longOnly: false,
    says: "an emergency central bank rate action",
    all: [
      /\b(emergency|unscheduled|inter meeting)\b/,
      /(\d\s*bps|\bbasis points\b|\brate (hike|hikes|cut|cuts|decision)\b|\binterest rates?\b)/,
      /\b(central bank|fed|federal reserve|ecb|boe|boj|snb|pboc|state bank|reserve bank)\b/,
    ],
  },
  {
    id: "market-halt", reason: "macro-warning", reach: "market", longOnly: false,
    says: "a halt to market or settlement operations",
    all: [
      /\b(halt|halts|halted|halting|suspend|suspends|suspended|suspending|freeze|freezes|froze|frozen)\b/,
      /\b(trading|settlements?|clearing|redemptions)\b/,
      /\b(all|global|nationwide|market wide|circuit breaker|systemic|clearing house|exchanges worldwide)\b/,
    ],
  },
  {
    id: "systemic-insolvency", reason: "macro-warning", reach: "market", longOnly: false,
    says: "a systemic insolvency or currency collapse",
    all: [
      /\b(insolvency|insolvent|bankruptcy|bankrupt|defaults?|defaulted|collapse|collapsed|run on)\b/,
      /\b(clearing house|banking system|financial system|sovereign|currency|systemic|global bank)\b/,
    ],
  },
  {
    id: "geopolitical", reason: "macro-warning", reach: "market", longOnly: false,
    says: "a major geopolitical crisis",
    all: [/\b(declares? war|declared war|invasion|invades|invaded|missile strikes?|military strikes?|blockade|nuclear|martial law|coup|armed conflict)\b/],
  },
  {
    id: "crypto-failure", reason: "macro-warning", reach: "crypto", longOnly: false,
    says: "a failure at a major crypto venue or stablecoin",
    all: [
      /\b(stablecoin|crypto exchange|exchange|lender|protocol|bridge)\b/,
      /\b(insolvent|insolvency|bankrupt|bankruptcy|hacked|hack|exploit|exploited|drained|depeg|depegs|depegged|halts withdrawals|suspends withdrawals|withdrawals halted|withdrawals suspended)\b/,
    ],
  },
  {
    id: "auditor-resigns", reason: "sentiment-conflict", reach: "asset", longOnly: true,
    says: "the auditor resigned over reported accounting problems",
    all: [/\bauditors?\b/, /\b(resign|resigns|resigned|resigning|quits|steps down|withdraws)\b/],
  },
  {
    id: "fraud-finding", reason: "sentiment-conflict", reach: "asset", longOnly: true,
    says: "fraud or a restatement was reported",
    all: [
      /\b(accounting fraud|securities fraud|fraud|fraudulent|restatement|restates|misstated|falsified|embezzlement|ponzi)\b/,
      /\b(charged|charges|indicted|alleged|allegations|investigation|probe|subpoena|citing|admits|uncovered|discloses)\b/,
    ],
  },
  {
    id: "federal-enforcement", reason: "sentiment-conflict", reach: "asset", longOnly: true,
    says: "a federal enforcement action was reported",
    all: [
      /\b(sec|doj|ftc|cftc|justice department|prosecutors?|federal)\b/,
      /\b(investigation|investigating|probe|subpoena|subpoenas|charges|sues|lawsuit|raid|raided|indicts|indicted|enforcement)\b/,
    ],
  },
  {
    id: "going-concern", reason: "sentiment-conflict", reach: "asset", longOnly: true,
    says: "a delisting, going-concern warning or bankruptcy filing was reported",
    all: [/\b(delisted|delisting|going concern|files for bankruptcy|files for chapter 11|declares bankruptcy)\b/],
  },
];

/// Words that make a headline something other than a fact that has happened: a rumour, a denial, a
/// proposal, a reversal. Any of them anywhere in the headline withdraws it as a trigger.
const HEDGE =
  /\b(rumou?rs?|rumou?red|unconfirmed|speculat\w*|reportedly considering|may|might|could|would|considering|weighs?|mulls?|denies|denied|deny|no plans?|lifts?|lifted|lifting|ends?|ended|resum\w*|reopen\w*|reverses|reversed|overturn\w*|rejects?|rejected|averted|avoids?|eases|eased|fears?|warns?|warning|doomsday|imminent)\b/;

export function normalise(title: string): string {
  return sanitizeText(title, 400).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/// The asset class the headline-reach rules compare against. The stored `assetType` wins; a symbol is
/// only read when none is stored.
export function assetClassOf(symbol: string, assetType?: string | null): string {
  if (assetType) return assetType.toLowerCase();
  const s = symbol.toUpperCase();
  if (/(-USD|-USDT|USDT|USDC)$/.test(s)) return "crypto";
  if (s.endsWith("=X")) return "forex";
  if (s.endsWith("=F")) return "commodity";
  return "stock";
}

export type Trust = "trusted" | "uncertain" | "ignored" | "unproven";

export function trustOf(source: string, reliability: GateInput["reliability"]): { trust: Trust; mean: number | null } {
  const key = source.trim().toLowerCase();
  const row = reliability.find((r) => r.source.trim().toLowerCase() === key);
  if (!row || !(row.alpha > 0) || !(row.beta > 0)) return { trust: "unproven", mean: null };
  const mean = row.alpha / (row.alpha + row.beta);
  if (mean < IGNORED_BELOW) return { trust: "ignored", mean };
  if (mean >= TRUSTED_MEAN && row.alpha + row.beta >= MIN_EVIDENCE) return { trust: "trusted", mean };
  return { trust: "uncertain", mean };
}

/// The rule a headline trips for this asset, or null. Pure; trust is judged by the caller.
export function ruleFor(news: GateNews, input: GateInput): Rule | null {
  const text = normalise(news.title);
  if (!text || HEDGE.test(text)) return null;
  const cls = assetClassOf(input.symbol, input.assetClass);
  for (const rule of RULES) {
    if (rule.longOnly && input.direction !== "LONG") continue;
    if (rule.reach === "crypto" && cls !== "crypto") continue;
    // A sector headline is about other names in the sector; only the asset's own news can convict it.
    if (rule.reach === "asset" && news.scope === "sector") continue;
    if (rule.all.every((re) => re.test(text))) return rule;
  }
  return null;
}

function pass(rationale: string): GateResult {
  return { verdict: "EXECUTE", reason: null, rationale: sanitizeText(rationale, MAX_RATIONALE), valid: true, fallback: null };
}

/// Decide one asset. Never throws: anything unreadable is an EXECUTE.
export function evaluateLocal(input: GateInput, now: Date): GateResult {
  try {
    if (input.direction !== "LONG" && input.direction !== "SHORT") return pass("No direction to refuse.");
    // Every headline in the window, not the model's eight: the cap exists to bound a prompt and a bill,
    // and this engine has neither. With it, a real shock buried under eight newer routine headlines
    // would be invisible.
    const fresh = selectNews(input.news ?? [], now, MACRO_WINDOW_HOURS, SCAN_LIMIT);
    if (!fresh.length) return pass(`No headline in the last ${MACRO_WINDOW_HOURS} hours, so nothing to weigh.`);
    const hits: { rule: Rule; news: GateNews; mean: number }[] = [];
    for (const n of fresh) {
      const { trust, mean } = trustOf(String(n.source ?? ""), input.reliability ?? []);
      if (trust !== "trusted" || mean === null) continue;
      const rule = ruleFor(n, input);
      if (rule) hits.push({ rule, news: n, mean });
    }
    if (!hits.length) {
      return pass("No fresh headline from a trusted source reports a shock that bears on this asset.");
    }
    // A systemic warning outranks a company-level conflict; within a kind the newest headline wins,
    // which `selectNews` already guarantees by ordering.
    const best = hits.find((h) => h.rule.reason === "macro-warning") ?? hits[0];
    const said = sanitizeText(String(best.news.title), 140);
    return {
      verdict: "REJECT",
      reason: best.rule.reason,
      rationale: sanitizeText(
        `${sanitizeText(String(best.news.source), 40)} (credibility ${best.mean.toFixed(2)}) reported ${best.rule.says}: "${said}".`,
        MAX_RATIONALE,
      ),
      valid: true,
      fallback: null,
    };
  } catch {
    return { verdict: "EXECUTE", reason: null, rationale: "", valid: false, fallback: "the local rules could not read the input" };
  }
}
