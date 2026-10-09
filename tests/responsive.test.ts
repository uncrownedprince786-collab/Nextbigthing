// The phone layout, pinned at the two places it has actually broken.
//
// Measured in a real browser at 375x812 on 2026-10-07: every card in the "Best evidenced, by
// market" grid laid out 411px wide inside a 343px track. `main` carries `overflow-x-clip`, so
// the extra 68px was not something a reader could scroll to -- it was cut off, and what sat in
// the cut was the right-hand end of every row: part of the verdict pill and the whole
// confidence column. The one layout with the least room to spare was the one hiding the answer.
//
// The cause is a CSS default rather than a style anyone wrote. A grid item is `min-width: auto`,
// which refuses to shrink below its content's min-content width, and these cards have a floor:
// each row pairs a truncating name with a `shrink-0` pill and a fixed-width confidence. Adding
// `min-w-0` lets the track win and the name truncate, which is what the row was built to do.
//
// These are source assertions, not layout assertions -- node cannot lay out CSS, and the
// alternative is no guard at all on a fault that is invisible in review and only appears on a
// viewport nobody develops at. The browser check is the real test; this is what stops the fix
// being deleted as a stray class.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const topByClass = readFileSync(new URL("../components/topByClass.tsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const decision = readFileSync(new URL("../components/decision.tsx", import.meta.url), "utf8");

test("the class cards can shrink below their own content", () => {
  // The card is the grid item. Without this it overflows its track and is clipped at 375px.
  const card = topByClass.match(/className="border-border bg-card[^"]*"/);
  assert.ok(card, "the class card's className no longer matches; check the overflow fix survived");
  assert.match(
    card[0],
    /\bmin-w-0\b/,
    "the class card lost min-w-0, so it will overflow its grid track and be clipped on a phone",
  );
});

test("the name in a card row truncates rather than pushing the verdict out of view", () => {
  // The other half of the same fix, and the half that was already right. The name shrinks and
  // truncates; the pill and confidence are shrink-0 because a half-rendered verdict is worse
  // than a shortened company name.
  assert.match(topByClass, /min-w-0 flex-1 truncate/);
  assert.match(topByClass, /flex shrink-0 items-baseline/);
});

test("the grid has a column for every class, so none is orphaned onto its own row", () => {
  // Five classes and four columns left Commodities alone on a second row, reading as an
  // afterthought rather than one of five top-level browse targets -- close to the problem that
  // separating it out was meant to fix.
  const classes = readFileSync(new URL("../lib/assetClass.ts", import.meta.url), "utf8");
  const count = (classes.match(/^\s{4}slug: "/gm) ?? []).length;
  const cols = topByClass.match(/lg:grid-cols-(\d+)/);
  assert.ok(cols, "the class grid no longer declares a large-screen column count");
  assert.equal(
    Number(cols[1]),
    count,
    `${count} asset classes but ${cols[1]} columns, so the last row is short`,
  );
});

test("the nav can still be reached when it outgrows the screen", () => {
  // It is eight items now. The layout's own comment says its cost is length rather than width,
  // and the sideways scroll is what makes that true -- without it the items past the fold are
  // simply unreachable on a phone, which for a nav means whole sections of the site are.
  assert.match(layout, /overflow-x-auto/);
});


test("the eight-column table starts at lg, not at sm", () => {
  // The row grew from six columns to eight when the current price joined it. At 640px that is
  // about 70px of track per price column, which "Rs.1,201.22" does not fit in -- the row either
  // wraps into an unreadable stack or clips. Measured in a browser at 768x1024 after the move:
  // four labelled cells per line, no horizontal overflow, header correctly hidden.
  //
  // The fragile part is that one breakpoint has to be right in six places at once: the grid, the
  // header, the row border, the padding, the name's column span and the per-cell labels. A
  // single `sm:` left behind puts the labels and the table on screen together.
  assert.match(decision, /lg:grid-cols-\[minmax/, "the eight-track grid must start at lg");
  assert.doesNotMatch(
    decision,
    /sm:grid-cols-\[minmax/,
    "eight tracks at sm is about 70px per price column",
  );

  // The per-cell labels and the header are the two halves that must not be on screen together.
  assert.match(decision, /const ROW_LABEL = "[^"]*lg:hidden"/);
  assert.match(decision, /text-xs lg:grid \$\{cols\}/);
});

test("a sector heading never reorders the rows inside it", () => {
  // The lists arrive sorted by evidence and the grouping is presentational. Sorting inside
  // `bySector` would quietly put a Low-confidence name above a High one under a heading, which
  // is the one thing the class pages' ordering exists to prevent.
  const at = decision.indexOf("function bySector(");
  assert.ok(at > 0, "bySector no longer matches; check the grouping survived");
  const body = decision.slice(at, decision.indexOf("\n}", at));

  // One sort, and it is over the groups rather than over any group's rows.
  assert.equal((body.match(/\.sort\(/g) ?? []).length, 1);
  assert.match(body, /groups\.values\(\)\]\s*\n?\s*\.sort\(/);
  assert.doesNotMatch(body, /rows\.sort\(/);
});
