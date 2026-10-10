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


test("the ten-column table starts at xl, not at sm or lg", () => {
  // Moved from lg to xl on 2026-10-11. At 1024 the Entry zone track was 86px and "Rs.1,165.00" is 91px,
  // so 106 of 176 PSX ranges broke into three lines and four-digit rupee prices spilled into the next
  // column. Between 1024 and 1279 the four-cells-a-line card layout has the room; the table needs 1280.
  // The row grew from six columns to eight when the current price joined it. At 640px that is
  // about 70px of track per price column, which "Rs.1,201.22" does not fit in -- the row either
  // wraps into an unreadable stack or clips. Measured in a browser at 768x1024 after the move:
  // four labelled cells per line, no horizontal overflow, header correctly hidden.
  //
  // The fragile part is that one breakpoint has to be right in six places at once: the grid, the
  // header, the row border, the padding, the name's column span and the per-cell labels. A
  // single `sm:` left behind puts the labels and the table on screen together.
  assert.match(decision, /xl:grid-cols-\[minmax/, "the ten-track grid must start at xl");
  assert.doesNotMatch(decision, /lg:grid-cols-\[minmax/, "ten tracks at 1024 cannot hold a rupee price");
  assert.doesNotMatch(
    decision,
    /sm:grid-cols-\[minmax/,
    "eight tracks at sm is about 70px per price column",
  );

  // The per-cell labels and the header are the two halves that must not be on screen together.
  // `lg:sr-only` and not `lg:hidden`: visually gone where the header carries them, but still in the
  // accessibility tree. The header is `aria-hidden`, so `lg:hidden` left a screen reader on a
  // desktop width with ten values per row and no names for any of them.
  assert.match(decision, /const ROW_LABEL = "[^"]*xl:sr-only"/);
  assert.doesNotMatch(decision, /const ROW_LABEL = "[^"]*xl:hidden"/);
  assert.match(decision, /aria-hidden="true"/, "the header must stay hidden from assistive tech");
  assert.match(decision, /text-xs xl:grid \$\{/, "the header must only grid at xl");
  // A range breaks only before "to", which travels with the second price: two lines at most.
  assert.match(decision, /<span className="whitespace-nowrap">\s*to <Px v=\{high\}/);

  // One track definition, used by the header and by every row. Two copies is how the overview
  // and a market page come to show the same name under different columns.
  assert.equal((decision.match(/grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4/g) ?? []).length, 1);
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

test("only a sector big enough to be a problem gets a scroll container", () => {
  // A nested scroll box is a cost: it traps a gesture and hides its own content behind a
  // scrollbar. It earns that cost on a 40-row sector and not on a four-row one, so the
  // container is conditional and the threshold is a named constant rather than a literal
  // somewhere in the markup.
  assert.match(decision, /const SECTOR_SCROLL_AFTER = \d+;/);
  assert.match(decision, /const scrolls = section\.rows\.length > SECTOR_SCROLL_AFTER;/);
  assert.match(
    decision,
    /className=\{scrolls \? "overflow-y-auto overscroll-contain" : undefined\}/,
    "the scroll container must be conditional, and must not chain its scroll to the page",
  );

  // Viewport-relative, because the thing it is staying smaller than is the screen. A pixel
  // height that fits a laptop fills a phone.
  assert.match(decision, /const SECTOR_MAX_HEIGHT = "\d+vh";/);
});

test("a scrolling sector is reachable without a mouse", () => {
  // A div that scrolls and holds focusable links is unreachable by keyboard unless it is
  // focusable itself, and unannounced unless it is labelled.
  assert.match(decision, /tabIndex=\{scrolls \? 0 : undefined\}/);
  assert.match(decision, /aria-label=\{scrolls \?/);
});

test("every sector block carries its own pinned column header, above its rows", () => {
  // The defect, from 2026-10-10: `SectorBoard` rendered `DecisionRows` with no `DecisionHeader`
  // anywhere, so no market page had a single column heading -- and at desktop width the per-row
  // labels are hidden because a header is assumed to be carrying them, so a reader saw eight
  // unlabelled values per row. Only the older `DecisionList` rendered the header.
  const start = decision.indexOf("export function SectorBoard(");
  assert.ok(start > 0, "SectorBoard no longer matches; check the sector blocks survived");
  const body = decision.slice(start, decision.indexOf("\n}\n", start));

  const header = body.indexOf("<DecisionHeader");
  const rows = body.indexOf("<DecisionRows");
  assert.ok(header > 0, "a sector block renders no column header");
  assert.ok(header < rows, "the header must come before the rows it names");

  // Inside the element that scrolls, and pinned. Outside it, the names would stay put while the
  // rows scrolled under them -- which works -- but only for a block tall enough to scroll, and the
  // short blocks would then carry a header the long ones did not.
  const scroller = body.indexOf("overflow-y-auto");
  assert.ok(scroller > 0 && scroller < header, "the header must sit inside the scroll container");
  assert.match(body, /<DecisionHeader rounded=\{false\} sticky \/>/);
  assert.match(decision, /sticky \? "bg-muted sticky top-0 z-10"/, "a pinned header needs an opaque ground");
});

test("the header names every field a row prints", () => {
  const at = decision.indexOf("function DecisionHeader(");
  // Whitespace collapsed: the file has CRLF endings and a label can sit on its own line inside a
  // span that carries a tooltip, so a search for "label then newline" depends on the platform.
  const header = decision
    .slice(at, decision.indexOf("/// The rows themselves", at))
    .replace(/\s+/g, " ");
  for (const label of [
    "Name",
    "Market",
    "Action",
    "Price",
    "Entry zone",
    "Stop loss",
    "Measured exit",
    "Reward:risk",
    "Horizon & validity",
    "Confirmations",
  ]) {
    assert.ok(header.includes(`>${label}<`) || header.includes(`> ${label} <`), `no header for ${label}`);
  }
  // And each is also a row label, so a phone -- where the header is hidden -- names the same ten.
  const rows = decision.slice(decision.indexOf("function DecisionRows("));
  for (const label of ["Name", "Market", "Action", "Price", "Entry zone", "Stop loss", "Measured exit", "Reward:risk", "Horizon & validity", "Confirmations"]) {
    assert.ok(rows.includes(`>${label}</span>`), `no row label for ${label}`);
  }
});

test("a WAIT prints its reason, never a confirmation score or a placeholder", () => {
  const rows = decision.slice(decision.indexOf("function DecisionRows("));
  // The WAIT branch is decided before the confirmation cells exist, so a held-back name can never
  // reach "0 of 5" (which reads as a call that nothing supports) or a grade it was never given.
  const wait = rows.indexOf('r.action === "WAIT" ? (');
  const score = rows.indexOf("LEG_TOTAL}");
  assert.ok(wait > 0 && score > wait, "the WAIT branch has to come first");
  assert.match(rows, /Why no call/);
  assert.match(rows, /r\.reason\.map/);
  assert.ok(!/not applicable/.test(rows));
});


test("the action cell is one line: the verdict and the star side by side, never stacked", () => {
  // Measured 2026-10-10 at 1280px: the Action track was 89px and SHORT beside "★ FALLING STAR ↓"
  // needs 171px, so all 25 stars on the stocks page wrapped under their call and made the row taller.
  // A row (no wrap, 6px gap) and a track with a floor wide enough for the widest pair fix it together;
  // either one alone brings the stack back or spills the star into the Price column.
  const rows = decision.slice(decision.indexOf("function DecisionRows("));
  const action = rows.slice(rows.indexOf("<span className={ROW_LABEL}>Action</span>"), rows.indexOf("<span className={ROW_LABEL}>Price</span>"));
  assert.match(action, /className="[^"]*\bflex flex-row flex-nowrap\b[^"]*\bgap-1\.5\b[^"]*\bwhitespace-nowrap\b/);
  assert.doesNotMatch(action, /flex-wrap(?!\S)/, "a wrapping action cell stacks the star under the call");
  const cols = decision.match(/const DECISION_COLS =\s*"([^"]+)"/)?.[1] ?? "";
  const tracks = cols.match(/xl:grid-cols-\[([^\]]+)\]/)?.[1].split("_") ?? [];
  assert.equal(tracks.length, 10);
  const floor = Number(tracks[2].match(/^minmax\((\d+)px,/)?.[1] ?? 0);
  assert.ok(floor >= 171, `the Action track needs a floor of at least 171px for SHORT and a falling star, has ${floor}`);
  // Below lg the cell spans two tracks, because one half-width track on a phone is narrower than the pair.
  assert.match(rows, /<span className="col-span-2 min-w-0 xl:col-span-1">\s*<span className=\{ROW_LABEL\}>Action<\/span>/);
  // The price tracks hold a four-digit rupee price, "Rs.1,165.00" (91px), and the range tracks the
  // widest second line measured at 1280, "to Rs.7,075.19" (NESTLE, 116px).
  for (const [i, floor] of [[3, 92], [4, 124], [5, 92], [6, 124]] as const) {
    assert.ok(Number(tracks[i].match(/^minmax\((\d+)px,/)?.[1] ?? 0) >= floor, `track ${i} needs ${floor}px`);
  }
  assert.match(cols, /\bgrid-flow-row-dense\b/, "without dense packing the spanning cell leaves a hole beside Market");
  // The badge itself never breaks inside.
  const badge = decision.slice(decision.indexOf("export function EarlySignalBadge("), decision.indexOf("export interface DecisionPanelProps"));
  assert.match(badge, /whitespace-nowrap/);
});
