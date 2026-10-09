"""Is there any condition under which the short side pays? Read-only.

The short side measured negative in mean expectancy at every stop width but the two tightest.
A gate is only worth adding if some stored condition separates the shorts that pay from the ones
that do not, so this conditions the same backtest on things the rule table can actually see at
decision time: how many confirmations are present, the market, and how far into the move it is.
"""
import sys, statistics
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

FAST, SLOW, VOLW, FWD = 20, 50, 20, 20
STOP_S, TGT_S = 1.5, 2.0

def sd(xs):
    if len(xs) < 3: return None
    m = sum(xs)/len(xs)
    return (sum((x-m)**2 for x in xs)/len(xs))**0.5

conn = nbt.db(); cur = conn.cursor()
cur.execute('''SELECT a.id, CASE WHEN a."assetType"::text IN ('crypto','forex','commodity')
   THEN a."assetType"::text ELSE lower(i.market) END cls
 FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId" ORDER BY a.symbol''')
rows = cur.fetchall()
cls = {r["id"]: r["cls"] for r in rows}
assets = [r["id"] for r in rows]

buckets = {}
def add(k, r): buckets.setdefault(k, []).append(r)

for i in range(0, len(assets), 25):
    cur.execute('SELECT "assetId", date, close, volume FROM "PriceSnapshot" '
                'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC',
                (assets[i:i+25],))
    series = {}
    for r in cur.fetchall(): series.setdefault(r["assetId"], []).append(r)

    for aid, bars in series.items():
        c = [float(b["close"]) for b in bars]
        v = [float(b["volume"]) if b["volume"] else None for b in bars]
        n = len(c)
        if n < SLOW + FWD + 60: continue
        ret = [None] + [(c[j]/c[j-1]-1.0)*100.0 if c[j-1] else None for j in range(1, n)]
        market = cls.get(aid, "us")

        for j in range(SLOW + 20, n - FWD):
            fast = sum(c[j-FAST+1:j+1])/FAST
            slow = sum(c[j-SLOW+1:j+1])/SLOW
            if not (c[j] < fast < slow): continue          # the short the engine would take
            s = sd([x for x in ret[j-FAST+1:j+1] if x is not None])
            if not s or s <= 0: continue
            vr = None
            prior = [x for x in v[j-VOLW:j] if x is not None]
            if v[j] is not None and len(prior) >= VOLW//2:
                avg = sum(prior)/len(prior)
                if avg > 0: vr = v[j]/avg
            r20 = (c[j]/c[j-20]-1.0)*100.0 if c[j-20] > 0 else None
            lo120 = min(c[max(0,j-119):j+1]); hi120 = max(c[max(0,j-119):j+1])
            pos = (c[j]-lo120)/(hi120-lo120)*100 if hi120 > lo120 else None

            stop = c[j]*(1 + STOP_S*s/100.0); tgt = c[j]*(1 - TGT_S*s/100.0)
            risk = stop - c[j]
            if risk <= 0: continue
            rr = (c[j]-tgt)/risk
            out = None
            for f in range(j+1, j+1+FWD):
                if c[f] >= stop: out = -1.0; break
                if c[f] <= tgt: out = rr; break
            if out is None: out = -(c[j+FWD]-c[j])/risk

            add(("all", "all"), out)
            add(("market", market), out)
            add(("volume", "ge1.2" if (vr is not None and vr >= 1.2) else
                 "lt1.2" if vr is not None else "none"), out)
            if r20 is not None:
                add(("already fallen", "> -3%" if r20 > -3 else "-3 to -10%" if r20 > -10 else "< -10%"), out)
            if pos is not None:
                add(("range position", "bottom 20%" if pos <= 20 else "20-50%" if pos <= 50 else "above half"), out)

print(f"{'condition':18} {'bucket':14} {'n':>9} {'target hit':>11} {'mean R':>9}")
print("-"*68)
for cond in ("all","market","volume","already fallen","range position"):
    for (c0, b), xs in sorted(buckets.items()):
        if c0 != cond: continue
        won = sum(1 for o in xs if o > 0)/len(xs)
        print(f"{c0:18} {b:14} {len(xs):>9} {won:>10.0%} {sum(xs)/len(xs):>9.3f}")
conn.close()
