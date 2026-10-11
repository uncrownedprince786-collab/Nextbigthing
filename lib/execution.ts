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
