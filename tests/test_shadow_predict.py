"""A shadow prediction must say what it was built from, and refuse when it cannot.

    python -m unittest discover -s tests -p test_shadow_predict.py -v

Stdlib unittest, no database, no network, no artifact on disk: the model here is synthetic, so
these run anywhere in well under a second and do not depend on which candidate happens to be
trained.

The property under test is not "does it predict". It is that a prediction built from imputed
averages cannot look like one built from observed evidence. At training an absent feature takes
the training fold's mean, which is measured and fine; at inference the same rule silently turns a
failed macro refresh into "an average day". So three things are pinned:

* a feature the model **usually had** and now lacks downgrades the record to `degraded`;
* a feature the model **usually lacked anyway** -- `entryTrigger` is null on about 90% of training
  rows, because a trigger only exists when there is one -- is imputed, listed, and does **not**
  degrade anything, or the word would mean nothing;
* a **critical** input missing produces no prediction at all, not a prediction with a caveat.

The second of those is here because the first version of the producer got it wrong in both
directions: it first refused 24 of 25 real rows by treating every price feature as critical, then
called every row degraded once that was fixed. Both are recorded in the module's own comments.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import shadow_predict as sp  # noqa: E402
from context_features import ContextSource  # noqa: E402

PRICE = ["r20", "returnZ", "entryTrigger"]
CTX = ContextSource.feature_names()
FEATURES = PRICE + CTX

#: What the model saw while training. `entryTrigger` is routinely absent; `r20` and `returnZ`
#: almost never are; `ctx_mktEventsIn90d` sits in between, which is the band that degrades.
NULL_SHARE = {"r20": 0.0, "returnZ": 0.0, "entryTrigger": 0.9,
              **{c: (0.95 if c.startswith("ctx_own") or "Prior" in c or "prior" in c else 0.0)
                 for c in CTX}}
NULL_SHARE["ctx_mktEventsIn90d"] = 0.25           # had it most of the time, not always


def a_model() -> dict:
    n = len(FEATURES)
    rng = np.random.default_rng(7)
    return {
        "meta": {"productionApproved": False},
        "manifest": {},
        "features": list(FEATURES),
        "classes": ["DOWN", "FLAT", "UP"],
        "W": rng.normal(0, 0.3, size=(n + 1, 3)),
        "mu": np.zeros(n), "sd": np.ones(n),
        "sha256": "deadbeef" * 8,
        "version": "test-model-v1",
        "featureSchema": "context-features-v2",
        "datasetVersion": "examples-v4-context",
        "critical": sorted(k for k, v in NULL_SHARE.items() if v < sp.CRITICAL_NULL_SHARE),
        "trainingNullShare": dict(NULL_SHARE),
    }


def a_ctx_block(macro_status="observed", **overrides) -> dict:
    f = {c: 1.0 for c in CTX}
    f.update(overrides)
    return {
        "macro": {"status": macro_status, "asOf": "2026-09-24", "ageDays": 1,
                  "f": {k: v for k, v in f.items() if k.startswith("macro_")}},
        "events": {"status": "observed",
                   "f": {k: v for k, v in f.items() if k.startswith("ctx_") and "Press" not in k
                         and "Prior" not in k and "matured" not in k}},
        "press": {"status": "observed",
                  "f": {k: v for k, v in f.items() if "Press" in k}},
        "reactionPrior": {"status": "observed",
                          "f": {k: v for k, v in f.items()
                                if "matured" in k or "Prior" in k}},
        "quality": {"status": "observed", "f": {}},
        "news": {"status": "excluded", "f": {}},
    }


def run(price: dict, block, model=None) -> dict:
    return sp.predict_one(model or a_model(), price, block, asset_id="a1", symbol="AAPL",
                          market="US", as_of=date(2026, 9, 25))


FULL_PRICE = {"r20": 1.0, "returnZ": 0.5, "entryTrigger": 2.0}


class ACompletePredictionSaysSo(unittest.TestCase):

    def test_everything_observed_is_ok_with_nothing_imputed(self):
        r = run(FULL_PRICE, a_ctx_block())
        self.assertEqual(r["quality"], sp.OK)
        self.assertEqual(r["imputed"], [])
        self.assertIn(r["predicted"], ("DOWN", "FLAT", "UP"))
        self.assertAlmostEqual(sum(r["scores"].values()), 1.0, places=6)

    def test_the_record_traces_to_the_exact_artifact(self):
        r = run(FULL_PRICE, a_ctx_block())
        self.assertEqual(r["modelVersion"], "test-model-v1")
        self.assertEqual(r["modelSha256"], "deadbeef" * 8)
        self.assertEqual(r["featureSchema"], "context-features-v2")
        self.assertFalse(r["approved"])

    def test_the_maturity_date_is_after_the_session(self):
        r = run(FULL_PRICE, a_ctx_block())
        self.assertGreater(r["maturesAfter"], r["asOf"])
        self.assertEqual(r["horizonSessions"], 20)

    def test_input_freshness_is_carried_rather_than_re_derived(self):
        r = run(FULL_PRICE, a_ctx_block())
        self.assertEqual(r["macroAsOf"], "2026-09-24")
        self.assertEqual(r["macroAgeDays"], 1)


class AnExpectedAbsenceIsNotADegradation(unittest.TestCase):
    """Or the word stops meaning anything: `entryTrigger` is null on ~90% of training rows."""

    def test_a_routinely_absent_feature_is_imputed_listed_and_still_ok(self):
        r = run({"r20": 1.0, "returnZ": 0.5, "entryTrigger": None}, a_ctx_block())
        self.assertEqual(r["quality"], sp.OK)
        self.assertIn("entryTrigger", r["imputed"])
        self.assertIn("entryTrigger", r["imputedExpected"])
        self.assertEqual(r["imputedUnexpected"], [])

    def test_the_own_scope_context_columns_are_expected_absences(self):
        r = run(FULL_PRICE, a_ctx_block(ctx_ownEventsIn90d=None, ctx_ownPressIn90d=None))
        self.assertEqual(r["quality"], sp.OK)
        self.assertIn("ctx_ownEventsIn90d", r["imputedExpected"])


class ARealDegradationIsNamed(unittest.TestCase):

    def test_a_feature_the_model_usually_had_is_an_unexpected_imputation(self):
        r = run(FULL_PRICE, a_ctx_block(ctx_mktEventsIn90d=None))
        self.assertEqual(r["quality"], sp.DEGRADED)
        self.assertEqual(r["imputedUnexpected"], ["ctx_mktEventsIn90d"])
        self.assertIsNotNone(r["predicted"], "a degradation still predicts; it does not refuse")

    def test_a_degraded_record_still_lists_every_imputed_feature(self):
        r = run({"r20": 1.0, "returnZ": 0.5, "entryTrigger": None},
                a_ctx_block(ctx_mktEventsIn90d=None))
        self.assertEqual(r["quality"], sp.DEGRADED)
        self.assertIn("entryTrigger", r["imputed"])
        self.assertIn("ctx_mktEventsIn90d", r["imputed"])


class ACriticalAbsenceRefuses(unittest.TestCase):
    """No prediction at all. A refusal that still carried a class would be the failure this
    whole module is about, only harder to notice."""

    def test_a_missing_critical_price_feature_produces_no_prediction(self):
        r = run({"r20": None, "returnZ": 0.5, "entryTrigger": 2.0}, a_ctx_block())
        self.assertEqual(r["quality"], sp.REFUSED)
        self.assertIsNone(r["predicted"])
        self.assertIsNone(r["scores"])
        self.assertTrue(any("r20" in m for m in r["missingCritical"]))

    def test_a_failed_macro_refresh_refuses_rather_than_averaging_twenty_inputs(self):
        r = run(FULL_PRICE, a_ctx_block(macro_status="absent"))
        self.assertEqual(r["quality"], sp.REFUSED)
        self.assertIsNone(r["predicted"])
        self.assertTrue(any("macro block" in m for m in r["missingCritical"]))

    def test_no_context_block_at_all_refuses(self):
        r = run(FULL_PRICE, None)
        self.assertEqual(r["quality"], sp.REFUSED)
        self.assertIsNone(r["predicted"])

    def test_a_refusal_still_records_what_it_tried_and_why(self):
        r = run({"r20": None, "returnZ": 0.5, "entryTrigger": 2.0}, a_ctx_block())
        self.assertEqual(r["modelVersion"], "test-model-v1")
        self.assertGreater(r["imputedCount"], 0)
        self.assertTrue(r["missingCritical"])
        self.assertFalse(r["approved"])


class TheToolRefusesAnApprovedModel(unittest.TestCase):
    """This path serves experiments. If an artifact ever claims approval, it is not this tool's
    to serve, and failing loudly is better than quietly shadow-running a production model."""

    def test_load_model_refuses_when_production_approved_is_not_false(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "model.json").write_text(json.dumps({
                "modelVersion": "x", "features": ["a"], "classes": ["DOWN", "FLAT", "UP"],
                "weights": [[0, 0, 0], [0, 0, 0]],
                "standardisation": {"mean": [0.0], "sd": [1.0]},
                "productionApproved": True}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                sp.load_model(p)


class TheCriticalSetComesFromTheModelsOwnExperience(unittest.TestCase):

    def test_a_column_the_model_rarely_saw_is_not_critical(self):
        m = a_model()
        self.assertIn("r20", m["critical"])
        self.assertNotIn("entryTrigger", m["critical"])

    def test_the_thresholds_are_ordered_so_the_bands_cannot_overlap(self):
        self.assertLess(sp.CRITICAL_NULL_SHARE, sp.ROUTINELY_ABSENT_NULL_SHARE)


class ARecordedCallMustHaveABasePrice(unittest.TestCase):
    """An outcome is a move from the close the call was read from. No close, no measurement."""

    def test_a_live_call_with_no_reference_price_is_refused(self):
        r = sp.predict_one(a_model(), FULL_PRICE, a_ctx_block(), asset_id="a1", symbol="AA",
                           market="US", as_of=date(2026, 10, 18), reference_price=None,
                           require_reference_price=True)
        self.assertEqual(r["quality"], sp.REFUSED)
        self.assertIsNone(r["predicted"])
        self.assertTrue(any("base price" in m for m in r["missingCritical"]))

    def test_the_same_call_with_a_reference_price_is_not_refused(self):
        r = sp.predict_one(a_model(), FULL_PRICE, a_ctx_block(), asset_id="a1", symbol="AA",
                           market="US", as_of=date(2026, 10, 18), reference_price=12.5,
                           require_reference_price=True)
        self.assertNotEqual(r["quality"], sp.REFUSED)
        self.assertEqual(r["referencePrice"], 12.5)

    def test_a_non_live_caller_is_not_made_to_produce_a_base(self):
        # The dataset path is diagnostic and the price may legitimately be absent there; only a
        # live call, which is the one that becomes evidence, refuses.
        r = run(FULL_PRICE, a_ctx_block())          # reference_price defaults to None
        self.assertNotEqual(r["quality"], sp.REFUSED)


class ACanaryIsBalancedAcrossMarkets(unittest.TestCase):
    """A canary that takes the alphabet's first names measures the alphabet, not the markets."""

    def _rows(self):
        # Deliberately: two US-first names, then the coin the stored market column calls US.
        return [
            {"symbol": "AA", "assetType": "stock", "market": "US"},
            {"symbol": "AAL", "assetType": "stock", "market": "US"},
            {"symbol": "AAPL", "assetType": "stock", "market": "US"},
            {"symbol": "aave-new", "assetType": "crypto", "market": "US"},
            {"symbol": "ABOT", "assetType": "stock", "market": "PK"},
        ]

    def test_per_market_keeps_at_most_n_in_row_order(self):
        got = sp.select_rows(self._rows(), None, 2)
        self.assertEqual([r["symbol"] for r in got], ["AA", "AAL", "aave-new", "ABOT"])

    def test_a_market_filter_uses_the_derived_market_not_the_stored_one(self):
        got = sp.select_rows(self._rows(), "Crypto", 0)
        self.assertEqual([r["symbol"] for r in got], ["aave-new"])
        self.assertEqual(got[0]["market"], "Crypto")

    def test_a_stock_is_filed_by_its_stored_market(self):
        self.assertEqual(sp.market_for_row({"assetType": "stock", "market": "PK"}), "PK")
        self.assertEqual(sp.market_for_row({"assetType": "stock", "market": "US"}), "US")


class ATradingSessionIsRequired(unittest.TestCase):
    """A call dated to a day its market was closed is dated to a session that never happened, so it
    can never be scored -- the same failure as a missing base, from the other side."""

    def test_a_weekday_market_call_dated_to_a_weekend_is_refused(self):
        r = sp.predict_one(a_model(), FULL_PRICE, a_ctx_block(), asset_id="a1", symbol="AAPL",
                           market="US", as_of=date(2026, 9, 26),   # a Saturday
                           reference_price=12.5, require_reference_price=True,
                           require_trading_session=True)
        self.assertEqual(r["quality"], sp.REFUSED)
        self.assertIsNone(r["predicted"])
        self.assertTrue(any("market is closed" in m or "trades" in m for m in r["missingCritical"]))

    def test_the_same_call_on_a_trading_day_is_not_refused(self):
        r = sp.predict_one(a_model(), FULL_PRICE, a_ctx_block(), asset_id="a1", symbol="AAPL",
                           market="US", as_of=date(2026, 9, 25),   # a Friday
                           reference_price=12.5, require_reference_price=True,
                           require_trading_session=True)
        self.assertNotEqual(r["quality"], sp.REFUSED)

    def test_crypto_trades_on_the_weekend_so_the_same_date_is_fine(self):
        r = sp.predict_one(a_model(), FULL_PRICE, a_ctx_block(), asset_id="c1", symbol="btc-bitcoin",
                           market="Crypto", as_of=date(2026, 9, 26),
                           reference_price=12.5, require_reference_price=True,
                           require_trading_session=True)
        self.assertNotEqual(r["quality"], sp.REFUSED)


class SessionsAreChosenPerMarket(unittest.TestCase):
    """One global `max(periodEnd)` was a session only crypto traded on 2026-10-18 (a Sunday); a US
    call dated to it would have matured against a close that never printed."""

    def test_each_market_gets_its_own_newest_session(self):
        sessions = {
            "US": [date(2026, 10, 16), date(2026, 10, 15)],
            "Crypto": [date(2026, 10, 18), date(2026, 10, 17)],
        }
        chosen, skipped = sp._choose_sessions(sessions, 2)
        self.assertEqual(chosen, {"US": date(2026, 10, 16), "Crypto": date(2026, 10, 18)})
        self.assertEqual(skipped, {})

    def test_a_market_that_has_fallen_behind_is_named_not_filled_from_an_old_date(self):
        sessions = {
            "US": [date(2026, 10, 16)],            # 4 US sessions before 2026-10-22
            "Crypto": [date(2026, 10, 22)],
        }
        chosen, skipped = sp._choose_sessions(sessions, 2)
        self.assertEqual(chosen, {"Crypto": date(2026, 10, 22)})
        self.assertEqual(skipped, {"US": 4})


class ThePerMarketCandidatesAreRouted(unittest.TestCase):
    """Each market must be served by the artifact built for it, all still unapproved."""

    def test_every_market_loads_its_own_candidate_and_none_is_approved(self):
        models = sp.load_market_models(sp.DEFAULT_MODELS_ROOT)
        self.assertEqual(sorted(models), sorted(sp.mk.MARKETS))
        for m, model in models.items():
            self.assertEqual(model["meta"]["productionApproved"], False)
            self.assertEqual(model["version"], f"brain-v4-{m.lower()}")

    def test_a_missing_artifact_refuses_rather_than_falling_back_to_the_global_model(self):
        with self.assertRaises(SystemExit):
            sp.load_market_models(sp.ROOT / "data" / "foundation" / "brain-nonexistent")


if __name__ == "__main__":
    unittest.main()

class TheScheduledCanaryRespectsTheStoredSessionCap(unittest.TestCase):
    def test_existing_rows_and_prior_inserts_share_one_market_session_budget(self):
        from types import SimpleNamespace
        from unittest import mock
        counts = {("US", "2026-10-19"): 1}
        class Cursor:
            rowcount = 0
            def execute(self, query, params=None):
                if query.startswith('SELECT COUNT(*)'):
                    self.result = {"n": counts.get(tuple(params), 0)}
                    self.rowcount = -1
                else:
                    key = (params[3], params[0])
                    counts[key] = counts.get(key, 0) + 1
                    self.rowcount = 1
            def fetchone(self): return self.result
            def close(self): pass
        class Connection:
            def __init__(self): self.cur = Cursor(); self.committed = False
            def cursor(self): return self.cur
            def commit(self): self.committed = True
            def close(self): pass
        connection = Connection()
        def record(asset_id, symbol):
            return {"asOf":"2026-10-19","assetId":asset_id,"symbol":symbol,"market":"US",
                "predicted":"UP","scores":{"UP":1.0},"modelVersion":"candidate","modelSha256":"digest",
                "featureSchema":"v1","datasetVersion":"v4","quality":"ok","imputed":[],"imputedCount":0,
                "missingCritical":None,"contextStatus":None,"macroAsOf":None,"macroAgeDays":None,
                "horizonSessions":20,"maturesAfter":"2026-11-16","strategy":"swing","timeframe":"swing",
                "referencePrice":100.0,"features":{"r20":0.1},"sources":None,"inputCutoff":"2026-10-19",
                "runId":"test-run","commit":"abc"}
        with mock.patch.dict(sys.modules, {"nbt": SimpleNamespace(db=lambda: connection)}):
            result = sp.write_rows([record("a2","MSFT"),record("a3","NVDA")], max_per_market_session=2)
        self.assertEqual(result, {"written":1,"status":"ok","skippedByCap":1})
        self.assertEqual(counts[("US","2026-10-19")],2)
        self.assertTrue(connection.committed)
