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
          {/*
            The header is sticky, so every row it wraps to is a row the reader pays for on
            every screen of every page. At 375px the seven links plus the tagline wrapped to
            three or four rows. Below `sm` the nav is therefore one row that scrolls
            sideways, the tagline is dropped (it repeats what the footer says at length), and
            the vertical padding is tighter. From `sm` up the layout is the wrapping row it
            has always been.
          */}
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2 sm:gap-y-2 sm:py-3">
            <Link
              href="/"
              className="py-1 text-[15px] font-semibold tracking-tight sm:py-0"
            >
              NextBigThing
            </Link>
            <nav
              className="-mx-4 flex w-full gap-x-1 overflow-x-auto px-4 text-sm [-ms-overflow-style:none] [scrollbar-width:none] sm:mx-0 sm:w-auto sm:flex-wrap sm:gap-x-4 sm:gap-y-1 sm:overflow-x-visible sm:px-0 [&::-webkit-scrollbar]:hidden"
              aria-label="Sections"
            >
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-muted-foreground hover:text-foreground flex shrink-0 items-center rounded px-2 py-3 whitespace-nowrap sm:px-0 sm:py-0"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <p className="text-muted-foreground ml-auto hidden text-xs sm:block">
              Read only. No advice, no forecasts.
            </p>
          </div>
        </header>
        {/*
          Safety net for H: `clip` rather than `hidden` on purpose. `overflow-x: hidden`
          would force the other axis to `auto`, making this element a vertical scroll
          container and breaking the sticky header above it. `clip` constrains the one axis
          and creates no scroll container. Every wide thing on the site — the tables — owns
          its own horizontal scroller inside this, so nothing scrollable is lost.
        */}
        <main className="mx-auto w-full max-w-6xl flex-1 overflow-x-clip px-4 py-8">
          {children}
        </main>
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
