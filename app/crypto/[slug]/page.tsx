import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ForecastChart } from "@/components/forecastChart";
import { forecastFor, type Forecast } from "@/lib/cryptoForecast";
import { HORIZONS, isHorizonKey, type HorizonKey } from "@/lib/cryptoHorizons";
import { coinPrice, coinSnapshot, compactUsd, signedPct } from "@/lib/cryptoMarket";
import { recordForecast } from "@/lib/forecastStore";
import { servingLane } from "@/lib/cryptoLanes";
import { STYLES, styleFrom } from "@/lib/tradingStyles";

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
  const forecast: Forecast | null = horizon ? await forecastFor(slug, horizon) : null;
  let stored: { stored: boolean; why?: string } | null = null;
  if (forecast && (forecast.kind === "direction" || forecast.kind === "quiet")) {
    stored = await recordForecast(snap.assetId, "Crypto", slug, forecast);
  }

  const up = (snap.change24h ?? 0) >= 0;
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
        <h1 className="text-2xl font-semibold">
          {snap.name} <span className="text-muted-foreground text-base">{snap.ticker}</span>
        </h1>
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
        <span className="num text-4xl font-semibold tracking-tight">{coinPrice(snap.price)}</span>
        {snap.change24h !== null ? (
          <span
            className={`num text-lg font-medium ${up ? "text-[var(--up)]" : "text-[var(--down)]"}`}
          >
            {snap.change24hAbs !== null ? `${up ? "+" : ""}${coinPrice(snap.change24hAbs).replace("$", "")} ` : ""}
            ({signedPct(snap.change24h)})
          </span>
        ) : null}
      </div>
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
          data-margin={forecast.kind === "quiet" ? forecast.margin.toFixed(4) : undefined}
          data-floor={forecast.kind === "quiet" ? forecast.floor.toFixed(3) : undefined}
        >
          <Decision forecast={forecast} slug={slug} stored={stored} />
        </div>
      ) : style ? (
        <p className="text-muted-foreground mt-4 text-sm">Pick a window to get a direction.</p>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm">
          Pick how you are trading. Nothing is chosen for you — a direction over five minutes and a
          direction over a month are different claims.
        </p>
      )}

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
  stored,
}: {
  forecast: Forecast;
  slug: string;
  stored: { stored: boolean; why?: string } | null;
}) {
  const h = f.horizon;

  if (f.kind === "direction" || f.kind === "quiet") {
    const w = f.window;
    const called = f.kind === "direction";
    const c = f.lane.conviction;
    return (
      <>
        <div className="border-border rounded-lg border p-4">
          <div className="text-muted-foreground text-xs tracking-wide uppercase">
            {h.label}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            {called ? (
              <span
                className={`text-5xl font-semibold tracking-tight ${
                  f.direction === "UP" ? "text-[var(--up)]" : "text-[var(--down)]"
                }`}
              >
                {f.direction}
              </span>
            ) : (
              <span className="text-muted-foreground text-3xl font-semibold tracking-tight">
                No clear pattern
              </span>
            )}
            {called ? (
              <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
                {f.confidence}
              </span>
            ) : null}
          </div>
          <p className="text-muted-foreground mt-2 text-sm">
            {called ? (
              <>
                {c
                  ? `Calls like this one were right ${(c.called.accuracy * 100).toFixed(1)}% of the time on ${c.called.rows.toLocaleString()} unseen rows, against ${(c.called.majorityHere * 100).toFixed(1)}% for naming one direction. The model speaks on about ${(c.called.coverage * 100).toFixed(0)} bars in 100.`
                  : `Right ${(f.lane.evidence.accuracy * 100).toFixed(1)}% of the time on ${f.lane.evidence.testRows.toLocaleString()} unseen rows, against ${(f.lane.evidence.testMajority * 100).toFixed(1)}% for naming one direction.`}
              </>
            ) : (
              <>
                The model put this window {(f.margin * 200).toFixed(1)} points from an even call,
                inside its {(f.floor * 200).toFixed(0)}-point floor.
                {c
                  ? ` When it does speak it is right ${(c.called.accuracy * 100).toFixed(1)}% of the time, on about ${(c.called.coverage * 100).toFixed(0)} bars in 100.`
                  : ""}{" "}
                Try another window, or the same one after the next bar.
              </>
            )}
          </p>
        </div>

        <div className="mt-3">
          <ForecastChart
            bars={w.bars}
            stepMs={w.stepMs}
            reference={f.referencePrice}
            horizonMinutes={h.minutes}
            horizonLabel={h.label}
            direction={called ? f.direction : null}
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
