import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ForecastChart } from "@/components/forecastChart";
import { forecastFor, type Forecast } from "@/lib/cryptoForecast";
import { HORIZONS, isHorizonKey, type HorizonKey } from "@/lib/cryptoHorizons";
import {
  coinPrice,
  coinSnapshot,
  compactUsd,
  REGISTRY_DEADLINE_MS,
  withDeadline,
} from "@/lib/cryptoMarket";
import { recordForecast, trackRecord } from "@/lib/forecastStore";
import { servingLane } from "@/lib/cryptoLanes";
import { STYLES, styleFrom } from "@/lib/tradingStyles";
import { universeCoin } from "@/lib/cryptoUniverse";
import { NewsCards } from "@/components/NewsCards";
import { LEVELS_CAVEATS, LEVELS_GENERATED_AT } from "@/lib/cryptoLevels";
import { tradeMath } from "@/lib/tradeMath";
import {
  breakEvenFeeBps,
  strategyFor,
  STRATEGY_COST_BPS,
  STRATEGY_GENERATED_AT,
} from "@/lib/cryptoStrategy";
import { getTopNews } from "@/lib/queries";
import { LiveCoinPrice } from "@/components/LiveCoinPrice";
import { BarClock } from "@/components/BarClock";

/// One coin: the price, the style you are trading it on, and the direction for that window.
///
/// **This is the page the old one was too slow to be.** `/asset/[symbol]` asks seventeen questions
/// of a free-tier pooler capped at two connections and takes seven to ten seconds whether or not a
/// window is chosen. Measured on the deployed site, almost none of that was the model. So the
/// crypto journey gets its own route that asks two questions before a window is picked and three
/// after -- the snapshot, the lane table (which is a bundled file, not a query) and the forecast.
///
/// `/asset/[symbol]` is untouched and still serves the other four markets and the full research
/// page for a coin; this is the fast path to the thing readers actually open a coin for.
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const snap = await coinSnapshot(decodeURIComponent(slug)).catch(() => null);
  return {
    title: snap ? `${snap.name} (${snap.ticker})` : "Coin",
    description: snap ? `${snap.name} price and a direction for the window you trade.` : undefined,
  };
}

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { slug: raw } = await params;
  const slug = decodeURIComponent(raw);
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

  const snap = await coinSnapshot(slug);
  if (!snap) notFound();

  const style = styleFrom(one(sp.style));
  const hParam = one(sp.h);
  const horizon: HorizonKey | null = isHorizonKey(hParam) ? hParam : null;

  // The forecast is the only expensive thing on this page, and it is only run when a window has
  // actually been asked for. A page that forecasts before being asked pays for a direction nobody
  // chose and makes the first load the slow one.
  // The forecast and the news go out together: both are independent of each other and of the
  // snapshot already in hand, and running them in series would add the slower one's time to the
  // faster one's for no reason.
  const [forecast, news, record] = await Promise.all([
    horizon ? forecastFor(slug, horizon) : Promise.resolve(null),
    // A venue-only coin has no asset row, so there is no stored news for it and nothing to ask.
    // Seven days. A fortnight-old headline beside a fifteen-minute direction is clutter
    // that buries the items a reader could actually act on.
    snap.assetId ? getTopNews(snap.assetId, 8, 7).catch(() => []) : Promise.resolve([]),
    // The only evidence on this page that is not a backtest. Asked for only once a window has
    // been chosen, because a record is per horizon and there is nothing to report before then.
    snap.assetId && horizon
      ? withDeadline(trackRecord(snap.assetId, horizon), REGISTRY_DEADLINE_MS, null)
      : Promise.resolve(null),
  ]);
  // Recorded only where there is an asset row to key it on. A venue-only coin's forecast is a
  // real forecast and it cannot enter the prospective record, so the page says so rather than
  // implying it will be graded later.
  let stored: { stored: boolean; why?: string } | null = null;
  if (forecast && forecast.kind === "direction") {
    stored = snap.assetId
      ? await recordForecast(snap.assetId, "Crypto", slug, forecast)
      : {
          stored: false,
          // Two different facts, and conflating them told a reader that Bitcoin is not a coin
          // this site covers, on a render where the database was merely busy.
          why:
            snap.registryRead === "unread"
              ? "the registry could not be read in time, so this forecast is not in the record"
              : "this coin is not in the registry, so there is no row to key it on",
        };
  }

  const u = universeCoin(slug);
  const logo = u?.paprikaId
    ? `https://static.coinpaprika.com/coin/${u.paprikaId}/logo.png`
    : null;
  const href = (q: Record<string, string>) =>
    `/crypto/${encodeURIComponent(slug)}?${new URLSearchParams(q).toString()}`;

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6">
      <div className="text-muted-foreground text-xs">
        <Link href="/crypto" className="hover:underline">
          Crypto
        </Link>{" "}
        / {snap.ticker}
      </div>

      {/* The price, first and large, because it is what the page is opened for. */}
      <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          {logo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logo} alt="" width={28} height={28} className="h-7 w-7 rounded-full" />
          ) : null}
          {snap.name} <span className="text-muted-foreground text-base">{snap.ticker}</span>
        </h1>
      </div>
      {/* The price keeps itself current in the browser and flashes on every tick, so a reader
          comparing it against the entry level below is comparing against now. */}
      <LiveCoinPrice
        slug={slug}
        initialPrice={snap.price}
        initialChange={snap.change24h}
        initialChangeAbs={snap.change24hAbs}
      />
      <p className="text-muted-foreground mt-1 text-xs">
        {snap.priceAt === "venue"
          ? "Live from the venue"
          : snap.priceAt === "close"
            ? `Last stored close${snap.closeDate ? ` ${snap.closeDate.toISOString().slice(0, 10)}` : ""} — the venue did not answer`
            : "No price available"}
        {snap.high24h !== null && snap.low24h !== null
          ? ` · 24h range ${coinPrice(snap.low24h)} – ${coinPrice(snap.high24h)}`
          : ""}
      </p>

      <div className="border-border mt-3 grid grid-cols-2 gap-4 rounded-lg border px-4 py-3 sm:grid-cols-3">
        <Stat label="Market cap" value={compactUsd(snap.marketCap)} />
        <Stat label="Volume (24h)" value={compactUsd(snap.volume24h)} />
        <Stat
          label="24h range"
          value={
            snap.high24h !== null && snap.low24h !== null
              ? `${coinPrice(snap.low24h)} – ${coinPrice(snap.high24h)}`
              : "—"
          }
        />
      </div>

      {/* How are you trading it. Style first, because that is how a reader arrives; the window is
          printed on every button, because the window is what the answer is about. */}
      <h2 className="mt-6 text-sm font-medium">How are you trading it?</h2>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {STYLES.map((s) => (
          <Link
            key={s.key}
            href={href({ style: s.key })}
            className={`rounded-lg border px-3 py-2.5 text-sm transition ${
              style?.key === s.key ? "border-primary bg-primary/5" : "border-border hover:bg-muted"
            }`}
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-muted-foreground mt-0.5 text-xs">{s.intent}</div>
          </Link>
        ))}
      </div>

      {style ? (
        <>
          <h2 className="mt-5 text-sm font-medium">Over which window?</h2>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {style.horizons.map((k) => {
              const lane = servingLane(slug, k);
              const state = !lane
                ? "not fitted"
                : !lane.servable
                  ? "tested, refused"
                  : `direction · ${lane.confidence.toLowerCase()}`;
              return (
                <Link
                  key={k}
                  href={href({ style: style.key, h: k })}
                  className={`rounded-lg border px-3 py-2.5 text-sm transition ${
                    horizon === k ? "border-primary bg-primary/5" : "border-border hover:bg-muted"
                  }`}
                >
                  <div className="font-medium">{HORIZONS[k].label}</div>
                  <div className="text-muted-foreground mt-0.5 text-xs">{state}</div>
                </Link>
              );
            })}
          </div>
        </>
      ) : null}

      {horizon && forecast ? (
        <div
          className="mt-5"
          data-forecast={forecast.kind}
          data-horizon={horizon}
          data-direction={forecast.kind === "direction" ? forecast.direction : undefined}
          data-margin={forecast.kind === "direction" ? forecast.margin.toFixed(4) : undefined}
          data-strength={
            forecast.kind === "direction" ? (forecast.strength ?? "unbanded") : undefined
          }
        >
          <Decision forecast={forecast} slug={slug} ticker={snap.ticker} stored={stored} />
          {record ? <LiveRecord record={record} label={HORIZONS[horizon].label} /> : null}
        </div>
      ) : style ? (
        <p className="text-muted-foreground mt-4 text-sm">Pick a window to get a direction.</p>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm">
          Pick how you are trading. Nothing is chosen for you — a direction over five minutes and a
          direction over a month are different claims.
        </p>
      )}

      <NewsCards
        items={news.map((n) => ({
          id: n.id,
          title: n.title,
          url: n.url,
          publisher: n.publisher,
          publishedAt: n.publishedAt,
          outlets: n.outlets,
          imageUrl: n.imageUrl ?? null,
        }))}
        name={snap.name}
        fallbackLogo={logo}
        ticker={snap.ticker}
      />

      {horizon ? (
        <details className="border-border mt-6 rounded-lg border px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium">
            What the levels are and are not
          </summary>
          <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-5 text-sm">
            {LEVELS_CAVEATS.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-xs">
            {LEVELS_GENERATED_AT
              ? `Distances measured ${LEVELS_GENERATED_AT.slice(0, 10)} on the training folds.`
              : "No distances have been measured in this build, so no levels are shown."}{" "}
            The stop and target are chosen by simulating every candidate pair bar by bar on the
            validation fold and serving the one with the best result after fees, then measuring
            that one once on the holdout — swept {STRATEGY_GENERATED_AT.slice(0, 10)}. Choosing
            on the holdout would be fitting the only fold kept back for measuring.
          </p>
        </details>
      ) : null}

      <p className="text-muted-foreground mt-6 text-xs">
        Research, not advice. Direction only: no transaction cost, spread or funding is in any
        number here.{" "}
        <Link href={`/asset/${encodeURIComponent(slug)}`} className="underline">
          Full research page for {snap.name}
        </Link>
      </p>
    </main>
  );
}

function Level({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note: string;
  tone?: "up" | "down";
}) {
  return (
    <div className="bg-background p-3">
      <div className="text-muted-foreground text-xs tracking-wide uppercase">{label}</div>
      <div
        className={`num mt-0.5 text-lg font-semibold ${
          tone === "up" ? "text-[var(--up)]" : tone === "down" ? "text-[var(--down)]" : ""
        }`}
      >
        {value}
      </div>
      <div className="text-muted-foreground mt-0.5 text-xs">{note}</div>
    </div>
  );
}

/// What this coin and window have actually done since forecasts started being recorded.
///
/// Kept strictly apart from every holdout number above it. The holdout is a backtest however
/// carefully it is split -- no forecast in it was made before its own data existed -- and this is
/// the only evidence on the page that was. It is also, for now, much smaller, so it says how
/// small rather than printing a rate over a handful: thirty graded results before a percentage
/// appears, which is the same bar the rest of the site holds itself to.
function LiveRecord({
  record,
  label,
}: {
  record: Awaited<ReturnType<typeof trackRecord>>;
  label: string;
}) {
  const { graded, correct, pending, awaitingScore, accuracy, quietGraded, quietCorrect, gradedUp } =
    record;
  if (graded + pending + awaitingScore + quietGraded === 0) return null;
  const allGraded = graded + quietGraded;
  const upRate = allGraded > 0 ? gradedUp / allGraded : null;
  // A base rate far from even means the graded window was a one-way market, and a balanced model
  // scores near 50% in one whatever it knows. Flagged rather than left for a reader to infer.
  const skewed = upRate !== null && Math.abs(upRate - 0.5) > 0.2;
  return (
    <div className="border-border mt-3 rounded-lg border px-4 py-3 text-sm">
      <span className="font-medium">Forward record, {label.toLowerCase()}.</span>{" "}
      <span className="text-muted-foreground">
        {graded >= 30 && accuracy !== null ? (
          <>
            {correct} of {graded} matured strong calls were right,{" "}
            <strong>{(accuracy * 100).toFixed(1)}%</strong>.
          </>
        ) : (
          <>
            {graded} matured so far{graded > 0 ? `, ${correct} right` : ""} — under the 30 this
            site needs before it prints a rate.
          </>
        )}{" "}
        {pending} still inside their window.
        {upRate !== null ? (
          <>
            {" "}
            Of those {allGraded} windows, {(upRate * 100).toFixed(0)}% actually went up
            {skewed ? (
              <strong>
                {" "}
                — so this was a one-way stretch, and a rate measured in one says more about the
                market than about the model
              </strong>
            ) : null}
            .
          </>
        ) : null}
        {quietGraded > 0 ? (
          <>
            {" "}
            Separately, {quietGraded} weak call{quietGraded === 1 ? "" : "s"} matured and{" "}
            {quietCorrect} went the way it leaned — never added to the rate above, because the two
            are different claims.
          </>
        ) : null}{" "}
        Every forecast is written down before its window closes and graded after, so this is the
        one number here that is not a backtest.
      </span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="num mt-0.5 text-sm font-semibold">{value}</div>
    </div>
  );
}

/// The answer. One verdict, the evidence under it in one line, and the bars it was read from.
function Decision({
  forecast: f,
  slug,
  ticker,
  stored,
}: {
  forecast: Forecast;
  slug: string;
  ticker: string;
  stored: { stored: boolean; why?: string } | null;
}) {
  const h = f.horizon;

  if (f.kind === "direction") {
    const w = f.window;
    const strong = f.strength === "strong";
    // A lane with no measured floor has no banding to report, so it carries its own
    // confidence grade instead of a word nothing measured.
    const banded = f.strength !== null;
    const c = f.lane.conviction;
    const lv = f.levels;
    const band = f.measured;
    // The win rate this call's own band actually achieved: the conviction band when the lane has
    // one and this call cleared it, else the coverage-curve band at today's margin, else the
    // lane's headline. Each is a measurement on the rows this call belongs to.
    const winRate =
      f.strength === "strong" && f.lane.conviction
        ? f.lane.conviction.called.accuracy
        : (band?.accuracy ?? f.lane.evidence.accuracy);
    const math = lv ? tradeMath(lv.entry, lv.stop, lv.target, winRate) : null;
    // What following this lane would actually have done, fee included. Without it the page shows
    // a win rate next to a stop and a target and lets a reader draw the only conclusion those
    // three things support -- which the measurement contradicts.
    const strat = strategyFor(f.lane.family, h.key);
    const beFee = strat ? breakEvenFeeBps(strat, STRATEGY_COST_BPS) : null;
    return (
      <>
        <div className="border-border rounded-lg border p-4">
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 text-xs tracking-wide uppercase">
            <span>{h.label}</span>
            {/* How long this call is current for. A verdict read from the last closed bar sits
                beside a price that ticks every two seconds, and without this a reader cannot tell
                which of the two they are looking at. */}
            <BarClock asOfMs={f.asOf.getTime()} stepMs={w.stepMs} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <span
              className={`text-5xl font-semibold tracking-tight ${
                f.direction === "UP" ? "text-[var(--up)]" : "text-[var(--down)]"
              }`}
            >
              {f.direction}
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                banded && strong
                  ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                  : "border border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
              }`}
            >
              {banded ? (strong ? "STRONG" : "WEAK") : f.confidence}
            </span>
            <span className="text-muted-foreground num text-sm">
              {(f.probUp * 100).toFixed(1)}% up · {(f.margin * 200).toFixed(1)} pts from even
            </span>
          </div>

          {/* The three numbers a direction is unusable without. */}
          {lv ? (
            <div className="border-border mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg border bg-border">
              <Level label="Entry" value={coinPrice(lv.entry)} note="the close it was read from" />
              <Level
                label="Stop"
                value={coinPrice(lv.stop)}
                note={`${lv.stopPct.toFixed(2)}% away`}
                tone={f.direction === "UP" ? "down" : "up"}
              />
              <Level
                label="Target"
                value={coinPrice(lv.target)}
                note={`${lv.targetPct.toFixed(2)}% away · ${lv.rr.toFixed(1)}R`}
                tone={f.direction === "UP" ? "up" : "down"}
              />
            </div>
          ) : null}

          <p className="text-muted-foreground mt-3 text-sm">
            {!banded
              ? `Right ${(f.lane.evidence.accuracy * 100).toFixed(1)}% of the time on ${f.lane.evidence.testRows.toLocaleString()} unseen rows, against ${(f.lane.evidence.testMajority * 100).toFixed(1)}% for naming one direction. This window has no strong/weak banding: its gated form did not beat the majority among the rows it would have spoken on, so every call here is reported the same way.`
              : strong
              ? c
                ? `Strong calls like this were right ${(c.called.accuracy * 100).toFixed(1)}% of the time on ${c.called.rows.toLocaleString()} unseen rows, against ${(c.called.majorityHere * 100).toFixed(1)}% for naming one direction. About ${(c.called.coverage * 100).toFixed(0)} bars in 100 are this strong.`
                : `Right ${(f.lane.evidence.accuracy * 100).toFixed(1)}% of the time on ${f.lane.evidence.testRows.toLocaleString()} unseen rows, against ${(f.lane.evidence.testMajority * 100).toFixed(1)}% for naming one direction.`
              : `This one is close to even. On the holdout, calls at least this confident were right ${band ? (band.accuracy * 100).toFixed(1) : (f.lane.evidence.accuracy * 100).toFixed(1)}% of the time${band ? ` (${band.rows.toLocaleString()} rows)` : ""}${c ? `, against ${(c.called.accuracy * 100).toFixed(1)}% for the strong band` : ""}. The direction is the model's; the thinness is too.`}
          </p>
          {/* The arithmetic that decides whether the edge survives the levels. A 64% win rate and
              an upside-down reward-to-risk lose money together, and the threshold is the only
              number that says so. */}
          {math ? (
            <div className="border-border mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
              <Level
                label="Needs to win"
                value={`${(math.breakEven * 100).toFixed(1)}%`}
                note={`to break even at ${math.rr.toFixed(1)}R`}
              />
              <Level
                label="Measured"
                value={`${(math.measured * 100).toFixed(1)}%`}
                note="on this band of the holdout"
                tone={math.edge > 0 ? "up" : "down"}
              />
              <Level
                label="Edge"
                value={`${math.edge >= 0 ? "+" : ""}${(math.edge * 100).toFixed(1)} pts`}
                note={math.edge > 0 ? "above break-even" : "below break-even"}
                tone={math.edge > 0 ? "up" : "down"}
              />
              <Level
                label="Size ceiling"
                value={`${(math.kelly * 100).toFixed(1)}%`}
                note="Kelly, capped at 25%"
              />
            </div>
          ) : null}
          {/* The measured result of following this lane, which the four tiles above cannot show:
              they are arithmetic on one call, and this is what every call did. */}
          {strat ? (
            <div
              className={`mt-3 rounded-lg border px-3 py-2.5 text-xs ${
                strat.test.netExpectancyR > 0
                  ? "border-emerald-500/40 bg-emerald-500/5"
                  : "border-amber-500/40 bg-amber-500/5"
              }`}
            >
              <strong>
                Followed mechanically on the holdout, this lane{" "}
                {strat.test.netExpectancyR > 0 ? "made" : "lost"}{" "}
                {Math.abs(strat.test.netExpectancyR).toFixed(4)}R per trade after fees.
              </strong>{" "}
              <span className="text-muted-foreground">
                {strat.test.trades.toLocaleString()} trades on rows the model never saw, entering
                at the close and charging {STRATEGY_COST_BPS} basis points a round trip: win rate{" "}
                {(strat.test.winRate * 100).toFixed(1)}% against{" "}
                {(strat.test.breakEvenWinRate * 100).toFixed(1)}% needed, profit factor{" "}
                {strat.test.profitFactor?.toFixed(3) ?? "—"}. Before the fee it was{" "}
                {strat.test.grossExpectancyR >= 0 ? "+" : ""}
                {strat.test.grossExpectancyR.toFixed(4)}R — the direction is real and the fee is{" "}
                {strat.test.meanCostInR.toFixed(3)}R of it.
                {beFee !== null ? (
                  <>
                    {" "}
                    It turns positive below a <strong>
                      {beFee.toFixed(1)} basis point
                    </strong>{" "}
                    round trip, which a maker order on a volume tier can reach and a retail taker
                    cannot.
                  </>
                ) : (
                  " Its edge is negative before fees too, so no fee makes it work."
                )}{" "}
                The accuracy above is unaffected by any of this; it is a different question, and
                this one had never been asked.
              </span>
            </div>
          ) : null}
          {math ? (
            <p className="text-muted-foreground mt-2 text-xs">
              Expectancy {math.expectancy >= 0 ? "+" : ""}
              {math.expectancy.toFixed(3)} per unit risked, before costs — and the costs are the
              point at this distance: the stop is {lv ? lv.stopPct.toFixed(2) : "—"}% away, and a
              taker fee plus spread on most venues is a meaningful fraction of that. Risking $100
              here is{" "}
              {lv
                ? (100 * math.unitsPerDollarRisked).toLocaleString("en-US", {
                    maximumFractionDigits:
                      100 * math.unitsPerDollarRisked >= 1000 ? 0 : 4,
                  })
                : "—"}{" "}
              units of {ticker}. The size ceiling is Kelly on a win rate estimated from a holdout, shown
              to make clear how small an honest position is — not as a recommendation.
            </p>
          ) : null}
          {lv ? (
            <p className="text-muted-foreground mt-2 text-xs">
              Stop and target are {lv.stopAtr}× and {lv.targetAtr}× the coin&apos;s own 14-bar
              range, picked for the best expected move over{" "}
              {lv.measuredRows.toLocaleString()} past windows. Of the ones that went this way,{" "}
              {(lv.targetFirstWhenRight * 100).toFixed(0)}% reached the target before the stop,{" "}
              {(lv.stoppedWhenRight * 100).toFixed(0)}% were stopped first, and{" "}
              {(lv.neitherWhenRight * 100).toFixed(0)}% closed the window with neither touched
              {lv.neitherWhenRight > 0.5 ? " — most of them, so treat the target as a direction to lean, not an event to expect" : ""}
              . A measurement of how far price travels, not a prediction: the model calls
              direction only.
            </p>
          ) : null}
        </div>

        <div className="mt-3">
          <ForecastChart
            bars={w.bars}
            stepMs={w.stepMs}
            reference={f.referencePrice}
            horizonMinutes={h.minutes}
            horizonLabel={h.label}
            direction={f.direction}
            symbol={slug}
          />
        </div>

        <p className="text-muted-foreground mt-2 text-xs">
          {f.lane.modelVersion} · {w.bars.length} {h.interval} bars from {w.venue}
          {w.quality === "ok" ? "" : ` · degraded: ${w.imputed.join(", ")} imputed`} ·{" "}
          {stored?.stored ? "recorded for grading" : `not recorded (${stored?.why ?? "unknown"})`}
        </p>
      </>
    );
  }

  const why = "why" in f ? f.why : "it could not be answered";
  const title =
    f.kind === "refused"
      ? "Tested, and refused"
      : f.kind === "no-model"
        ? "Not fitted yet"
        : f.kind === "no-source"
          ? "No intraday series"
          : f.kind === "data"
            ? "The bars are not there"
            : "Not served";
  return (
    <div className="border-border rounded-lg border p-4">
      <div className="text-xl font-semibold">{title}</div>
      <p className="text-muted-foreground mt-1 text-sm">{why}.</p>
    </div>
  );
}
