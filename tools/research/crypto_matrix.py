"""The feature matrix for a pool of coins, built once and cached on disk.

`train_crypto_short.prepare` reads every bar of every coin and recomputes the whole feature set on
each run. For one fit that is fine -- it is a few minutes against a twenty-minute fit. For a sweep
that fits the same matrix twenty times it is most of the run, and it is the same matrix every
time, so it is cached here instead.

    from crypto_matrix import prepare_cached
    data = prepare_cached(["BTCUSDT"], "5m", stride=1)

The returned dict is the **same shape** `prepare` returns, including the private `_series` tuples
`train_crypto_short.labels_for` reads, so the cache is a speed-up and never a second definition:
anything downstream treats a cached pool and a freshly built one identically.

What the cache key covers
-------------------------
The symbols, the interval, the stride, the feature schema version, and the content of every corpus
file that went into it (size and modification time). A recollected corpus, an edited feature
definition or a different stride all produce a different key, so a stale matrix cannot be served
to a new feature set -- which is the one failure that would silently invalidate every number a
sweep produced.

The parity check against `intraday_features.features_at` runs when the matrix is **built** and its
result is stored in the cache, so a cached pool still carries the evidence that the fast twin
agreed with the readable definition on the rows it holds.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from intraday_features import N_FEATURES as N_F1, VERSION as FEATURE_VERSION, WARMUP  # noqa: E402
from intraday_matrix import build, verify_against_reference  # noqa: E402
from market_context import (  # noqa: E402
    CONTEXT_FEATURES,
    VERSION as CONTEXT_VERSION,
    context_for,
)

#: The coin whose bars are the market factor every other coin is read against.
MARKET_SYMBOL = "BTCUSDT"

CORPUS = ROOT / ".cache" / "foundation" / "intraday"
CACHE = ROOT / ".cache" / "scratch" / "matrix"


def _corpus_path(symbol: str, interval: str) -> Path:
    return CORPUS / f"{symbol}-{interval}.jsonl.gz"


def _key(symbols: list[str], interval: str, stride: int, context: bool = False) -> str:
    parts = [FEATURE_VERSION, interval, str(stride)]
    if context:
        # The factor's own bars are an input to every row, so the cache key has to cover the
        # context definition and the factor's corpus as well as each coin's.
        parts.append(CONTEXT_VERSION)
        mp = _corpus_path(MARKET_SYMBOL, interval)
        mst = mp.stat() if mp.exists() else None
        parts.append(f"mkt:{mst.st_size if mst else 0}:{int(mst.st_mtime) if mst else 0}")
    for s in sorted(symbols):
        p = _corpus_path(s, interval)
        st = p.stat() if p.exists() else None
        parts.append(f"{s}:{st.st_size if st else 0}:{int(st.st_mtime) if st else 0}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _load_bars(symbol: str, interval: str) -> list[dict]:
    import gzip

    path = _corpus_path(symbol, interval)
    if not path.exists():
        raise SystemExit(f"no corpus at {path}; run tools/foundation/crypto_intraday.py first")
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            out.append(json.loads(line))
    return out


def _corpus_report(symbol: str, interval: str) -> dict:
    p = CORPUS / f"{symbol}-{interval}.manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _build_pool(symbols: list[str], interval: str, stride: int, context: bool = False) -> dict:
    """Exactly what `train_crypto_short.prepare` builds, with the same exclusions and parity check.

    With `context`, the market-factor block is appended to every row and a row the factor has no
    bar for is dropped from `valid` -- not imputed. A context feature filled across an outage in
    the factor's series would be a claim about what the market did while nobody was trading it.
    """
    mkt = None
    if context:
        mbars = _load_bars(MARKET_SYMBOL, interval)
        mkt = {
            "ts": np.asarray([b["ts"] for b in mbars], dtype=np.int64),
            "c": np.asarray([b["c"] for b in mbars], dtype=np.float64),
            "h": np.asarray([b["h"] for b in mbars], dtype=np.float64),
            "l": np.asarray([b["l"] for b in mbars], dtype=np.float64),
        }

    Xs, ts_all, close_all, sym_all = [], [], [], []
    corpora: dict[str, dict] = {}
    parity: dict[str, dict] = {}
    for s in symbols:
        bars = _load_bars(s, interval)
        X, ts, valid, step = build(bars)
        if context and mkt is not None:
            closes_all = np.asarray([b["c"] for b in bars], dtype=np.float64)
            C, ctx_ok = context_for(ts, closes_all, mkt["ts"], mkt["c"], mkt["h"], mkt["l"],
                                    WARMUP)
            X = np.hstack([X, C]).astype(np.float32)
            valid = valid & ctx_ok
        if not valid.any():
            corpora[s] = {"bars": len(bars), "usableRows": 0, "stepMs": int(step),
                          "excluded": "fewer bars than the feature window needs, or the market "
                                      "factor has no bar inside it",
                          "_series": (ts, np.asarray([b["c"] for b in bars], dtype=np.float64),
                                      np.zeros(0, dtype=np.int64))}
            continue
        # The parity check compares against `intraday_features.features_at`, which defines the 41
        # f1 columns and knows nothing about the context block, so it is handed those columns
        # only. The context block has its own definition and is checked by `test_market_context`.
        parity[s] = verify_against_reference(bars, X[:, :N_F1], valid, sample=60)
        closes = np.asarray([b["c"] for b in bars], dtype=np.float64)
        keep = np.flatnonzero(valid)[:: max(1, stride)]
        Xs.append(X[keep])
        ts_all.append(ts[keep])
        close_all.append(closes[keep])
        sym_all.append(np.full(len(keep), s))
        corpora[s] = {
            "bars": len(bars), "usableRows": int(len(keep)), "stepMs": int(step),
            "manifest": {k: v for k, v in _corpus_report(s, interval).items()
                         if k in ("completeness", "gapRuns", "missingBars", "first", "last",
                                  "rejected", "conflictingDuplicates", "crossVenue")},
            "_series": (ts, closes, keep),
        }
    return {
        "X": np.vstack(Xs),
        "ts": np.concatenate(ts_all),
        "close": np.concatenate(close_all),
        "symbol": np.concatenate(sym_all),
        "corpora": corpora,
        "parity": parity,
    }


def _save(path: Path, data: dict, symbols: list[str]) -> None:
    arrays = {
        "X": data["X"],
        "ts": data["ts"],
        "close": data["close"],
        "symbol": data["symbol"],
    }
    meta = {}
    for s, m in data["corpora"].items():
        full_ts, full_close, keep = m["_series"]
        arrays[f"s:{s}:ts"] = full_ts
        arrays[f"s:{s}:close"] = full_close
        arrays[f"s:{s}:keep"] = keep
        meta[s] = {k: v for k, v in m.items() if k != "_series"}
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    path.with_suffix(".meta.json").write_text(
        json.dumps({"symbols": symbols, "corpora": meta, "parity": data["parity"]}, indent=1),
        encoding="utf-8")


def _load(path: Path) -> dict:
    z = np.load(path, allow_pickle=False)
    meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    corpora = {}
    for s, m in meta["corpora"].items():
        corpora[s] = dict(m)
        corpora[s]["_series"] = (z[f"s:{s}:ts"], z[f"s:{s}:close"], z[f"s:{s}:keep"])
    return {
        "X": z["X"], "ts": z["ts"], "close": z["close"], "symbol": z["symbol"],
        "corpora": corpora, "parity": meta["parity"],
    }


def prepare_cached(symbols: list[str], interval: str, stride: int = 1,
                   verbose: bool = True, context: bool = False) -> dict:
    """The pool, from cache when the corpus and the feature definition are unchanged."""
    path = CACHE / f"{_key(symbols, interval, stride, context)}.npz"
    if path.exists() and path.with_suffix(".meta.json").exists():
        if verbose:
            print(f"   matrix cache hit {path.name}", flush=True)
        return _load(path)
    if verbose:
        print(f"   building matrix for {len(symbols)} symbols at {interval} "
              f"(stride {stride}{', +market context' if context else ''})", flush=True)
    data = _build_pool(symbols, interval, stride, context)
    _save(path, data, symbols)
    if verbose:
        worst = max((p["worstRelativeDiff"] for p in data["parity"].values()), default=0.0)
        print(f"   {len(data['ts']):,} usable rows cached (parity worst {worst:.2g})", flush=True)
    return data


def symbols_with(interval: str) -> list[str]:
    """Every symbol the corpus holds at this interval, sorted."""
    return sorted(p.name.split("-")[0] for p in CORPUS.glob(f"*-{interval}.jsonl.gz"))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build and cache a crypto feature matrix.")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--context", action="store_true",
                    help="append the market-factor block (market_context.py)")
    a = ap.parse_args()
    syms = a.symbols or symbols_with(a.interval)
    d = prepare_cached(syms, a.interval, a.stride, context=a.context)
    print(f"{len(d['ts']):,} rows, {d['X'].shape[1]} features, {len(d['corpora'])} symbols")
