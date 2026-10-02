// Filter links. The interesting cases are all adversarial: a value that is not on the menu, a
// repeated key, an unknown key trying to ride along.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  describeFilters,
  hrefFor,
  isActive,
  readFilters,
  readParam,
  type FilterGroup,
} from "../lib/filters.ts";

const GROUPS: FilterGroup[] = [
  {
    key: "market",
    label: "Market",
    options: [
      { label: "All markets", value: null },
      { label: "US", value: "US" },
      { label: "PSX", value: "PSX" },
      { label: "Crypto", value: "Crypto" },
    ],
  },
  {
    key: "action",
    label: "Action",
    options: [
      { label: "Any action", value: null },
      { label: "LONG", value: "LONG" },
      { label: "SHORT", value: "SHORT" },
      { label: "WAIT", value: "WAIT" },
    ],
  },
];

test("a single value reads straight through", () => {
  assert.equal(readParam({ market: "PSX" }, "market"), "PSX");
  assert.equal(readParam({}, "market"), null);
  assert.equal(readParam({ market: undefined }, "market"), null);
  // An empty value is the same as absent, so ?market= is a clean default rather than a no-match.
  assert.equal(readParam({ market: "" }, "market"), null);
});

test("a repeated key takes the first value instead of crashing", () => {
  assert.equal(readParam({ market: ["US", "PSX"] }, "market"), "US");
  assert.equal(readParam({ market: [] }, "market"), null);
});

test("only values the group offers survive", () => {
  assert.deepEqual(readFilters(GROUPS, { market: "PSX", action: "LONG" }), {
    market: "PSX",
    action: "LONG",
  });
  // Not on the menu. A filter is a closed set, and this value would otherwise reach a query.
  assert.deepEqual(readFilters(GROUPS, { market: "Mars" }), {});
  assert.deepEqual(readFilters(GROUPS, { action: "DELETE FROM Asset" }), {});
  // Case matters: the options are the vocabulary.
  assert.deepEqual(readFilters(GROUPS, { market: "psx" }), {});
});

test("keys we do not own are dropped, not carried", () => {
  const got = readFilters(GROUPS, { market: "US", somethingElse: "x", redirect: "//evil" });
  assert.deepEqual(got, { market: "US" });
});

test("setting a filter keeps the others and sorts the result", () => {
  assert.equal(hrefFor("/", {}, "market", "PSX"), "/?market=PSX");
  // Sorted, so one view always has one address.
  assert.equal(hrefFor("/", { market: "PSX" }, "action", "LONG"), "/?action=LONG&market=PSX");
  assert.equal(hrefFor("/", { action: "LONG" }, "market", "PSX"), "/?action=LONG&market=PSX");
});

test("choosing All removes the key rather than emptying it", () => {
  assert.equal(hrefFor("/", { market: "PSX", action: "LONG" }, "market", null), "/?action=LONG");
  // The fully default view is the bare path, with no trailing question mark.
  assert.equal(hrefFor("/", { market: "PSX" }, "market", null), "/");
});

test("values are encoded", () => {
  assert.equal(hrefFor("/", {}, "market", "a b&c"), "/?market=a+b%26c");
});

test("the active chip is the set one, and All is active when nothing is set", () => {
  assert.equal(isActive({}, "market", null), true);
  assert.equal(isActive({}, "market", "US"), false);
  assert.equal(isActive({ market: "US" }, "market", "US"), true);
  assert.equal(isActive({ market: "US" }, "market", null), false);
  assert.equal(isActive({ market: "US" }, "market", "PSX"), false);
});

test("the heading says what is being shown, so an empty list is not mistaken for a broken one", () => {
  assert.equal(describeFilters(GROUPS, {}), "Everything stored");
  assert.equal(describeFilters(GROUPS, { market: "PSX" }), "PSX");
  assert.equal(describeFilters(GROUPS, { market: "PSX", action: "LONG" }), "PSX · LONG");
  // Order follows the groups, not the URL, so the sentence reads the same either way.
  assert.equal(describeFilters(GROUPS, { action: "LONG", market: "PSX" }), "PSX · LONG");
});
