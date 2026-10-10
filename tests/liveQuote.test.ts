// Live quotes: what is shown beside a close, when a quote is stale, and how a stale one is refreshed.
//
// The properties worth testing are the ones where getting it wrong is silent: a quote that repeats the
// close and clutters every row, a stale quote presented as current, a provider answer that is not a
// price being displayed as one, and an on-demand fetch that a public endpoint could turn into a way to
// hammer a free provider.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  FETCH_TIMEOUT_MS, MEMO_TTL_MS, QUOTE_STALE_MS, clockUtc, fetchFreshQuote, isStale, makeMemo, quoteAgeMs, quoteBesideClose,
} from "../lib/liveQuote.ts";

const NOW = new Date("2026-10-10T12:00:00Z");
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();

// --- stale or not -----------------------------------------------------------------------------

test("a quote is stale after five minutes exactly, and a missing or unreadable one is stale", () => {
  assert.equal(QUOTE_STALE_MS, 300_000);
  assert.equal(isStale(ago(299_999), NOW), false);
  assert.equal(isStale(ago(300_000), NOW), false);
  assert.equal(isStale(ago(300_001), NOW), true);
  assert.equal(isStale(null, NOW), true);
  assert.equal(isStale(undefined, NOW), true);
  assert.equal(isStale("not a date", NOW), true);
  assert.equal(quoteAgeMs(ago(90_000), NOW), 90_000);
});

test("the clock is UTC and says so", () => {
  assert.equal(clockUtc("2026-10-09T19:59:00Z"), "19:59 UTC");
  assert.equal(clockUtc("2026-10-10T00:05:00+05:00"), "19:05 UTC");
  assert.equal(clockUtc("garbage"), "");
});

// --- what earns a line beside the close --------------------------------------------------------

test("a quote that only repeats the close is not shown, and one that adds something is", () => {
  const close = { price: 100, date: "2026-10-09" };
  // The same price struck on the same day: the market has closed and the last trade IS the close.
  assert.equal(quoteBesideClose({ price: 100, quotedAt: "2026-10-09T19:59:00Z" }, close), null);
  assert.equal(quoteBesideClose({ price: 100.04, quotedAt: "2026-10-09T19:59:00Z" }, close), null);
  // More than a twentieth of a percent away: a live market has moved since the close.
  assert.deepEqual(quoteBesideClose({ price: 100.06, quotedAt: "2026-10-09T19:59:00Z" }, close), {
    price: 100.06, quotedAt: "2026-10-09T19:59:00.000Z",
  });
  // Struck on a later day than the close, even at the same price: it is news that the close is old.
  assert.notEqual(quoteBesideClose({ price: 100, quotedAt: "2026-10-10T01:00:00Z" }, close), null);
  // No close at all: the quote is the only price there is.
  assert.notEqual(quoteBesideClose({ price: 5, quotedAt: "2026-10-10T01:00:00Z" }, { price: null, date: null }), null);
});

test("a quote that is not a price is never shown", () => {
  const close = { price: 100, date: "2026-10-09" };
  for (const price of [0, -1, NaN, Infinity]) {
    assert.equal(quoteBesideClose({ price, quotedAt: "2026-10-10T01:00:00Z" }, close), null, String(price));
  }
  assert.equal(quoteBesideClose({ price: 101, quotedAt: "garbage" }, close), null);
  assert.equal(quoteBesideClose(null, close), null);
});

// --- the on-demand fetch -----------------------------------------------------------------------

const respond = (body: unknown, ok = true) => async () => ({ ok, json: async () => body });
const yahoo = (price: unknown, time: number) => ({ chart: { result: [{ meta: { regularMarketPrice: price, regularMarketTime: time } }] } });
const nowS = Math.floor(NOW.getTime() / 1000);

test("a Yahoo answer is read for its price and the time it was struck", async () => {
  const q = await fetchFreshQuote({ source: "yahoo", ref: "AAPL" }, respond(yahoo(212.34, nowS - 60)), NOW);
  assert.deepEqual(q, { price: 212.34, quotedAt: new Date((nowS - 60) * 1000).toISOString() });
});

test("a CoinPaprika answer is read the same way", async () => {
  const body = { quotes: { USD: { price: 0.4321 } }, last_updated: "2026-10-10T11:59:00Z" };
  const q = await fetchFreshQuote({ source: "coinpaprika", ref: "ada-cardano" }, respond(body), NOW);
  assert.deepEqual(q, { price: 0.4321, quotedAt: "2026-10-10T11:59:00.000Z" });
});

test("anything that is not a clean price is no answer, never a made-up one", async () => {
  const bad: [string, unknown][] = [
    ["zero", yahoo(0, nowS)],
    ["negative", yahoo(-3, nowS)],
    ["string price", yahoo("212", nowS)],
    ["null price", yahoo(null, nowS)],
    ["no time", yahoo(212, NaN)],
    ["a time from the future", yahoo(212, nowS + 3600)],
    ["empty body", {}],
    ["wrong shape", { chart: { result: [] } }],
  ];
  for (const [name, body] of bad) {
    assert.equal(await fetchFreshQuote({ source: "yahoo", ref: "AAPL" }, respond(body), NOW), null, name);
  }
  assert.equal(await fetchFreshQuote({ source: "yahoo", ref: "AAPL" }, respond(yahoo(212, nowS), false), NOW), null, "HTTP error");
  assert.equal(
    await fetchFreshQuote({ source: "yahoo", ref: "AAPL" }, async () => { throw new Error("boom"); }, NOW),
    null,
    "a thrown error",
  );
});

test("a reference that is not an identifier never reaches a URL", async () => {
  let calls = 0;
  const spy = async () => (calls++, { ok: true, json: async () => yahoo(1, nowS) });
  for (const ref of ["", "A B", "../x", "a/b", "A?x=1", "x".repeat(40), "AAPL#frag"]) {
    assert.equal(await fetchFreshQuote({ source: "yahoo", ref }, spy, NOW), null, ref);
  }
  for (const ref of ["ADA", "ada cardano", "ada_cardano", "ADA-CARDANO"]) {
    assert.equal(await fetchFreshQuote({ source: "coinpaprika", ref }, spy, NOW), null, ref);
  }
  assert.equal(calls, 0);
});

test("the request is bounded: it carries an abort signal and gives up", async () => {
  assert.equal(FETCH_TIMEOUT_MS, 1500);
  let signal: AbortSignal | undefined;
  const hang = (_url: string, init: { signal: AbortSignal }) => {
    signal = init.signal;
    return new Promise<never>((_, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted"))));
  };
  const started = Date.now();
  const q = await fetchFreshQuote({ source: "yahoo", ref: "AAPL" }, hang as never, NOW);
  assert.equal(q, null);
  assert.ok(signal?.aborted);
  assert.ok(Date.now() - started < FETCH_TIMEOUT_MS + 1000, "it waited far longer than its own timeout");
});

// --- the memo ----------------------------------------------------------------------------------

test("an answer, including no answer, is reused for the time to live and not longer", () => {
  let t = 0;
  const memo = makeMemo<number | null>(MEMO_TTL_MS, () => t);
  assert.deepEqual(memo.get("k"), { hit: false });
  memo.set("k", null);
  assert.deepEqual(memo.get("k"), { hit: true, value: null });
  t = MEMO_TTL_MS - 1;
  assert.equal(memo.get("k").hit, true);
  t = MEMO_TTL_MS;
  assert.equal(memo.get("k").hit, false);
});

test("the memo is bounded, so a public endpoint cannot grow it without limit", () => {
  const t = 0;
  const memo = makeMemo<number>(MEMO_TTL_MS, () => t);
  for (let i = 0; i < 2600; i++) memo.set(`k${i}`, i);
  assert.equal(memo.get("k0").hit, false, "the oldest entries are evicted");
  assert.equal(memo.get("k2599").hit, true);
});
