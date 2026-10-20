// Fresh bars for a forecast: fetched, validated, gap-filled from a second venue, or refused.
//
// The gate this implements is the one the serving path needs and the daily pipeline does not. A
// 20-session call reads a stored close and a stale one is caught by a date comparison. A
// five-minute call reads the last twenty-four hours of bars, and every way that window can be
// wrong -- a short series, a bar still open, a venue outage in the middle, a duplicate from a
// paging seam, a price the exchange later corrected -- produces a *plausible* forecast rather
// than an error. So each is checked by name, and a window that fails is refused with the reason
// rather than served with a shrug.
//
// Refusal is not the preferred outcome and the fallbacks exist so that it is rare: a gap inside
// the window is patched from a second exchange where one can supply the missing minutes, and the
// patch is counted and reported rather than blended in silently. What is never done is inventing
// a bar -- a forward-filled five minutes is a five minutes in which the market did not move,
// which is a claim, not a gap.

import { WARMUP, type Bar } from "@/lib/intradayFeatures";

export type Interval = "5m" | "4h";

const STEP_MS: Record<Interval, number> = { "5m": 300_000, "4h": 14_400_000 };

/// How old the newest closed bar may be before the window is refused as stale, in intervals.
///
/// Three at five minutes (fifteen minutes) and two at four hours. Both are deliberately tight:
/// the point of a short-horizon forecast is that it is about the next few minutes, and one built
/// on an hour-old book is about a market that has moved on.
const MAX_STALE_INTERVALS: Record<Interval, number> = { "5m": 3, "4h": 2 };

/// How many bars are needed: the feature warm-up plus the decision bar.
export const NEEDED = WARMUP + 1;

export interface WindowChecks {
  fetched: number;
  openBarsDropped: number;
  rejected: Record<string, number>;
  duplicates: number;
  conflictingDuplicates: number;
  gapsFound: number;
  barsPatched: number;
}

export interface BarWindow {
  bars: Bar[];
  stepMs: number;
  interval: Interval;
  venue: string;
  patchedFrom: string | null;
  fetchedAt: string;
  /// The close time of the newest bar -- the instant the forecast is made from.
  asOfMs: number;
  ageMs: number;
  referencePrice: number;
  /// `ok` when every feature input was observed; `degraded` when one was imputed, with the names.
  quality: "ok" | "degraded";
  imputed: string[];
  checks: WindowChecks;
}

export type BarResult =
  | { ok: true; window: BarWindow }
  | { ok: false; why: string; tried: { venue: string; outcome: string }[] };

interface Venue {
  name: string;
  /// Null when this venue cannot serve this instrument or this interval at all.
  url: (instrument: string, interval: Interval, limit: number) => string | null;
  parse: (payload: unknown, interval: Interval) => RawBar[];
  /// Feature inputs this venue does not publish, imputed to a neutral value when it is used.
  imputes: string[];
}

/// A bar before the maturity and structure checks: `closeMs` is what decides whether it is closed.
interface RawBar extends Bar {
  closeMs: number;
}

function num(x: unknown): number {
  const v = typeof x === "string" ? Number(x) : (x as number);
  return typeof v === "number" ? v : NaN;
}

const BINANCE: Venue = {
  name: "Binance",
  url: (sym, interval, limit) =>
    `https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(sym)}` +
    `&interval=${interval === "5m" ? "5m" : "4h"}&limit=${Math.min(limit, 1000)}`,
  parse: (payload) => {
    if (!Array.isArray(payload)) return [];
    return payload.map((k) => {
      const a = k as unknown[];
      return {
        ts: num(a[0]),
        o: num(a[1]),
        h: num(a[2]),
        l: num(a[3]),
        c: num(a[4]),
        v: num(a[5]),
        closeMs: num(a[6]),
        n: num(a[8]),
        tb: num(a[9]),
      };
    });
  },
  imputes: [],
};

const COINBASE: Venue = {
  name: "Coinbase Exchange",
  // 300 candles a request and no 4-hour granularity, so it backs the 5-minute series only. A
  // venue that cannot serve an interval says so here rather than returning a shorter window that
  // would fail the length check further down with a less useful reason.
  url: (product, interval) =>
    interval === "5m"
      ? `https://api.exchange.coinbase.com/products/${encodeURIComponent(product)}/candles?granularity=300`
      : null,
  parse: (payload) => {
    if (!Array.isArray(payload)) return [];
    // [ time, low, high, open, close, volume ], newest first.
    return payload
      .map((r) => {
        const a = r as unknown[];
        const ts = num(a[0]) * 1000;
        const v = num(a[5]);
        return {
          ts,
          o: num(a[3]),
          h: num(a[2]),
          l: num(a[1]),
          c: num(a[4]),
          v,
          closeMs: ts + 300_000,
          // Coinbase publishes neither a trade count nor taker-side volume. Both are imputed to
          // the neutral value the training-fold mean stands for -- balanced flow, no trade-size
          // signal -- and named in `imputed`, so a forecast built on them is marked degraded
          // rather than presented as one read from full inputs.
          n: 0,
          tb: v / 2,
        };
      })
      .reverse();
  },
  imputes: ["tbi1", "tbi12", "tbi48", "tsz48"],
};

const KRAKEN: Venue = {
  name: "Kraken",
  url: (pair, interval) =>
    `https://api.kraken.com/0/public/OHLC?pair=${encodeURIComponent(pair)}` +
    `&interval=${interval === "5m" ? 5 : 240}`,
  parse: (payload, interval) => {
    const body = payload as { result?: Record<string, unknown> } | null;
    const result = body?.result;
    if (!result) return [];
    const key = Object.keys(result).find((k) => k !== "last");
    const rows = key ? (result[key] as unknown[]) : [];
    if (!Array.isArray(rows)) return [];
    const step = STEP_MS[interval];
    return rows.map((r) => {
      const a = r as unknown[];
      const ts = num(a[0]) * 1000;
      const v = num(a[6]);
      return {
        ts,
        o: num(a[1]),
        h: num(a[2]),
        l: num(a[3]),
        c: num(a[4]),
        v,
        closeMs: ts + step,
        n: num(a[7]),
        // Kraken publishes a trade count but not taker-side volume.
        tb: v / 2,
      };
    });
  },
  imputes: ["tbi1", "tbi12", "tbi48"],
};

export interface Instruments {
  binance: string | null;
  coinbase: string | null;
  kraken: string | null;
}

/// The venue order for an instrument: depth first, then whatever can fill a hole.
function chainFor(inst: Instruments): { venue: Venue; instrument: string }[] {
  const out: { venue: Venue; instrument: string }[] = [];
  if (inst.binance) out.push({ venue: BINANCE, instrument: inst.binance });
  if (inst.kraken) out.push({ venue: KRAKEN, instrument: inst.kraken });
  if (inst.coinbase) out.push({ venue: COINBASE, instrument: inst.coinbase });
  return out;
}

async function getJson(url: string, timeoutMs = 6_000): Promise<unknown> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      signal: ctl.signal,
      headers: { "User-Agent": "nextbigthing/1.0 (+https://nextbigthing-nu.vercel.app)" },
      cache: "no-store",
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

/// Structural validation. Every rejection is counted by reason; nothing is dropped silently.
function clean(raw: RawBar[], interval: Interval, nowMs: number):
  { bars: Bar[]; checks: Omit<WindowChecks, "gapsFound" | "barsPatched"> } {
  const step = STEP_MS[interval];
  const rejected: Record<string, number> = {};
  const bump = (k: string) => {
    rejected[k] = (rejected[k] ?? 0) + 1;
  };
  const seen = new Map<number, Bar>();
  let open = 0;
  let duplicates = 0;
  let conflicting = 0;

  for (const b of raw) {
    if (![b.ts, b.o, b.h, b.l, b.c, b.v, b.closeMs].every(Number.isFinite)) {
      bump("unparseable");
      continue;
    }
    // A bar whose close time has not passed is a partial observation of a window still running.
    if (b.closeMs > nowMs) {
      open += 1;
      continue;
    }
    if (Math.min(b.o, b.h, b.l, b.c) <= 0) {
      bump("non-positive price");
      continue;
    }
    if (b.v < 0) {
      bump("negative volume");
      continue;
    }
    if (b.h < Math.max(b.o, b.c) || b.l > Math.min(b.o, b.c) || b.h < b.l) {
      bump("inconsistent OHLC");
      continue;
    }
    if (b.ts % step !== 0) {
      bump("off-grid open time");
      continue;
    }
    const prev = seen.get(b.ts);
    if (prev) {
      duplicates += 1;
      if (Math.abs(prev.c - b.c) > 1e-9 || Math.abs(prev.v - b.v) > 1e-9) conflicting += 1;
      continue;
    }
    seen.set(b.ts, {
      ts: b.ts,
      o: b.o,
      h: b.h,
      l: b.l,
      c: b.c,
      v: b.v,
      n: Number.isFinite(b.n) ? b.n : 0,
      tb: Number.isFinite(b.tb) ? b.tb : b.v / 2,
    });
  }
  const bars = [...seen.values()].sort((a, b) => a.ts - b.ts);
  return {
    bars,
    checks: {
      fetched: raw.length,
      openBarsDropped: open,
      rejected,
      duplicates,
      conflictingDuplicates: conflicting,
    },
  };
}

/// Which timestamps are missing from the last `NEEDED` bars of a series.
function holes(bars: Bar[], step: number): number[] {
  if (bars.length === 0) return [];
  const last = bars[bars.length - 1].ts;
  const first = last - (NEEDED - 1) * step;
  const have = new Set(bars.map((b) => b.ts));
  const out: number[] = [];
  for (let t = first; t <= last; t += step) if (!have.has(t)) out.push(t);
  return out;
}

/// Fresh, validated bars for one instrument, or a refusal naming every venue that was asked.
///
/// The window returned is exactly the last `NEEDED` bars, contiguous, all closed. A caller does
/// not have to re-check any of that; a caller that is handed `ok: false` has a sentence it can
/// print.
export async function windowFor(
  inst: Instruments,
  interval: Interval,
  nowMs: number = Date.now(),
): Promise<BarResult> {
  const step = STEP_MS[interval];
  const chain = chainFor(inst);
  const tried: { venue: string; outcome: string }[] = [];
  if (chain.length === 0) {
    return { ok: false, why: "no venue serves this coin's intraday series", tried };
  }

  for (let i = 0; i < chain.length; i++) {
    const { venue, instrument } = chain[i];
    const url = venue.url(instrument, interval, NEEDED + 80);
    if (!url) {
      tried.push({ venue: venue.name, outcome: `does not serve ${interval} bars` });
      continue;
    }
    let raw: RawBar[];
    try {
      raw = venue.parse(await getJson(url), interval);
    } catch (e) {
      tried.push({ venue: venue.name, outcome: e instanceof Error ? e.message : "unreachable" });
      continue;
    }
    const { bars, checks } = clean(raw, interval, nowMs);
    if (bars.length === 0) {
      tried.push({ venue: venue.name, outcome: "answered with no usable bar" });
      continue;
    }
    const newest = bars[bars.length - 1];
    const asOfMs = newest.ts + step;
    const ageMs = nowMs - asOfMs;
    if (ageMs > MAX_STALE_INTERVALS[interval] * step) {
      tried.push({
        venue: venue.name,
        outcome: `newest closed bar is ${Math.round(ageMs / 60_000)} minutes old, over the ` +
          `${(MAX_STALE_INTERVALS[interval] * step) / 60_000}-minute limit`,
      });
      continue;
    }

    let missing = holes(bars, step);
    let patchedFrom: string | null = null;
    let patched = 0;
    const imputed = new Set(venue.imputes);

    // One hole-filling pass from the next venue down. A second pass is not attempted: a window
    // that two exchanges together cannot complete is a window to refuse, not one to keep patching.
    if (missing.length > 0 && i + 1 < chain.length) {
      const alt = chain[i + 1];
      const altUrl = alt.venue.url(alt.instrument, interval, NEEDED + 80);
      if (altUrl) {
        try {
          const altRaw = alt.venue.parse(await getJson(altUrl), interval);
          const altClean = clean(altRaw, interval, nowMs);
          const byTs = new Map(altClean.bars.map((b) => [b.ts, b]));
          for (const t of missing) {
            const b = byTs.get(t);
            if (b) {
              bars.push(b);
              patched += 1;
            }
          }
          if (patched > 0) {
            bars.sort((a, b) => a.ts - b.ts);
            patchedFrom = alt.venue.name;
            for (const f of alt.venue.imputes) imputed.add(f);
          }
        } catch {
          // The patch is best effort. A failed patch leaves the hole, which the length and
          // contiguity checks below then refuse with the gap's own reason.
        }
      }
      missing = holes(bars, step);
    }

    if (missing.length > 0) {
      tried.push({
        venue: venue.name,
        outcome: `${missing.length} missing bar${missing.length === 1 ? "" : "s"} inside the ` +
          `${NEEDED}-bar window and no venue could supply them`,
      });
      continue;
    }

    const windowBars = bars.slice(bars.length - NEEDED);
    if (windowBars.length < NEEDED) {
      tried.push({
        venue: venue.name,
        outcome: `only ${bars.length} bars, ${NEEDED} needed for the feature window`,
      });
      continue;
    }

    return {
      ok: true,
      window: {
        bars: windowBars,
        stepMs: step,
        interval,
        venue: venue.name,
        patchedFrom,
        fetchedAt: new Date(nowMs).toISOString(),
        asOfMs,
        ageMs,
        referencePrice: newest.c,
        quality: imputed.size === 0 ? "ok" : "degraded",
        imputed: [...imputed],
        checks: { ...checks, gapsFound: 0, barsPatched: patched },
      },
    };
  }

  return {
    ok: false,
    why: "no venue served a complete, fresh window",
    tried,
  };
}
