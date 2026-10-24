// What the rest of the market was doing at the instant this coin's bar closed.
//
// The serving half of `tools/research/market_context.py`. That file is **the** definition; this
// recomputes it on the request path, and `tests/marketContextParity.test.ts` feeds both the same
// bars and fails above 1e-9. Two implementations of one feature block is exactly how a model comes
// to be served inputs it was never trained on, and the parity fixture is what makes that a test
// failure rather than a silent accuracy loss -- the same arrangement `lib/intradayFeatures.ts` has
// with `intraday_features.py`, for the same reason.
//
// Point-in-time by construction. Bitcoin's bar at timestamp `t` closes at the same instant as the
// coin's bar at `t`, so reading it is not look-ahead -- but it trivially could be, and a context
// feature that peeked one bar forward would look like a brilliant model until it was served. The
// alignment is by exact timestamp and nothing is interpolated or carried forward: a coin bar with
// no factor bar at the same open has no context and the forecast is refused rather than imputed.
//
// For Bitcoin itself the factor series *is* its own series, so the residuals are exactly zero and
// the beta is exactly one. That is left as it is rather than special-cased: it is the truth about
// those rows, it is what the trainer saw, and a tree that learned "beta is exactly 1" learned
// "this is the factor coin", which is a real thing to know.

import type { Bar } from "@/lib/intradayFeatures";

/// Appended after the 41 f1 features, in this order. Mirrors `CONTEXT_FEATURES`.
export const CONTEXT_FEATURES = [
  "mktR1",
  "mktR12",
  "mktR48",
  "mktR288",
  "mktVol48",
  "mktPos288",
  "relR1",
  "relR12",
  "relR48",
  "beta48",
  "corr48",
] as const;

export const N_CONTEXT = CONTEXT_FEATURES.length;

/// Mirrors `market_context.VERSION`. Stamped on artifacts; a mismatch is a refusal.
export const CONTEXT_VERSION = "crypto-market-c1";

/// The rolling window the beta and correlation are fitted over, in bars.
const LINK_WINDOW = 48;
/// The longest lookback the block uses, so the factor window must reach back at least this far.
const CONTEXT_WARMUP = 288;

const EPS = 1e-12;

function logOf(x: number): number {
  return x > 0 ? Math.log(x) : Math.log(EPS);
}

/// Trailing mean of the last `n` values ending at `end` (inclusive).
function trailingMean(a: number[], end: number, n: number): number {
  let s = 0;
  for (let i = end - n + 1; i <= end; i++) s += a[i];
  return s / n;
}

/// `null` when the factor series cannot answer for this instant, which the caller refuses on.
///
/// `coinBars` and `mktBars` are both ascending by `ts`, one bar per interval. `i` is the index of
/// the coin's decision bar.
export function contextAt(coinBars: Bar[], i: number, mktBars: Bar[]): number[] | null {
  if (i < CONTEXT_WARMUP || i >= coinBars.length) return null;
  if (mktBars.length < CONTEXT_WARMUP + 1) return null;

  // Where the decision instant sits in the factor's series. Exact match only: a position whose
  // timestamp differs is a bar the factor does not have, and filling it from a neighbour would be
  // a claim about what the market did while nobody was trading it.
  const ts = coinBars[i].ts;
  const byTs = new Map<number, number>();
  for (let k = 0; k < mktBars.length; k++) byTs.set(mktBars[k].ts, k);
  const j = byTs.get(ts);
  if (j === undefined || j < CONTEXT_WARMUP) return null;

  const mLog = mktBars.map((b) => logOf(b.c));
  const cLog = coinBars.map((b) => logOf(b.c));

  const mRet = (k: number) => mLog[j] - mLog[j - k];
  const cRet = (k: number) => cLog[i] - cLog[i - k];

  // One-bar returns on both series, over the link window, aligned by timestamp.
  const mr1: number[] = [];
  const cr1: number[] = [];
  for (let k = 0; k < LINK_WINDOW; k++) {
    const ci = i - LINK_WINDOW + 1 + k;
    const mi = byTs.get(coinBars[ci].ts);
    // A hole anywhere inside the regression window makes the beta a statistic over two different
    // stretches of time. Refused, not patched.
    if (mi === undefined || mi < 1 || ci < 1) return null;
    mr1.push(mLog[mi] - mLog[mi - 1]);
    cr1.push(cLog[ci] - cLog[ci - 1]);
  }

  const n = LINK_WINDOW;
  const last = n - 1;
  const sx = trailingMean(mr1, last, n);
  const sy = trailingMean(cr1, last, n);
  const sxx = trailingMean(mr1.map((v) => v * v), last, n);
  const syy = trailingMean(cr1.map((v) => v * v), last, n);
  const sxy = trailingMean(mr1.map((v, k) => v * cr1[k]), last, n);
  const cov = sxy - sx * sy;
  const varX = Math.max(sxx - sx * sx, 0);
  const varY = Math.max(syy - sy * sy, 0);
  let beta = varX > EPS ? cov / varX : 0;
  const denom = Math.sqrt(varX * varY);
  let corr = denom > EPS ? cov / denom : 0;
  // A rolling beta on 48 five-minute bars is noisy and its tails are not information: one window
  // of near-zero factor variance would otherwise hand the tree a split on a beta of 400.
  beta = Math.min(5, Math.max(-5, beta));
  corr = Math.min(1, Math.max(-1, corr));

  // The factor's own volatility and range position, on the factor's index.
  const fr: number[] = [];
  for (let k = j - 47; k <= j; k++) fr.push(mLog[k] - mLog[k - 1]);
  const fm = fr.reduce((a, b) => a + b, 0) / fr.length;
  const fvar = fr.reduce((a, b) => a + (b - fm) * (b - fm), 0) / fr.length;
  const mktVol48 = Math.sqrt(Math.max(fvar, 0));

  let hi = -Infinity;
  let lo = Infinity;
  for (let k = j - 287; k <= j; k++) {
    if (mktBars[k].h > hi) hi = mktBars[k].h;
    if (mktBars[k].l < lo) lo = mktBars[k].l;
  }
  const rng = hi - lo;
  const mktPos288 = rng > EPS ? (mktBars[j].c - lo) / rng : 0.5;

  return [
    mRet(1),
    mRet(12),
    mRet(48),
    mRet(288),
    mktVol48,
    mktPos288,
    cRet(1) - mRet(1),
    cRet(12) - mRet(12),
    cRet(48) - mRet(48),
    beta,
    corr,
  ];
}
