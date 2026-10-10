/// The "rising star" marker: a name caught at the start of a move, by an event measured to be worth
/// catching.
///
/// **What fires it.** The two entry events `jobs/factors.py` stores for every asset every day, and
/// nothing else:
///   * `squeeze_break` -- the expansion bar out of the quietest stretch in six months (a volatility
///     squeeze releasing);
///   * `vol_flip` -- five-session momentum turning on a busy session (a volume spike with a turn).
/// brain.md rule 54 backtested four "early" rules on identical terms against the moving-average trend
/// the engine otherwise enters on. These two paid more (0.153R and 0.146R against 0.128R, long side)
/// and fire at the very start of a move -- and the rule's own conclusion was that their honest use is
/// "a marker on the card saying this one was caught at the start". This is that marker.
///
/// **What does not fire it, and why.** Price/RSI or MACD divergence is not computed anywhere here and
/// has never been tested; the same research found another "earlier" rule (`inflection`) that paid
/// *less* than the trend, so earliness alone is not a reason. And a news "sentiment spike" cannot,
/// because news may only ever withdraw confidence (rule 44); a headline promoting a name is the
/// pump-and-dump the macro gate exists to refuse.
///
/// **What the marker says.** Which event, which way, and whether it agrees with the call beside it --
/// never an instruction. A rising star on a name the rule table still holds back says so: the event
/// is real, the plan is not taken, and the reason is printed on the row.

export type EarlyRule = "squeeze_break" | "vol_flip";

export interface EarlySignal {
  rule: EarlyRule;
  direction: "up" | "down";
  /// "Rising star" for an upward event, "Falling star" for a downward one.
  label: string;
  /// The event in words.
  words: string;
  /// How it sits with the call beside it.
  stance: "with" | "against" | "held";
  /// The full sentence for a tooltip or the asset page.
  explain: string;
}

const WORDS: Record<EarlyRule, string> = {
  squeeze_break: "a break out of its quietest stretch in six months",
  vol_flip: "momentum turning on a high-volume session",
};

/// The stored pair read into a marker, or null. Checked, not cast: both columns are free text in
/// Postgres, and an unrecognised rule or direction is no marker rather than a guessed one.
export function earlySignalOf(
  rule: string | null | undefined,
  direction: string | null | undefined,
  action: string,
): EarlySignal | null {
  if (rule !== "squeeze_break" && rule !== "vol_flip") return null;
  if (direction !== "up" && direction !== "down") return null;
  const stance: EarlySignal["stance"] =
    action === "WAIT" ? "held" : (action === "LONG") === (direction === "up") ? "with" : "against";
  const label = direction === "up" ? "Rising star" : "Falling star";
  const words = WORDS[rule];
  const sits =
    stance === "with"
      ? "It agrees with this call."
      : stance === "against"
        ? "It points the other way from this call."
        : "The rule table still holds this name back; the reason is printed beside it.";
  return {
    rule,
    direction,
    label,
    words,
    stance,
    explain:
      `Early signal: ${words} this session, ${direction === "up" ? "upward" : "downward"}. ` +
      `One of the two entry events that measured better than the trend alone in past data. ${sits} ` +
      `A marker, not an instruction.`,
  };
}
