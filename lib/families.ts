import {
  ANALOGS_CONFIRM_MIN,
  ANALOG_SHARE_CONFIRMS,
  VOLUME_CONFIRMS_AT,
  type Action,
  type Confidence,
  type Market,
  type WaitBasis,
  REL_BAND,
} from "./decision.ts";

/// The evidence families, their votes, and the arithmetic that turns them into a verdict.
///
/// **This is `BRAIN-SPEC-V1.md` §3 as corrected by `BRAIN-LOGIC-CLOSURE-2026-10-16.md` §B4-B5.**
/// Where the two disagree the closure wins, because it was written against the shipped code and the
/// specification was not: V1.1 §3.2 promotes macro to a voting family F5, and the closure records
/// that as "a regression from shipped behaviour" -- `lib/decision.ts` has always had macro as a veto
/// only, *"it can turn a LONG or SHORT into a WAIT and can do nothing else"*.
///
/// **What votes, and why that list.** E1 trend, E2 participation, E3 volatility, E4 cross-sectional
/// and E5 history. All five are asset-specific and derived from the instrument's own price, volume
/// or peer group, which is the governing rule: **only asset-specific evidence may cast a directional
/// vote.** Macro (E7) and news/events (E8) are context and cannot vote, and that is what stops one
/// monetary announcement becoming two confirmations -- structurally, with no event-id matching to
/// get wrong. E6 `entryTrigger` is not a family at all: it answers *when*, not *which way*.
///
/// **What is deliberately not resolved.** E1, E3 and E5 all re-read one price series, and the
/// closure records that openly rather than claiming five independent witnesses. E4 is the one family
/// that removes the common factor by construction. A `NET` of 5 is therefore not five independent
/// facts, and nothing here pretends otherwise -- which is why `support` is published as named
/// families rather than as a number (see `Aggregate.supporting`).
///
/// **Thresholds are imported, never restated.** `VOLUME_CONFIRMS_AT`, `ANALOGS_CONFIRM_MIN`,
/// `ANALOG_SHARE_CONFIRMS` and `relBandFor` come from `lib/decision.ts` so the family path and the
/// shipped path cannot hold different opinions about when volume confirms or when matched days
/// agree. That divergence has happened here before: this module once asked for an analog share of
/// `> 0.5` while `jobs/setup.py` required 0.55, and the looser number was the one grading confidence
/// on the page.
///
/// **Nothing here is published yet.** `decide()` still decides what the site shows. This path is
/// computed, recorded and evaluated under its own `LOGIC_VERSION`, because §9 gate 5 requires a
/// candidate to beat both references out-of-sample before acceptance and gate 7 makes deployment a
/// separate decision. Switching the published contract would also redefine `confidence` in place,
/// which §B5 forbids: historical `DecisionLog` rows must keep their meaning.

/// The version this logic ships under. Any change to a family rule, a threshold or the arithmetic
/// takes a new value, so `tools/scorecard.py` never averages two semantics.
export const LOGIC_VERSION = "families-v1.2";

export type FamilyId = "E1" | "E2" | "E3" | "E4" | "E5";

/// The name each family is recorded under. These are the words `DecisionLog.legs` already uses, so
/// a family and a leg of the same name mean the same measurement.
export const FAMILY_NAME: Record<FamilyId, string> = {
  E1: "trend",
  E2: "volume",
  E3: "volatility",
  E4: "peers",
  E5: "history",
};

export const FAMILIES: FamilyId[] = ["E1", "E2", "E3", "E4", "E5"];

/// §D2, frozen. Not to be tuned against an evaluation result; changing either needs a specification
/// amendment and a recorded reason.
export const MIN_FAMILIES = 3;
export const MIN_NET = 2;

/// §3.3 deadband. A [PROPOSED] design default chosen before any evaluation, not an empirical finding.
export const TAU = 0.5;

/// §3.3 F3 bounds, likewise proposed defaults.
export const DRAWDOWN_CONSTRUCTIVE = -5;
export const DRAWDOWN_STRESS = -15;
export const ATR_STRESS_MULTIPLE = 1.5;
/// The midpoint of `rangePct`, which is a *position* in the trailing range and not a width. The
/// constructive arm wants the upper half; see `e3` for the measurement that settled that.
export const RANGE_MIDPOINT = 50;

/// §3.2/§B4 eligibility floor for the peer family.
export const PEERS_MIN = 3;

export type Vote = -1 | 0 | 1;

export interface FamilyReading {
  id: FamilyId;
  name: string;
  /// Eligible means the file could be read for this family (§3.2). An eligible family that comes out
  /// even still counts toward `MIN_FAMILIES` and contributes 0 -- that is an *evidence* fact. An
  /// ineligible one counts toward nothing -- that is a *file* fact. The two are never merged.
  eligible: boolean;
  /// Why it could not be read. Null when it could. Never a reason to read a vote as 0.
  ineligibleBecause: string | null;
  score: number | null;
  vote: Vote;
  /// What the family actually measured, for the audit record.
  detail: string;
}

/// Everything the families read, and nothing else.
///
/// Narrow on purpose: a family rule that can reach the whole `DecisionInput` is a family rule that
/// can quietly start reading news. `fromDecisionInput` is the only adapter.
export interface FamilyInput {
  market: Market;
  r20: number | null;
  sma20: number | null;
  sma50: number | null;
  volumeRatio: number | null;
  r1: number | null;
  atr14: number | null;
  /// Trailing median of `atr14`, for the stress clause of F3. **Not stored anywhere today**, so it
  /// arrives null and that clause is reported as unmeasured rather than as not-stressed (I1).
  atrTrailingMedian?: number | null;
  rangePct: number | null;
  drawdownPct: number | null;
  relStrength: number | null;
  peers: number;
  analogs: { count: number; positive: number | null } | null;
  /// Stage-0 integrity findings, by family. A family named here is withheld before any voting.
  integrityVeto?: Partial<Record<FamilyId, string>>;
}

function voteOf(score: number): Vote {
  if (score >= TAU) return 1;
  if (score <= -TAU) return -1;
  return 0;
}

function sign(n: number): number {
  return n > 0 ? 1 : n < 0 ? -1 : 0;
}

/// **E1 trend.** `a = sign(r20)`, `b = +1 if sma20 > sma50 else -1 if sma20 < sma50 else 0`,
/// `s = (a + b) / 2`. Two numbers describing one fact -- where the move went and where the averages
/// sit -- which is why `r5`, `r20`, `sma20` and `sma50` are one family and vote once.
function e1(i: FamilyInput): FamilyReading {
  const base = { id: "E1" as const, name: FAMILY_NAME.E1 };
  if (i.r20 === null && (i.sma20 === null || i.sma50 === null)) {
    return { ...base, eligible: false, ineligibleBecause: "no 20-session return and no moving averages", score: null, vote: 0, detail: "" };
  }
  const a = i.r20 === null ? 0 : sign(i.r20);
  const b = i.sma20 === null || i.sma50 === null ? 0 : sign(i.sma20 - i.sma50);
  const s = (a + b) / 2;
  return {
    ...base, eligible: true, ineligibleBecause: null, score: s, vote: voteOf(s),
    detail: `r20 ${i.r20 === null ? "absent" : i.r20.toFixed(2) + "%"}, averages ${b > 0 ? "fast above slow" : b < 0 ? "fast below slow" : "level or absent"}`,
  };
}

/// **E2 participation.** Volume confirms the direction of the move it accompanied, and only above
/// `VOLUME_CONFIRMS_AT`. Where the venue publishes no volume -- every FX pair -- the family is
/// **ineligible, never 0**: "we did not look" is not "volume was flat" (I1, and the stored-null rule
/// that keeps FX volume out of the averages).
function e2(i: FamilyInput): FamilyReading {
  const base = { id: "E2" as const, name: FAMILY_NAME.E2 };
  if (i.volumeRatio === null) {
    return { ...base, eligible: false, ineligibleBecause: "no volume published for this venue", score: null, vote: 0, detail: "" };
  }
  if (i.r1 === null) {
    return { ...base, eligible: false, ineligibleBecause: "no session return to attribute the volume to", score: null, vote: 0, detail: "" };
  }
  const s = i.volumeRatio >= VOLUME_CONFIRMS_AT ? sign(i.r1) : 0;
  return {
    ...base, eligible: true, ineligibleBecause: null, score: s, vote: voteOf(s),
    detail: `volume ${i.volumeRatio.toFixed(2)}x average on a ${i.r1 >= 0 ? "rising" : "falling"} session`,
  };
}

/// **E3 volatility & range.**
///
/// `-1` when `drawdownPct <= -15` **or** `atr14` exceeds its trailing median by >= 50% (stress);
/// `+1` when `drawdownPct > -5` **and** `rangePct` is in its **upper** half (constructive); else `0`.
///
/// **A corrected unit, measured before it was corrected.** §3.3 writes the constructive arm as
/// "`drawdownPct > -5` and `rangePct` is in its lower half". `AssetFactor.rangePct` is *"position in
/// the trailing range, 0 at the low and 100 at the high"*, and `drawdownPct` is distance below the
/// trailing high -- so "within 5% of the high" and "in the lower half of the range" cannot both hold,
/// and the arm is unreachable as written. That is not a threshold to argue about: measured over the
/// 21,753 usable rows of the only assembly available, the `+1` arm fired **0 times** while the `-1`
/// arm fired 8,734, which made E3 a family that could only ever vote against. The whole table ran
/// 5,019 SHORT against 1,184 LONG on that reading.
///
/// The specification was written against an assumed meaning of `rangePct` -- range *width*, where a
/// narrow range is calm -- that the stored column contradicts. This is the same class of defect as
/// `BRAIN-LOGIC-CLOSURE-2026-10-16.md` §B1, where the proposed contract compared `atr14` in price
/// units against a percentage, and it is corrected the same way: to the documented unit, with the
/// measurement that forced it recorded, under a new `LOGIC_VERSION`. The direction of the fix is the
/// stated intent -- "constructive" -- read in the column's real units: little drawdown and the close
/// in the upper part of its own range.
///
/// The `atr14` stress clause needs a trailing median that nothing stores. It is therefore reported
/// as unmeasured and cannot contribute -- it is never read as "not stressed".
function e3(i: FamilyInput): FamilyReading {
  const base = { id: "E3" as const, name: FAMILY_NAME.E3 };
  const haveAtrStress = i.atr14 !== null && (i.atrTrailingMedian ?? null) !== null;
  if (i.drawdownPct === null && i.rangePct === null && !haveAtrStress) {
    return { ...base, eligible: false, ineligibleBecause: "no drawdown, range position or volatility baseline", score: null, vote: 0, detail: "" };
  }
  const stressed =
    (i.drawdownPct !== null && i.drawdownPct <= DRAWDOWN_STRESS) ||
    (haveAtrStress && (i.atr14 as number) >= (i.atrTrailingMedian as number) * ATR_STRESS_MULTIPLE);
  const constructive =
    i.drawdownPct !== null && i.drawdownPct > DRAWDOWN_CONSTRUCTIVE &&
    i.rangePct !== null && i.rangePct >= RANGE_MIDPOINT;
  const s = stressed ? -1 : constructive ? 1 : 0;
  const parts = [
    i.drawdownPct === null ? "drawdown absent" : `drawdown ${i.drawdownPct.toFixed(1)}%`,
    i.rangePct === null ? "range position absent" : `range position ${i.rangePct.toFixed(0)}`,
    haveAtrStress ? "volatility against its median" : "volatility baseline not stored",
  ];
  return { ...base, eligible: true, ineligibleBecause: null, score: s, vote: voteOf(s), detail: parts.join(", ") };
}

/// **E4 cross-sectional.** `sign(relStrength)` once the gap clears its market's band, and only with
/// at least `PEERS_MIN` peers behind the median. The one family that removes the common factor by
/// construction: a name up 4% in an industry up 10% is a laggard, and its own return cannot say so.
function e4(i: FamilyInput): FamilyReading {
  const base = { id: "E4" as const, name: FAMILY_NAME.E4 };
  if (i.peers < PEERS_MIN) {
    return { ...base, eligible: false, ineligibleBecause: `only ${i.peers} peers, below the floor of ${PEERS_MIN}`, score: null, vote: 0, detail: "" };
  }
  if (i.relStrength === null) {
    return { ...base, eligible: false, ineligibleBecause: "peer group too small to take a median over", score: null, vote: 0, detail: "" };
  }
  // The same table `relBandFor` reads, so the family path and the shipped path cannot drift apart.
  const band = REL_BAND[i.market];
  const s = Math.abs(i.relStrength) >= band ? sign(i.relStrength) : 0;
  return {
    ...base, eligible: true, ineligibleBecause: null, score: s, vote: voteOf(s),
    detail: `${i.relStrength >= 0 ? "+" : ""}${i.relStrength.toFixed(1)}pp against ${i.peers} peers, band ${band}`,
  };
}

/// **E5 history.** The share of matched past days that went one way, once there are at least
/// `ANALOGS_CONFIRM_MIN` of them and the share clears `ANALOG_SHARE_CONFIRMS` either side.
///
/// It votes, which was the one open question in the approval register (§B7 item 3) and is recorded
/// there with "Votes" as the recommended default. The reason it is contestable is in this module's
/// own header: it re-reads the observations E1 and E3 already read. It votes with that recorded
/// rather than counted as an independent witness.
function e5(i: FamilyInput): FamilyReading {
  const base = { id: "E5" as const, name: FAMILY_NAME.E5 };
  const a = i.analogs;
  if (!a || a.count < ANALOGS_CONFIRM_MIN) {
    return { ...base, eligible: false, ineligibleBecause: `${a?.count ?? 0} matched days, below the floor of ${ANALOGS_CONFIRM_MIN}`, score: null, vote: 0, detail: "" };
  }
  if (a.positive === null || a.positive === undefined) {
    return { ...base, eligible: false, ineligibleBecause: "matched days carry no direction count", score: null, vote: 0, detail: "" };
  }
  const share = a.positive / a.count;
  const s = share >= ANALOG_SHARE_CONFIRMS ? 1 : share <= 1 - ANALOG_SHARE_CONFIRMS ? -1 : 0;
  return {
    ...base, eligible: true, ineligibleBecause: null, score: s, vote: voteOf(s),
    detail: `${a.positive} of ${a.count} matched days rose (${(share * 100).toFixed(0)}%)`,
  };
}

export function readFamilies(i: FamilyInput): FamilyReading[] {
  const veto = i.integrityVeto ?? {};
  return [e1(i), e2(i), e3(i), e4(i), e5(i)].map((r) =>
    // Stage 0: an integrity finding withholds the inputs, which makes the family ineligible. It can
    // never produce a vote, and never a vote of 0 that would read as "measured and even".
    veto[r.id] ? { ...r, eligible: false, ineligibleBecause: veto[r.id] as string, score: null, vote: 0 as Vote, detail: "" } : r,
  );
}

export interface Aggregate {
  readings: FamilyReading[];
  /// Eligible families, **including those voting 0**: this is the count `MIN_FAMILIES` is held
  /// against, and it is a statement about how much of the file is readable.
  eligible: number;
  net: number;
  /// Named, not counted -- a count cannot say *which* family earned its place, and without the names
  /// a capped grade and an uncapped one are indistinguishable in the log afterwards.
  supporting: string[];
  opposing: string[];
  /// Eligible, counted toward `MIN_FAMILIES`, and contributed nothing. An *evidence* fact.
  abstaining: string[];
  /// Not readable at all. A *file* fact, and never a vote.
  ineligible: string[];
  dissent: number;
  action: Action;
  basis: WaitBasis | null;
  gate: string;
  confidence: Confidence;
  logicVersion: string;
}

/// §B5. `NET` by subtraction, the two gates in order, then the grade with its published cap.
///
/// Gate order matters and is the point of example C: an FX pair with two agreeing families reaches
/// `NET = +2`, which would clear `MIN_NET` -- and is still `WAIT` with basis `file`, because too
/// little of the file was readable. **A coverage failure is never reported as weak evidence.**
export function aggregate(readings: FamilyReading[]): Aggregate {
  const eligible = readings.filter((r) => r.eligible);
  const net = eligible.reduce((sum, r) => sum + r.vote, 0);
  const d = sign(net);
  const supporting = eligible.filter((r) => d !== 0 && r.vote === d).map((r) => r.name);
  const opposing = eligible.filter((r) => d !== 0 && r.vote === -d).map((r) => r.name);
  const abstaining = eligible.filter((r) => r.vote === 0).map((r) => r.name);
  const ineligible = readings.filter((r) => !r.eligible).map((r) => r.name);
  const longVotes = eligible.filter((r) => r.vote === 1).length;
  const shortVotes = eligible.filter((r) => r.vote === -1).length;
  const dissent = Math.min(longVotes, shortVotes);

  const base = {
    readings, eligible: eligible.length, net, supporting, opposing, abstaining, ineligible, dissent,
    logicVersion: LOGIC_VERSION,
  };

  // GATE 1 -- how much of the file is readable.
  if (eligible.length < MIN_FAMILIES) {
    return { ...base, supporting: [], opposing: [], action: "WAIT", basis: "file", gate: "file", confidence: "Low" };
  }
  // GATE 2 -- how decisive the readable evidence is. A tie lands here.
  if (Math.abs(net) < MIN_NET) {
    return { ...base, action: "WAIT", basis: "evidence", gate: "thin-evidence", confidence: "Low" };
  }
  // GATES 3 and 4.
  const action: Action = net >= MIN_NET ? "LONG" : "SHORT";
  // `NET >= 2` forces `support >= 2`, so High means at least three families agree and none disagrees.
  let confidence: Confidence = supporting.length >= 3 ? "High" : "Medium";
  if (opposing.length >= 1) confidence = confidence === "High" ? "Medium" : "Low";
  return { ...base, action, basis: null, gate: action === "LONG" ? "long" : "short", confidence };
}

/// The families as a sentence, for the audit record.
export function explain(a: Aggregate): string {
  const parts = [`${a.eligible} of ${FAMILIES.length} families readable`, `NET ${a.net >= 0 ? "+" : ""}${a.net}`];
  if (a.supporting.length) parts.push(`for: ${a.supporting.join(", ")}`);
  if (a.opposing.length) parts.push(`against: ${a.opposing.join(", ")}`);
  if (a.abstaining.length) parts.push(`even: ${a.abstaining.join(", ")}`);
  if (a.ineligible.length) parts.push(`unreadable: ${a.ineligible.join(", ")}`);
  return parts.join(" · ");
}
