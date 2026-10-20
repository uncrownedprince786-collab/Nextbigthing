// The served copy about the research candidates must match the candidates that exist.
//
// On 2026-10-19 the overview and status screens still said "Four candidates have been trained and
// evaluated; all four are recorded NO-GO". Five candidates exist — one per market — and Commodity's
// local result is a positive-but-thin GO that is not promoted. A stale count on a served page is
// the same class of defect as a stale price, so the two screens are pinned to the same fact here.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overview = readFileSync(new URL("../app/preview/page.tsx", import.meta.url), "utf8");
// Promoted out of /preview on 2026-10-20 with the rest of the journey (the cutover
// runbook); the guarantees asserted below moved with the file, not away from it.
const status = readFileSync(new URL("../app/status/page.tsx", import.meta.url), "utf8");

test("the research-status copy states five candidates, one per market", () => {
  for (const [name, src] of [["overview", overview], ["status", status]] as const) {
    assert.match(src, /five candidates/i, `${name} should say five candidates`);
    assert.doesNotMatch(src, /four candidates/i, `${name} still claims four candidates`);
    assert.match(src, /Commodity/i, `${name} should name Commodity's thin result`);
  }
});

test("the copy never claims every candidate is a NO-GO", () => {
  // Commodity's local pass is thin, not absent; the honest words are "too few symbols to promote".
  for (const [name, src] of [["overview", overview], ["status", status]] as const) {
    assert.doesNotMatch(src, /all four are recorded NO-GO/i, `${name} claims all candidates failed`);
    assert.match(src, /not approved|not promoted|to promote/i, `${name} should say why none is approved`);
  }
});
