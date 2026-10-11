// A market page left behind the data cache is realigned (brain.md rule 94). Live on 2026-10-11 the five
// market pages were re-rendered from a read taken while the schema lane was writing, the cache kept a later
// read, and /api/revalidate answered "nothing to do" because it compared the cache alone. It now reads the
// stamps the pages print as well, and these tests pin how a page is judged and what the route does.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isBehind, snapshotOf, STAMPED_PAGES } from "../lib/alignment.ts";

const NOW = "553|2026-10-11T01:24:22.523Z|2026-10-11T11:02:59.746Z|q|c|n";
const EARLIER = "553|2026-10-11T01:24:22.523Z|2026-10-11T01:21:01.693Z|q|c|n";

test("the stamp is read from the page's data-snapshot attribute", () => {
  assert.equal(snapshotOf(`<p class="x" data-market-status data-snapshot="${NOW}">`), NOW);
  assert.equal(snapshotOf('<p data-snapshot="">'), null);
  assert.equal(snapshotOf("<p>no stamp</p>"), null);
});

test("a page served as current on an older snapshot is behind; the live case of 2026-10-11", () => {
  assert.equal(isBehind({ cache: "HIT", seen: EARLIER }, NOW), true);
  assert.equal(isBehind({ cache: "PRERENDER", seen: EARLIER }, NOW), true);
  assert.equal(isBehind({ cache: null, seen: EARLIER }, NOW), true);
  assert.equal(isBehind({ cache: "HIT", seen: NOW }, NOW), false);
});

test("a page already re-rendering is not judged, so the route cannot loop on it", () => {
  assert.equal(isBehind({ cache: "STALE", seen: EARLIER }, NOW), false);
  assert.equal(isBehind({ cache: "stale", seen: EARLIER }, NOW), false);
});

test("a page with no stamp is not evidence of a skew", () => {
  assert.equal(isBehind({ cache: "HIT", seen: null }, NOW), false);
});

test("the pages judged are the ones that print the stamp", () => {
  const index = readFileSync(new URL("../components/classIndex.tsx", import.meta.url), "utf8");
  assert.match(index, /data-snapshot=\{rows\[0\]\?\.dataStamp/);
  assert.deepEqual([...STAMPED_PAGES], ["/stocks", "/crypto", "/psx", "/forex", "/commodities"]);
});

test("the route reads the pages only when the cache is current, and then re-renders pages without a database read", () => {
  const src = readFileSync(new URL("../app/api/revalidate/route.ts", import.meta.url), "utf8");
  const current = src.slice(src.indexOf("if (fresh !== null && cached === fresh)"), src.indexOf("revalidateTag(DATA_TAG"));
  assert.match(current, /pagesBehind\(/);
  assert.match(current, /revalidatePath\("\/", "layout"\)/);
  // The data entry is already current here, so it is kept: only the pages re-render, from it.
  assert.doesNotMatch(current, /revalidateTag/);
  assert.match(current, /revalidated: false, stamp: fresh/);
});
