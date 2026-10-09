"""How early in a trend does the engine enter? Read-only.

"Already moved" is not the same as "late". A system that enters on day 3 of a move is early
even though the move started; one that enters on day 40 is chasing. The measurable version of
that question is how many consecutive sessions the trend condition had already held when the
verdict was written.
"""
import sys, statistics
sys.path.insert(0, r"C:\Users\NEW TECH\Nextbigthing\jobs")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\NEW TECH\Nextbigthing\.env")
import nbt

FAST, SLOW = 20, 50
conn = nbt.db(); cur = conn.cursor()
cur.execute('''
  SELECT a.id, a.symbol, d.action FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
  WHERE d."periodEnd" = (SELECT max("periodEnd") FROM "DecisionLog") AND d.action <> 'WAIT' ''')
calls = cur.fetchall()
by_id = {r["id"]: r for r in calls}

ages = {"LONG": [], "SHORT": []}
for i in range(0, len(calls), 25):
    ids = [r["id"] for r in calls[i:i+25]]
    cur.execute('SELECT "assetId", date, close FROM "PriceSnapshot" '
                'WHERE "assetId" = ANY(%s) AND close IS NOT NULL ORDER BY "assetId", date ASC', (ids,))
    series = {}
    for r in cur.fetchall(): series.setdefault(r["assetId"], []).append(float(r["close"]))
    for aid, closes in series.items():
        if len(closes) < SLOW + 60: continue
        action = by_id[aid]["action"]
        # Walk back from the newest session counting how long the condition has held.
        held = 0
        for j in range(len(closes) - 1, SLOW - 1, -1):
            fast = sum(closes[j-FAST+1:j+1]) / FAST
            slow = sum(closes[j-SLOW+1:j+1]) / SLOW
            up = closes[j] > fast > slow
            down = closes[j] < fast < slow
            on = up if action == "LONG" else down
            # The bias path: the two means on the right side, price between them.
            if not on:
                on = (fast > slow) if action == "LONG" else (fast < slow)
            if not on: break
            held += 1
            if held > 250: break
        ages[action].append(held)

print(f"{'action':8} {'n':>5} {'p25':>6} {'median':>7} {'p75':>6} {'<=5 sessions':>13} {'>60 sessions':>13}")
for action, xs in ages.items():
    if not xs: continue
    xs.sort()
    q = lambda p: xs[min(len(xs)-1, int(len(xs)*p))]
    early = sum(1 for x in xs if x <= 5) / len(xs)
    late = sum(1 for x in xs if x > 60) / len(xs)
    print(f"{action:8} {len(xs):>5} {q(.25):>6} {statistics.median(xs):>7.0f} {q(.75):>6} "
          f"{early:>12.0%} {late:>12.0%}")
conn.close()
