"""Is anything measurably earlier than the moving-average stack, and does it pay? Read-only.

Five entry rules on the same footing: entry at that session's close, stop 1.5 of the asset's own
daily dispersion, target 2.0 of it, first touch over the next 20 stored sessions, outcome in
units of the risk taken. Two questions per rule, and the second does not follow from the first:

  * **earlier** -- how many sessions had the moving-average stack already held when the rule
    fired? 0 means the rule fires before the stack exists at all.
  * **does it pay** -- mean outcome in R, and the share reaching the target.

Nothing is written.
"""
import sys, statistics
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

FAST, SLOW, VOLW, FWD = 20, 50, 20, 20
BASE = 120            # the window a squeeze is judged against
STOP_S, TGT_S = 1.5, 2.0
LOW_Q = 0.20          # bottom fifth of its own volatility history

def sd(xs):
    if len(xs) < 3: return None
    m = sum(xs)/len(xs)
    return (sum((x-m)**2 for x in xs)/len(xs))**0.5

conn = nbt.db(); cur = conn.cursor()
cur.execute('SELECT id FROM "Asset" ORDER BY symbol')
assets = [a["id"] for a in cur.fetchall()]

res = {}   # (rule, side) -> [(R, stack_age)]
def add(rule, side, r, age): res.setdefault((rule, side), []).append((r, age))

for i in range(0, len(assets), 25):
    cur.execute('SELECT "assetId", date, close, volume FROM "PriceSnapshot" '
                'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC',
                (assets[i:i+25],))
    series = {}
    for r in cur.fetchall(): series.setdefault(r["assetId"], []).append(r)

    for bars in series.values():
        c = [float(b["close"]) for b in bars]
        v = [float(b["volume"]) if b["volume"] else None for b in bars]
        n = len(c)
        if n < BASE + SLOW + FWD + 10: continue
        ret = [None] + [(c[j]/c[j-1]-1.0)*100.0 if c[j-1] else None for j in range(1, n)]

        fast = [None]*n; slow = [None]*n; sig = [None]*n
        for j in range(SLOW-1, n):
            fast[j] = sum(c[j-FAST+1:j+1])/FAST
            slow[j] = sum(c[j-SLOW+1:j+1])/SLOW
        for j in range(FAST, n):
            sig[j] = sd([x for x in ret[j-FAST+1:j+1] if x is not None])

        # how long the stack has held, per session
        age_up = [0]*n; age_dn = [0]*n
        for j in range(SLOW, n):
            up = fast[j] is not None and c[j] > fast[j] > slow[j]
            dn = fast[j] is not None and c[j] < fast[j] < slow[j]
            age_up[j] = age_up[j-1] + 1 if up else 0
            age_dn[j] = age_dn[j-1] + 1 if dn else 0

        for j in range(BASE + SLOW, n - FWD):
            s = sig[j]
            if not s or s <= 0 or c[j] <= 0: continue
            hist = [x for x in sig[j-BASE:j] if x is not None]
            if len(hist) < BASE//2: continue
            quiet = sum(1 for x in hist if x <= s)/len(hist) <= LOW_Q
            vr = None
            prior = [x for x in v[j-VOLW:j] if x is not None]
            if v[j] is not None and len(prior) >= VOLW//2:
                avg = sum(prior)/len(prior)
                if avg > 0: vr = v[j]/avg
            hi20 = max(c[j-FAST+1:j+1]); lo20 = min(c[j-FAST+1:j+1])
            r5 = (c[j]/c[j-5]-1.0)*100.0 if c[j-5] > 0 else None
            r5p = (c[j-1]/c[j-6]-1.0)*100.0 if c[j-6] > 0 else None
            fslope = fast[j] - fast[j-5] if fast[j-5] is not None else None

            fire = {}
            # 1. what the engine uses today
            fire[("ma_stack","long")]  = c[j] > fast[j] > slow[j]
            fire[("ma_stack","short")] = c[j] < fast[j] < slow[j]
            # 2. a new 20-session extreme, today
            fire[("breakout20","long")]  = c[j] >= hi20 and ret[j] is not None and ret[j] > 0
            fire[("breakout20","short")] = c[j] <= lo20 and ret[j] is not None and ret[j] < 0
            # 3. expansion out of a squeeze
            fire[("squeeze_break","long")]  = quiet and ret[j] is not None and ret[j] > STOP_S*s
            fire[("squeeze_break","short")] = quiet and ret[j] is not None and ret[j] < -STOP_S*s
            # 4. five-day momentum flipping sign on heavy volume
            fire[("vol_flip","long")]  = (r5 is not None and r5p is not None and r5 > 0 >= r5p
                                          and vr is not None and vr >= 1.2)
            fire[("vol_flip","short")] = (r5 is not None and r5p is not None and r5 < 0 <= r5p
                                          and vr is not None and vr >= 1.2)
            # 5. the fast mean turning while price is still the wrong side of the slow one
            fire[("inflection","long")]  = fslope is not None and fslope > 0 and c[j] < slow[j]
            fire[("inflection","short")] = fslope is not None and fslope < 0 and c[j] > slow[j]

            for (rule, side), on in fire.items():
                if not on: continue
                sign = 1.0 if side == "long" else -1.0
                stop = c[j]*(1 - sign*STOP_S*s/100.0)
                tgt  = c[j]*(1 + sign*TGT_S*s/100.0)
                risk = abs(c[j]-stop)
                if risk <= 0: continue
                rr = abs(tgt-c[j])/risk
                out = None
                for f in range(j+1, j+1+FWD):
                    hit_s = c[f] <= stop if side == "long" else c[f] >= stop
                    hit_t = c[f] >= tgt  if side == "long" else c[f] <= tgt
                    if hit_s: out = -1.0; break
                    if hit_t: out = rr; break
                if out is None: out = sign*(c[j+FWD]-c[j])/risk
                add(rule, side, out, age_up[j] if side == "long" else age_dn[j])

print(f"{'rule':16} {'side':6} {'n':>8} {'stack age med':>14} {'fires at 0':>11} "
      f"{'target hit':>11} {'mean R':>8}")
print("-"*82)
for side in ("long","short"):
    for rule in ("ma_stack","breakout20","squeeze_break","vol_flip","inflection"):
        rows = res.get((rule, side))
        if not rows: continue
        outs = [r for r,_ in rows]; ages = [a for _,a in rows]
        fresh = sum(1 for a in ages if a == 0)/len(ages)
        won = sum(1 for o in outs if o > 0)/len(outs)
        print(f"{rule:16} {side:6} {len(rows):>8} {statistics.median(ages):>14.0f} "
              f"{fresh:>10.0%} {won:>10.0%} {sum(outs)/len(outs):>8.3f}")
conn.close()
