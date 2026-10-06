import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Not found",
};

/// The 404, for both an unmatched URL and a `notFound()` thrown from a route segment.
///
/// Four routes call `notFound()` — `/asset/[symbol]`, `/event/[slug]`, `/industry/[slug]` and
/// `/product/[slug]` — and until this file existed all four landed on Next's built-in 404:
/// correct status, no header, no nav, no way to find the thing the reader was actually after.
///
/// This is a Server Component and it renders inside the root layout, so it inherits the header,
/// the nav and the footer. That inheritance is the point. A reader who mistyped a symbol does
/// not need an apology; they need the search surfaces, which on this site are the industry and
/// product indexes, and those are already one row above this text in the header.
///
/// The wording names the likeliest cause rather than the generic one. On a site addressed by
/// ticker and slug, a 404 is almost always a symbol that is not in the covered universe — not a
/// deleted page — and saying so turns a dead end into a fact about coverage.
export default function NotFound() {
  return (
    <div className="mx-auto max-w-2xl py-8">
      <h1 className="text-lg font-semibold tracking-tight">
        That page is not here
      </h1>
      <p className="text-muted-foreground mt-3 text-sm leading-relaxed">
        Either the address is wrong, or it names something this site does not cover. The site
        tracks a fixed list of companies, funds, coins and products rather than everything that
        trades, so a symbol that exists in the market can still have no page here.
      </p>

      <ul className="mt-5 space-y-2 text-sm">
        <li>
          <Link href="/" className="text-primary underline underline-offset-2">
            The overview
          </Link>
          <span className="text-muted-foreground"> — what, if anything, is worth doing today</span>
        </li>
        <li>
          <Link
            href="/industry/mega-cap-tech"
            className="text-primary underline underline-offset-2"
          >
            Industries
          </Link>
          <span className="text-muted-foreground">
            {" "}
            — every covered company, grouped, with its rankings
          </span>
        </li>
        <li>
          <Link href="/products" className="text-primary underline underline-offset-2">
            Products
          </Link>
          <span className="text-muted-foreground"> — the consumer demand signals</span>
        </li>
        <li>
          <Link href="/methodology" className="text-primary underline underline-offset-2">
            Methodology
          </Link>
          <span className="text-muted-foreground">
            {" "}
            — what is measured, what is missing, and why
          </span>
        </li>
      </ul>
    </div>
  );
}
