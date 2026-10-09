"""If compression does not precede expansion, what does? Read-only.

Tests the rule the engine already applies -- volume above its own average confirming a move --
against the same unconditional control, and the directional version of it.
"""
import sys, statistics
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

VOL_WIN, FWD = 20, 20
conn = nbt.db(); cur = conn.cursor()
cur.execute('SELECT id FROM "Asset" ORDER BY symbol')
assets = [a["id"] for a in cur.fetchall()]
buckets = {}
def add(name, signed): buckets.setdefault(name, []).append(signed)

for i in range(0, len(assets), 25):
    cur.execute('SELECT "assetId", date, close, volume FROM "PriceSnapshot" '
                'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC',
                (assets[i:i+25],))
    series = {}
    for r in cur.fetchall(): series.setdefault(r["assetId"], []).append(r)
    for bars in series.values():
        closes = [float(b["close"]) for b in bars]
        vols = [float(b["volume"]) if b["volume"] else None for b in bars]
        if len(closes) < VOL_WIN + FWD + 60: continue
        rets = [None] + [(closes[j]/closes[j-1]-1.0)*100.0 if closes[j-1] else None
                         for j in range(1, len(closes))]
        for j in range(VOL_WIN + 40, len(closes) - FWD):
            if closes[j] <= 0 or rets[j] is None: continue
            signed = (closes[j+FWD]/closes[j]-1.0)*100.0
            add("all days", signed)
            if vols[j] is None: continue
            prior = [x for x in vols[j-VOL_WIN:j] if x is not None]
            if len(prior) < VOL_WIN//2: continue
            avg = sum(prior)/len(prior)
            if avg <= 0: continue
            vr = vols[j]/avg
            if vr < 1.2: 
                add("quiet volume, any move", signed); continue
            add("volume >=1.2x, any move", signed)
            if rets[j] > 0.5: add("volume >=1.2x, day UP", signed)
            elif rets[j] < -0.5: add("volume >=1.2x, day DOWN", signed)
            if vr >= 2.0 and rets[j] > 0.5: add("volume >=2.0x, day UP", signed)
            if vr >= 2.0 and rets[j] < -0.5: add("volume >=2.0x, day DOWN", signed)

print(f"{'bucket':28} {'n':>8} {'up rate':>8} {'median |move|':>14} {'median signed':>14}")
for name in ["all days", "quiet volume, any move", "volume >=1.2x, any move",
             "volume >=1.2x, day UP", "volume >=1.2x, day DOWN",
             "volume >=2.0x, day UP", "volume >=2.0x, day DOWN"]:
    xs = buckets.get(name)
    if not xs: print(f"{name:28}  (none)"); continue
    up = sum(1 for x in xs if x > 0)/len(xs)
    print(f"{name:28} {len(xs):>8} {up:>7.1%} "
          f"{statistics.median([abs(x) for x in xs]):>13.2f}% {statistics.median(xs):>+13.2f}%")
conn.close()
