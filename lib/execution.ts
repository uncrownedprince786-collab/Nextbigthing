/// Whether a published direction can be acted on, kept apart from whether it is right (brain.md rule 93).
///
/// Direction, confidence, data quality and execution readiness are four different questions, and a
/// panel that printed "SHORT · NOW" answered the fourth without asking it. The site stores no bid or ask,
/// no short-sale eligibility for any market, and no exchange compliance status, so the most it can say
/// from what it holds is this:
///
///   * **blocked** -- the last session printed no trade at all (volume 0 on a market that publishes
///     volume): nothing traded at the price the levels are measured from;
///   * **unverified** -- a SHORT on a share or a coin (the site holds no short-sale eligibility data: PSX
///     allows it only in designated securities, a US borrow is not public data, and a coin needs margin or
///     a derivative), or a market that publishes no volume, where liquidity cannot be measured at all. A
///     currency pair or a future is sold as easily as it is bought, so its SHORT carries no eligibility
///     question;
///   * **checked** -- a LONG whose last session traded, in a pool whose names already clear a turnover
///     floor (jobs/pool.py). Bid and ask are still not stored, and the reason says so.
///
/// Only a checked call may be shown as "NOW". The others keep their direction and say why execution is
/// not confirmed. A WAIT has no execution question and returns null.
export interface Execution {
  status: "checked" | "unverified" | "blocked";
  reasons: string[];
}

export function executionOf(o: {
  action: string;
  /// "US", "PSX", "Crypto", "FX", "Commodity" or "Other". Short-sale eligibility is a question only for
  /// shares and coins.
  market?: string | null;
  /// The volume printed on the session the decision read; null when the market publishes none.
  closeVolume: number | null | undefined;
}): Execution | null {
  if (o.action !== "LONG" && o.action !== "SHORT") return null;
  const volume = o.closeVolume;
  if (volume !== null && volume !== undefined && Number.isFinite(volume) && volume <= 0) {
    return { status: "blocked", reasons: ["no trade was printed on the last session"] };
  }
  const reasons: string[] = [];
  if (o.action === "SHORT" && o.market !== "FX" && o.market !== "Commodity") {
    reasons.push("the site holds no short-sale eligibility data for this security");
  }
  if (volume === null || volume === undefined || !Number.isFinite(volume)) {
    reasons.push("this market publishes no volume, so liquidity cannot be measured");
  }
  if (reasons.length) return { status: "unverified", reasons };
  return {
    status: "checked",
    reasons: ["traded on the last session, inside a pool that clears a turnover floor; no bid or ask is stored"],
  };
}

/// The timing a call is shown with, and the price it was read from (rule 94). The rule table's "NOW"
/// means the decision's close sits inside the inclusive entry zone; that is a fact about price and is
/// never hidden. When execution is not checked it is shown as "IN ZONE" instead of "NOW" -- the price is in
/// the zone, the trade is not confirmed executable -- and never as "WAIT FOR LEVEL", which would say the
/// price is outside the zone when it is not (CHBL, 2026-10-11: close Rs.8.82 in Rs.8.80-9.17, printed as
/// "not in the zone yet"). Null on a WAIT.
export interface Timing {
  label: "NOW" | "IN ZONE" | "WAIT FOR LEVEL" | "CARE";
  /// The close the timing rule read, and its session day.
  price: number | null;
  on: string | null;
  inZone: boolean | null;
}

export function timingOf(o: {
  action: string;
  timeSense: string;
  entry: { low: number; high: number } | null;
  close: number | null;
  closeDate: Date | string | null;
  execution: Execution | null;
}): Timing | null {
  if (o.action !== "LONG" && o.action !== "SHORT") return null;
  const day = o.closeDate
    ? (o.closeDate instanceof Date ? o.closeDate.toISOString() : String(o.closeDate)).slice(0, 10)
    : null;
  const inZone =
    o.close !== null && Number.isFinite(o.close) && o.entry ? o.close >= o.entry.low && o.close <= o.entry.high : null;
  const label: Timing["label"] =
    o.timeSense === "CARE"
      ? "CARE"
      : o.timeSense === "NOW"
        ? o.execution && o.execution.status !== "checked"
          ? "IN ZONE"
          : "NOW"
        : "WAIT FOR LEVEL";
  return { label, price: o.close, on: day, inZone };
}
