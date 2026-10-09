"""Does a tighter stop actually pay, or does it only flatter the ratio? Read-only.

Reward against risk is a ratio. Narrowing the denominator raises it mechanically and also
raises the chance the stop is taken out by noise before the target is reached, so the ratio on
its own cannot answer whether a change is an improvement. Expectancy can.

Population: the state the panel calls NOW. An upward bias (20 day mean above the 50 day) with
the close within ENTRY_BAND of the 20-session high, so price is at the level the setup asks for.
Entry is filled at that close. The short side is the mirror and is measured separately.

Outcome: the next FORWARD sessions of stored closes, first touch wins, measured in units of the
risk taken. A trade that reaches neither is marked to market at the end.
"""
import sys, statistics
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

FAST, SLOW, FORWARD = 20, 50, 20
ENTRY_BAND = 0.02          # close within 2% of the window extreme counts as "at the entry"
TARGET_SIGMAS = 2.0        # the volatility target horizons.py writes, in the same units
STOPS = [("current (window extreme)", None), ("0.75 sigma", 0.75), ("1.0 sigma", 1.0),
         ("1.5 sigma", 1.5), ("2.0 sigma", 2.0), ("2.5 sigma", 2.5), ("3.0 sigma", 3.0)]

def stdev(xs):
    if len(xs) < 3: return None
    m = sum(xs)/len(xs)
    return (sum((x-m)**2 for x in xs)/len(xs))**0.5

conn = nbt.db(); cur = conn.cursor()
cur.execute('SELECT id FROM "Asset" ORDER BY symbol')
assets = [a["id"] for a in cur.fetchall()]
res = {}   # (side, stop label) -> list of (R outcome, rr_at_target, stopped)

for i in range(0, len(assets), 25):
    cur.execute('SELECT "assetId", date, close FROM "PriceSnapshot" '
                'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC',
                (assets[i:i+25],))
    series = {}
    for r in cur.fetchall(): series.setdefault(r["assetId"], []).append(float(r["close"]))
    for closes in series.values():
        if len(closes) < SLOW + FORWARD + 5: continue
        rets = [None] + [(closes[j]/closes[j-1]-1.0)*100.0 if closes[j-1] else None
                         for j in range(1, len(closes))]
        for j in range(SLOW, len(closes) - FORWARD):
            w = closes[j-FAST+1:j+1]
            fast_mean = sum(w)/FAST
            slow_mean = sum(closes[j-SLOW+1:j+1])/SLOW
            sig = stdev([x for x in rets[j-FAST+1:j+1] if x is not None])
            if not sig or sig <= 0: continue
            price = closes[j]
            if price <= 0: continue
            hi, lo = max(w), min(w)

            for side in ("long", "short"):
                if side == "long":
                    if fast_mean <= slow_mean: continue
                    if hi <= 0 or (hi - price)/hi > ENTRY_BAND: continue
                else:
                    if fast_mean >= slow_mean: continue
                    if lo <= 0 or (price - lo)/lo > ENTRY_BAND: continue
                entry = price
                sign = 1.0 if side == "long" else -1.0
                target = entry * (1 + sign * TARGET_SIGMAS * sig / 100.0)
                for label, k in STOPS:
                    stop = (lo if side == "long" else hi) if k is None \
                        else entry * (1 - sign * k * sig / 100.0)
                    risk = abs(entry - stop)
                    if risk <= 0: continue
                    rr = abs(target - entry) / risk
                    out, stopped = None, False
                    for f in range(j+1, j+1+FORWARD):
                        c = closes[f]
                        hit_stop = c <= stop if side == "long" else c >= stop
                        hit_tgt = c >= target if side == "long" else c <= target
                        if hit_stop and hit_tgt:      # both in one close: the worse one counts
                            out, stopped = -1.0, True; break
                        if hit_stop: out, stopped = -1.0, True; break
                        if hit_tgt: out = rr; break
                    if out is None:
                        out = sign * (closes[j+FORWARD] - entry) / risk
                    res.setdefault((side, label), []).append((out, rr, stopped))

print(f"{'side':6} {'stop rule':26} {'n':>7} {'R:R':>6} {'target hit':>11} "
      f"{'stopped':>8} {'mean R':>8} {'median R':>9}")
for side in ("long", "short"):
    for label, _ in STOPS:
        rows_ = res.get((side, label))
        if not rows_: continue
        outs = [r[0] for r in rows_]
        rrs = [r[1] for r in rows_]
        stopped = sum(1 for r in rows_ if r[2]) / len(rows_)
        won = sum(1 for r in rows_ if r[0] > 0.0 and r[0] >= r[1] - 1e-9) / len(rows_)
        print(f"{side:6} {label:26} {len(rows_):>7} {statistics.median(rrs):>6.2f} "
              f"{won:>10.1%} {stopped:>8.1%} {sum(outs)/len(outs):>8.3f} "
              f"{statistics.median(outs):>9.3f}")
conn.close()
