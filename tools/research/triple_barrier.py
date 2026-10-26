"""Label a row by what the trade would have done, not by where the close landed.

Every model in this repository has been fitted on one label: `close_later > close_now`. It is the
simplest honest target and it has a defect that no amount of retraining reaches -- **it does not
know what a trade is**. Two rows that both end a tenth of a percent up are identical to it, even
when one drifted there quietly and the other fell two percent first and would have stopped you
out on the way. The model is rewarded for calling the sign and never told what the path cost.

The triple-barrier method labels the path instead. Three barriers are placed around each entry:

  * an upper barrier at `+target x ATR`
  * a lower barrier at `-stop x ATR`
  * a vertical barrier at `bars_ahead` bars

and the row is labelled by **which is touched first**: `1` if the upper, `-1` if the lower, `0` if
neither and the window simply closes. A model fitted on that learns risk directly -- it is being
asked which trades work, not which closes are higher.

Why the path and not the endpoint
----------------------------------
The backtest has always walked the path: it is where the 0.5R-per-trade fee and the
never-reached-15-ATR-target findings came from. But the *model* never saw any of it. Training on
the endpoint and judging on the path is a mismatch that shows up as a model which is 53% right
about direction and loses money anyway, because being right about the close says nothing about
whether you survived the middle.

A bar that touches both barriers is labelled a loss, the same convention the backtest uses: a
bar records a high and a low, not which came first, and assuming the favourable one is how a
backtest flatters itself.

Barriers scale with ATR, so a label means the same thing on Bitcoin and on a small cap, and they
are read from the same `atr14` the feature vector carries at the decision bar.
"""

from __future__ import annotations

import numpy as np


def directional_barrier_labels(
    data: dict,
    bars_ahead: int,
    atr: np.ndarray,
    stop_atr: float,
    target_atr: float,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """`(y, usable, stats)` -- 1 when a long works, 0 when a short works, rest dropped.

    **The one-sided barrier label collapses, and measuring it is how that was found.** Labelling
    "does a long reach its target before its stop" and folding the stop and the timeout together
    produces a 76/24 split at fifteen minutes, and the model takes the free lunch: it answered
    "no" to every row in the test fold, scored 75.84% against a 75.84% majority, and predicted a
    single class. The gates refused it, which is what they are for, but the label was the fault.

    This asks the symmetric question instead. From each bar, two trades are imagined -- a long
    with its target above and stop below, and a short with the mirror. A row is labelled:

      * **1** when the long resolves at its target and the short does not,
      * **0** when the short resolves at its target and the long does not,
      * **dropped** when neither resolves, or both do.

    Dropping is the point. A window that touches neither barrier is a window with no trade in it,
    and a window that would have paid both ways in the same three bars is a whipsaw whose sign is
    an artefact of which tick landed first. Training on either teaches noise. What is left is a
    balanced, path-aware directional target: the model is asked which *way* to trade among the
    bars where trading was possible, with the stop already built into the question.
    """
    n_all = len(data["ts"])
    y = np.zeros(n_all, dtype=np.int64)
    usable = np.zeros(n_all, dtype=bool)
    longs = shorts = neither = both = 0

    offset = 0
    for _sym, meta in data["corpora"].items():
        full_ts, full_close, keep = meta["_series"]
        n = len(keep)
        if n == 0:
            continue
        step = meta["stepMs"]
        highs = meta.get("_high")
        lows = meta.get("_low")
        fwd = keep + bars_ahead
        ok = fwd < len(full_close)
        aligned = np.zeros(n, dtype=bool)
        aligned[ok] = (full_ts[fwd[ok]] - full_ts[keep[ok]]) == bars_ahead * step
        a = atr[offset:offset + n]
        good = aligned & np.isfinite(a) & (a > 1e-9)
        idx = np.flatnonzero(good)
        if len(idx) == 0:
            offset += n
            continue

        entry = full_close[keep[idx]]
        up_t = entry * (1.0 + a[idx] * target_atr)     # long target / short stop
        dn_t = entry * (1.0 - a[idx] * target_atr)     # short target / long stop at -stop
        up_s = entry * (1.0 + a[idx] * stop_atr)
        dn_s = entry * (1.0 - a[idx] * stop_atr)

        long_win = np.zeros(len(idx), dtype=bool)
        short_win = np.zeros(len(idx), dtype=bool)
        long_live = np.ones(len(idx), dtype=bool)
        short_live = np.ones(len(idx), dtype=bool)
        for off in range(1, bars_ahead + 1):
            if not (long_live.any() or short_live.any()):
                break
            j = keep[idx] + off
            hi = highs[j] if highs is not None else full_close[j]
            lo = lows[j] if lows is not None else full_close[j]
            # A bar reaching both a trade's target and its stop closes that trade as a loss, the
            # same convention the backtest uses: the bar does not say which came first.
            lt, ls = long_live & (hi >= up_t), long_live & (lo <= dn_s)
            long_win |= lt & ~ls
            long_live &= ~(lt | ls)
            st, ss = short_live & (lo <= dn_t), short_live & (hi >= up_s)
            short_win |= st & ~ss
            short_live &= ~(st | ss)

        decided = long_win ^ short_win          # exactly one of the two resolved
        both += int((long_win & short_win).sum())
        neither += int((~long_win & ~short_win).sum())
        sel = idx[decided]
        y[offset + sel] = long_win[decided].astype(np.int64)
        usable[offset + sel] = True
        longs += int(long_win[decided].sum())
        shorts += int((~long_win[decided]).sum())
        offset += n

    total = longs + shorts
    stats = {
        "kind": "directional-barrier",
        "stopAtr": stop_atr, "targetAtr": target_atr,
        "rows": total, "longWins": longs, "shortWins": shorts,
        "droppedNeither": neither, "droppedBoth": both,
        "longShare": round(longs / total, 5) if total else 0.0,
    }
    return y, usable, stats


def triple_barrier_labels(
    data: dict,
    bars_ahead: int,
    atr: np.ndarray,
    stop_atr: float,
    target_atr: float,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """`(y, usable, stats)` where y is 1 (target first), 0 (stop first or timed out).

    Binary rather than three-class on purpose. A three-class target lets a model score by naming
    the largest class, and the timeout class is the largest at short horizons -- a model that
    says "nothing happens" to everything would look accurate and be useless. Collapsing timeout
    into the negative class asks the question a trader actually has: *is this trade worth taking*,
    where not reaching the target is a loss whether or not the stop was hit first.

    `usable` excludes rows whose forward window crosses a venue gap, and rows with no usable ATR.
    """
    n_all = len(data["ts"])
    y = np.zeros(n_all, dtype=np.int64)
    usable = np.zeros(n_all, dtype=bool)
    hit_target = hit_stop = timed_out = both = 0

    offset = 0
    for _sym, meta in data["corpora"].items():
        full_ts, full_close, keep = meta["_series"]
        n = len(keep)
        if n == 0:
            continue
        step = meta["stepMs"]
        highs = meta.get("_high")
        lows = meta.get("_low")

        fwd = keep + bars_ahead
        ok = fwd < len(full_close)
        aligned = np.zeros(n, dtype=bool)
        aligned[ok] = (full_ts[fwd[ok]] - full_ts[keep[ok]]) == bars_ahead * step

        a = atr[offset:offset + n]
        good = aligned & np.isfinite(a) & (a > 1e-9)
        idx = np.flatnonzero(good)
        if len(idx) == 0:
            offset += n
            continue

        entry = full_close[keep[idx]]
        up = entry * (1.0 + a[idx] * target_atr)
        dn = entry * (1.0 - a[idx] * stop_atr)

        # Walk the window bar by bar, stopping at the first barrier touched. Closes are used
        # where the corpus has no highs and lows, which is the conservative reading: a barrier
        # only counts as touched if a close reached it.
        first = np.zeros(len(idx), dtype=np.int64)       # 0 none, 1 target, -1 stop
        touched_both = np.zeros(len(idx), dtype=bool)
        live = np.ones(len(idx), dtype=bool)
        for off in range(1, bars_ahead + 1):
            if not live.any():
                break
            j = keep[idx] + off
            hi = highs[j] if highs is not None else full_close[j]
            lo = lows[j] if lows is not None else full_close[j]
            t_hit = live & (hi >= up)
            s_hit = live & (lo <= dn)
            # A bar touching both is a loss: the bar does not record which came first, and
            # assuming the favourable one is how a backtest flatters itself.
            both_now = t_hit & s_hit
            touched_both |= both_now
            first = np.where(both_now, -1, np.where(t_hit & ~s_hit, 1,
                             np.where(s_hit & ~t_hit, -1, first)))
            live &= ~(t_hit | s_hit)

        y[offset + idx] = (first == 1).astype(np.int64)
        usable[offset + idx] = True
        hit_target += int((first == 1).sum())
        hit_stop += int((first == -1).sum())
        timed_out += int((first == 0).sum())
        both += int(touched_both.sum())
        offset += n

    total = hit_target + hit_stop + timed_out
    stats = {
        "stopAtr": stop_atr, "targetAtr": target_atr,
        "rows": total,
        "hitTarget": hit_target, "hitStop": hit_stop, "timedOut": timed_out,
        "touchedBoth": both,
        "targetShare": round(hit_target / total, 5) if total else 0.0,
        "stopShare": round(hit_stop / total, 5) if total else 0.0,
        "timeoutShare": round(timed_out / total, 5) if total else 0.0,
    }
    return y, usable, stats
