"""label60 experiment: build the target, then evaluate it chronologically. Writes a JSON report.

Pre-registered before any result was seen:
  * band_pct = max(m * atr14 / base * 100, 2.0); m = median implied multiple over TRAINING rows only
  * 6 chronological folds, 60-session purge at every boundary
  * multinomial logistic regression, same 15 pit.f features as the label20 baseline, seed 20261015
  * headline = accuracy vs the fold's own majority-class rate
  * quality-flagged rows excluded explicitly and counted by cause
"""
import gzip, json, math, pathlib, sys, hashlib
from collections import Counter, defaultdict
import numpy as np

ROOT = pathlib.Path(sys.argv[1])            # extracted/dataset
REPO = pathlib.Path(sys.argv[2])            # repo root
OUT  = pathlib.Path(sys.argv[3])
sys.path.insert(0, str(REPO))
from tools.research.label60 import band_pct, label_of, calibrate_m, LABEL_THRESHOLD_PCT

FEATURES = ["atr14","drawdownPct","entryTrigger","peerMedianR20","peers","r1","r20","r5",
            "rangePct","relStrength","returnZ","sma20","sma50","triggerDirection","volumeRatio"]
CLASSES = ["DOWN","FLAT","UP"]
HORIZON, PURGE, SEED, FOLDS = 60, 60, 20261015, 6

def env():
    v={}
    for ln in open(REPO/".env",encoding="utf-8"):
        ln=ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k,val=ln.split("=",1); v[k]=val.strip().strip('"').strip("'")
    return v

# ---------------------------------------------------------------- forward closes from the DB
import psycopg
print("pulling close series from the database ...", flush=True)
series=defaultdict(list)
with psycopg.connect(env()["SUPABASE_DATABASE_URL"], connect_timeout=30) as cn:
    with cn.cursor(name="px") as c:
        c.itersize=50000
        c.execute('''select a.symbol, p.date, p.close
                     from "PriceSnapshot" p join "Asset" a on a.id=p."assetId"
                     where p.close is not null order by a.symbol, p.date''')
        for sym,d,close in c:
            series[sym].append((d.isoformat(), float(close)))
idx={s:{d:i for i,(d,_) in enumerate(v)} for s,v in series.items()}
print(f"  {len(series)} symbols, {sum(len(v) for v in series.values()):,} sessions", flush=True)

def fwd(sym, as_of, base, h):
    """Percent return to the h-th stored session STRICTLY AFTER as_of, or None if immature."""
    v=series.get(sym); i=idx.get(sym,{}).get(as_of)
    if v is None or i is None or base in (None,0): return None
    j=i+h
    return None if j>=len(v) else (v[j][1]/base-1.0)*100.0

# ---------------------------------------------------------------- load rows
print("loading dataset ...", flush=True)
rows=[]; excl=Counter(); seen=0
for p in sorted(ROOT.glob("examples-v3-*.jsonl.gz")):
    with gzip.open(p,"rt",encoding="utf-8") as f:
        for line in f:
            seen+=1
            r=json.loads(line)
            o=r.get("outcome") or {}; pit=r.get("pit") or {}; fe=pit.get("f") or {}
            dq=r.get("dataQuality") or {}
            if not fe: excl["noPointInTimeFeatures"]+=1; continue
            if dq.get("unadjustedActionInWindow"): excl["unadjustedActionInWindow"]+=1; continue
            if dq.get("basisBreakInWindow"): excl["basisBreakInWindow"]+=1; continue
            if dq.get("windowIsNotDaily"): excl["windowIsNotDaily"]+=1; continue
            base=o.get("baseClose")
            if base is None: excl["noBaseClose"]+=1; continue
            rows.append((r["asOf"], r["symbol"], r.get("assetType"), r.get("market"),
                         base, fe, o.get("label20")))
print(f"  scanned {seen:,}  kept {len(rows):,}  excluded {sum(excl.values()):,}", flush=True)
rows.sort(key=lambda t:(t[0],t[1]))
dates=sorted({t[0] for t in rows})

# ---------------------------------------------------------------- folds (chronological)
cut=[dates[int(len(dates)*k/(FOLDS+1))] for k in range(1,FOLDS+1)]
def fold_of(d):
    for i,c in enumerate(cut):
        if d<c: return i
    return FOLDS

# ---------------------------------------------------------------- calibrate m on TRAINING rows only
train_mask=[t[0] < cut[0] for t in rows]
m=calibrate_m([(t[5]["atr14"], t[4]) for t,tr in zip(rows,train_mask) if tr])
print(f"calibrated m = {m:.4f} on {sum(train_mask):,} training-period rows "
      f"(first fold boundary {cut[0]})", flush=True)
by_cls=defaultdict(list)
for t,tr in zip(rows,train_mask):
    if tr: by_cls[t[2]].append((t[5]["atr14"], t[4]))
m_by_class={k:round(calibrate_m(v),4) for k,v in by_cls.items() if calibrate_m(v)}

# ---------------------------------------------------------------- build label60
print("building label60 ...", flush=True)
def encode(fe):
    """Exactly the baseline's encoding: absent is 0.0, up/down are +/-1, other strings 0.0."""
    out=[]
    for k in FEATURES:
        v=fe.get(k)
        if v is None: v=0.0
        if isinstance(v,str): v={"up":1.0,"down":-1.0}.get(v,0.0)
        try: out.append(float(v))
        except (TypeError,ValueError): return None
    return out

X=[];Y=[];D=[];CLS=[];MKT=[];immature=0;noband=0;noenc=0
bands=[]
for as_of,sym,cls,mkt,base,fe,l20 in rows:
    b=band_pct(fe["atr14"], base, m)
    if b is None: noband+=1; continue
    f60=fwd(sym,as_of,base,HORIZON)
    lab=label_of(f60,b)
    if lab is None: immature+=1; continue
    vec=encode(fe)
    if vec is None: noenc+=1; continue
    X.append(vec); Y.append(CLASSES.index(lab))
    D.append(as_of); CLS.append(cls); MKT.append(mkt); bands.append(b)
X=np.asarray(X,dtype=np.float64); Y=np.asarray(Y)
print(f"  labelled {len(Y):,}   immature(<60 fwd sessions) {immature:,}   no band {noband:,}", flush=True)
dist=Counter(CLASSES[y] for y in Y)
print("  label60 distribution:", {k:round(v/len(Y),4) for k,v in dist.items()}, flush=True)

# ---------------------------------------------------------------- model (same as the baseline)
def softmax(z):
    z=z-z.max(axis=1,keepdims=True); e=np.exp(z); return e/e.sum(axis=1,keepdims=True)
def fit(Xtr,ytr,epochs=400,lr=0.5,l2=1e-4):   # matches tools/research/baseline_experiment.py
    rng=np.random.default_rng(SEED)
    mu=Xtr.mean(0); sd=Xtr.std(0); sd[sd==0]=1.0
    Z=(Xtr-mu)/sd; Z=np.hstack([Z,np.ones((len(Z),1))])
    W=rng.normal(0,0.01,(Z.shape[1],len(CLASSES)))
    Yh=np.zeros((len(ytr),len(CLASSES))); Yh[np.arange(len(ytr)),ytr]=1
    for _ in range(epochs):
        G=Z.T@(softmax(Z@W)-Yh)/len(Z)+l2*W
        W-=lr*G
    return W,mu,sd
def predict(W,mu,sd,Xte):
    Z=(Xte-mu)/sd; Z=np.hstack([Z,np.ones((len(Z),1))])
    return softmax(Z@W).argmax(1)

folds=[]
D=np.asarray(D)
for k in range(FOLDS):
    te_lo=cut[k]; te_hi=cut[k+1] if k+1<FOLDS else None
    te = (D>=te_lo)&((D<te_hi) if te_hi else np.ones(len(D),bool))
    # purge: training rows whose 60-session outcome window reaches into the test block
    tr_dates=sorted(d for d in dates if d<te_lo)
    purge_from = tr_dates[-PURGE] if len(tr_dates)>PURGE else tr_dates[0]
    tr = D < purge_from
    if tr.sum()<5000 or te.sum()<500: continue
    W,mu,sd=fit(X[tr],Y[tr])
    pred=predict(W,mu,sd,X[te]); truth=Y[te]
    acc=float((pred==truth).mean())
    maj=Counter(truth.tolist()).most_common(1)[0]
    folds.append({"fold":k+1,"testFrom":te_lo,"testTo":te_hi or dates[-1],
                  "trainRows":int(tr.sum()),"testRows":int(te.sum()),
                  "purgedSessions":PURGE,"purgeFrom":purge_from,
                  "accuracy":round(acc,4),
                  "majorityClass":CLASSES[maj[0]],
                  "majorityRate":round(maj[1]/len(truth),4),
                  "margin":round(acc-maj[1]/len(truth),4),
                  "predictedDistribution":{CLASSES[c]:round(n/len(pred),4)
                                           for c,n in Counter(pred.tolist()).items()}})
    print(f"  fold {k+1}: acc={acc:.4f} majority={maj[1]/len(truth):.4f} "
          f"margin={acc-maj[1]/len(truth):+.4f} n={te.sum():,}", flush=True)

accs=[f["accuracy"] for f in folds]; margins=[f["margin"] for f in folds]
report={
 "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
 "experiment":"label60-v1",
 "preRegistered":{"m":"median implied multiple, TRAINING rows only","floorPct":LABEL_THRESHOLD_PCT,
                  "horizon":HORIZON,"purgeSessions":PURGE,"folds":FOLDS,"seed":SEED,"steps":400,"lr":0.5,"l2":1e-4,
                  "features":FEATURES,"headline":"accuracy minus the fold's own majority-class rate"},
 "calibration":{"m":round(m,4),"mByAssetClass":m_by_class,
                "trainingRowsUsed":int(sum(train_mask)),"firstFoldBoundary":cut[0],
                "medianBandPct":round(float(np.median(bands)),4)},
 "rows":{"scanned":seen,"kept":len(rows),"labelled":int(len(Y)),
         "immature60":immature,"noBand":noband,"unencodable":noenc,"excludedByCause":dict(excl)},
 "labelDistribution":{k:round(v/len(Y),4) for k,v in dist.items()},
 "folds":folds,
 "summary":{"meanAccuracy":round(float(np.mean(accs)),4),
            "meanMajorityRate":round(float(np.mean([f["majorityRate"] for f in folds])),4),
            "meanMargin":round(float(np.mean(margins)),4),
            "worstFoldMargin":round(float(min(margins)),4),
            "foldsBeatingMajority":int(sum(1 for x in margins if x>0))},
}
report["verdict"]=("NO EDGE: mean margin over the majority class is not positive across folds"
                   if np.mean(margins)<=0 else
                   "POSITIVE MEAN MARGIN -- not an edge claim; see worstFoldMargin and stability")
OUT.write_text(json.dumps(report,indent=1),encoding="utf-8")
print("\n"+json.dumps(report["summary"],indent=1))
print("VERDICT:",report["verdict"])
print("wrote",OUT)
