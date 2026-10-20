import type { Metadata } from "next";
import Link from "next/link";

/// The replacement interface, served under `/preview` and nowhere else.
///
/// Isolation is the whole design constraint. Every existing route keeps its own files, this
/// subtree adds none of its own to them, and rolling the replacement back is deleting one folder.
/// `WORKSTREAMS-2026-10-17.md` records that contract; this is the half of it that is code.
///
/// The banner is not decoration. A preview that looks like the product is a preview someone will
/// quote, and the one thing this project cannot afford is a reader mistaking an unvalidated view
/// for the published one.
export const metadata: Metadata = {
  title: { default: "Preview", template: "%s · Preview · NextBigThing" },
  description: "The replacement interface, in development. Not the published product.",
  robots: { index: false, follow: false },
};

const NAV = [
  ["/preview", "Overview"],
  ["/markets", "Markets"],
  ["/preview/news", "News & events"],
  ["/predictions", "Predictions"],
  ["/preview/watchlist", "Watchlist"],
  ["/status", "Status"],
  ["/", "← Live site"],
] as const;

export default function PreviewLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-5 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm">
        <strong>Preview.</strong> The replacement interface, in development against real data. The
        published site is unchanged and remains at <Link href="/" className="underline">/</Link>.
      </div>
      <nav className="mb-6 flex flex-wrap gap-4 text-sm">
        {NAV.map(([href, label]) => (
          <Link key={href} href={href} className="underline underline-offset-2">
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
