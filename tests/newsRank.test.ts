// Which headlines reach the asset page's top block. Run with `npm run test:web`.
//
// Every case below is a real stored row, quoted. That is deliberate: a keyword ranker is only
// ever as good as the examples it was written against, and a test file of invented headlines
// would drift away from the News table without ever going red. When this ranker gets something
// wrong in production, the fix is to paste the row in here first.
//
// What these tests guard is the *order*, not the wording of any one rule. The patterns in
// `lib/newsRank.ts` are meant to be argued with and edited; the properties asserted here are
// the ones that must survive the editing.

import { test } from "node:test";
import assert from "node:assert/strict";
import { rankHeadline, rankHeadlines } from "../lib/newsRank.ts";

/// Attock Refinery on 2026-10-01, as stored. This is the set that produced the complaint: the
/// awards item was newest, so a newest-first top block led with it and pushed a $5bn government
/// upgrade programme and a 50,000 bpd refinery plan below the fold.
const ATRL = [
  {
    title: "Attock Refinery secures 1st position in labour category at GCNP Sustainability Awards - The Nation (Pakistan )",
    publisher: "The Nation (Pakistan )",
    publishedAt: "2026-10-01",
    outlets: 1,
    lineageId: "l-awards",
    isOriginal: true,
  },
  {
    title: "Attock Refinery plans 50,000-bpd deep-conversion refinery - The News Pakistan",
    publisher: "The News Pakistan",
    publishedAt: "2026-09-28",
    outlets: 3,
    lineageId: "l-refinery",
    isOriginal: false,
  },
  {
    title: "Attock Refinery plans new 50,000 bpd deep-conversion refinery - Business Recorder",
    publisher: "Business Recorder",
    publishedAt: "2026-09-28",
    outlets: 3,
    lineageId: "l-refinery",
    isOriginal: true,
  },
  {
    title: "4 local refineries sign $5bn upgradation deals with govt to improve quality, production - Dawn",
    publisher: "Dawn",
    publishedAt: "2026-09-24",
    outlets: 1,
    lineageId: "l-deals",
    isOriginal: true,
  },
];

test("a newer awards item does not outrank an older refinery programme", () => {
  const ranked = rankHeadlines(ATRL);
  // The thing the reader came for is first, three days older than the awards item.
  assert.match(ranked[0].title, /deep-conversion refinery/);
  assert.match(ranked[1].title, /\$5bn upgradation deals/);
  // And the awards item is last rather than removed: it is a real event about a real company,
  // it is simply not a reason to hold or sell a refinery.
  assert.match(ranked[ranked.length - 1].title, /Sustainability Awards/);
});

test("one story takes one slot, however many desks carried it", () => {
  const ranked = rankHeadlines(ATRL);
  const refinery = ranked.filter((r) => /deep-conversion/.test(r.title));
  assert.equal(refinery.length, 1);
  // The original report represents the story, not whichever copy sorted first.
  assert.equal(refinery[0].publisher, "Business Recorder");
  assert.equal(new Set(ranked.map((r) => r.lineageId)).size, ranked.length);
});

test("the outlet count outweighs a single material word", () => {
  // Three desks and one matched group beats one desk and one matched group. This is the only
  // term in the score that is not a guess about language, which is why it is the heaviest.
  const three = rankHeadline("Attock Refinery plans new 50,000 bpd refinery", "Business Recorder", 3);
  const one = rankHeadline("Attock Refinery plans new 50,000 bpd refinery", "Business Recorder", 1);
  assert.ok(three.score > one.score);
});

test("an unclustered row counts as one outlet and is not dropped", () => {
  // Null is the state of a row `jobs/lineage.py` has not reached yet. It must read as one desk,
  // never as none, or a fresh row would be scored as though nobody had published it.
  assert.equal(
    rankHeadline("Meezan Bank housing finance surpasses Rs3bn under GHTA", "Business Recorder", null).score,
    rankHeadline("Meezan Bank housing finance surpasses Rs3bn under GHTA", "Business Recorder", 1).score,
  );
});

test("consumer gadget coverage is not a business story", () => {
  // Thirteen consecutive AAPL rows looked like this. None of them is about Apple's business.
  for (const title of [
    "Buying a New iPhone 18 or Android Phone? Read These Tips Before You Spend Your Cash - CNET",
    "The iPhone Duo Might Not Support Your Old MagSafe Accessories — Here's Why - bgr.com",
    "Why I can't wait to swap this iPhone 18 Pro Max for an iPhone Duo - AppleInsider",
    "Some iPhone 18 Pro and Max users say the devices' color is already fading - mashable.com",
    "How to find compromised passwords on iPhone and Android - Fox News",
  ]) {
    assert.equal(rankHeadline(title, "CNET", 1).relevant, false, title);
  }
});

test("sport is dropped by publisher as well as by wording", () => {
  // Cricinfo has 26 rows in the News table, matched into an industry feed. Nothing from that
  // desk is about a listed company, whatever the headline happens to say.
  const r = rankHeadline("Pakistan name squad for the T20 series", "Cricinfo", 1);
  assert.equal(r.relevant, false);
  assert.ok(r.score < 0);
});

test("an upgrade is a rating only when something says whose it is", () => {
  // "iPhone Duo can be just $9/month with trade-in using Apple Upgrade" scored as an analyst
  // rating on a bare /upgrades?/ pattern. A trade-in programme is not a broker's opinion.
  const tradeIn = rankHeadline(
    "iPhone Duo can be just $9/month with trade-in using Apple Upgrade", "9to5Mac", 1,
  );
  assert.ok(!tradeIn.material.includes("rating"));

  const real = rankHeadline("Morgan Stanley upgrades Apple to overweight", "Reuters", 1);
  assert.ok(real.material.includes("rating"));

  // And a refinery upgrade programme is capacity, which is the group that actually describes it.
  const plant = rankHeadline(
    "4 local refineries sign $5bn upgradation deals with govt", "Dawn", 1,
  );
  assert.ok(plant.material.includes("capacity"));
});

test("a pre-order queue is not demand", () => {
  // "when you can start the iPhone Duo pre-order process" matched a bare /orders?/. An order
  // book is a business fact; a shopper's queue is a retail one.
  const preorder = rankHeadline(
    "Apple announces when you can start the iPhone Duo pre-order process", "9to5Mac", 1,
  );
  assert.ok(!preorder.material.includes("demand"));
  assert.ok(rankHeadline("Record $13 billion iPhone exports from India", "ET", 1).material.includes("demand"));
});

test("a headline with nothing either way is kept, not dropped", () => {
  // Relevance is not the same question as the score. An unremarkable company headline scores 0
  // and is still a company headline; only a row that is positively off-topic is removed.
  const r = rankHeadline("Meezan Bank Number of Employees 2026", "Revelio Labs", 1);
  assert.equal(r.score, 0);
  assert.equal(r.relevant, true);
});

test("recency decides between two equally material stories", () => {
  const ranked = rankHeadlines([
    { title: "Company wins contract worth $1bn", publisher: "Reuters", publishedAt: "2026-09-01", outlets: 1, lineageId: "a" },
    { title: "Company wins contract worth $2bn", publisher: "Reuters", publishedAt: "2026-09-20", outlets: 1, lineageId: "b" },
  ]);
  assert.match(ranked[0].title, /\$2bn/);
});

test("ranking never invents or rewrites a headline", () => {
  // The top block quotes stored titles. A ranker that edited one would be writing the only
  // unsourced claim on the page.
  const ranked = rankHeadlines(ATRL);
  for (const r of ranked) {
    assert.ok(ATRL.some((a) => a.title === r.title && a.publisher === r.publisher));
  }
});
