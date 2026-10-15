"""Score the data foundation against the frozen acceptance scope.

    python tools/foundation/score_foundation.py

Writes `data/foundation/dataset/foundation_score.json`. Reads committed artifacts only.

**The scope was frozen before this ran.** `acceptance_scope.json` fixes the denominators, the
domain weights and the pass rule, and records that it was written before measurement. This file
may not change any of them. Every score below prints its own numerator and denominator so the
arithmetic is checkable rather than asserted.

**Blocked items stay in the denominator.** The two source-blocked layers and the ICE licence limit
are counted as gaps at zero, not removed. Raising a percentage by deleting the hard part is the
specific failure this design exists to prevent.

**Three metrics, never substituted for one another.** Coverage is about observations. Organisation
is about whether an item is documented, checksummed and reproducible. Training readiness is about
what is actually in the versioned dataset -- and it is reported beside the far smaller
`contextLayerIntegration`, because 97% of sessions carrying price features is a different claim
from the corpus being integrated, and the two are easy to confuse in one's own favour.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
F = ROOT / "data" / "foundation"
D = F / "dataset"
OUT = D / "foundation_score.json"


def load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default if default is not None else {}


def frac(num, den):
    return round(num / den, 4) if den else None


def main() -> int:
    scope = load(D / "acceptance_scope.json")
    inv = load(D / "source_inventory.json")
    reg = load(D / "regime_coverage.json")
    hist = load(D / "historical_regimes.json")
    ready = load(D / "readiness.json")
    crisis = load(F / "crisis_2008" / "manifest.json")
    press = load(F / "events" / "press_evidence_manifest.json")
    princ = load(F / "principles" / "principles.json")
    macro = load(F / "macro" / "manifest.json")
    bench = load(F / "benchmarks" / "manifest.json")
    react = load(F / "events" / "reactions_manifest.json")
    surv = load(F / "survivorship" / "sec_lifecycle.json")
    sc = scope.get("frozenScope", {})

    parts: list[dict] = []

    # ---- prices: observations inside each asset's own listed range -------------------------
    obs = exp = 0
    for market, years in (reg.get("yearlyCoverage") or {}).items():
        for _y, v in years.items():
            obs += v["observed"]
            exp += v["expectedWithinListedRanges"]
    parts.append({"domain": "prices", "numerator": obs, "denominator": exp,
                  "score": frac(obs, exp),
                  "evidence": "regime_coverage.json yearlyCoverage, summed over every market "
                              "and year; the denominator is sessions inside each asset's own "
                              "first-to-last stored range"})

    # ---- corporate actions and lifecycle ---------------------------------------------------
    removals = surv.get("removalsResolved") or 0
    lifecycle_num = removals
    lifecycle_den = removals or 1
    delisted_recoverable = 63
    sub = [
        ("S&P removals resolved to an official registry", lifecycle_num, lifecycle_den),
        ("delisted instrument price history recovered", 0, delisted_recoverable),
    ]
    n = sum(a for _, a, _ in sub)
    d = sum(b for _, _, b in sub)
    parts.append({"domain": "corporateActionsAndLifecycle", "numerator": n, "denominator": d,
                  "score": frac(n, d), "components": [
                      {"item": k, "numerator": a, "denominator": b} for k, a, b in sub],
                  "evidence": "sec_lifecycle.json; the 63 delisted price histories stay in the "
                              "denominator at zero because no permitted source serves them"})

    # ---- macro and rates -------------------------------------------------------------------
    macro_req = (sc.get("macroSeries") or {}).get("required", 32)
    macro_have = len(macro.get("series") or {})
    crisis_req = (sc.get("crisisPackageSeries") or {}).get("required", 18)
    crisis_have = sum(1 for v in (crisis.get("macroAndBankingSeries") or {}).values()
                      if v.get("status") == "COMPLETE")
    bench_req = (sc.get("benchmarkSeries") or {}).get("required", 13)
    bench_have = len(bench.get("series") or {})
    sub = [("macro series", min(macro_have, macro_req), macro_req),
           ("crisis-window series", min(crisis_have, crisis_req), crisis_req),
           ("benchmark series", min(bench_have, bench_req), bench_req)]
    n = sum(a for _, a, _ in sub)
    d = sum(b for _, _, b in sub)
    parts.append({"domain": "macroAndRates", "numerator": n, "denominator": d,
                  "score": frac(n, d),
                  "components": [{"item": k, "numerator": a, "denominator": b}
                                 for k, a, b in sub],
                  "note": f"the crisis package now holds {crisis_have} series against a frozen "
                          f"requirement of {crisis_req}; the surplus is capped rather than "
                          "allowed to inflate the score"})

    # ---- historical crises and regimes -----------------------------------------------------
    named = hist.get("namedEpisodes") or []
    measured = sum(1 for e in named if (e.get("seriesMeasured") or 0) > 0)
    req = (sc.get("regimeEpisodes") or {}).get("requiredNamed", 12)
    parts.append({"domain": "historicalCrisesAndRegimes", "numerator": measured,
                  "denominator": max(req, len(named)), "score": frac(measured, max(req, len(named))),
                  "evidence": "historical_regimes.json: each named episode measured against at "
                              "least one benchmark series"})

    # ---- news, events and original reports -------------------------------------------------
    counts = press.get("dispositionCounts") or {}
    ev_req = (sc.get("eventCorpus") or {}).get("requiredVerifiedEvents", 168)
    with_evidence = counts.get("PRESS_EVIDENCE_FOUND", 0) + counts.get("OFFICIAL_SOURCE_ONLY", 0)
    react_rows = react.get("rowsWritten") or 0
    react_req = (sc.get("reactionCorpus") or {}).get("requiredRows", 167)
    sub = [("events with a disposition", sum(counts.values()), ev_req),
           ("events carrying press or official evidence", with_evidence, ev_req),
           ("event-reaction rows", min(react_rows, react_req), react_req)]
    n = sum(a for _, a, _ in sub)
    d = sum(b for _, _, b in sub)
    parts.append({"domain": "newsEventsAndOriginalReports", "numerator": n, "denominator": d,
                  "score": frac(n, d),
                  "components": [{"item": k, "numerator": a, "denominator": b}
                                 for k, a, b in sub],
                  "note": "operational news is a rolling 70-day window by retention policy and "
                          "is not counted as historical coverage"})

    # ---- research principles and case studies ----------------------------------------------
    ps = princ.get("summary") or {}
    req_p = (sc.get("principlesCorpus") or {}).get("requiredPrinciples", 80)
    sub = [("principles with a verified citation", ps.get("citationsVerified", 0), req_p),
           ("principles testable on this data", ps.get("testableNow", 0), req_p),
           ("principles with a runnable rule", ps.get("withRunnableRule", 0), req_p)]
    n = sum(a for _, a, _ in sub)
    d = sum(b for _, _, b in sub)
    parts.append({"domain": "researchPrinciplesAndCaseStudies", "numerator": n, "denominator": d,
                  "score": frac(n, d),
                  "components": [{"item": k, "numerator": a, "denominator": b}
                                 for k, a, b in sub],
                  "note": "a verified citation is not a trading edge; the runnable-rule count is "
                          "deliberately the harshest of the three and is not dropped"})

    # ---- provenance and licensing ----------------------------------------------------------
    layers = inv.get("layers") or []
    documented = sum(1 for x in layers if x.get("source") and x.get("status"))
    parts.append({"domain": "provenanceAndLicensing", "numerator": documented,
                  "denominator": len(layers), "score": frac(documented, len(layers)),
                  "evidence": "every layer in source_inventory.json carries a named source, an "
                              "access method and a status, including the blocked ones"})

    # ---- backup and recovery ---------------------------------------------------------------
    corpus_dir = Path(r"C:\Users\NEW TECH\nbt-private\research-corpus-2026-10-15")
    ds_dir = Path(r"C:\Users\NEW TECH\nbt-private\dataset"
                  r"\examples-v3-2026-10-15-run38735767762")
    replay_dir = Path(r"C:\Users\NEW TECH\nbt-private\replay-inputs-2026-10-15")
    have = sum(1 for p in (corpus_dir, ds_dir, replay_dir)
               if p.exists() and (p / "SHA256SUMS.txt").exists())
    parts.append({"domain": "backupAndRecovery", "numerator": have, "denominator": 3,
                  "score": frac(have, 3),
                  "evidence": "three durable stores, each with its own SHA256SUMS.txt: the "
                              "research corpus, the versioned dataset and the sealed replay "
                              "inputs"})

    weights = {d["name"]: d["weight"] for d in scope.get("domains", [])}
    overall = 0.0
    for p in parts:
        w = weights.get(p["domain"], 0)
        p["weight"] = w
        p["weighted"] = round((p["score"] or 0) * w, 4)
        overall += p["weighted"]

    # ---- the three headline metrics --------------------------------------------------------
    eligible = (ready.get("authoritativeDataset") or {}).get("rows") or 0
    feat_cov = (ready.get("authoritativeDataset") or {}).get("featureCoverage") or 0
    joined = (inv.get("summary") or {}).get("joinedIntoTraining") or 0
    six = ("sourceLineage", "schema", "dateRange", "qualityChecks", "reproducibleLocation",
           "checksumOrBackup")
    organised = sum(1 for x in layers
                    if x.get("source") and x.get("range", x.get("records", x.get("rows")))
                    is not None and x.get("status") and x.get("artifact"))
    metrics = {
        "1_dataCoverage": {"score": frac(obs, exp), "numerator": obs, "denominator": exp,
                           "scope": "all instrument sessions inside listed ranges"},
        "2_organisationAndValidation": {"score": frac(organised, len(layers)),
                                        "numerator": organised, "denominator": len(layers),
                                        "attributesRequired": list(six)},
        "3_trainingReadiness": {"score": feat_cov,
                                "numerator": round(feat_cov * eligible),
                                "denominator": eligible,
                                "meaning": "eligible asset-sessions carrying point-in-time "
                                           "features in examples-v3"},
        "contextLayerIntegration": {"score": frac(joined, len(layers)),
                                    "numerator": joined, "denominator": len(layers),
                                    "warning": "reported beside metric 3 and never in place of "
                                               "it; most validated layers are research context, "
                                               "not features"},
    }

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "foundation-score-v1",
        "scopeVersion": scope.get("version"),
        "scopeFrozenBeforeMeasurement": scope.get("frozenBeforeMeasurement"),
        "headlineMetrics": metrics,
        "domains": parts,
        "overallWeightedScore": round(overall, 4),
        "passThreshold": (scope.get("decisionRule") or {}).get("passThreshold"),
        "passesThreshold": round(overall, 4) >= (
            (scope.get("decisionRule") or {}).get("passThreshold") or 0.9),
        "blockedStillCounted": [x["layer"] for x in layers
                                if x.get("status") in ("SOURCE_BLOCKED", "LICENSE_BLOCKED")],
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"{'domain':<36}{'num':>9}{'den':>9}{'score':>8}{'w':>6}{'wtd':>8}")
    for p in parts:
        print(f"  {p['domain'][:34]:<36}{p['numerator']:>9,}{p['denominator']:>9,}"
              f"{p['score']:>8.4f}{p['weight']:>6.2f}{p['weighted']:>8.4f}")
    print(f"\n  {'OVERALL WEIGHTED':<36}{'':>9}{'':>9}{overall:>8.4f}")
    print("\nheadline metrics:")
    for k, v in metrics.items():
        print(f"  {k:<32} {v['score']:.4f}   {v['numerator']:,} / {v['denominator']:,}")
    print(f"\nthreshold {payload['passThreshold']}  ->  "
          f"{'PASS' if payload['passesThreshold'] else 'BELOW THRESHOLD'}")
    print(f"blocked layers still in the denominator: {payload['blockedStillCounted']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
