"""The same question with the control the first pass was missing.

A 54.4% up-rate means nothing without the unconditional up-rate beside it: these are eight
years in which most of these assets rose, so the baseline is not 50%.
"""
import sys, statistics
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

VOL_WIN, FWD_LIST = 20, (5, 20)
BASES = (120, 250)
LOW_PCT = 0.20

def stdev(xs):
    if len(xs) < 3: return None
    m = sum(xs)/len(xs)
    return (sum((x-m)**2 for x in xs)/len(xs))**0.5

conn = nbt.db(); cur = conn.cursor()
cur.execute('SELECT id FROM "Asset" ORDER BY symbol')
assets = [a["id"] for a in cur.fetchall()]

# bucket -> fwd -> list of signed moves
buckets = {}
def add(name, fwd, signed):
    buckets.setdefault(name, {}).setdefault(fwd, []).append(signed)

CHUNK = 25
for i in range(0, len(assets), CHUNK):
    ids = assets[i:i+CHUNK]
    cur.execute('SELECT "assetId", date, close, volume FROM "PriceSnapshot" '
                'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC', (ids,))
    series = {}
    for r in cur.fetchall():
        series.setdefault(r["assetId"], []).append(r)

    for bars in series.values():
        closes = [float(b["close"]) for b in bars]
        vols = [float(b["volume"]) if b["volume"] else None for b in bars]
        if len(closes) < max(BASES) + VOL_WIN + max(FWD_LIST) + 5:
            continue
        rets = [None] + [(closes[j]/closes[j-1]-1.0)*100.0 if closes[j-1] else None
                         for j in range(1, len(closes))]
        v = [None]*len(closes)
        for j in range(VOL_WIN, len(closes)):
            w = [x for x in rets[j-VOL_WIN+1:j+1] if x is not None]
            v[j] = stdev(w)

        start = max(BASES) + VOL_WIN
        for j in range(start, len(closes) - max(FWD_LIST)):
            if v[j] is None or closes[j] <= 0: continue
            tags = ["all days"]
            for base in BASES:
                hist = [x for x in v[j-base:j] if x is not None]
                if len(hist) >= base//2 and sum(1 for x in hist if x <= v[j])/len(hist) <= LOW_PCT:
                    tags.append(f"compressed vs own {base}")
            if vols[j] is not None and rets[j] is not None:
                prior = [x for x in vols[j-VOL_WIN:j] if x is not None]
                if len(prior) >= VOL_WIN//2:
                    avg = sum(prior)/len(prior)
                    if avg > 0:
                        vr = vols[j]/avg
                        if vr >= 1.5 and abs(rets[j]) <= 0.5: tags.append("volume>=1.5x, flat day")
                        elif vr >= 2.5 and abs(rets[j]) <= 0.5: tags.append("volume>=2.5x, flat day")
            for fwd in FWD_LIST:
                signed = (closes[j+fwd]/closes[j]-1.0)*100.0
                for t in tags: add(t, fwd, signed)

print(f"{'bucket':28} {'fwd':>4} {'n':>8} {'up rate':>8} {'median |move|':>14} {'median signed':>14}")
for name in ["all days", "compressed vs own 120", "compressed vs own 250",
             "volume>=1.5x, flat day", "volume>=2.5x, flat day"]:
    for fwd in FWD_LIST:
        xs = buckets.get(name, {}).get(fwd)
        if not xs:
            print(f"{name:28} {fwd:>4}  (none)"); continue
        up = sum(1 for x in xs if x > 0)/len(xs)
        print(f"{name:28} {fwd:>4} {len(xs):>8} {up:>7.1%} "
              f"{statistics.median([abs(x) for x in xs]):>13.2f}% {statistics.median(xs):>+13.2f}%")
conn.close()
