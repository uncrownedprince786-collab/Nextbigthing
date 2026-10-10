import { cachedDecisionRows, cachedSourceHealth } from "@/lib/cached";
import { scoreRows } from "@/lib/assetClass";
import { todayISO } from "@/lib/decisionInput";
import { validityOf } from "@/lib/validity";
import { MIN_CONFIRMATIONS, MIN_REWARD_RISK, MIN_STOP_ATR } from "@/lib/quality";

/// The published calls as data: the same rows, by the same functions, as the market pages.
///
/// Read-only and built from the cached list the pages use, so it costs no extra database read and can
/// never disagree with a page rendered from the same cache. Every published call carries everything the
/// quality gate requires (lib/quality.ts) -- direction, trading style, entry range, stop, measured target,
/// reward:risk and the confirmations behind it -- and an open call says it is held open. The withheld
/// calls are listed with the rule each failed and nothing else. `tools/logic_audit.py` compares this
/// against the rendered pages.
///
/// Styles: the engine decides from completed daily closes (brain.md rules 41 and 81), so every call is
/// SWING (1-7 days) or POSITION (1-4 weeks). It publishes no SCALPING or INTRADAY call, and says so here
/// rather than labelling a daily call as one.
export async function GET() {
  try {
    const today = todayISO();
    const [rows, health] = await Promise.all([cachedDecisionRows(), cachedSourceHealth()]);
    const scored = scoreRows(rows, health, today);
    const published = scored
      .filter((s) => s.gate?.published && (s.decision.action === "LONG" || s.decision.action === "SHORT"))
      .map((s) => {
        const v = validityOf({
          action: s.decision.action,
          setupHorizon: s.setupHorizon,
          runAction: s.row.callAction,
          runSince: s.row.callSince,
          asOf: s.row.closeDate,
          today,
        });
        return {
          symbol: s.row.symbol,
          name: s.row.name,
          market: s.market,
          direction: s.decision.action,
          style: s.style,
          entry: s.decision.entry,
          stop: s.decision.invalidation,
          target: s.target ? { low: s.target.low, high: s.target.high, method: s.target.method } : null,
          rewardRisk: s.target?.rewardRisk ?? null,
          confirmations: s.decision.legs,
          confidence: s.decision.confidence,
          validFrom: v?.from ?? null,
          validUntil: v?.until ?? null,
          open: s.gate?.held ? { since: s.gate.held.since, todays: s.gate.held.todays } : null,
        };
      });
    const withheld = scored
      .filter((s) => !s.gate?.published && s.decision.action !== "WAIT")
      .map((s) => ({ symbol: s.row.symbol, reasons: s.gate?.reasons ?? [] }));
    return Response.json(
      {
        asOf: today,
        rules: { minRewardRisk: MIN_REWARD_RISK, minStopAtr: MIN_STOP_ATR, minConfirmations: MIN_CONFIRMATIONS, measuredTargetOnly: true },
        styles: { SWING: "1-7 days", POSITION: "1-4 weeks", SCALPING: "not produced", INTRADAY: "not produced" },
        counts: { published: published.length, open: published.filter((p) => p.open).length, withheld: withheld.length },
        published,
        withheld,
      },
      { status: 200, headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=60" } },
    );
  } catch {
    return Response.json({ error: "the calls could not be read" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
