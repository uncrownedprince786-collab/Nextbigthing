// Sub-cent prices: a fixed two decimals printed every coin under a cent as $0.00 or $0.01, so an
// entry band, its stop and its target all read the same. These pin the formats that replaced it.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { compactPrice, plainPrice, price } from "../lib/format.ts";

test("two decimals from a dollar, four under it, four significant digits under a cent", () => {
  assert.equal(price(510.08), "$510.08");
  assert.equal(price(121234.5), "$121,234.50");
  assert.equal(price(0.24), "$0.2400");
  assert.equal(price(0.005458), "$0.005458");
  assert.equal(price(0.000004036), "$0.000004036");
  assert.equal(price(0.0000001234), "$0.0000001234");
  assert.equal(plainPrice(0), "0.00");
  // A stop and a band a hair apart stay apart.
  assert.notEqual(price(0.00000395), price(0.0000045));
});

test("nothing that is not a number is ever printed as one", () => {
  for (const v of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    assert.equal(price(v), "not available");
    assert.equal(compactPrice(v), "not available");
  }
});

test("a narrow cell writes the zeros of a tiny price as a subscript count", () => {
  assert.equal(compactPrice(0.000004036), "$0.0₅4036");
  assert.equal(compactPrice(0.00000546), "$0.0₅546");
  assert.equal(compactPrice(0.00001), "$0.0₄1");
  assert.equal(compactPrice(0.0000001234), "$0.0₆1234");
  // The zeros are counted after rounding: just under a power of ten rounds up to it, never down a
  // factor of ten. 0.0000099999 printed as $0.0₅1 (0.000001) before.
  assert.equal(compactPrice(0.0000099999), "$0.0₄1");
  assert.equal(compactPrice(0.00009999949), price(0.00009999949));
  assert.equal(compactPrice(-0.000004036), "$-0.0₅4036", "the sign sits where price() puts it");
  assert.equal(price(-5), "$-5.00");
  // At 0.0001 and above it is the ordinary price.
  assert.equal(compactPrice(0.005458), price(0.005458));
  assert.equal(compactPrice(510.08), "$510.08");
});

test("no price on the site is rounded to a fixed two decimals any more", () => {
  for (const f of ["components/chart.tsx", "components/decision.tsx", "app/asset/[symbol]/page.tsx"]) {
    const src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
    assert.doesNotMatch(src, /(close|Close|max|min)\.toFixed\(2\)/, f);
  }
});
