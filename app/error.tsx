"use client";

import Link from "next/link";

/// The segment error boundary: what a reader sees when a page throws instead of rendering.
///
/// Before this file existed the answer was Next's own fallback — an unstyled, unbranded
/// "Application error: a server-side exception has occurred" with no header, no way back and
/// nothing to do. For a site whose whole promise is a ten-second answer, that is the worst
/// screen in the product, and it is the one most likely to be shown at the worst moment: every
/// page here is a direct read against a Neon free-tier database that suspends when idle, so a
/// cold start or a connect timeout is the expected failure, not an exotic one.
///
/// The wording is deliberately about data rather than about faults. That is not a euphemism —
/// it is the only honest thing this component can say. Next replaces the `message` of any error
/// thrown in a Server Component with a generic string in production and forwards only
/// `error.digest`, so this boundary genuinely cannot tell a connect timeout from a null
/// dereference. Since every route on this site is a database read and nothing else, "the data
/// did not load" is true of both, and claiming to know which would be a guess printed as fact.
///
/// `retry` and not `reset`: `retry()` re-fetches and re-renders the boundary's children, which
/// is exactly the recovery a woken database needs. `reset()` only clears the error state and
/// re-renders the same already-failed payload, so on the failure this page exists for it would
/// redraw this page. `retry` became stable in Next 16.3.0 and this project is on 16.3.7.
export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <div className="mx-auto max-w-2xl py-8">
      <h1 className="text-lg font-semibold tracking-tight">
        Data temporarily unavailable
      </h1>
      <p className="text-muted-foreground mt-3 text-sm leading-relaxed">
        This page could not read its figures just now. The database this site reads from goes
        to sleep when nobody is using it, and the first request after that can time out before
        it wakes. Trying again usually works.
      </p>
      <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
        Nothing is wrong with your request, and no figure on the site has changed — this is a
        read that did not arrive, not a number that was withdrawn.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {/*
          A button rather than a link to the same URL. A plain reload re-runs the whole
          document including the layout and the fonts; `retry()` re-renders only the segment
          that failed, which is the faster of the two and the one that keeps the reader's
          place on the page.
        */}
        <button
          type="button"
          onClick={() => retry()}
          className="bg-primary text-primary-foreground rounded px-3 py-2 text-sm font-medium transition-opacity hover:opacity-90"
        >
          Try again
        </button>
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground text-sm underline underline-offset-2"
        >
          Back to the overview
        </Link>
      </div>

      {/*
        The digest, when there is one. It is a hash and not a message, so it tells the reader
        nothing — but it is the only handle that matches this failure to its line in the server
        log, which is what makes a report of "it broke" actionable. Rendered small and last so
        it is available without being the point.
      */}
      {error.digest ? (
        <p className="text-muted-foreground mt-6 text-xs">
          If you are reporting this, the reference is <code>{error.digest}</code>.
        </p>
      ) : null}
    </div>
  );
}
