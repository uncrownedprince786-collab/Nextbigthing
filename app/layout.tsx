import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "NextBigThing: market rankings and demand signals",
    template: "%s | NextBigThing",
  },
  description:
    "Which stocks, crypto, funds and consumer products are gaining ground on the US and Pakistani markets, measured from free public data. Every figure names its source and as of date. No forecasts, no paid data.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/industry/mega-cap-tech", label: "Industries" },
  { href: "/industry/psx-banks", label: "Pakistan" },
  { href: "/products", label: "Products" },
  { href: "/marketplace", label: "Marketplace" },
  { href: "/events", label: "Events" },
  { href: "/methodology", label: "Methodology" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <header className="border-border bg-card/80 sticky top-0 z-20 border-b backdrop-blur">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-[15px] font-semibold tracking-tight">
              NextBigThing
            </Link>
            <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <p className="text-muted-foreground ml-auto text-xs">
              Read only. No advice, no forecasts.
            </p>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-border text-muted-foreground mt-8 border-t px-4 py-6 text-xs">
          <div className="mx-auto max-w-6xl space-y-1">
            <p>
              Figures come from Yahoo Finance, Binance, CoinPaprika, the Pakistan Stock
              Exchange, Google Trends, Wikipedia, Hacker News, Reddit, Google News RSS and
              Amazon Best Sellers. Data may be late or wrong. Nothing on this site is
              investment advice or a prediction, and where an event sits next to a price
              move the site is reporting a sequence, not a cause.
            </p>
            <Link href="/methodology" className="underline underline-offset-2">
              How each number is measured, and what is missing
            </Link>
          </div>
        </footer>
      </body>
    </html>
  );
}
