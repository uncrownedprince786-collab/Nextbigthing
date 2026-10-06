"use client";

/// The last resort: what a reader sees when the root layout itself throws.
///
/// `app/error.tsx` wraps the pages inside the layout, but not the layout above them, so a
/// failure in `app/layout.tsx` — the header, the font loader, the nav — escapes it entirely.
/// This file catches that, and it is the only screen on the site that renders without the
/// site's own chrome, because the chrome is what failed.
///
/// Everything here is inline on purpose, and this is the one place in the codebase where that
/// is correct. `global-error` replaces the root layout when it is active, which means it never
/// receives `app/globals.css`, never receives the Geist font variables, and never receives the
/// Tailwind utility classes the rest of the site is written in. A Tailwind class name here
/// would be a string that styles nothing. So the colours below are the literal values of the
/// `:root` tokens in `globals.css` — `--background`, `--foreground`, `--muted-foreground`,
/// `--border`, `--primary`, `--primary-foreground` — written out rather than referenced, so
/// this page still looks like the site it belongs to.
///
/// Only the light values are inlined, and that matches the app rather than cutting a corner:
/// `globals.css` gates dark mode behind a `.dark` class and nothing in the app ever sets one,
/// so the site has exactly one palette today. If a theme toggle is ever added, this file is a
/// place that has to be revisited, which is why the reason is written down here.
///
/// `<html>` and `<body>` are mandatory. This component replaces the root layout, so if it does
/// not render the document shell, nothing does.
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          background: "#fbfbfa",
          color: "#16181d",
          fontFamily:
            'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
          WebkitFontSmoothing: "antialiased",
        }}
      >
        {/* React's own <title>, because `metadata` exports are not supported in a Client
            Component and an error boundary has to be one. Without this the tab reads as the
            URL. */}
        <title>Something went wrong | NextBigThing</title>

        <main
          style={{
            maxWidth: "36rem",
            margin: "0 auto",
            padding: "4rem 1rem",
          }}
        >
          <p
            style={{
              fontSize: "0.875rem",
              fontWeight: 600,
              letterSpacing: "-0.01em",
              margin: 0,
            }}
          >
            NextBigThing
          </p>
          <h1
            style={{
              fontSize: "1.125rem",
              fontWeight: 600,
              letterSpacing: "-0.01em",
              margin: "1.5rem 0 0",
            }}
          >
            The site failed to load
          </h1>
          <p
            style={{
              color: "#5d6570",
              fontSize: "0.875rem",
              lineHeight: 1.6,
              margin: "0.75rem 0 0",
            }}
          >
            This is not a page that is missing or a figure that is late — the page frame itself
            did not render, so the site could not show you its own error page. Trying again is
            worth one attempt; if it repeats, the fault is being logged and is not yours.
          </p>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "0.75rem",
              marginTop: "1.25rem",
            }}
          >
            <button
              type="button"
              onClick={() => retry()}
              style={{
                background: "#1d4ed8",
                color: "#ffffff",
                border: 0,
                borderRadius: "0.25rem",
                padding: "0.5rem 0.75rem",
                fontSize: "0.875rem",
                fontWeight: 500,
                fontFamily: "inherit",
                cursor: "pointer",
              }}
            >
              Try again
            </button>
            {/*
              A plain <a> and not next/link. The router is part of what may have failed here,
              and a full document load is the recovery this page wants anyway.
            */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- the rule exists to
                keep client-side navigation from being lost to a full reload. Here the full
                reload is the feature: this boundary is active because the root layout threw, so
                the React tree the router lives in is the thing that is broken, and a soft
                navigation would re-enter it. */}
            <a
              href="/"
              style={{
                color: "#5d6570",
                fontSize: "0.875rem",
                textDecoration: "underline",
                textUnderlineOffset: "2px",
              }}
            >
              Reload the overview
            </a>
          </div>

          {error.digest ? (
            <p
              style={{
                color: "#5d6570",
                fontSize: "0.75rem",
                marginTop: "1.5rem",
              }}
            >
              If you are reporting this, the reference is{" "}
              <code style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                {error.digest}
              </code>
              .
            </p>
          ) : null}
        </main>
      </body>
    </html>
  );
}
