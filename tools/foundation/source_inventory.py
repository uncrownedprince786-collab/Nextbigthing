"""One authoritative source-to-training inventory, assembled from the manifests already written.

    python tools/foundation/source_inventory.py

Writes `data/foundation/dataset/source_inventory.json`. Reads committed manifests and the durable
dataset copy; no network, no database.

**The three questions this separates**, because conflating them is how a project convinces itself
it has data it has not got:

  1. Is it *downloaded*? A website having a dataset is not possession.
  2. Is it *validated*? A file on disk is not a checked file.
  3. Is it *joined into training examples*? A validated artifact sitting beside `examples-v3` is
     not a feature in it.

Every layer below answers all three, and the third answer is `false` far more often than the
first. That is not a failure; it is the honest shape of a research corpus whose first training
task is price-and-volume direction classification.

Status vocabulary: `COMPLETE`, `PARTIAL`, `MISSING`, `SOURCE_BLOCKED`, `LICENSE_BLOCKED`,
`NOT_APPLICABLE`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
F = ROOT / "data" / "foundation"
OUT = F / "dataset" / "source_inventory.json"


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None


def main() -> int:
    bench = load(F / "benchmarks" / "manifest.json") or {}
    macro = load(F / "macro" / "manifest.json") or {}
    crisis = load(F / "crisis_2008" / "manifest.json") or {}
    press = load(F / "events" / "press_evidence_manifest.json") or {}
    events = load(F / "events" / "events.json") or {}
    react = load(F / "events" / "reactions_manifest.json") or {}
    princ = load(F / "principles" / "principles.json") or {}
    surv = load(F / "survivorship" / "sec_lifecycle.json") or {}
    regimes = load(F / "dataset" / "regime_coverage.json") or {}
    hist = load(F / "dataset" / "historical_regimes.json") or {}
    ready = load(F / "dataset" / "readiness.json") or {}
    acq = load(F / "acquisition" / "manifest.json") or {}

    layers = [
        {
            "layer": "prices / OHLCV (instrument level)",
            "source": "PSX daily archive, Yahoo Finance, Yahoo Karachi listing, Coinbase, Kraken",
            "access": "free public endpoints, no key",
            "range": "2018-01-01 .. 2026-10-15",
            "rows": 1098074, "assets": 616,
            "downloaded": True, "validated": True, "joinedIntoTraining": True,
            "artifact": "Neon PriceSnapshot + nbt-private backups",
            "status": "COMPLETE",
            "evidence": "regime_coverage.json yearlyCoverage; US 1.0000 every year, PSX 0.8476->0.9985",
        },
        {
            "layer": "market / index benchmarks (deep history)",
            "source": "Yahoo chart API, FRED",
            "access": "free, no key",
            "range": "1927-12-30 .. 2026-10-14",
            "series": len(bench.get("series", {})),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/benchmarks/ (13 series)",
            "status": "COMPLETE",
            "evidence": "historical_regimes.json: 1929 -86.19%, 1987 -33.51%, 2008 -56.78% all "
                        "measured from these series",
            "whyNotJoined": "used for regime identification and event benchmarking, not as a "
                            "per-instrument feature",
        },
        {
            "layer": "corporate actions",
            "source": "derived from two independent price providers",
            "access": "free",
            "range": "2018 .. 2026",
            "records": 237,
            "downloaded": True, "validated": True, "joinedIntoTraining": True,
            "artifact": "data/foundation/price_verification/unadjusted_actions.json",
            "status": "PARTIAL",
            "evidence": "237 actions across 150 assets drive dataQuality.unadjustedActionInWindow "
                        "on 24,224 rows",
            "limitation": "detected from price behaviour, not from an issuer action feed; a "
                          "split with no price signature would be missed",
        },
        {
            "layer": "macroeconomic series (point-in-time)",
            "source": "FRED / ALFRED",
            "access": "free, no key",
            "range": "2010-01-01 .. 2026-10",
            "series": len(macro.get("series", {})),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/macro/ + dataset/macro/macro-sessions.jsonl.gz",
            "status": "COMPLETE",
            "evidence": "every row carries availableAt; 10 series revision-tracked from 400 "
                        "ALFRED snapshots each; 0 observations dated after their session",
            "whyNotJoined": "ships inside the dataset bundle and is joinable on date; not "
                            "pre-joined into example rows",
        },
        {
            "layer": "interest rates and yield curve",
            "source": "FRED (DGS10, DGS2, DGS3MO, T10Y2Y, T10Y3M, DFF)",
            "access": "free",
            "range": "1954-07-01 .. 2026-10",
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "benchmarks/ and macro/",
            "status": "COMPLETE",
        },
        {
            "layer": "banking and credit stress (2008 window)",
            "source": "FDIC BankFind, FRED (TEDRATE, DRSFRMACBS, WALCL, CSUSHPINSA)",
            "access": "free public API",
            "range": "2005-01-01 .. 2012-12-31",
            "records": (crisis.get("bankFailures") or {}).get("records"),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/crisis_2008/",
            "status": "COMPLETE",
            "evidence": "unemployment peaks 10.00% 2009-10; TED spread 4.58 on 2008-10-10; "
                        "Case-Shiller -27.4% peak to trough; 481 bank failures and assistance",
            "whyNotJoined": "the crisis predates the instrument history by a decade",
        },
        {
            "layer": "credit spreads (2008 window)",
            "source": "ICE BofA via FRED",
            "access": "free but licence-limited",
            "range": "rolling three years only",
            "downloaded": False, "validated": False, "joinedIntoTraining": False,
            "status": "LICENSE_BLOCKED",
            "evidence": "BAMLH0A0HYM2 returns data only from 2023-10-16; ICE licensing limits "
                        "FRED to a rolling window. TEDRATE used instead",
        },
        {
            "layer": "gold and commodities",
            "source": "Yahoo (GC=F, BZ=F), FRED (DCOILWTICO)",
            "access": "free",
            "range": "1986-01-02 .. 2026-10",
            "downloaded": True, "validated": True, "joinedIntoTraining": True,
            "artifact": "benchmarks/ and PriceSnapshot (8 commodity instruments)",
            "status": "COMPLETE",
        },
        {
            "layer": "instrument identity and lifecycle",
            "source": "SEC EDGAR submissions + company_tickers",
            "access": "free, contact User-Agent required",
            "records": surv.get("removalsResolved"),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/survivorship/sec_lifecycle.json",
            "status": "COMPLETE",
            "evidence": "all 127 S&P removals resolved: 65 still listed, 62 absent, 12 renamed",
        },
        {
            "layer": "delisted instrument price history",
            "source": "Yahoo download, Yahoo v8 chart, stooq",
            "access": "free but unavailable",
            "downloaded": False, "validated": False, "joinedIntoTraining": False,
            "status": "SOURCE_BLOCKED",
            "evidence": "Yahoo 404s both endpoints for delisted tickers; stooq answers a bot "
                        "challenge this project will not circumvent; EDGAR has no prices. "
                        "63 of 127 removals have no recoverable bars",
            "impact": "survivorship bias stays a measured lower bound",
        },
        {
            "layer": "PSX history before 2013-11-04",
            "source": "PSX daily archive; KSE-100 EOD endpoint; Karandaaz file",
            "access": "free / private",
            "downloaded": False, "validated": False, "joinedIntoTraining": False,
            "status": "SOURCE_BLOCKED",
            "evidence": "GET of 2008-08-27 and 2013-11-01 both return 404; 2013-11-04 returns "
                        "430 symbols. The archive floor is 2013-11-04. The public KSE-100 "
                        "endpoint starts 2021-10-15 and the 2018-2021 segment is private",
            "impact": "no Pakistani market evidence for the 2008 crisis or any earlier episode",
        },
        {
            "layer": "dated events corpus",
            "source": "Wikipedia + Wikidata verified, SEC filings",
            "access": "free",
            "records": len([e for e in events.get("events", []) if e.get("verified")]),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/events/events.json; Event/EventLink in the database",
            "status": "COMPLETE",
            "evidence": "168 verified, every one with a disposition; 176 historical Event rows, "
                        "642 EventLink rows",
        },
        {
            "layer": "press and original-document evidence",
            "source": "GDELT GKG archive, GDELT DOC API, SEC EDGAR filings",
            "access": "free; DOC API rate-limited",
            "records": press.get("pressReferenceRecords"),
            "publishers": press.get("distinctPublishers"),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/events/press_evidence.jsonl",
            "status": "PARTIAL",
            "evidence": f"dispositions {press.get('dispositionCounts')}",
            "limitation": "148 of 168 events carry press references; 2 searched-no-match, "
                          "6 source-limited where the archive file is absent",
        },
        {
            "layer": "operational news feed",
            "source": "Google News RSS and per-asset feeds",
            "access": "free",
            "range": "a rolling ~37-day window",
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "status": "PARTIAL",
            "evidence": "jobs/retention.py prunes News at 70 days by design; this is operational "
                        "freshness, not a historical corpus",
        },
        {
            "layer": "event-to-market reactions",
            "source": "derived from stored prices and benchmarks",
            "records": react.get("rowsWritten"),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/events/reactions.jsonl.gz",
            "status": "COMPLETE",
            "evidence": "167 rows over 1/5/20/60 sessions; 0 before-states dated on or after "
                        "their event; 0 forward windows starting at or before it",
        },
        {
            "layer": "books, references and testable principles",
            "source": "academic papers with DOIs, verified at Crossref",
            "records": (princ.get("summary") or {}).get("principles"),
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "data/foundation/principles/principles.json",
            "status": "PARTIAL",
            "evidence": f"{(princ.get('summary') or {}).get('citationsVerified')} citations "
                        f"verified; {(princ.get('summary') or {}).get('testableNow')} testable "
                        f"now; {(princ.get('summary') or {}).get('withRunnableRule')} with a "
                        "runnable rule",
            "limitation": "bibliographic records and extracted findings only. No copyrighted "
                          "book text is stored; a principle is a hypothesis, not an edge",
        },
        {
            "layer": "regime episodes",
            "source": "derived from benchmarks and stored prices",
            "downloaded": True, "validated": True, "joinedIntoTraining": False,
            "artifact": "regime_coverage.json (2018+, with dataset representation) and "
                        "historical_regimes.json (1927+, benchmark evidence only)",
            "status": "COMPLETE",
            "evidence": f"{len(hist.get('namedEpisodes', []))} named episodes measured; "
                        "4 of them sit inside the training window",
        },
        {
            "layer": "training examples",
            "source": "assembled from the above by data-assemble.yml",
            "rows": (ready.get("authoritativeDataset") or {}).get("rows"),
            "downloaded": True, "validated": True, "joinedIntoTraining": True,
            "artifact": (ready.get("authoritativeDataset") or {}).get("durableLocation"),
            "status": "COMPLETE",
            "evidence": "15 price/volume features + outcomes; leakage 0/0; 9 of 9 content "
                        "digests verified; effective independent examples ~54,277",
        },
    ]

    joined = [x for x in layers if x.get("joinedIntoTraining")]
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "source-inventory-v1",
        "threeQuestions": ["downloaded", "validated", "joinedIntoTraining"],
        "note": ("a website having a dataset is not possession; a file on disk is not a checked "
                 "file; a checked artifact beside the dataset is not a feature in it"),
        "layers": layers,
        "summary": {
            "layers": len(layers),
            "byStatus": {s: sum(1 for x in layers if x["status"] == s)
                         for s in sorted({x["status"] for x in layers})},
            "joinedIntoTraining": len(joined),
            "joinedLayers": [x["layer"] for x in joined],
            "preservedButNotJoined": [x["layer"] for x in layers
                                      if not x.get("joinedIntoTraining")
                                      and x["status"] in ("COMPLETE", "PARTIAL")],
        },
        "checksums": {
            "regime_coverage.json": sha(F / "dataset" / "regime_coverage.json"),
            "historical_regimes.json": sha(F / "dataset" / "historical_regimes.json"),
            "readiness.json": sha(F / "dataset" / "readiness.json"),
            "press_evidence.jsonl": sha(F / "events" / "press_evidence.jsonl"),
            "crisis_2008/manifest.json": sha(F / "crisis_2008" / "manifest.json"),
            "acquisitionManifestVersion": acq.get("version"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"{'layer':<44}{'status':<18}{'down':>5}{'valid':>6}{'joined':>7}")
    for x in layers:
        print(f"  {x['layer'][:42]:<44}{x['status']:<18}"
              f"{str(x.get('downloaded'))[:5]:>5}{str(x.get('validated'))[:5]:>6}"
              f"{str(x.get('joinedIntoTraining'))[:5]:>7}")
    print(f"\nby status: {payload['summary']['byStatus']}")
    print(f"joined into training: {len(joined)} of {len(layers)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
