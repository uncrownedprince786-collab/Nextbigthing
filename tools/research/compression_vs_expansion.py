"""Does compression actually precede expansion in this database? Read-only measurement.

Nothing is written. The question is whether a claim worth putting in the rule table survives
contact with eight years of stored closes, measured before anything is built on it.
"""
import os, sys, statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..", "jobs"))
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

VOL_WIN = 20        # sessions the realised volatility is measured over
BASE_WIN = 250      # sessions its percentile is taken against
FWD = 20            # forward sessions the outcome is measured over
LOW_PCT = 0.20      # bottom fifth of an asset's own volatility history is "compressed"

def stdev(xs):
    if len(xs) < 3: return None
    m = sum(xs)/len(xs)
    return (sum((x-m)**2 for x in xs)/len(xs))**0.5

conn = nbt.db(); cur = conn.cursor()
cur.execute('SELECT id, symbol FROM "Asset" ORDER BY symbol')
assets = cur.fetchall()

comp_fwd, base_fwd = [], []          # |forward move| after compressed / all other days
quiet_fwd, quiet_signed = [], []     # volume spike with no price move
loud_fwd = []
n_days = n_comp = n_quiet = 0

CHUNK = 25
for i in range(0, len(assets), CHUNK):
    ids = [a["id"] for a in assets[i:i+CHUNK]]
    cur.execute(
        'SELECT "assetId", date, close, volume FROM "PriceSnapshot" '
        'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC', (ids,))
    series = {}
    for r in cur.fetchall():
        series.setdefault(r["assetId"], []).append(r)

    for bars in series.values():
        closes = [float(b["close"]) for b in bars]
        vols = [float(b["volume"]) if b["volume"] else None for b in bars]
        if len(closes) < BASE_WIN + VOL_WIN + FWD + 5:
            continue
        rets = [None] + [(closes[j]/closes[j-1]-1.0)*100.0 if closes[j-1] else None
                         for j in range(1, len(closes))]
        # realised volatility at each index, over the VOL_WIN returns ending there
        v = [None]*len(closes)
        for j in range(VOL_WIN, len(closes)):
            w = [x for x in rets[j-VOL_WIN+1:j+1] if x is not None]
            v[j] = stdev(w)

        for j in range(BASE_WIN + VOL_WIN, len(closes) - FWD):
            if v[j] is None or closes[j] <= 0:
                continue
            hist = [x for x in v[j-BASE_WIN:j] if x is not None]
            if len(hist) < BASE_WIN//2:
                continue
            fwd = abs(closes[j+FWD]/closes[j]-1.0)*100.0
            n_days += 1
            rank = sum(1 for x in hist if x <= v[j]) / len(hist)
            if rank <= LOW_PCT:
                comp_fwd.append(fwd); n_comp += 1
            else:
                base_fwd.append(fwd)

            # volume anomaly with no price move
            if vols[j] is not None:
                prior = [x for x in vols[j-VOL_WIN:j] if x is not None]
                if len(prior) >= VOL_WIN//2:
                    avg = sum(prior)/len(prior)
                    if avg > 0 and rets[j] is not None:
                        vr = vols[j]/avg
                        if vr >= 1.5 and abs(rets[j]) <= 0.5:
                            quiet_fwd.append(fwd)
                            quiet_signed.append((closes[j+FWD]/closes[j]-1.0)*100.0)
                            n_quiet += 1
                        elif vr >= 1.5:
                            loud_fwd.append(fwd)

def say(name, xs):
    if not xs:
        print(f"{name:34} no observations"); return
    xs2 = sorted(xs)
    print(f"{name:34} n={len(xs):7}  median={statistics.median(xs2):6.2f}%  "
          f"mean={sum(xs)/len(xs):6.2f}%  p75={xs2[int(len(xs2)*0.75)]:6.2f}%")

print(f"asset-sessions examined: {n_days}")
print(f"forward window: {FWD} sessions; |move| from the close on the day\n")
say("after a compressed day", comp_fwd)
say("after every other day", base_fwd)
say("volume >=1.5x, |day move| <=0.5%", quiet_fwd)
say("volume >=1.5x, day moved", loud_fwd)
if quiet_signed:
    up = sum(1 for x in quiet_signed if x > 0)
    print(f"\nquiet-volume days followed by a rise: {up} of {len(quiet_signed)} "
          f"({up/len(quiet_signed):.1%})  median signed={statistics.median(quiet_signed):+.2f}%")
conn.close()
