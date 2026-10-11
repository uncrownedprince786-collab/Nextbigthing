import { cachedDecisionRows, cachedSourceHealth } from "@/lib/cached";
import { ASSET_CLASSES, marketStatus, marketStatusLines, scoreRows, toSignal } from "@/lib/assetClass";
import { coverageLabelFor } from "@/lib/decisionInput";
import { outcomeStatusOf } from "@/lib/outcome";
import { todayISO } from "@/lib/decisionInput";
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
      // One record per call, by the function the cross-surface test holds every list to (lib/assetClass.ts).
      .map((s) => toSignal(s, today));
    const withheld = scored
      .filter((s) => !s.gate?.published && s.decision.action !== "WAIT")
      .map((s) => ({ symbol: s.row.symbol, reasons: s.gate?.reasons ?? [] }));
    // Every market's own state, by the function its page prints (rule 93): newest close, newest run,
    // source status, and where every name went.
    const markets = ASSET_CLASSES.map((cls) => {
      const mine = scored.filter(cls.holds);
      const status = marketStatus(mine, scored, health, mine[0] ? coverageLabelFor(mine[0].market) : null);
      return { market: cls.slug, ...status, summary: marketStatusLines(status).join(" ") };
    });
    const latestRun = markets.reduce<string | null>((m, x) => (x.latestRun && (!m || x.latestRun > m) ? x.latestRun : m), null);
    return Response.json(
      {
        asOf: today,
        rules: { minRewardRisk: MIN_REWARD_RISK, minStopAtr: MIN_STOP_ATR, minConfirmations: MIN_CONFIRMATIONS, measuredExitOnly: true, confidenceIs: "evidence grade" },
        styles: { SWING: "1-7 days", POSITION: "1-4 weeks", SCALPING: "not produced", INTRADAY: "not produced" },
        // The snapshot these figures come from: the newest decision run and the pool size the pages share.
        snapshot: { latestRun, pool: scored.length },
        // Whether the calls have been right in matured results -- a separate question from each call's
        // `confidence`, which is its evidence grade (lib/outcome.ts).
        outcome: outcomeStatusOf(rows[0]?.outcome ?? null),
        counts: {
          published: published.length,
          open: published.filter((p) => p.open).length,
          withheld: withheld.length,
          heldBack: scored.filter((s) => s.decision.action === "WAIT").length,
        },
        markets,
        published,
        withheld,
      },
      // No edge cache: the data cache is the cache, revalidated with the pages (rule 93), so the API can
      // never be a minute behind the pages it is audited against.
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json({ error: "the calls could not be read" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
