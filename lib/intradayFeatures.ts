// The serving half of the short-horizon feature set. The definition lives in
// `tools/research/intraday_features.py`; this is its mirror, and `tests/intradayParity.test.ts`
// feeds both the same bars from a fixture the trainer writes and fails on any component that
// differs by more than 1e-9.
//
// Two implementations of one feature set is normally a mistake. It is unavoidable here: the model
// is fitted in Python over four hundred thousand bars and served from a Node request handler that
// has no Python, and the alternative -- a Python service on the serving path -- is a second
// deployment for one matrix multiply. So the duplication is kept and *tested*, rather than kept
// and trusted. A feature that drifts between the two is the failure this file's test exists to
// turn from an invisible accuracy loss into a red build.
//
// Every function below is a transliteration, deliberately literal rather than idiomatic: the
// windows, the denominators and the order of operations match the Python line for line, because
// a tidier formulation that is algebraically equal can still differ in float, and the fixture
// compares numbers.

/// One closed bar. `tb` is taker-buy base volume (the kline's own field), `n` the trade count.
export interface Bar {
  ts: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  n: number;
  tb: number;
}

/// Bumped with any change to the list below. Checked against the artifact's `featureSchema`
/// before a model is used, so a model trained on one feature set can never be fed another.
export const FEATURE_VERSION = "crypto-intraday-f1";

/// The longest lookback any feature uses. A forecast needs this many bars before the decision bar.
export const WARMUP = 288;

const EPS = 1e-12;

export const FEATURES = [
  "r1", "r3", "r6", "r12", "r24", "r48", "r96", "r288",
  "vol12", "vol48", "vol288",
  "rz12", "rz48",
  "pos12", "pos48", "pos288",
  "ema12d", "ema48d", "ema288d",
  "atr14", "atrRatio",
  "rsi14",
  "vol_r48", "vol_r288",
  "tbi1", "tbi12", "tbi48",
  "tsz48",
  "body", "upWick", "dnWick", "body12",
  "persist6", "persist24",
  "skew48",
  "d24hHigh", "d24hLow",
  "todSin", "todCos", "dowSin", "dowCos",
] as const;

function logRatio(a: number, b: number): number {
  if (a <= 0 || b <= 0) return 0;
  return Math.log(a / b);
}

/// Sample standard deviation (n - 1), matching `intraday_features._std`.
function std(xs: number[]): number {
  const n = xs.length;
  if (n < 2) return 0;
  let m = 0;
  for (const x of xs) m += x;
  m /= n;
  let s = 0;
  for (const x of xs) s += (x - m) * (x - m);
  return Math.sqrt(s / (n - 1));
}

/// EMA seeded on the window's first close, so the value depends only on the window handed in.
/// Carrying it across the whole series would make it unreproducible from a serving window.
function ema(closes: number[], span: number): number {
  const k = 2 / (span + 1);
  let e = closes[0];
  for (let i = 1; i < closes.length; i++) e = closes[i] * k + e * (1 - k);
  return e;
}

/// Wilder's RSI as a 0..1 fraction over the last `period` close-to-close changes.
function rsi(closes: number[], period = 14): number {
  let gains = 0;
  let losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gains += d;
    else losses -= d;
  }
  if (gains + losses <= EPS) return 0.5;
  return gains / (gains + losses);
}

/// True when the `back + 1` bars ending at `i` are consecutive at `stepMs`.
///
/// A feature window spanning a venue outage mixes two different markets into one 24-hour range,
/// so a forecast over a gap is refused rather than served. The trainer drops the same rows, by the
/// same test, so neither side can treat a window the other would reject.
export function contiguous(bars: Bar[], i: number, stepMs: number, back = WARMUP): boolean {
  if (i < back) return false;
  return bars[i].ts - bars[i - back].ts === back * stepMs;
}

/// The feature vector readable at the close of `bars[i]`, or null when the window is short.
///
/// Reads `bars[i - WARMUP .. i]` and nothing after `i`. There is no forward reference anywhere in
/// this function, which is what makes a forecast built from it a forecast rather than a reading
/// of the answer.
export function featuresAt(bars: Bar[], i: number): number[] | null {
  if (i < WARMUP || i >= bars.length) return null;
  const w = bars.slice(i - WARMUP, i + 1);
  const closes = w.map((b) => b.c);
  const highs = w.map((b) => b.h);
  const lows = w.map((b) => b.l);
  const opens = w.map((b) => b.o);
  const vols = w.map((b) => b.v);
  const tbs = w.map((b) => (Number.isFinite(b.tb) ? b.tb : b.v / 2));
  const trades = w.map((b) => Math.max(b.n || 0, 0));
  const c = closes[closes.length - 1];
  const L = w.length;

  const rets: number[] = [];
  for (let j = 1; j < closes.length; j++) rets.push(logRatio(closes[j], closes[j - 1]));

  const ret = (n: number) => logRatio(c, closes[closes.length - 1 - n]);
  const tail = (xs: number[], n: number) => xs.slice(xs.length - n);

  const vol12 = std(tail(rets, 12));
  const vol48 = std(tail(rets, 48));
  const vol288 = std(rets);

  const pos = (n: number) => {
    const hi = Math.max(...tail(highs, n));
    const lo = Math.min(...tail(lows, n));
    return hi - lo > EPS ? (c - lo) / (hi - lo) : 0.5;
  };

  const trAt = (j: number) =>
    Math.max(highs[j] - lows[j], Math.abs(highs[j] - closes[j - 1]), Math.abs(lows[j] - closes[j - 1]));

  let atrSum = 0;
  for (let j = L - 14; j < L; j++) atrSum += trAt(j);
  const atr14 = atrSum / 14;
  let atr288Sum = 0;
  for (let j = 1; j < L; j++) atr288Sum += trAt(j);
  const atr288 = atr288Sum / (L - 1);

  const volRatio = (n: number) => {
    let m = 0;
    for (const v of tail(vols, n)) m += v;
    m /= n;
    return Math.log((vols[L - 1] + EPS) / (m + EPS));
  };

  const tbi = (n: number) => {
    let v = 0;
    let t = 0;
    for (const x of tail(vols, n)) v += x;
    for (const x of tail(tbs, n)) t += x;
    return v > EPS ? (2 * t) / v - 1 : 0;
  };

  const sizes = w.map((_, j) => (trades[j] > 0 ? vols[j] / trades[j] : 0));
  let msize = 0;
  for (const s of tail(sizes, 48)) msize += s;
  msize /= 48;
  const tsz48 = Math.log((sizes[L - 1] + EPS) / (msize + EPS));

  const shape = (j: number): [number, number, number] => {
    const rng = highs[j] - lows[j];
    if (rng <= EPS) return [0, 0, 0];
    return [
      (closes[j] - opens[j]) / rng,
      (highs[j] - Math.max(opens[j], closes[j])) / rng,
      (Math.min(opens[j], closes[j]) - lows[j]) / rng,
    ];
  };
  const [body, upWick, dnWick] = shape(L - 1);
  let body12 = 0;
  for (let j = L - 12; j < L; j++) body12 += shape(j)[0];
  body12 /= 12;

  const persist = (n: number) => {
    let s = 0;
    for (const r of tail(rets, n)) s += r > 0 ? 1 : r < 0 ? -1 : 0;
    return s / n;
  };

  const skew = (n: number) => {
    const xs = tail(rets, n);
    let m = 0;
    for (const x of xs) m += x;
    m /= n;
    const sd = std(xs);
    if (sd <= EPS) return 0;
    let s = 0;
    for (const x of xs) s += ((x - m) / sd) ** 3;
    return s / n;
  };

  const hi24 = Math.max(...tail(highs, 288));
  const lo24 = Math.min(...tail(lows, 288));

  // The decision instant is the bar's *close*, which is its open plus one interval. The interval
  // is read off the series rather than assumed, so a 4-hour corpus is not given 5-minute angles.
  const step = w[L - 1].ts - w[L - 2].ts;
  const closeMs = w[L - 1].ts + step;
  const minuteOfDay = Math.floor(closeMs / 60000) % 1440;
  const dow = ((Math.floor(closeMs / 86400000) + 4) % 7 + 7) % 7;
  const tod = (2 * Math.PI * minuteOfDay) / 1440;
  const dw = (2 * Math.PI * dow) / 7;

  return [
    ret(1), ret(3), ret(6), ret(12), ret(24), ret(48), ret(96), ret(288),
    vol12, vol48, vol288,
    ret(12) / (vol12 * Math.sqrt(12) + EPS),
    ret(48) / (vol48 * Math.sqrt(48) + EPS),
    pos(12), pos(48), pos(288),
    (c - ema(tail(closes, 12), 12)) / c,
    (c - ema(tail(closes, 48), 48)) / c,
    (c - ema(closes, 288)) / c,
    atr14 / c,
    atr14 / (atr288 + EPS),
    rsi(closes, 14),
    volRatio(48), volRatio(288),
    tbi(1), tbi(12), tbi(48),
    tsz48,
    body, upWick, dnWick, body12,
    persist(6), persist(24),
    skew(48),
    logRatio(hi24, c), logRatio(c, lo24),
    Math.sin(tod), Math.cos(tod), Math.sin(dw), Math.cos(dw),
  ];
}
