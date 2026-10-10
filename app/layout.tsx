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

// The nav is one row that scrolls sideways below `sm`, so its cost is length rather than width.
//
// The four asset classes replace the two industry links that used to sit here. Those pointed at
// one industry each -- `/industry/mega-cap-tech` under the word "Industries" and
// `/industry/psx-banks` under "Pakistan" -- so a reader who wanted "all the US names" landed on
// nine of them and had no route to the rest. The class pages are the complete list, which is what
// those two words were promising.
const NAV = [
  { href: "/", label: "Overview" },
  { href: "/stocks", label: "Stocks" },
  { href: "/psx", label: "PSX" },
  { href: "/crypto", label: "Crypto" },
  { href: "/forex", label: "Forex" },
  { href: "/commodities", label: "Commodities" },
  { href: "/products", label: "Products" },
  { href: "/logbook", label: "Logbook" },
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
            {/*
              The wordmark, with the text name kept as the accessible name rather than deleted.
              A logo that replaces the name leaves a screen reader announcing "link, image", and
              leaves every reader with a broken image and nothing at all if the file 404s.

              `next/image` is deliberately not used. This is one small PNG in the header of every
              page; the optimizer's win is for large content images, and routing a 1.3 KB mark
              through it costs a request on first paint for nothing. `width`/`height` are set so
              the row does not reflow when it loads, which is the actual problem worth solving
              here. Dimensions are the file's own, 489x96 -- stored at roughly three times the
              28px it renders at, so a dense display has pixels to use and the file stays small.
            */}
            <Link href="/" className="flex items-center py-1 sm:py-0" aria-label="NextBigThing, home">
              {/* eslint-disable-next-line @next/next/no-img-element -- the rule is about large
                  content images. This is a 34 KB header mark on every page, already resized to
                  roughly three times its rendered height, and Vercel's image optimization is
                  metered on the free tier. The optimizer earns its cost on large content images,
                  not on a mark that is already the size it is drawn at. */}
              <img
                src="/logo.png"
                alt="NextBigThing"
                width={489}
                height={96}
                decoding="async"
                fetchPriority="high"
                className="h-6 w-auto sm:h-7"
              />
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
            <Link href="/privacy" className="underline underline-offset-2">
              Privacy and disclaimer
            </Link>
          </div>
        </footer>
      </body>
    </html>
  );
}
