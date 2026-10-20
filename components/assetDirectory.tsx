import Link from "next/link";

/// Every name in a class, alphabetical, as links.
///
/// **Why this exists next to the lists below it.** Those lists answer "what is there to do
/// today", grouped by sector and ordered by evidence, and they are the right shape for that
/// question. They are the wrong shape for the other thing this page is used for: finding one
/// coin. On /crypto that meant seventy-six names spread across a directions board, a withheld
/// fold, a forming list and a collapsed held-back table -- and ten of them on no list at all,
/// because they sit outside the active pool. A reader looking for Litecoin had to know which of
/// five places it had landed in today.
///
/// So the complete list is first, flat and alphabetical, and the analysis follows it. Nothing
/// here is a verdict: it is a directory, and the only thing it says about a name is whether the
/// lists below cover it.
///
/// **No filter box, deliberately.** One would need `use client`, and the guarantee this site
/// holds -- no client component outside a short reviewed allow list, so no server value can reach
/// the browser bundle at all -- is worth more than a text input over a list the browser's own
/// find-in-page already searches. Seventy-six links in a four-column grid is a glance, not a
/// scroll.
export function AssetDirectory({
  rows,
  noun,
}: {
  rows: { symbol: string; name: string; inPool: boolean }[];
  /// "coin", "pair", "contract" -- the word this class calls its members.
  noun: string;
}) {
  if (rows.length === 0) return null;
  const outside = rows.filter((r) => !r.inPool).length;
  return (
    <div className="border-border bg-muted/30 mt-4 rounded-lg border px-4 py-3">
      <h2 className="text-sm font-medium">
        Every {noun} on the site ({rows.length})
      </h2>
      <p className="text-muted-foreground mt-1 text-xs">
        Pick one to open its page, where you choose how far ahead you are asking and get a
        direction for exactly that window.
        {outside
          ? ` ${outside} of these carry no call today, marked below, because they are under this market's liquidity floor.`
          : ""}
      </p>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((r) => (
          <li key={r.symbol} className="truncate text-sm">
            <Link
              href={`/asset/${encodeURIComponent(r.symbol)}`}
              className="underline-offset-2 hover:underline"
              title={r.symbol}
            >
              {r.name}
            </Link>
            {r.inPool ? null : (
              <span
                className="text-muted-foreground ml-1 text-[10px]"
                title="Under this market's liquidity floor, so the lists below make no call for it"
              >
                (no call)
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
